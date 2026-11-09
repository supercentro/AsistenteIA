"""Normalisation of extracted text before chunking (group 5, task 5.2; resolves TD-027)."""

import pytest

from app.rag.normalizer import has_visible_text, normalize_text

BIDI_CONTROLS = [
    "\u061c",  # Arabic letter mark
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\u202a",  # left-to-right embedding
    "\u202b",  # right-to-left embedding
    "\u202c",  # pop directional formatting
    "\u202d",  # left-to-right override
    "\u202e",  # right-to-left override
    "\u2066",  # left-to-right isolate
    "\u2067",  # right-to-left isolate
    "\u2068",  # first strong isolate
    "\u2069",  # pop directional isolate
]
UNICODE_SPACES = [
    "\u00a0",  # no-break space
    "\u1680",
    "\u2000",
    "\u2001",
    "\u2002",
    "\u2003",
    "\u2004",
    "\u2005",
    "\u2006",
    "\u2007",
    "\u2008",
    "\u2009",
    "\u200a",
    "\u202f",
    "\u205f",
    "\u3000",
]


def test_nul_is_removed() -> None:
    assert normalize_text("La\x00 derivada\x00") == "La derivada"


@pytest.mark.parametrize("control", ["\x01", "\x07", "\x08", "\x0e", "\x1b", "\x1f", "\x7f"])
def test_c0_controls_and_delete_are_removed(control: str) -> None:
    assert normalize_text(f"uno{control}dos") == "unodos"


@pytest.mark.parametrize("control", ["\x80", "\x8e", "\x90", "\x9f"])
def test_c1_controls_are_removed(control: str) -> None:
    assert normalize_text(f"uno{control}dos") == "unodos"


@pytest.mark.parametrize("mark", BIDI_CONTROLS)
def test_bidirectional_controls_are_removed(mark: str) -> None:
    assert normalize_text(f"abc{mark}def") == "abcdef"


def test_a_right_to_left_override_cannot_reorder_visible_text() -> None:
    assert (
        normalize_text("transferencia \u202egnp.exe\u202c final") == "transferencia gnp.exe final"
    )


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\x85"])
def test_line_separators_and_next_line_become_line_breaks(separator: str) -> None:
    assert normalize_text(f"primera{separator}segunda") == "primera\nsegunda"


def test_carriage_returns_become_line_feeds() -> None:
    assert normalize_text("a\r\nb\rc\nd") == "a\nb\nc\nd"


@pytest.mark.parametrize("control", ["\x0b", "\x0c"])
def test_vertical_tab_and_form_feed_become_line_breaks(control: str) -> None:
    assert normalize_text(f"fin de pagina{control}inicio") == "fin de pagina\ninicio"


@pytest.mark.parametrize("space", UNICODE_SPACES)
def test_unicode_spaces_become_plain_spaces(space: str) -> None:
    assert normalize_text(f"uno{space}dos") == "uno dos"


def test_line_breaks_and_tabs_are_kept() -> None:
    assert normalize_text("a\tb\nc\n\nd") == "a\tb\nc\n\nd"


def test_lone_surrogates_are_removed_so_the_text_can_be_stored() -> None:
    cleaned = normalize_text("ok\ud800 fin")

    assert cleaned == "ok fin"
    cleaned.encode("utf-8")  # raises UnicodeEncodeError if a surrogate survived


def test_ordinary_text_is_unchanged_apart_from_the_outer_whitespace() -> None:
    text = "Ñandú, niño y corazón: ¿qué pasó? 日本語 العربية 😀 é"

    assert normalize_text(f"  {text}\n") == text


def test_zero_width_joiner_sequences_of_emoji_are_kept() -> None:
    family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"

    assert normalize_text(f"hola {family}") == f"hola {family}"


# --- cases of TD-027 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blank",
    [
        "\u00a0",
        "\u00a0\u00a0\u00a0",
        "\x85",
        "\x85\u00a0\x85",
        "\u2028\u2029",
        "\u200b",
        "\u200b\u200c\u200d\u2060\ufeff",
        "\u202e\u202c",
        "\x00\x01\x02",
        " \t\n ",
        "\u3000\u2003",
        "",
    ],
)
def test_text_without_a_visible_character_normalises_to_nothing(blank: str) -> None:
    assert normalize_text(blank) == ""
    assert not has_visible_text(blank)


@pytest.mark.parametrize("text", ["a", "\u00a0a\u00a0", "\u200ba", "1", "。", "😀", "́a"])
def test_a_single_visible_character_is_enough(text: str) -> None:
    assert has_visible_text(text)
    assert normalize_text(text) != ""


def test_a_combining_mark_alone_is_not_visible() -> None:
    assert not has_visible_text("́̂")


def test_normalising_twice_changes_nothing() -> None:
    messy = "A\x00\u00a0B\u2028C\u202eD\ud800\x0c\x85  \t "

    once = normalize_text(messy)

    assert normalize_text(once) == once


def test_the_result_is_always_storable_as_chunk_content() -> None:
    """What the database stores must be encodable and never blank-looking (TD-027)."""
    samples = ["\u00a0", "\x85", "a\ud800b", "\x00", "texto\u2029", "\u200b"]

    for sample in samples:
        cleaned = normalize_text(sample)
        cleaned.encode("utf-8")
        assert cleaned == "" or has_visible_text(cleaned)
