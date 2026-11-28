"""The real PDF child reading bookmarks (change `frequent-questions-and-topics`, task 6.1).

Linux only, like the text extraction: the limits rely on `rlimit`. The files are generated here;
nothing is committed or downloaded.
"""

import io
import sys

import pytest

from app.models.ingestion import DocumentErrorCode
from app.rag.loaders import DocumentLoadError, OutlineEntry, PdfLimits, load_pdf, load_pdf_outline
from tests import pdf_support

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="the PDF child runs on Linux only")

LIMITS = PdfLimits(
    max_pages=300,
    max_chars=2_000_000,
    memory_mb=768,
    cpu_seconds=20,
    timeout_seconds=30,
    max_output_bytes=8 * 1024 * 1024,
)


def with_outline(entries: list[tuple[str, int]], *, root: str | None = None) -> bytes:
    """A six-page PDF whose bookmarks are `entries` (title, zero-based page)."""
    from pypdf import PdfReader, PdfWriter

    base = pdf_support.pdf_with_pages([f"page {n}" for n in range(1, 7)])
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(base)))
    parent = writer.add_outline_item(root, 0) if root else None
    for title, page in entries:
        writer.add_outline_item(title, page, parent=parent)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_the_bookmarks_and_their_pages_are_read() -> None:
    pdf = with_outline([("Modelo relacional", 0), ("Normalización", 3)])

    assert load_pdf_outline(pdf, LIMITS) == [
        OutlineEntry("Modelo relacional", 1),
        OutlineEntry("Normalización", 4),
    ]
    assert len(load_pdf(pdf, LIMITS)) == 6  # the text is read as before


def test_a_single_root_gives_its_children() -> None:
    pdf = with_outline([("Uno", 1), ("Dos", 2)], root="Libro")

    assert [e.title for e in load_pdf_outline(pdf, LIMITS)] == ["Uno", "Dos"]


def test_a_file_without_bookmarks_gives_none() -> None:
    assert load_pdf_outline(pdf_support.pdf_with_pages(["only text"]), LIMITS) == []


def test_more_than_a_hundred_bookmarks_give_none() -> None:
    pdf = with_outline([(f"T{n}", n % 6) for n in range(101)])

    assert load_pdf_outline(pdf, LIMITS) == []


def test_hostile_titles_arrive_bounded() -> None:
    pdf = with_outline([("x" * 100_000, 0), ('<script>"\n{"end": true}', 1)])

    found = load_pdf_outline(pdf, LIMITS)

    assert len(found[0].title) == 1000 and found[1].title.startswith("<script>")


def test_a_cyclic_outline_ends() -> None:
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /Outlines 5 0 R >>",
        2: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",
        5: b"<< /Type /Outlines /First 6 0 R /Last 7 0 R >>",
        6: b"<< /Title (A) /Parent 5 0 R /Dest [4 0 R /Fit] /Next 7 0 R >>",
        7: b"<< /Title (B) /Parent 5 0 R /Dest [4 0 R /Fit] /Next 6 0 R >>",
    }

    try:
        found = load_pdf_outline(pdf_support.assemble(objects), LIMITS)
    except DocumentLoadError:
        return  # refused: also a valid end
    assert [e.title for e in found] == ["A", "B"]


def test_an_encrypted_file_is_refused() -> None:
    with pytest.raises(DocumentLoadError) as refused:
        load_pdf_outline(pdf_support.encrypted_pdf(["secret"]), LIMITS)

    assert refused.value.code is DocumentErrorCode.ENCRYPTED_PDF


def test_a_timeout_is_reported_and_not_hung() -> None:
    limits = PdfLimits(300, 2_000_000, 768, 20, 0, 8 * 1024 * 1024)

    with pytest.raises(DocumentLoadError):
        load_pdf_outline(with_outline([("A", 0), ("B", 1)]), limits)


def test_a_child_that_runs_out_of_memory_is_reported() -> None:
    limits = PdfLimits(300, 2_000_000, 20, 20, 30, 8 * 1024 * 1024)

    with pytest.raises(DocumentLoadError):
        load_pdf_outline(with_outline([("A", 0), ("B", 1)]), limits)
