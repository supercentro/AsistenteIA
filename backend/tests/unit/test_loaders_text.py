"""Strict UTF-8 text and Markdown loading (change 6, task 6.1)."""

from collections.abc import Callable
from typing import Any

import pytest

from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.rag.chunker import Page
from app.rag.loaders import DocumentLoadError, load_markdown, load_text

Loader = Callable[..., list[Page]]

LOADERS = [pytest.param(load_text, id="text"), pytest.param(load_markdown, id="markdown")]


def _fails(loader: Loader, payload: bytes, **kwargs: Any) -> DocumentLoadError:
    with pytest.raises(DocumentLoadError) as caught:
        loader(payload, **kwargs)
    return caught.value


@pytest.mark.parametrize("loader", LOADERS)
class TestLoadingText:
    def test_plain_text_becomes_one_page_without_a_number(self, loader: Loader) -> None:
        pages = loader("Hola mundo\nSegunda línea".encode())

        assert pages == [Page(number=None, text="Hola mundo\nSegunda línea")]

    def test_non_ascii_text_is_kept(self, loader: Loader) -> None:
        text = "ñandú, 日本語, \U0001f600, Ελληνικά"

        assert loader(text.encode())[0].text == text

    def test_a_leading_byte_order_mark_is_removed(self, loader: Loader) -> None:
        pages = loader(b"\xef\xbb\xbfHola")

        assert pages == [Page(number=None, text="Hola")]

    def test_only_the_leading_byte_order_mark_is_special(self, loader: Loader) -> None:
        text = loader("a﻿b".encode())[0].text

        assert text == "a﻿b"

    def test_line_endings_are_unified(self, loader: Loader) -> None:
        assert loader(b"one\r\ntwo\rthree\nfour")[0].text == "one\ntwo\nthree\nfour"

    def test_the_text_goes_through_the_normaliser(self, loader: Loader) -> None:
        payload = "a\u0001b‮c d e".encode()

        assert loader(payload)[0].text == "abc d\ne"

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(b"\xff\xfe", id="utf16-byte-order-mark"),
            pytest.param(b"abc\xe2\x82", id="truncated-sequence"),
            pytest.param(b"\xc0\xaf", id="overlong-encoding"),
            pytest.param(b"\xed\xa0\x80", id="encoded-surrogate"),
            pytest.param(b"ok \x80 bad", id="lone-continuation-byte"),
            pytest.param("texto".encode("utf-16"), id="utf16-text"),
            pytest.param("texto ñ".encode("latin-1"), id="latin1-text"),
        ],
    )
    def test_invalid_utf8_is_a_corrupt_file(self, loader: Loader, payload: bytes) -> None:
        error = _fails(loader, payload)

        assert error.code is DocumentErrorCode.CORRUPT_FILE

    @pytest.mark.parametrize(
        "payload",
        [b"abc\x00def", b"\x00", "ñ\x00".encode(), b"\xef\xbb\xbf\x00hola"],
    )
    def test_nul_is_a_corrupt_file(self, loader: Loader, payload: bytes) -> None:
        assert _fails(loader, payload).code is DocumentErrorCode.CORRUPT_FILE

    @pytest.mark.parametrize(
        "payload",
        [
            b"",
            b"   \n\t  ",
            b"\xef\xbb\xbf",
            b"\xc2\xa0\xc2\x85\xe2\x80\xa8",
            "​‍".encode(),
            b"\r\n\r\n",
        ],
    )
    def test_text_without_visible_characters_has_no_extractable_text(
        self, loader: Loader, payload: bytes
    ) -> None:
        assert _fails(loader, payload).code is DocumentErrorCode.NO_EXTRACTABLE_TEXT

    def test_text_above_the_character_cap_is_too_large(self, loader: Loader) -> None:
        error = _fails(loader, b"a" * 11, max_chars=10)

        assert error.code is DocumentErrorCode.TEXT_TOO_LARGE

    def test_text_exactly_at_the_character_cap_is_accepted(self, loader: Loader) -> None:
        assert loader(b"a" * 10, max_chars=10)[0].text == "a" * 10

    def test_the_cap_counts_characters_not_bytes(self, loader: Loader) -> None:
        assert loader("ñ".encode() * 10, max_chars=10)[0].text == "ñ" * 10

    def test_the_default_cap_is_the_approved_two_million_characters(self, loader: Loader) -> None:
        loader(b"a" * 2_000_000)

        assert _fails(loader, b"a" * 2_000_001).code is DocumentErrorCode.TEXT_TOO_LARGE

    def test_the_error_carries_the_fixed_message_of_its_code(self, loader: Loader) -> None:
        error = _fails(loader, b"\xff")

        assert str(error) == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.CORRUPT_FILE]
        assert error.args == (DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.CORRUPT_FILE],)

    def test_the_decoder_error_is_not_chained_to_the_failure(self, loader: Loader) -> None:
        error = _fails(loader, b"MARKER-\xff-bytes")

        assert error.__cause__ is None
        assert error.__context__ is None or error.__suppress_context__


class TestMarkdownIsData:
    SOURCE = (
        "# Title\n\n<script>alert(1)</script>\n"
        '<img src=x onerror="alert(2)">\n'
        "[click](javascript:alert(3)) ![pixel](http://example.invalid/p.png)\n"
        "```html\n<b>bold</b>\n```\n&lt;escaped&gt; <!-- comment -->\n"
    )

    def test_html_and_links_are_stored_unchanged(self) -> None:
        pages = load_markdown(self.SOURCE.encode())

        assert pages == [Page(number=None, text=self.SOURCE.strip())]

    def test_markdown_syntax_is_not_converted(self) -> None:
        text = load_markdown(b"**bold** _it_ `code`\n- item\n> quote")[0].text

        assert text == "**bold** _it_ `code`\n- item\n> quote"

    def test_text_files_keep_html_as_text_too(self) -> None:
        assert load_text(b"<script>x</script>")[0].text == "<script>x</script>"


def test_the_loaders_return_new_lists_of_pages() -> None:
    first = load_text(b"abc")
    first.append(Page(number=9, text="extra"))

    assert load_text(b"abc") == [Page(number=None, text="abc")]
