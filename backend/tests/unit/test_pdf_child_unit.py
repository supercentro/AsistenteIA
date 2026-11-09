"""The child's own logic run in-process with a stand-in reader (any operating system).

The real child process and its limits are tested in `test_pdf_child.py` (Linux only); here the
extraction loop, the protocol it writes and the mapping of its failures are checked directly,
without `pypdf` and without applying any resource limit.
"""

import io
import json
import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

from app.rag import pdf_child


class FakePage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class FakeReader:
    pages: list[FakePage] = []
    encrypted = False
    error: BaseException | None = None

    def __init__(self, stream: io.BytesIO, strict: bool = True) -> None:
        assert strict is False  # tolerant parsing, as designed
        if FakeReader.error is not None:
            raise FakeReader.error
        self.is_encrypted = FakeReader.encrypted
        self.pages = FakeReader.pages


class Streams:
    def __init__(self, data: bytes) -> None:
        self.stdin = types.SimpleNamespace(buffer=io.BytesIO(data))
        self.stdout = types.SimpleNamespace(buffer=io.BytesIO())

    def records(self) -> list[dict[str, Any]]:
        lines = self.stdout.buffer.getvalue().decode("utf-8").splitlines()
        return [json.loads(line) for line in lines]


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    applied: list[tuple[int, int]] = []
    monkeypatch.setattr(pdf_child, "apply_limits", lambda m, c: applied.append((m, c)))
    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakeReader))
    FakeReader.pages, FakeReader.encrypted, FakeReader.error = [], False, None

    def go(
        *pages: str | None,
        max_pages: int = 10,
        max_chars: int = 1000,
        encrypted: bool = False,
        error: BaseException | None = None,
    ) -> tuple[int, list[dict[str, Any]], list[tuple[int, int]]]:
        FakeReader.pages = [FakePage(text) for text in pages]
        FakeReader.encrypted = encrypted
        FakeReader.error = error
        streams = Streams(b"%PDF-1.4 data")
        monkeypatch.setattr(sys, "stdin", streams.stdin)
        monkeypatch.setattr(sys, "stdout", streams.stdout)
        arguments = ["pdf_child.py", "321", "9", str(max_pages), str(max_chars)]
        status = pdf_child.main(arguments)
        return status, streams.records(), applied

    yield go


def test_every_page_is_written_in_order_followed_by_the_end_marker(run: Any) -> None:
    status, records, _ = run("uno", "dos", "tres")

    assert status == 0
    assert records == [
        {"page": 1, "text": "uno"},
        {"page": 2, "text": "dos"},
        {"page": 3, "text": "tres"},
        {"end": True},
    ]


def test_a_page_without_text_is_written_as_an_empty_string(run: Any) -> None:
    _, records, _ = run(None, "x")

    assert records[0] == {"page": 1, "text": ""}


def test_lone_surrogates_are_removed_from_the_text(run: Any) -> None:
    status, records, _ = run("a\ud800b\udfffc \U0001f600")

    assert status == 0
    assert records[0] == {"page": 1, "text": "abc \U0001f600"}


def test_non_ascii_text_is_not_escaped(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeReader.pages = [FakePage("ñandú 日本")]
    streams = Streams(b"x")
    monkeypatch.setattr(sys, "stdin", streams.stdin)
    monkeypatch.setattr(sys, "stdout", streams.stdout)

    pdf_child.main(["pdf_child.py", "300", "5", "10", "100"])

    assert "ñandú 日本".encode() in streams.stdout.buffer.getvalue()


def test_the_limits_are_applied_with_the_given_values(run: Any) -> None:
    _, _, applied = run("x")

    assert applied == [(321, 9)]


def test_the_limits_are_applied_before_stdin_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Stdin:
        class buffer:  # noqa: N801 - mimics sys.stdin.buffer
            @staticmethod
            def read() -> bytes:
                events.append("read")
                return b""

    monkeypatch.setattr(pdf_child, "apply_limits", lambda m, c: events.append("limits"))
    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakeReader))
    FakeReader.pages, FakeReader.encrypted, FakeReader.error = [], False, None
    monkeypatch.setattr(sys, "stdin", Stdin)
    monkeypatch.setattr(sys, "stdout", types.SimpleNamespace(buffer=io.BytesIO()))

    pdf_child.main(["pdf_child.py", "300", "5", "10", "100"])

    assert events == ["limits", "read"]


def test_an_encrypted_pdf_is_rejected_before_any_page_is_touched(run: Any) -> None:
    status, records, _ = run("secret", encrypted=True)

    assert status == 1
    assert records == [{"error": "ENCRYPTED_PDF"}]


def test_too_many_pages_are_rejected_before_any_text_is_extracted(run: Any) -> None:
    status, records, _ = run("a", "b", "c", max_pages=2)

    assert status == 1
    assert records == [{"error": "TOO_MANY_PAGES"}]


def test_exactly_the_page_cap_is_accepted(run: Any) -> None:
    status, records, _ = run("a", "b", max_pages=2)

    assert status == 0
    assert records[-1] == {"end": True}


def test_the_character_cap_is_checked_per_page_as_the_total_grows(run: Any) -> None:
    status, records, _ = run("abcde", "fghij", "klmno", max_chars=12)

    assert status == 1
    assert records == [
        {"page": 1, "text": "abcde"},
        {"page": 2, "text": "fghij"},
        {"error": "TEXT_TOO_LARGE"},
    ]


def test_exactly_the_character_cap_is_accepted(run: Any) -> None:
    status, _, _ = run("abcde", "fghij", max_chars=10)

    assert status == 0


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (MemoryError(), "RESOURCE_LIMIT_EXCEEDED"),
        (ValueError("secret detail"), "CORRUPT_FILE"),
        (RecursionError(), "CORRUPT_FILE"),
        (KeyError("k"), "CORRUPT_FILE"),
    ],
)
def test_a_reader_failure_is_reported_with_a_code_only(
    run: Any, error: BaseException, code: str
) -> None:
    status, records, _ = run("x", error=error)

    assert status == 1
    assert records == [{"error": code}]


def test_a_page_failure_after_some_pages_is_reported_as_corrupt(
    run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Exploding(FakePage):
        def extract_text(self) -> str:
            raise RuntimeError("detail that must not be printed")

    def reader(stream: io.BytesIO, strict: bool = True) -> Any:
        return types.SimpleNamespace(is_encrypted=False, pages=[FakePage("ok"), Exploding(None)])

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=reader))
    streams = Streams(b"x")
    monkeypatch.setattr(sys, "stdin", streams.stdin)
    monkeypatch.setattr(sys, "stdout", streams.stdout)

    status = pdf_child.main(["pdf_child.py", "300", "5", "10", "100"])

    assert status == 1
    assert streams.records()[-1] == {"error": "CORRUPT_FILE"}
    assert b"detail" not in streams.stdout.buffer.getvalue()
