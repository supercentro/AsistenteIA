"""The golden set: fictitious documents and cases, loaded and validated from a directory.

Layout: `VERSION`, `cases.json` and `corpus/<subject>/<file>.md|txt`. Every document and every
question is fictitious (see the README of the set). A case names the passages that are acceptable
evidence, so that judging is a deterministic substring check and does not depend on chunk
boundaries or on a model.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Kind = Literal[
    "answerable",
    "unanswerable",
    "follow_up",
    "trap_history_marker",
    "trap_document_marker",
    "injection_question",
    "injection_document",
    "cross_subject",
    "not_enrolled",
]

# The expected outcome type each kind must carry.
EXPECTED_TYPE: dict[str, str] = {
    "answerable": "sources",
    "follow_up": "sources",
    "trap_history_marker": "sources",
    "trap_document_marker": "sources",
    "injection_document": "sources",
    "injection_question": "free",
    "unanswerable": "no_material",
    "cross_subject": "isolation",
    "not_enrolled": "denied",
}
NEEDS_HISTORY = {"follow_up", "trap_history_marker"}
CONTENT_TYPES = {".md": "text/markdown", ".txt": "text/plain"}

_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lower case with collapsed whitespace: how passages are compared with chunk text."""
    return _SPACES.sub(" ", text).strip().lower()


class GoldenSetError(ValueError):
    """The golden set is incomplete or inconsistent; the message names the case or file."""


class ExpectedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    passage_contains: str = Field(min_length=1)
    page: int | None = None


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["sources", "no_material", "denied", "isolation", "free"]
    sources: list[ExpectedSource] = Field(default_factory=list)


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    kind: Kind
    subject: str = Field(min_length=1)
    student: Literal["enrolled", "not_enrolled", "enrolled_elsewhere"] = "enrolled"
    question: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list)
    expected: Expected
    # Asked to the real model in the answers mode (bounded by the call cap).
    model: bool = False
    must_not_contain: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class GoldenDocument:
    subject: str
    filename: str
    content_type: str
    payload: bytes


@dataclass(frozen=True)
class GoldenSet:
    version: str
    root: Path
    documents: list[GoldenDocument]
    cases: list[Case]
    _subjects: dict[str, str] = field(default_factory=dict)

    @property
    def subjects(self) -> list[str]:
        return sorted({doc.subject for doc in self.documents})

    @property
    def model_case_count(self) -> int:
        return sum(1 for case in self.cases if case.model)

    def subject_of_filename(self, filename: str) -> str:
        return self._subjects[filename]


def _check_case(case: Case, texts: dict[str, str], subjects: dict[str, str]) -> None:
    label = f"case {case.id!r}"
    if case.subject not in set(subjects.values()):
        raise GoldenSetError(f"{label}: unknown subject {case.subject!r}")
    if case.expected.type != EXPECTED_TYPE[case.kind]:
        raise GoldenSetError(
            f"{label}: kind {case.kind!r} needs expected type {EXPECTED_TYPE[case.kind]!r}"
        )
    if case.kind in NEEDS_HISTORY and not case.history:
        raise GoldenSetError(f"{label}: kind {case.kind!r} needs earlier messages")
    if (case.kind == "not_enrolled") != (case.student != "enrolled"):
        raise GoldenSetError(f"{label}: only not_enrolled cases use a student without access")
    if case.expected.type == "sources" and not case.expected.sources:
        raise GoldenSetError(f"{label}: expected sources are missing")
    for source in case.expected.sources:
        text = texts.get(source.filename)
        if text is None:
            raise GoldenSetError(f"{label}: unknown file {source.filename!r}")
        if normalize(source.passage_contains) not in text:
            raise GoldenSetError(
                f"{label}: the passage {source.passage_contains!r} is not in {source.filename!r}"
            )


def load_golden_set(root: Path) -> GoldenSet:
    """Load and validate a golden set; raise `GoldenSetError` naming the first problem."""
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
        raw_cases = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GoldenSetError(f"cannot read the golden set at {root}: {error}") from None
    if not version:
        raise GoldenSetError("VERSION is empty")

    documents: list[GoldenDocument] = []
    subjects: dict[str, str] = {}
    texts: dict[str, str] = {}
    for path in sorted((root / "corpus").glob("*/*")):
        content_type = CONTENT_TYPES.get(path.suffix)
        if content_type is None or not path.is_file():
            continue
        if path.name in subjects:
            raise GoldenSetError(f"the file name {path.name!r} is used in two subjects")
        payload = path.read_bytes()
        subjects[path.name] = path.parent.name
        texts[path.name] = normalize(payload.decode("utf-8"))
        documents.append(GoldenDocument(path.parent.name, path.name, content_type, payload))
    if not documents:
        raise GoldenSetError("the corpus has no documents")

    cases: list[Case] = []
    seen: set[str] = set()
    for raw in raw_cases:
        label = raw.get("id", "?") if isinstance(raw, dict) else "?"
        try:
            case = Case.model_validate(raw)
        except ValidationError as error:
            fields = ", ".join(str(item["loc"][0]) for item in error.errors() if item["loc"])
            raise GoldenSetError(f"case {label!r}: invalid fields: {fields}") from None
        if case.id in seen:
            raise GoldenSetError(f"duplicate case id {case.id!r}")
        seen.add(case.id)
        _check_case(case, texts, subjects)
        cases.append(case)
    return GoldenSet(version, root, documents, cases, subjects)


def select_cases(golden: GoldenSet, ids: Sequence[str]) -> GoldenSet:
    """The same set restricted to the named cases (to repeat only some of a run)."""
    by_id = {case.id: case for case in golden.cases}
    missing = [case_id for case_id in ids if case_id not in by_id]
    if missing:
        raise GoldenSetError(f"unknown case ids: {', '.join(missing)}")
    return replace(golden, cases=[by_id[case_id] for case_id in ids])
