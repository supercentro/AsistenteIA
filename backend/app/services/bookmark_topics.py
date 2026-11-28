"""Topics from the bookmarks of a PDF (change `frequent-questions-and-topics`, D8). Pure.

A bookmark title is untrusted text written by whoever made the file: it is cleaned, never refused,
and never logged or sent to a model. Pages are positions in the file.
"""

import unicodedata
from collections.abc import Sequence

from app.models.topic import TITLE_MAX_LENGTH
from app.rag.loaders import OutlineEntry
from app.schemas.validators import BIDI_CONTROLS, has_visible_character
from app.services.topic_rules import Topic

MIN_BOOKMARK_TOPICS = 2
_SPACED_CATEGORIES = frozenset({"Cc", "Zl", "Zp", "Zs"})


def clean_title(value: str) -> str:
    """One bounded line: controls become spaces, direction marks and surrogates are dropped.

    Empty when nothing visible is left.
    """
    kept = []
    for char in value:
        category = unicodedata.category(char)
        if char in BIDI_CONTROLS or category == "Cs":
            continue
        kept.append(" " if category in _SPACED_CATEGORIES else char)
    title = " ".join("".join(kept).split())[:TITLE_MAX_LENGTH].strip()
    return title if has_visible_character(title) else ""


def bookmark_topics(entries: Sequence[OutlineEntry], *, last_page: int) -> list[Topic]:
    """Each usable entry runs to the page before the next start; the last one to `last_page`.

    Entries with no title left or starting outside the pages with text are dropped; fewer than
    two usable entries give no topics at all.
    """
    usable = sorted(
        (
            (title, entry.page)
            for entry in entries
            if (title := clean_title(entry.title)) and 1 <= entry.page <= last_page
        ),
        key=lambda item: item[1],
    )
    if len(usable) < MIN_BOOKMARK_TOPICS:
        return []
    starts = sorted({page for _, page in usable})
    ends = {start: following - 1 for start, following in zip(starts, starts[1:], strict=False)}
    ends[starts[-1]] = last_page
    return [Topic(title=title, start_page=page, end_page=ends[page]) for title, page in usable]
