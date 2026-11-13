"""The helpers of the CI privilege gate (change `database-least-privilege`, task 10.2).

`check_results.py` must fail on any failure, error, skipped test, missing report or too few tests
(the number of privilege tests executed is reported); `assert_disposable_cluster.py` must refuse a
cluster that is not the exclusive, empty, local pgvector cluster the workflow created. Both are pure
functions here, so every refusal is tested without a database.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / ".github" / "scripts"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"{name}.py is missing"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


results = load("check_results")
cluster = load("assert_disposable_cluster")


def junit(
    tmp_path: Path, name: str, *, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0
) -> Path:
    path = tmp_path / name
    path.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite name="pytest" errors="{errors}" '
        f'failures="{failures}" skipped="{skipped}" tests="{tests}"></testsuite></testsuites>',
        encoding="utf-8",
    )
    return path


def test_a_clean_report_above_the_minimum_passes_and_is_counted(tmp_path: Path) -> None:
    report = junit(tmp_path, "a.xml", tests=410)

    rows, problems = results.summarise({"role suites": (report, 400)})

    assert problems == [] and rows == [("role suites", 410, 0, 0, 0)]


@pytest.mark.parametrize(
    ("kwargs", "word"),
    [
        ({"tests": 500, "failures": 1}, "failed"),
        ({"tests": 500, "errors": 2}, "errors"),
        ({"tests": 500, "skipped": 3}, "skipped"),
        ({"tests": 12}, "fewer"),
    ],
)
def test_any_failure_error_skip_or_shortfall_is_a_problem(
    tmp_path: Path, kwargs: dict[str, int], word: str
) -> None:
    report = junit(tmp_path, "a.xml", **kwargs)

    _, problems = results.summarise({"role suites": (report, 400)})

    assert len(problems) == 1 and word in problems[0]


def test_a_missing_report_is_a_problem_not_a_pass(tmp_path: Path) -> None:
    _, problems = results.summarise({"role suites": (tmp_path / "absent.xml", 1)})

    assert problems and "missing" in problems[0]


def test_a_malformed_report_is_a_problem(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<not-xml", encoding="utf-8")

    _, problems = results.summarise({"role suites": (bad, 1)})

    assert problems and "unreadable" in problems[0]


def test_the_main_function_exits_non_zero_on_a_problem(tmp_path: Path) -> None:
    report = junit(tmp_path, "a.xml", tests=5)

    assert results.main([f"role suites={report}:400"]) == 1
    assert results.main([f"role suites={report}:5"]) == 0


GOOD = cluster.Facts(
    host="127.0.0.1",
    port=5433,
    version="PostgreSQL 15.19 (Debian 15.19-1.pgdg12+2) on x86_64-pc-linux-gnu",
    vector_versions=["0.8.7"],
    databases=["postgres", "template0", "template1"],
    roles=["ci_admin"],
    superuser=True,
)


def test_the_expected_cluster_has_no_problem() -> None:
    assert cluster.evaluate(GOOD, "flow", allowed_hosts={"127.0.0.1", "localhost"}) == []


@pytest.mark.parametrize(
    ("change", "word"),
    [
        ({"host": "db.example.com"}, "host"),
        ({"version": "PostgreSQL 16.2"}, "version"),
        ({"vector_versions": ["0.8.6"]}, "pgvector"),
        ({"vector_versions": []}, "pgvector"),
        ({"databases": ["postgres", "template0", "template1", "asistenteia"]}, "database"),
        ({"databases": ["postgres", "template0", "template1", "asistenteia_test"]}, "database"),
        ({"roles": ["ci_admin", "asistente_app"]}, "role"),
        ({"roles": ["ci_admin", "asistente"]}, "role"),
        ({"superuser": False}, "superuser"),
    ],
)
def test_a_cluster_that_is_not_the_exclusive_empty_local_one_is_refused(
    change: dict[str, object], word: str
) -> None:
    facts = cluster.Facts(**{**GOOD.__dict__, **change})

    problems = cluster.evaluate(facts, "flow", allowed_hosts={"127.0.0.1", "localhost"})

    assert any(word in p for p in problems), problems


def test_the_test_cluster_tolerates_only_its_own_scratch_objects() -> None:
    mixed = cluster.Facts(
        **{
            **GOOD.__dict__,
            "databases": ["postgres", "template0", "template1", "tstdb_ci_test"],
            "roles": ["ci_admin", "tstrole_app"],
        }
    )

    assert cluster.evaluate(mixed, "tests", allowed_hosts={"127.0.0.1"}) == []
    assert cluster.evaluate(mixed, "flow", allowed_hosts={"127.0.0.1"})  # not on the flow cluster


def test_the_two_clusters_must_be_different_servers() -> None:
    assert cluster.same_server(
        "postgresql+psycopg://u:p@127.0.0.1:5433/postgres",
        "postgresql+psycopg://u:q@127.0.0.1:5433/other",
    )
    assert not cluster.same_server(
        "postgresql+psycopg://u:p@127.0.0.1:5433/postgres",
        "postgresql+psycopg://u:p@127.0.0.1:5434/postgres",
    )


def test_the_report_never_contains_the_password() -> None:
    text = cluster.describe(GOOD, "flow")

    assert "5433" in text and "password" not in text.lower()


# ---- cluster identity and revision checks (review L1 and L8 of group 10)


def test_localhost_and_the_loopback_address_are_the_same_server() -> None:
    assert cluster.same_server(
        "postgresql+psycopg://u:p@localhost:5433/postgres",
        "postgresql+psycopg://u:p@127.0.0.1:5433/postgres",
    )


alembic_check = load("alembic_check")


@pytest.mark.parametrize(
    ("head", "current", "expected"),
    [
        ("0006", "0006", True),
        ("0007", "0007", True),
        ("0010", "0010", True),
        ("0005", "0005", False),
        ("0006", "0005", False),
        ("0006", None, False),
        (None, None, False),
        ("abc", "abc", False),
    ],
)
def test_the_database_must_be_at_the_head_and_the_head_at_least_0006(
    head: str | None, current: str | None, expected: bool
) -> None:
    assert alembic_check.acceptable(head, current) is expected
