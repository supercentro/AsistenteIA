"""Retrieval, refusal and isolation metrics computed from what the production read phase returned.

The harness asks the production code for the chunks (one call with a wide top-k and no threshold);
every (top-k, threshold) row is then derived by cutting that ranking exactly as the production
code does: nearest `top_k` first, then those at or above the threshold.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.repositories.chunk_repository import ScoredChunk
from tests.evaluation.cases import Case, ExpectedSource, normalize

SELF_CONTAINED = {"answerable"}
FOLLOW_UP = {"follow_up"}
TRAPS = {"trap_history_marker", "trap_document_marker", "injection_document"}


@dataclass(frozen=True)
class Retrieved:
    """What the read phase gave for one case: the ranked chunks, or a refusal of access."""

    chunks: tuple[ScoredChunk, ...] = ()
    denied: bool = False


@dataclass(frozen=True)
class GroupStats:
    n: int
    hit1: float
    hit3: float
    hit5: float
    supported: float
    mrr: float
    refused: float


@dataclass(frozen=True)
class RetrievalRow:
    top_k: int
    threshold: float
    default: bool
    answerable: GroupStats
    follow_up: GroupStats
    trap: GroupStats
    unanswerable_total: int
    unanswerable_passed: float


def supports(chunk: ScoredChunk, sources: Iterable[ExpectedSource]) -> bool:
    """True when the chunk contains one of the accepted passages of the right file (and page)."""
    text = normalize(chunk.content)
    return any(
        chunk.document_filename == source.filename
        and normalize(source.passage_contains) in text
        and (source.page is None or chunk.page_number == source.page)
        for source in sources
    )


def cut(chunks: Sequence[ScoredChunk], top_k: int, threshold: float) -> list[ScoredChunk]:
    """The chunks the production code keeps for these settings."""
    return [chunk for chunk in chunks[:top_k] if chunk.similarity >= threshold]


def _group(
    cases: Sequence[Case], outcomes: Mapping[str, Retrieved], k: int, t: float
) -> GroupStats:
    if not cases:
        return GroupStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ranks: list[int | None] = []
    refused = 0
    for case in cases:
        kept = cut(outcomes[case.id].chunks, k, t)
        refused += 0 if kept else 1
        rank = next(
            (i for i, chunk in enumerate(kept, start=1) if supports(chunk, case.expected.sources)),
            None,
        )
        ranks.append(rank)
    n = len(cases)
    return GroupStats(
        n=n,
        hit1=sum(1 for r in ranks if r is not None and r <= 1) / n,
        hit3=sum(1 for r in ranks if r is not None and r <= 3) / n,
        hit5=sum(1 for r in ranks if r is not None and r <= 5) / n,
        supported=sum(1 for r in ranks if r is not None) / n,
        mrr=sum(1 / r for r in ranks if r is not None) / n,
        refused=refused / n,
    )


def retrieval_rows(
    cases: Sequence[Case],
    outcomes: Mapping[str, Retrieved],
    *,
    top_ks: Sequence[int],
    thresholds: Sequence[float],
    default: tuple[int, float],
) -> list[RetrievalRow]:
    """One row per (top-k, threshold) combination; the configured default is marked."""
    answerable = [c for c in cases if c.kind in SELF_CONTAINED]
    follow_up = [c for c in cases if c.kind in FOLLOW_UP]
    traps = [c for c in cases if c.kind in TRAPS]
    unanswerable = [c for c in cases if c.kind == "unanswerable"]
    rows: list[RetrievalRow] = []
    for k in top_ks:
        for t in thresholds:
            passed = sum(1 for c in unanswerable if cut(outcomes[c.id].chunks, k, t))
            rows.append(
                RetrievalRow(
                    top_k=k,
                    threshold=t,
                    default=(k, t) == default,
                    answerable=_group(answerable, outcomes, k, t),
                    follow_up=_group(follow_up, outcomes, k, t),
                    trap=_group(traps, outcomes, k, t),
                    unanswerable_total=len(unanswerable),
                    unanswerable_passed=passed / len(unanswerable) if unanswerable else 0.0,
                )
            )
    return rows


def isolation_violations(
    cases: Sequence[Case],
    outcomes: Mapping[str, Retrieved],
    subject_of_filename: Mapping[str, str],
) -> list[str]:
    """Ids of the cases that returned a chunk of another subject, or whose access was not denied.

    A student who is not enrolled must be refused; every other case may only see the chunks of the
    subject it asked about.
    """
    violations: list[str] = []
    for case in cases:
        outcome = outcomes[case.id]
        if case.student != "enrolled":
            if not outcome.denied:
                violations.append(case.id)
            continue
        if any(
            subject_of_filename.get(c.document_filename) != case.subject for c in outcome.chunks
        ):
            violations.append(case.id)
    return violations
