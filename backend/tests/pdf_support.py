"""Generated PDF fixtures for the loader tests (change 6, group 6).

Every file is built here from bytes: no binary fixture is committed and nothing is downloaded.
The helpers produce small, valid PDFs and a few hostile shapes used to check the limits of the
isolated PDF child. Text is written with the standard Helvetica font, so only Latin-1 text can be
placed in a page (enough to check page numbers, limits and leak markers).
"""

import io
import zlib


def _escape(text: str) -> bytes:
    raw = text.encode("latin-1")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def text_stream(lines: list[str], *, size: int = 12, leading: int = 14) -> bytes:
    """A content stream that shows `lines`, one under the other."""
    parts = [b"BT /F1 %d Tf %d TL 40 760 Td" % (size, leading)]
    for line in lines:
        parts.append(b"(" + _escape(line) + b") '")
    parts.append(b"ET")
    return b"\n".join(parts)


def assemble(
    objects: dict[int, bytes],
    *,
    root: int = 1,
    trailer_extra: bytes = b"",
) -> bytes:
    """Write numbered objects (`{n: body}`) with a classic cross-reference table."""
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = out.tell()
        out.write(b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n")
    size = max(objects) + 1
    xref_at = out.tell()
    out.write(b"xref\n0 %d\n" % size)
    out.write(b"0000000000 65535 f \n")
    for number in range(1, size):
        if number in offsets:
            out.write(b"%010d 00000 n \n" % offsets[number])
        else:
            out.write(b"0000000000 65535 f \n")
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R %s >>\nstartxref\n%d\n%%%%EOF\n"
        % (size, root, trailer_extra, xref_at)
    )
    return out.getvalue()


def stream_object(data: bytes, *, extra: bytes = b"") -> bytes:
    return b"<< /Length %d %s >>\nstream\n" % (len(data), extra) + data + b"\nendstream"


def pdf_from_streams(
    streams: list[bytes],
    *,
    stream_extra: bytes = b"",
    catalog_extra: bytes = b"",
    page_extra: bytes = b"",
) -> bytes:
    """A PDF with one page per content stream (`streams`), all using Helvetica as /F1."""
    count = len(streams)
    page_numbers = [4 + 2 * index for index in range(count)]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R %s >>" % catalog_extra,
        2: b"<< /Type /Pages /Kids [%s] /Count %d >>"
        % (b" ".join(b"%d 0 R" % number for number in page_numbers), count),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, data in enumerate(streams):
        page = page_numbers[index]
        objects[page] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R %s >>" % (page + 1, page_extra)
        )
        objects[page + 1] = stream_object(data, extra=stream_extra)
    return assemble(objects)


def pdf_with_pages(pages: list[str]) -> bytes:
    """A PDF with one line of text per page."""
    return pdf_from_streams([text_stream([text]) for text in pages])


def pdf_without_text(page_count: int = 1) -> bytes:
    """Pages that draw a rectangle and no text (what a scan looks like to a text extractor)."""
    return pdf_from_streams([b"0 0 100 100 re f" for _ in range(page_count)])


def pdf_many_pages(page_count: int) -> bytes:
    """A PDF with many tiny pages that share one content stream (small file, many pages)."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: stream_object(text_stream(["page"])),
    }
    kids = []
    for index in range(page_count):
        number = 5 + index
        kids.append(b"%d 0 R" % number)
        objects[number] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>"
        )
    objects[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), page_count)
    return assemble(objects)


def pdf_many_text_lines(line_count: int) -> bytes:
    """A small file with one page of `line_count` text lines: costly to extract, cheap to send."""
    parts = [b"BT /F1 6 Tf 7 TL 10 780 Td"]
    parts.extend(b"(line) '" for _ in range(line_count))
    parts.append(b"ET")
    return pdf_from_streams([b"\n".join(parts)])


def pdf_with_flate_stream(decompressed_size: int) -> bytes:
    """A page whose content stream inflates to `decompressed_size` bytes of spaces."""
    compressor = zlib.compressobj(9)
    chunk = b" " * (1 << 20)
    compressed = bytearray()
    remaining = decompressed_size
    while remaining > 0:
        piece = chunk[: min(len(chunk), remaining)]
        compressed += compressor.compress(piece)
        remaining -= len(piece)
    compressed += compressor.flush()
    return pdf_from_streams([bytes(compressed)], stream_extra=b"/Filter /FlateDecode")


def truncated(pdf: bytes, keep: float = 0.5) -> bytes:
    return pdf[: int(len(pdf) * keep)]


def pdf_with_xfa() -> bytes:
    """A catalog with an AcroForm that carries an /XFA array (an advisory of recent pypdf)."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] /XFA [(template) 5 0 R] >> >>",
        2: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 3 0 R >> >> /Contents 6 0 R >>",
        5: stream_object(b"<xdp:xdp xmlns:xdp='http://ns.adobe.com/xdp/'></xdp:xdp>"),
        6: stream_object(text_stream(["form with xfa"])),
    }
    return assemble(objects)


def pdf_with_bad_jpeg() -> bytes:
    """A page with text and an image whose JPEG data is garbage (it must never be decoded)."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 5 0 R >> >> /Contents 6 0 R >>",
        5: stream_object(
            b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xc0\x00\x0b\x08\xff\xff\xff\xff\x01\x01\x11\x00",
            extra=b"/Type /XObject /Subtype /Image /Width 65535 /Height 65535 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode",
        ),
        6: stream_object(text_stream(["image page"]) + b"\nq 100 0 0 100 0 0 cm /Im1 Do Q"),
    }
    return assemble(objects)


def pdf_xref_stream_with_equal_offsets() -> bytes:
    """A cross-reference stream whose entries all point at the same offset (advisory shape)."""
    body = io.BytesIO()
    body.write(b"%PDF-1.5\n")
    first = body.tell()
    body.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    body.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    body.write(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>\nendobj\n")
    entries = b""
    for _ in range(4):
        entries += b"\x01" + first.to_bytes(2, "big") + b"\x00"
    xref_at = body.tell()
    body.write(
        b"4 0 obj\n<< /Type /XRef /Size 4 /W [1 2 1] /Root 1 0 R /Length %d >>\nstream\n"
        % len(entries)
        + entries
        + b"\nendstream\nendobj\n"
    )
    body.write(b"startxref\n%d\n%%%%EOF\n" % xref_at)
    return body.getvalue()


def encrypted_pdf(
    pages: list[str], *, user_password: str = "", algorithm: str = "RC4-128"
) -> bytes:
    """A PDF encrypted with pypdf (RC4 needs no extra package; AES needs `cryptography`)."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_with_pages(pages))))
    writer.encrypt(user_password=user_password, owner_password="owner-secret", algorithm=algorithm)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def pdf_with_metadata(marker: str, text: str) -> bytes:
    """A PDF whose document information and outline carry `marker` (it must never be returned)."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R /Outlines 7 0 R >>",
        2: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R /Annots [8 0 R] >>",
        5: stream_object(text_stream([text])),
        6: b"<< /Title (" + _escape(marker) + b") /Author (" + _escape(marker) + b") >>",
        7: b"<< /Type /Outlines /Count 0 /Title (" + _escape(marker) + b") >>",
        8: b"<< /Type /Annot /Subtype /Text /Rect [0 0 10 10] /Contents (" + _escape(marker) + b") >>",
    }
    return assemble(objects, trailer_extra=b"/Info 6 0 R")
