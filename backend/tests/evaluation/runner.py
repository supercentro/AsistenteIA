"""Runs the golden set against the production read and generate phases of the chat service.

Nothing of the pipeline is reimplemented here: the chunks come from `RAGService.prepare`, the
prompt and the model call from `RAGService.generate`, and the sources from `select_cited`. The
harness only prepares synthetic users, subjects, documents and stored conversations in the
isolated test database, asks, and removes everything it created (also when it fails).
"""

import asyncio
import os
import sys
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.api.chat_deps import build_rag_service
from app.core.config import Settings
from app.core.database import create_db_engine, create_session_factory
from app.core.errors import ForbiddenError
from app.core.vector_validation import validate_embedding
from app.models.conversation import Conversation, Message, MessageRole
from app.rag.chunker import chunk_pages
from app.rag.embedder import Embedder
from app.rag.loaders import load_markdown, load_text
from app.services.llm_service import LLMService
from app.services.rag_service import RetrievedContext
from tests.db_support import guarded_engine
from tests.evaluation.attribution import (
    Attribution,
    AttributionStats,
    attribution_summary,
    classify_answer,
    not_exercised,
)
from tests.evaluation.budget import load_ledger, require_budget, reserve_run, settle_run
from tests.evaluation.cases import Case, GoldenDocument, GoldenSet, normalize
from tests.evaluation.guards import (
    CallCapExceededError,
    assert_isolated_database,
    plan_model_calls,
)
from tests.evaluation.metrics import Retrieved, cut, isolation_violations, retrieval_rows
from tests.evaluation.report import Header, Report, ReviewItem
from tests.sql_support import (
    insert_chunk,
    insert_document,
    insert_enrollment,
    insert_subject,
    insert_user,
    vector_literal,
)

CONSENT_VERSION = "2026-10-v1"
MAX_CONSECUTIVE_MODEL_ERRORS = 2


@dataclass(frozen=True)
class RunSettings:
    mode: Literal["retrieval", "answers"]
    top_ks: list[int]
    thresholds: list[float]
    default_top_k: int
    default_threshold: float
    max_calls: int
    revision: str
    embedder_name: str
    model_name: str
    pause_seconds: float = 0.0
    ledger_path: Path | None = None


@dataclass
class _Created:
    """Ids of what the run created: the only rows it ever deletes."""

    users: list[uuid.UUID] = field(default_factory=list)
    subjects: list[uuid.UUID] = field(default_factory=list)
    llm: "_CountingLLM | None" = None
    reserved: int = 0


class _CountingLLM:
    """Counts the calls that reach the model, refuses to exceed the cap and paces the calls."""

    def __init__(
        self,
        inner: LLMService,
        cap: int,
        pause_seconds: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._cap = cap
        self._pause = pause_seconds
        self._sleep = sleep
        self.calls = 0

    async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
        if self.calls >= self._cap:
            raise CallCapExceededError(f"the cap of {self._cap} model calls was reached")
        if self.calls > 0 and self._pause > 0:
            await self._sleep(self._pause)
        self.calls += 1
        return await self._inner.generate(system_prompt, user_messages)


def _sql(url: str, statement: str, **params: object) -> None:
    with guarded_engine(url) as engine, engine.connect() as connection:
        connection.execute(text(statement), params)


def _ingest(
    url: str, subject_id: uuid.UUID, document: GoldenDocument, embedder: Embedder
) -> list[str]:
    """Load, chunk and embed with the production functions; store as a ready document.

    Returns the text of the stored chunks (to check that accepted passages fit in one chunk).
    """
    if document.content_type == "text/markdown":
        pages = load_markdown(document.payload)
    else:
        pages = load_text(document.payload)
    chunks = chunk_pages(pages, embedder)
    vectors = [validate_embedding(v) for v in embedder.embed([chunk.text for chunk in chunks])]
    document_id = insert_document(url, subject_id, document.filename, "ready")
    for chunk, vector in zip(chunks, vectors, strict=True):
        insert_chunk(
            url,
            document_id,
            subject_id,
            chunk_index=chunk.index,
            embedding=vector_literal(vector),
            content=chunk.text,
            page_number=chunk.page_number,
        )
    return [chunk.text for chunk in chunks]


def _make_student(url: str, label: str, created: _Created) -> uuid.UUID:
    student = insert_user(url, f"{label}@example.com", "student")
    created.users.append(student)
    _sql(
        url,
        "UPDATE users SET consent_version = :version, consent_accepted_at = now() WHERE id = :id",
        version=CONSENT_VERSION,
        id=student,
    )
    return student


def _store_history(
    session: Session, student: uuid.UUID, subject: uuid.UUID, case: Case
) -> uuid.UUID:
    conversation = Conversation(student_id=student, subject_id=subject)
    session.add(conversation)
    session.flush()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index, message in enumerate(case.history):
        session.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole(message.role),
                content=message.content,
                created_at=base.replace(second=index),
            )
        )
    session.commit()
    return conversation.id


def _cleanup(url: str, created: _Created) -> list[str]:
    """Delete only the rows this run created: subjects first (they cascade), then the users.

    Returns what could not be removed instead of raising, so that it never hides the report.
    """
    failures: list[Exception] = []
    for statement, ids in (
        ("DELETE FROM subjects WHERE id = :id", created.subjects),
        ("DELETE FROM users WHERE id = :id", created.users),
    ):
        for row_id in ids:
            try:
                _sql(url, statement, id=row_id)
            except Exception as error:  # noqa: BLE001 - keep deleting the rest, report afterwards
                failures.append(error)
    return [f"cleanup left {len(failures)} synthetic rows behind"] if failures else []


def run_evaluation(
    url: str,
    settings: Settings,
    golden: GoldenSet,
    embedder: Embedder,
    llm: LLMService,
    options: RunSettings,
    announce: Callable[[str], None] | None = None,
) -> Report:
    """Measure the golden set; always leaves the database as it found it."""
    # The process environment wins: the harness builds settings for the fake backends with
    # APP_ENV=test, which must not hide a production environment from the guard.
    app_env = os.environ.get("APP_ENV") or settings.app_env
    assert_isolated_database(url, os.environ.get("DATABASE_URL"), app_env)
    created = _Created()
    engine = create_db_engine(url)
    try:
        report = _measure(url, settings, golden, embedder, llm, options, created, engine, announce)
    except BaseException:
        # Whatever failed, settle the ledger and clean up; their own failures are printed, never
        # raised, so that they cannot hide the original error.
        for message in _finish(url, golden, options, created, engine):
            print(message, file=sys.stderr)
        raise
    notes = _finish(url, golden, options, created, engine)
    return replace(report, problems=[*report.problems, *notes])


def _finish(
    url: str, golden: GoldenSet, options: RunSettings, created: _Created, engine: Engine
) -> list[str]:
    """Settle the request ledger, close the engine and remove the synthetic rows."""
    messages: list[str] = []
    engine.dispose()
    if options.ledger_path is not None and created.reserved:
        made = created.llm.calls if created.llm is not None else 0
        try:
            settle_run(options.ledger_path, reserved=created.reserved, calls=made)
        except Exception:  # noqa: BLE001 - the reservation stays: it is the safe side
            messages.append(
                f"ledger: the reservation of {created.reserved} requests could not be settled "
                f"({made} calls were made); the ledger keeps the higher figure"
            )
    messages += _cleanup(url, created)
    return messages


def _measure(
    url: str,
    settings: Settings,
    golden: GoldenSet,
    embedder: Embedder,
    llm: LLMService,
    options: RunSettings,
    created: _Created,
    engine: Engine,
    announce: Callable[[str], None] | None,
) -> Report:
    factory: Callable[[], Session] = create_session_factory(engine)
    run_id = uuid.uuid4().hex[:8]

    teacher = insert_user(url, f"eval-teacher-{run_id}@example.com", "teacher")
    created.users.append(teacher)
    subject_ids: dict[str, uuid.UUID] = {}
    students: dict[str, uuid.UUID] = {}
    for slug in golden.subjects:
        subject = insert_subject(url, teacher, f"eval-{slug}-{run_id}")
        created.subjects.append(subject)
        subject_ids[slug] = subject
        students[slug] = _make_student(url, f"eval-student-{slug}-{run_id}", created)
        insert_enrollment(url, subject, students[slug])
    outsider = _make_student(url, f"eval-outsider-{run_id}", created)
    chunk_texts: dict[str, list[str]] = {}
    for document in golden.documents:
        chunk_texts[document.filename] = _ingest(
            url, subject_ids[document.subject], document, embedder
        )

    conversation_of: dict[str, uuid.UUID] = {}
    with factory() as session:
        for case in golden.cases:
            if case.history:
                conversation_of[case.id] = _store_history(
                    session, students[case.subject], subject_ids[case.subject], case
                )

    top_ks = sorted(set(options.top_ks) | {options.default_top_k})
    thresholds = sorted(set(options.thresholds) | {options.default_threshold})
    wide = settings.model_copy(update={"chat_top_k": max(top_ks), "chat_relevance_threshold": 0.0})
    default = settings.model_copy(
        update={
            "chat_top_k": options.default_top_k,
            "chat_relevance_threshold": options.default_threshold,
        }
    )
    counting = _CountingLLM(llm, options.max_calls, options.pause_seconds)
    created.llm = counting

    def prepare(case: Case, configured: Settings) -> RetrievedContext | None:
        if case.student == "not_enrolled":
            student = outsider
        elif case.student == "enrolled_elsewhere":
            other = next((slug for slug in golden.subjects if slug != case.subject), None)
            student = students[other] if other is not None else outsider
        else:
            student = students[case.subject]
        with factory() as session:
            service = build_rag_service(
                db=session, settings=configured, embedder=embedder, llm=counting
            )
            try:
                return service.prepare(
                    student_id=student,
                    subject_id=subject_ids[case.subject],
                    message=case.question,
                    conversation_id=conversation_of.get(case.id),
                )
            except ForbiddenError:
                return None

    problems: list[str] = []
    for case in golden.cases:
        for source in case.expected.sources:
            wanted = normalize(source.passage_contains)
            if not any(wanted in normalize(c) for c in chunk_texts.get(source.filename, [])):
                problems.append(
                    f"{case.id}: an accepted passage is not inside a single chunk of "
                    f"{source.filename} (it can never be matched after chunking)"
                )
    outcomes: dict[str, Retrieved] = {}
    default_contexts: dict[str, RetrievedContext | None] = {}
    for case in golden.cases:
        wide_context = prepare(case, wide)
        outcomes[case.id] = (
            Retrieved(denied=True)
            if wide_context is None
            else Retrieved(tuple(wide_context.chunks))
        )
        default_context = prepare(case, default)
        default_contexts[case.id] = default_context
        if default_context is not None and wide_context is not None:
            derived = [
                c.chunk_id
                for c in cut(wide_context.chunks, options.default_top_k, options.default_threshold)
            ]
            if derived != [c.chunk_id for c in default_context.chunks]:
                problems.append(f"{case.id}: the derived ranking differs from the production one")

    rows = retrieval_rows(
        golden.cases,
        outcomes,
        top_ks=top_ks,
        thresholds=thresholds,
        default=(options.default_top_k, options.default_threshold),
    )
    subject_of = {doc.filename: doc.subject for doc in golden.documents}
    violations = isolation_violations(golden.cases, outcomes, subject_of)
    problems += [f"{case_id}: isolation check failed" for case_id in violations]

    attribution: dict[str, AttributionStats] = {}
    results: list[Attribution] = []
    review: list[ReviewItem] = []
    notes: list[str] = []
    if options.mode == "answers":
        asked = [
            case
            for case in golden.cases
            if case.model and (ctx := default_contexts[case.id]) is not None and ctx.chunks
        ]
        if announce is not None:
            announce(f"{len(asked)} model calls will be made (cap {options.max_calls})")
        plan_model_calls(needed=len(asked), cap=options.max_calls)
        if options.ledger_path is not None:
            require_budget(load_ledger(options.ledger_path), len(asked))
            reserve_run(
                options.ledger_path,
                calls=len(asked),
                date=datetime.now(UTC).date().isoformat(),
                mode=options.mode,
                revision=options.revision,
                note=f"golden set {golden.version}; {options.model_name}",
            )
            created.reserved = len(asked)
        errors_in_a_row = 0
        # One event loop for every call: the provider client keeps pooled connections that belong
        # to the loop they were created in, so a loop per call breaks every second request.
        with asyncio.Runner() as runner:
            for case in asked:
                context = default_contexts[case.id]
                assert context is not None
                service = build_rag_service(
                    db=factory(), settings=default, embedder=embedder, llm=counting
                )
                try:
                    answer = runner.run(service.generate(context))
                    errors_in_a_row = 0
                except Exception as error:  # noqa: BLE001 - only the type is kept: text can echo input
                    problems.append(f"{case.id}: the model call failed ({type(error).__name__})")
                    errors_in_a_row += 1
                    if errors_in_a_row >= MAX_CONSECUTIVE_MODEL_ERRORS:
                        problems.append("stopped after repeated model failures")
                        break
                    continue
                finally:
                    service._db.close()  # noqa: SLF001 - the session was opened for this call only
                result = classify_answer(case, answer, context.chunks)
                results.append(result)
                if not_exercised(case, context.chunks):
                    notes.append(f"{case.id}: not exercised (the target chunk was not retrieved)")
                if result.forbidden_found:
                    problems.append(f"{case.id}: forbidden text in the answer")
                if result.prompt_leak:
                    problems.append(f"{case.id}: the answer repeats the system prompt")
                if case.kind == "unanswerable":
                    review.append(ReviewItem(case.id, case.question, answer))
        attribution = attribution_summary(results, golden.cases)

    return Report(
        header=Header(
            golden_set_version=golden.version,
            revision=options.revision,
            mode=options.mode,
            embedder=options.embedder_name,
            model=options.model_name,
            date=datetime.now(UTC).date().isoformat(),
            top_k=options.default_top_k,
            threshold=options.default_threshold,
            cases=len(golden.cases),
            model_calls=counting.calls,
        ),
        rows=rows,
        isolation_violations=violations,
        attribution=attribution,
        fallback_cases=[r.case_id for r in results if r.fallback and r.supporting is not None],
        unsupported_cases=[r.case_id for r in results if r.unsupported],
        review=review,
        problems=problems,
        stale_cases=[r.case_id for r in results if r.stale_markers],
        notes=notes,
    )
