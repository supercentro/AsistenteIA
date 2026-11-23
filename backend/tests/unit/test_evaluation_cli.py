"""The command line refuses before doing anything when a guard says so (tasks 1.5)."""

import json
from pathlib import Path

import pytest

from tests.evaluation.__main__ import main

OK_URL = "postgresql+psycopg://owner:s3cr3tP4ss@db:5432/asistenteia_test"
APP_URL = "postgresql+psycopg://app:appS3cret@db:5432/asistenteia"
KEY = "AIzaSyFAKE-KEY-FOR-TESTS-0123456789"


def tiny_set(tmp_path: Path) -> Path:
    (tmp_path / "corpus" / "bio").mkdir(parents=True)
    (tmp_path / "corpus" / "bio" / "p.md").write_text("La fotosintesis ocurre aqui.\n", "utf-8")
    (tmp_path / "VERSION").write_text("t\n", encoding="utf-8")
    (tmp_path / "cases.json").write_text(
        json.dumps(
            [
                {
                    "id": "a1",
                    "kind": "answerable",
                    "subject": "bio",
                    "question": "Donde?",
                    "expected": {
                        "type": "sources",
                        "sources": [{"filename": "p.md", "passage_contains": "fotosintesis"}],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_the_real_model_is_refused_without_the_flag_and_nothing_connects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL, "GOOGLE_API_KEY": KEY}

    code = main(["--llm", "gemini", "--golden-set", str(tiny_set(tmp_path))], env)

    err = capsys.readouterr().err
    assert code == 2
    assert "allow-real-llm" in err
    assert KEY not in err and "s3cr3tP4ss" not in err


def test_a_database_that_is_not_the_isolated_test_database_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {"TEST_DATABASE_URL": APP_URL, "DATABASE_URL": APP_URL}

    code = main(["--golden-set", str(tiny_set(tmp_path))], env)

    captured = capsys.readouterr()
    assert code == 2
    assert "appS3cret" not in captured.err
    assert captured.out == ""


def test_the_same_database_as_the_application_is_refused(tmp_path: Path) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": OK_URL}

    assert main(["--golden-set", str(tiny_set(tmp_path))], env) == 2


def test_production_is_refused(tmp_path: Path) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL, "APP_ENV": "production"}

    assert main(["--golden-set", str(tiny_set(tmp_path))], env) == 2


def test_a_missing_database_url_is_refused(tmp_path: Path) -> None:
    assert main(["--golden-set", str(tiny_set(tmp_path))], {}) == 2


def test_an_invalid_golden_set_is_refused_before_connecting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL}

    code = main(["--golden-set", str(tmp_path)], env)  # empty directory: no set

    assert code == 2
    assert "refused" in capsys.readouterr().err


def test_a_cap_above_the_authorised_ceiling_is_refused(tmp_path: Path) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL, "GOOGLE_API_KEY": KEY}

    code = main(["--max-calls", "51", "--golden-set", str(tiny_set(tmp_path))], env)

    assert code == 2


def test_an_unexpected_failure_is_reported_without_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # --llm gemini without GOOGLE_API_KEY makes the settings fail with a validation error whose
    # text can echo its input; the command line must still print no password and exit with 2.
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps({"authorised_total": 50, "spent": 0, "entries": []}), encoding="utf-8"
    )
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL}

    code = main(
        [
            "--ledger",
            str(ledger),
            "--mode",
            "answers",
            "--llm",
            "gemini",
            "--allow-real-llm",
            "--embedder",
            "fake",
            "--golden-set",
            str(tiny_set(tmp_path)),
        ],
        env,
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "s3cr3tP4ss" not in captured.err + captured.out
    assert "unexpected failure" in captured.err


def test_unknown_case_ids_are_refused(tmp_path: Path) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL}

    assert main(["--only", "nope", "--golden-set", str(tiny_set(tmp_path))], env) == 2


def test_the_real_model_needs_a_ledger_with_budget_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps({"authorised_total": 50, "spent": 154, "entries": []}), encoding="utf-8"
    )
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL, "GOOGLE_API_KEY": KEY}

    code = main(
        [
            "--mode",
            "answers",
            "--llm",
            "gemini",
            "--allow-real-llm",
            "--ledger",
            str(ledger),
            "--golden-set",
            str(tiny_set(tmp_path)),
        ],
        env,
    )

    assert code == 2
    assert "budget" in capsys.readouterr().err


def test_a_used_authorisation_stops_the_real_run_before_it_connects_to_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "authorised_total": 204,
                "spent": 156,
                "entries": [
                    {"date": "2026-11-24", "mode": "answers", "calls": 2, "authorised_total": 204}
                ],
            }
        ),
        encoding="utf-8",
    )
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL, "GOOGLE_API_KEY": KEY}

    code = main(
        [
            "--mode",
            "answers",
            "--llm",
            "gemini",
            "--allow-real-llm",
            "--ledger",
            str(ledger),
            "--golden-set",
            str(tiny_set(tmp_path)),
        ],
        env,
    )

    assert code == 2
    assert "already used" in capsys.readouterr().err


def test_the_real_model_without_a_ledger_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {"TEST_DATABASE_URL": OK_URL, "DATABASE_URL": APP_URL, "GOOGLE_API_KEY": KEY}

    code = main(
        [
            "--mode",
            "answers",
            "--llm",
            "gemini",
            "--allow-real-llm",
            "--golden-set",
            str(tiny_set(tmp_path)),
        ],
        env,
    )

    assert code == 2
    assert "--ledger is required" in capsys.readouterr().err


def test_the_password_of_a_database_url_is_registered_decoded_and_quoted() -> None:
    from tests.evaluation.__main__ import _password_forms

    forms = _password_forms("postgresql+psycopg://owner:p%40ss%2Fword@db:5432/asistenteia_test")

    assert "p@ss/word" in forms
    assert "p%40ss%2Fword" in forms
    assert _password_forms("") == []
    assert _password_forms("not a url") == []
