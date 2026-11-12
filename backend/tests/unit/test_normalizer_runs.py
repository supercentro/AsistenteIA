"""Long runs of characters with no content are bounded (second review, finding S-01).

Root cause: the normaliser kept zero-width, combining, format, private-use and whitespace characters
in any number, so one visible character followed by about 2,000,000 of them reached the chunker as
a single 2,000,000-character piece and cost 17 to 60 s of tokenizer work (on 2 CPUs) for one chunk.
The normaliser now keeps at most `MAX_NON_CONTENT_RUN` consecutive characters that carry no content
(whitespace, combining marks, format and other invisible characters, plus one separator if the
run had whitespace and none survived, so words never glue together); letters, digits,
punctuation and symbols are never touched, and every sequence used by real scripts is far
below the limit.
"""

import time

import pytest

from app.rag.normalizer import MAX_NON_CONTENT_RUN, normalize_text

HOSTILE_PADDING = [
    pytest.param(" ", id="space"),
    pytest.param("\t", id="tab"),
    pytest.param("\n", id="newline"),
    pytest.param("\u00a0", id="no-break space"),
    pytest.param("\u3000", id="ideographic space"),
    pytest.param("\u200b", id="zero width space"),
    pytest.param("\u200c", id="zero width non-joiner"),
    pytest.param("\u200d", id="zero width joiner"),
    pytest.param("\u2060", id="word joiner"),
    pytest.param("\ufeff", id="byte order mark"),
    pytest.param("\u00ad", id="soft hyphen"),
    pytest.param("\u0301", id="combining acute accent"),
    pytest.param("\ufe0f", id="variation selector"),
    pytest.param("\ue000", id="private use"),
    pytest.param("\U000e0020", id="tag space"),
    pytest.param("\u0378", id="unassigned"),
]


@pytest.mark.parametrize("padding", HOSTILE_PADDING)
def test_a_visible_character_followed_by_two_million_padding_characters_stays_small(
    padding: str,
) -> None:
    started = time.perf_counter()

    result = normalize_text("x" + padding * 1_999_999 + "y")

    assert result.startswith("x")
    assert result.endswith("y")
    assert len(result) <= 2 + MAX_NON_CONTENT_RUN + 1  # the run, plus one separator
    assert time.perf_counter() - started < 5  # a linear pass, not a blow-up


def test_the_case_of_the_review_one_visible_character_and_two_million_zero_width_spaces() -> None:
    result = normalize_text("x" + "\u200b" * 1_999_999)

    assert result == "x" + "\u200b" * MAX_NON_CONTENT_RUN


def test_alternating_kinds_of_padding_count_as_one_run() -> None:
    result = normalize_text("x" + " \u200b\u0301\n" * 500_000 + "y")

    assert len(result) <= 2 + MAX_NON_CONTENT_RUN + 1  # the run, plus one separator


def test_a_run_ends_at_the_next_character_with_content() -> None:
    result = normalize_text("a" + " " * 100 + "b" + "\u200b" * 100 + "c")

    assert result == "a" + " " * MAX_NON_CONTENT_RUN + "b" + "\u200b" * MAX_NON_CONTENT_RUN + "c"


def test_the_limit_is_exactly_the_constant() -> None:
    at_limit = "a" + "\u0301" * MAX_NON_CONTENT_RUN + "b"
    over_limit = "a" + "\u0301" * (MAX_NON_CONTENT_RUN + 1) + "b"

    assert normalize_text(at_limit) == at_limit
    assert normalize_text(over_limit) == at_limit


def test_hostile_text_is_still_normalised_once_and_for_all() -> None:
    hostile = "x" + "\u200b \u0301\n" * 10_000 + "y"

    once = normalize_text(hostile)

    assert normalize_text(once) == once


# --- nothing meaningful is lost ----------------------------------------------------------------

LEGITIMATE = [
    pytest.param("La niña comió ñoquis y bebió té con azúcar. ¿Qué tal?", id="spanish"),
    pytest.param("Ünïcödé — « français » naïve café", id="latin accents"),
    pytest.param("Tie\u0302\u0301ng Vi\u0323\u0302\u0301t", id="vietnamese decomposed"),
    pytest.param("م\u064eر\u0652ح\u064eب\u064bا ب\u0650ك", id="arabic vowels"),
    pytest.param("ב\u05b0\u05bcר\u05b5אש\u05c1\u05b4ית", id="hebrew niqqud"),
    pytest.param("می\u200cخواهم کتاب\u200cها", id="persian zwnj"),
    pytest.param("क\u094d\u200dष स\u094d\u200cत", id="devanagari joiners"),
    pytest.param("สว\u0e31สด\u0e35\u200bคร\u0e31บ", id="thai zero width space"),
    pytest.param(
        "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 familia",
        id="emoji family",
    ),
    pytest.param(
        "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
        id="tag flag",
    ),
    pytest.param("\u2764\ufe0f \U0001f44d\U0001f3fd", id="emoji variation and skin tone"),
    pytest.param("日本語のテキスト、中文文本，한국어 텍스트", id="cjk"),
    pytest.param("def f(x):\n        return x  # 8 spaces of indentation", id="indentation"),
    pytest.param("Primer párrafo.\n\nSegundo párrafo.\n\n\nTercero.", id="paragraphs"),
    pytest.param("a" + "\u0301" * 10 + "b", id="a stack of ten marks"),
]


@pytest.mark.parametrize("text", LEGITIMATE)
def test_real_text_is_returned_unchanged(text: str) -> None:
    assert normalize_text(text) == text


def test_every_visible_character_survives_in_order() -> None:
    text = "".join(f"w{number}" + "\u200b" * 40 + " " * 40 for number in range(500))

    result = normalize_text(text)

    assert [part for part in result.replace("\u200b", " ").split() if part] == [
        f"w{number}" for number in range(500)
    ]


def test_cutting_a_run_never_glues_two_words_together() -> None:
    result = normalize_text("alfa" + chr(0x200B) * 50 + " beta")

    assert result.startswith("alfa")
    assert result.endswith(" beta")
    assert result.count(" ") == 1


def test_a_newline_that_would_be_cut_still_separates_the_lines() -> None:
    result = normalize_text("alfa" + chr(0x0301) * 50 + chr(10) + "beta")

    assert result.endswith(chr(10) + "beta")


def test_characters_removed_by_the_cleaning_do_not_break_a_run() -> None:
    # NUL, controls and bidirectional marks are removed first; they must not reset the count.
    padding = chr(0x0301) + chr(0) + chr(0x202E) + chr(0x0085 + 0)
    result = normalize_text("x" + padding * 100_000 + "y")

    assert len(result) <= 2 + MAX_NON_CONTENT_RUN + 1


def test_the_limit_is_sixteen_not_a_value_defined_by_the_constant_alone() -> None:
    # Third review T-04: the other tests compare with the constant, so pin its value here.
    assert MAX_NON_CONTENT_RUN == 16
    zero_width = chr(0x200B)
    assert normalize_text("a" + zero_width * 16 + "b") == "a" + zero_width * 16 + "b"
    assert normalize_text("a" + zero_width * 17 + "b") == "a" + zero_width * 16 + "b"


@pytest.mark.parametrize(
    "character",
    [
        pytest.param(".", id="full stop"),
        pytest.param("-", id="hyphen"),
        pytest.param("$", id="currency symbol"),
        pytest.param(chr(0x2014), id="em dash"),
        pytest.param(chr(0x1F600), id="emoji"),
        pytest.param(chr(0x2581), id="block element"),
        pytest.param(chr(0xFFFD), id="replacement character"),
    ],
)
def test_runs_of_punctuation_and_symbols_are_never_touched(character: str) -> None:
    # They carry content (the documentation says so); the cost of such runs is the accepted
    # residual of TD-034, not something the normaliser cuts.
    text = "a" + character * 100 + "b"

    assert normalize_text(text) == text
