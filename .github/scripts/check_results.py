"""Fail the privilege gate unless every pytest report is clean, complete and not skipped.

usage: check_results.py "label=path/to/junit.xml:minimum_tests" [...]

A report that is missing or unreadable, any failure or error, any skipped test and a number of
tests below the minimum are problems; the table of executed tests is printed and appended to
`$GITHUB_STEP_SUMMARY` so that the number of privilege tests executed is always visible.
Change `database-least-privilege`, task 10.2.
"""

import os
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - reports written by our own pytest run
from pathlib import Path

Row = tuple[str, int, int, int, int]  # label, tests, failures, errors, skipped


def summarise(reports: dict[str, tuple[Path, int]]) -> tuple[list[Row], list[str]]:
    rows: list[Row] = []
    problems: list[str] = []
    for label, (path, minimum) in reports.items():
        if not path.is_file():
            problems.append(f"{label}: the report {path.name} is missing (the step did not run)")
            continue
        try:
            root = ET.parse(path).getroot()  # noqa: S314
        except ET.ParseError:
            problems.append(f"{label}: the report {path.name} is unreadable")
            continue
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) for s in suites)
        errors = sum(int(s.get("errors", 0)) for s in suites)
        skipped = sum(int(s.get("skipped", 0)) for s in suites)
        rows.append((label, tests, failures, errors, skipped))
        if failures:
            problems.append(f"{label}: {failures} test(s) failed")
        if errors:
            problems.append(f"{label}: {errors} errors")
        if skipped:
            problems.append(f"{label}: {skipped} test(s) skipped (a privilege test never skips)")
        if tests < minimum:
            problems.append(f"{label}: {tests} tests executed, fewer than the expected {minimum}")
    return rows, problems


def render(rows: list[Row], problems: list[str]) -> str:
    lines = ["| Suite | Executed | Failed | Errors | Skipped |", "|---|---|---|---|---|"]
    lines += [f"| {label} | {t} | {f} | {e} | {s} |" for label, t, f, e, s in rows]
    total = sum(row[1] for row in rows)
    lines.append(f"\nPrivilege tests executed in total: **{total}**")
    if problems:
        lines += ["", "Problems:"] + [f"- {problem}" for problem in problems]
    return "\n".join(lines) + "\n"


def parse(argument: str) -> tuple[str, tuple[Path, int]]:
    label, _, rest = argument.partition("=")
    path, _, minimum = rest.rpartition(":")
    return label, (Path(path), int(minimum))


def main(argv: list[str]) -> int:
    rows, problems = summarise(dict(parse(a) for a in argv))
    text = render(rows, problems)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(text)
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
