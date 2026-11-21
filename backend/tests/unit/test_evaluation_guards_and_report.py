"""Guards (real model, call cap, database), secret scrubbing and the report (tasks 1.5, 1.8)."""

import json
from pathlib import Path

import pytest

from tests.evaluation.attribution import AttributionStats
from tests.evaluation.guards import (
    CallCapExceededError,
    HarnessRefusedError,
    assert_isolated_database,
    plan_model_calls,
    require_cap_within_ceiling,
    require_real_model_permission,
    scrub,
)
from tests.evaluation.report import Header, Report, ReviewItem, render_markdown, write_report

KEY = "AIzaSyFAKE-KEY-FOR-TESTS-0123456789"
URL = "postgresql+psycopg://owner:s3cr3tP4ss@db:5432/asistenteia_test"


def test_the_real_model_needs_the_explicit_flag() -> None:
    with pytest.raises(HarnessRefusedError, match="allow-real-llm"):
        require_real_model_permission(llm="gemini", allow_real_llm=False)


def test_the_flag_is_enough_and_the_fake_model_needs_none() -> None:
    require_real_model_permission(llm="gemini", allow_real_llm=True)
    require_real_model_permission(llm="fake", allow_real_llm=False)


def test_the_call_plan_stops_before_the_first_call_when_the_cap_is_exceeded() -> None:
    with pytest.raises(CallCapExceededError) as stopped:
        plan_model_calls(needed=51, cap=50)

    assert "51" in str(stopped.value) and "50" in str(stopped.value)


def test_the_call_plan_accepts_the_cap_itself() -> None:
    assert plan_model_calls(needed=50, cap=50) == 50
    assert plan_model_calls(needed=0, cap=50) == 0


def test_the_database_guard_refuses_a_name_without_the_test_suffix() -> None:
    url = "postgresql+psycopg://owner:s3cr3tP4ss@db:5432/asistenteia"

    with pytest.raises(HarnessRefusedError) as refused:
        assert_isolated_database(url, "postgresql+psycopg://a:b@db:5432/asistenteia", "development")

    assert "s3cr3tP4ss" not in str(refused.value)


def test_the_database_guard_refuses_the_application_database_and_production() -> None:
    with pytest.raises(HarnessRefusedError):
        assert_isolated_database(URL, URL, "development")
    with pytest.raises(HarnessRefusedError):
        assert_isolated_database(URL, "postgresql+psycopg://a:b@db:5432/other", "production")


def test_the_database_guard_accepts_the_isolated_test_database() -> None:
    assert_isolated_database(URL, "postgresql+psycopg://a:b@db:5432/asistenteia", "development")


def test_scrub_removes_every_secret_and_the_password_of_urls() -> None:
    text = f"key={KEY} url={URL} again {KEY}"

    cleaned = scrub(text, [KEY, URL])

    assert KEY not in cleaned
    assert "s3cr3tP4ss" not in cleaned


def test_scrub_removes_the_password_of_a_url_that_was_not_registered() -> None:
    cleaned = scrub("connect postgresql+psycopg://u:hunter2hunter2@h:1/x_test failed", [])

    assert "hunter2hunter2" not in cleaned


def make_report() -> Report:
    return Report(
        header=Header(
            golden_set_version="v1",
            revision="abc1234-dirty",
            mode="answers",
            embedder="local",
            model="gemini-3.1-flash-lite",
            date="2026-11-21",
            top_k=5,
            threshold=0.3,
            cases=3,
            model_calls=2,
        ),
        rows=[],
        isolation_violations=[],
        attribution={
            "answerable": AttributionStats(
                n=2, valid_marker=1.0, fallback=0.0, supported=1.0, unsupported=0.0
            )
        },
        fallback_cases=["a2"],
        unsupported_cases=[],
        review=[ReviewItem(case_id="u1", question="Pregunta?", answer=f"Respuesta con {KEY}")],
        problems=[],
    )


def test_the_report_header_states_set_revision_settings_embedder_model_and_mode() -> None:
    text = render_markdown(make_report())

    for expected in (
        "v1",
        "abc1234-dirty",
        "answers",
        "local",
        "gemini-3.1-flash-lite",
        "0.3",
        "fictitious",
    ):
        assert expected in text


def test_the_report_lists_fallbacks_and_the_pending_human_review() -> None:
    text = render_markdown(make_report())

    assert "a2" in text
    assert "u1" in text and "Pregunta?" in text and "pending human review" in text.lower()


def test_written_reports_never_contain_a_secret(tmp_path: Path) -> None:
    markdown, structured = write_report(make_report(), tmp_path, secrets=[KEY, URL])

    for path in (markdown, structured):
        assert KEY not in path.read_text(encoding="utf-8")
    data = json.loads(structured.read_text(encoding="utf-8"))
    assert data["header"]["golden_set_version"] == "v1"


def test_the_same_report_renders_identically_twice() -> None:
    assert render_markdown(make_report()) == render_markdown(make_report())


def test_the_counting_wrapper_refuses_a_call_beyond_the_cap() -> None:
    import asyncio

    from app.services.llm_service import FakeLLMService
    from tests.evaluation.runner import _CountingLLM

    counting = _CountingLLM(FakeLLMService(), cap=1)

    asyncio.run(counting.generate("system", [{"role": "user", "content": "uno"}]))
    with pytest.raises(CallCapExceededError):
        asyncio.run(counting.generate("system", [{"role": "user", "content": "dos"}]))

    assert counting.calls == 1


def test_the_counting_wrapper_pauses_between_calls_but_not_before_the_first() -> None:
    import asyncio

    from app.services.llm_service import FakeLLMService
    from tests.evaluation.runner import _CountingLLM

    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    counting = _CountingLLM(FakeLLMService(), cap=3, pause_seconds=2.5, sleep=fake_sleep)

    for index in range(3):
        asyncio.run(counting.generate("system", [{"role": "user", "content": str(index)}]))

    assert pauses == [2.5, 2.5]


def test_the_cap_cannot_exceed_the_authorised_ceiling() -> None:
    require_cap_within_ceiling(50)
    with pytest.raises(HarnessRefusedError, match="50"):
        require_cap_within_ceiling(51)
    with pytest.raises(HarnessRefusedError):
        require_cap_within_ceiling(-1)
