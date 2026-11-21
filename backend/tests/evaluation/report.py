"""The report of a run: Markdown for people, JSON for comparison. Secrets are scrubbed on write."""

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tests.evaluation.attribution import AttributionStats
from tests.evaluation.guards import scrub
from tests.evaluation.metrics import GroupStats, RetrievalRow


@dataclass(frozen=True)
class Header:
    golden_set_version: str
    revision: str
    mode: str
    embedder: str
    model: str
    date: str
    top_k: int
    threshold: float
    cases: int
    model_calls: int


@dataclass(frozen=True)
class ReviewItem:
    case_id: str
    question: str
    answer: str


@dataclass(frozen=True)
class Report:
    header: Header
    rows: list[RetrievalRow]
    isolation_violations: list[str]
    attribution: dict[str, AttributionStats]
    fallback_cases: list[str]
    unsupported_cases: list[str]
    review: list[ReviewItem]
    problems: list[str] = field(default_factory=list)
    stale_cases: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.0f}%"


def _group_cells(group: GroupStats) -> str:
    if group.n == 0:
        return "- | - | - | - | -"
    return (
        f"{_pct(group.hit1)} | {_pct(group.hit3)} | {_pct(group.hit5)} | "
        f"{group.mrr:.3f} | {_pct(group.refused)}"
    )


def _table(title: str, rows: list[RetrievalRow], pick: str) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| top-k | threshold | default | n | Hit@1 | Hit@3 | Hit@5 | MRR | refused |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        group: GroupStats = getattr(row, pick)
        mark = "yes" if row.default else ""
        lines.append(
            f"| {row.top_k} | {row.threshold:g} | {mark} | {group.n} | {_group_cells(group)} |"
        )
    return [*lines, ""]


def render_markdown(report: Report) -> str:
    head = report.header
    lines = [
        f"# RAG evaluation ({head.mode})",
        "",
        "All documents, questions and users of this run are **fictitious**.",
        "",
        f"- Golden set version: {head.golden_set_version}",
        f"- Code revision: {head.revision}",
        f"- Date: {head.date}",
        f"- Embedder: {head.embedder}",
        f"- Model: {head.model}",
        f"- Configured defaults: top-k {head.top_k}, threshold {head.threshold:g}",
        f"- Cases: {head.cases}; model calls made: {head.model_calls}",
        "",
        "## Retrieval and refusal",
        "",
    ]
    lines += _table("Self-contained questions", report.rows, "answerable")
    lines += _table("Follow-ups (retrieval ignores the conversation)", report.rows, "follow_up")
    lines += _table("Traps with expected sources", report.rows, "trap")
    lines += [
        "### Unanswerable questions that pass the threshold",
        "",
        "| top-k | threshold | default | n | passed |",
        "|---|---|---|---|---|",
    ]
    for row in report.rows:
        mark = "yes" if row.default else ""
        lines.append(
            f"| {row.top_k} | {row.threshold:g} | {mark} | {row.unanswerable_total} | "
            f"{_pct(row.unanswerable_passed)} |"
        )
    lines += ["", "## Isolation", ""]
    lines.append(
        "No case returned a chunk of another subject and every not enrolled student was denied."
        if not report.isolation_violations
        else "**FAILED** cases: " + ", ".join(report.isolation_violations)
    )
    if report.attribution:
        lines += [
            "",
            "## Attribution (answers mode)",
            "",
            "| group | n | valid marker | fallback to all chunks | supported | wrong marker |",
            "|---|---|---|---|---|---|",
        ]
        for name, stats in report.attribution.items():
            lines.append(
                f"| {name} | {stats.n} | {_pct(stats.valid_marker)} | {_pct(stats.fallback)} | "
                f"{_pct(stats.supported)} | {_pct(stats.unsupported)} |"
            )
        lines += [
            "",
            "Cases that fell back to all retrieved chunks: "
            + (", ".join(report.fallback_cases) or "none"),
            "",
            "Cases where the model chose a marker for a wrong chunk: "
            + (", ".join(report.unsupported_cases) or "none"),
            "",
            "Cases that repeated a wrong marker already present in the history or in a document: "
            + (", ".join(report.stale_cases) or "none"),
        ]
    if report.review:
        lines += [
            "",
            "## Unanswerable cases that reached the model: pending human review "
            f"({len(report.review)})",
            "",
        ]
        for item in report.review:
            lines += [f"### {item.case_id}", "", f"Question: {item.question}", "", "Answer:", ""]
            lines += ["> " + line for line in item.answer.splitlines() or [""]]
            lines.append("")
    if report.notes:
        lines += ["", "## Notes", ""] + [f"- {note}" for note in report.notes]
    if report.problems:
        lines += ["", "## Problems", ""] + [f"- {problem}" for problem in report.problems]
    return "\n".join(lines) + "\n"


def to_json(report: Report) -> str:
    return json.dumps(asdict(report), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_report(report: Report, directory: Path, secrets: Iterable[str] = ()) -> tuple[Path, Path]:
    """Write the Markdown and JSON files with every secret removed; return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    head = report.header
    safe_revision = re.sub(r"[^A-Za-z0-9._-]", "-", head.revision)
    stem = f"{head.date}-rag-evaluation-{head.mode}-{safe_revision}"
    markdown = directory / f"{stem}.md"
    structured = directory / f"{stem}.json"
    secret_list = list(secrets)
    markdown.write_text(scrub(render_markdown(report), secret_list), encoding="utf-8")
    structured.write_text(scrub(to_json(report), secret_list), encoding="utf-8")
    return markdown, structured
