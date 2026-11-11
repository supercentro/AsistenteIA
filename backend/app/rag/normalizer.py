"""Normalisation of extracted text before it is chunked and stored (resolves TD-027).

PDF extraction and text files can carry characters that PostgreSQL cannot store (NUL, lone
surrogates), characters that make text look different from what it is (bidirectional controls) and
characters that look blank but are not whitespace for the database locale (no-break space, next
line). All of it is cleaned here, before it reaches the database. The function is idempotent and
never raises; the text is data and is neither logged nor interpreted.

It also bounds the cost of what follows (second review, finding S-01). Whitespace, combining marks,
zero-width and other format characters, private-use and unassigned code points carry no content, yet
a file of one visible character and two million of them used to reach the chunker as one
2,000,000-character piece that cost 17 to 60 s of tokenizer work. At most `MAX_NON_CONTENT_RUN`
consecutive characters of that kind are kept (plus one separator when the run had whitespace and
none survived, so words never glue together). Letters, digits, punctuation and symbols are never
touched.
"""

import unicodedata
from collections.abc import Iterable

# Bidirectional formatting characters: they can reorder what a reader sees (CVE-style spoofing).
_BIDI_CONTROLS = frozenset(
    chr(code)
    for code in (
        0x061C,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
    )
)
# Characters that start a new line: the Unicode line and paragraph separators, the C1 "next line",
# and the vertical tab and form feed that PDF extractors emit at layout breaks.
_LINE_BREAKS = frozenset(chr(code) for code in (0x2028, 0x2029, 0x85, 0x0B, 0x0C))
_KEPT_CONTROLS = frozenset("\n\t")
# The longest real sequences (a base letter with ten stacked marks, an emoji tag flag of seven tag
# characters, indentation plus blank lines) stay well below this.
MAX_NON_CONTENT_RUN = 16
_WHITESPACE = frozenset(" \n\t")


def _clean_character(character: str) -> str:
    if character in _KEPT_CONTROLS:
        return character
    if character in _LINE_BREAKS:
        return "\n"
    if character in _BIDI_CONTROLS:
        return ""
    category = unicodedata.category(character)
    if category == "Zs":  # no-break space, em space, ideographic space, ...
        return " "
    if category in ("Cc", "Cs"):  # NUL, other C0 and C1 controls, DEL, lone surrogates
        return ""
    return character


def has_visible_text(text: str) -> bool:
    """True if the text has a character a reader can see.

    Spaces (Z), controls and format characters such as zero width or bidirectional marks (C) and
    combining marks on their own (M) are not visible, so text made only of them counts as blank.
    """
    return any(unicodedata.category(character)[0] not in "ZCM" for character in text)


def normalize_text(text: str) -> str:
    """Return the cleaned text, or an empty string when nothing visible remains.

    - carriage returns become line feeds; line and paragraph separators, "next line", vertical tab
      and form feed become line feeds;
    - NUL and every other C0 or C1 control (except line feed and tab), DEL and lone surrogates are
      removed; bidirectional controls are removed;
    - Unicode space characters (no-break, em, ideographic, ...) become plain spaces;
    - line feeds and tabs are kept; other format characters (for example the zero width joiner of
      emoji sequences) are kept but never count as visible text;
    - surrounding whitespace is trimmed, and text without a visible character becomes "".
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _limit_runs(_clean_character(character) for character in unified).strip()
    return cleaned if has_visible_text(cleaned) else ""


def _has_content(character: str) -> bool:
    """False for whitespace and for marks, format, private-use and unassigned characters."""
    if character.isalnum():
        return True
    return character not in _WHITESPACE and unicodedata.category(character)[0] not in "ZMC"


def _limit_runs(characters: Iterable[str]) -> str:
    """Keep at most `MAX_NON_CONTENT_RUN` consecutive characters without content."""
    kept: list[str] = []
    run = 0
    whitespace_kept = False
    separator: str | None = None  # the first whitespace dropped from a run that kept none
    for character in characters:
        if not character:  # removed by the cleaning
            continue
        if _has_content(character):
            if separator is not None and not whitespace_kept:
                kept.append(separator)
            kept.append(character)
            run, whitespace_kept, separator = 0, False, None
            continue
        run += 1
        if run <= MAX_NON_CONTENT_RUN:
            kept.append(character)
            whitespace_kept = whitespace_kept or character in _WHITESPACE
        elif separator is None and not whitespace_kept and character in _WHITESPACE:
            separator = character
    # A separator still pending here would end the text; the caller strips it anyway.
    return "".join(kept)
