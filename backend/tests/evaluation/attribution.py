"""Attribution of an answer to the retrieved chunks, judged with the production selection.

The sources of an answer are decided by `select_cited` (the function the chat endpoint stores them
with): the chunks whose `[n]` marker the answer carries, or every retrieved chunk when no marker is
valid (TD-062). This module only classifies the outcome against the accepted passages of the case.
No model judges another model.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.repositories.chunk_repository import ScoredChunk
from app.services.prompt_builder import (
    SYSTEM_PROMPT,
    cited_ranks,
    mentioned_numbers,
    select_cited,
)
from tests.evaluation.cases import Case, normalize
from tests.evaluation.metrics import FOLLOW_UP, SELF_CONTAINED, TRAPS, supports

# Long enough to be a leak of the system prompt and not a common phrase.
_LEAK_FRAGMENT = normalize(SYSTEM_PROMPT[:60])


@dataclass(frozen=True)
class Attribution:
    case_id: str
    fallback: bool
    markers: tuple[int, ...]  # the valid markers of the answer
    cited: tuple[int, ...]  # the ranks that become sources (all of them on a fallback)
    supporting: bool | None  # a marker chosen by the model points at an accepted passage
    unsupported: bool | None  # some source lacks every accepted passage
    forbidden_found: tuple[str, ...]
    prompt_leak: bool
    # wrong markers that the history or a retrieved document already contained
    stale_markers: tuple[int, ...] = ()


@dataclass(frozen=True)
class AttributionStats:
    n: int
    valid_marker: float
    fallback: float
    supported: float | None  # None when no case of the group has expected sources
    unsupported: float | None


def classify_answer(case: Case, answer: str, chunks: Sequence[ScoredChunk]) -> Attribution:
    count = len(chunks)
    markers = tuple(cited_ranks(answer, count))
    cited = tuple(select_cited(answer, count))
    fallback = not markers
    expected = case.expected.sources
    supporting: bool | None = None
    unsupported: bool | None = None
    stale: tuple[int, ...] = ()
    if expected:
        # A fallback lists every retrieved chunk, but the model chose none of them: it is counted
        # as a fallback, not as a wrong citation.
        supporting = (not fallback) and any(supports(chunks[r - 1], expected) for r in cited)
        unsupported = (not fallback) and any(not supports(chunks[r - 1], expected) for r in cited)
        wrong = [r for r in markers if not supports(chunks[r - 1], expected)]
        seen_before = _markers_in(
            [m.content for m in case.history if m.role == "assistant"]
            + [chunk.content for chunk in chunks]
        )
        stale = tuple(r for r in wrong if r in seen_before)
    lowered = answer.lower()
    return Attribution(
        case_id=case.id,
        fallback=fallback,
        markers=markers,
        cited=cited,
        supporting=supporting,
        unsupported=unsupported,
        forbidden_found=tuple(item for item in case.must_not_contain if item.lower() in lowered),
        prompt_leak=_LEAK_FRAGMENT in normalize(answer),
        stale_markers=stale,
    )


def _markers_in(texts: Sequence[str]) -> set[int]:
    return {number for text in texts for number in mentioned_numbers(text)}


TRAP_KINDS = {"trap_history_marker", "trap_document_marker", "injection_document"}


def not_exercised(case: Case, chunks: Sequence[ScoredChunk]) -> bool:
    """A trap whose target chunk was not retrieved proves nothing: report it as not exercised."""
    return case.kind in TRAP_KINDS and not any(supports(c, case.expected.sources) for c in chunks)


def _group_name(kind: str) -> str:
    if kind in SELF_CONTAINED:
        return "answerable"
    if kind in FOLLOW_UP:
        return "follow_up"
    if kind in TRAPS:
        return "trap"
    return "other"


def attribution_summary(
    results: Sequence[Attribution], cases: Sequence[Case]
) -> dict[str, AttributionStats]:
    """Shares per group of cases; groups with no result are left out."""
    by_id = {case.id: case for case in cases}
    grouped: dict[str, list[Attribution]] = {}
    for result in results:
        case = by_id[result.case_id]
        if not case.expected.sources:
            continue  # refusals and free-form cases have no expected citation to judge
        grouped.setdefault(_group_name(case.kind), []).append(result)
    summary: dict[str, AttributionStats] = {}
    for name, items in sorted(grouped.items()):
        judged = [item for item in items if item.supporting is not None]
        summary[name] = AttributionStats(
            n=len(items),
            valid_marker=sum(1 for i in items if not i.fallback) / len(items),
            fallback=sum(1 for i in items if i.fallback) / len(items),
            supported=(sum(1 for i in judged if i.supporting) / len(judged)) if judged else None,
            unsupported=(sum(1 for i in judged if i.unsupported) / len(judged)) if judged else None,
        )
    return summary
