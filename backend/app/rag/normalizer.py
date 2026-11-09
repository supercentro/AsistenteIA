"""Normalisation of extracted text before it is chunked and stored (resolves TD-027).

PDF extraction and text files can carry characters that PostgreSQL cannot store (NUL, lone
surrogates), characters that make text look different from what it is (bidirectional controls) and
characters that look blank but are not whitespace for the database locale (no-break space, next
line). All of it is cleaned here, before it reaches the database. The function is idempotent and
never raises; the text is data and is neither logged nor interpreted.
"""

import unicodedata

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
    cleaned = "".join(_clean_character(character) for character in unified).strip()
    return cleaned if has_visible_text(cleaned) else ""
