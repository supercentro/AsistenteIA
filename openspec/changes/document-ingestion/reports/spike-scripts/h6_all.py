"""H6: generate hostile PDFs and run each through the child under limits (run inside a limited container)."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import zlib

OUT = "/tmp/pdfs"
os.makedirs(OUT, exist_ok=True)


def esc(text: str) -> bytes:
    return text.encode("latin-1", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def assemble(objects: list[bytes], root: int = 1, extra_trailer: bytes = b"") -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R %s>>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, root, extra_trailer, start)
    return bytes(out)


def stream(data: bytes, flate: bool = False, extra: bytes = b"") -> bytes:
    if flate:
        data = zlib.compress(data, 9)
        return b"<< /Length %d /Filter /FlateDecode %s>>\nstream\n" % (len(data), extra) + data + b"\nendstream"
    return b"<< /Length %d %s>>\nstream\n" % (len(data), extra) + data + b"\nendstream"


def text_content(lines: list[str]) -> bytes:
    body = bytearray(b"BT /F1 11 Tf 40 760 Td 13 TL\n")
    for line in lines:
        body += b"(" + esc(line) + b") Tj T*\n"
    body += b"ET"
    return bytes(body)


def pdf_from_pages(contents: list[bytes], flate: bool = False) -> bytes:
    n = len(contents)
    kids = b" ".join(b"%d 0 R" % (4 + 2 * i) for i in range(n))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, content in enumerate(contents):
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R /Resources << /Font << /F1 3 0 R >> >> >>" % (5 + 2 * i))
        objects.append(stream(content, flate))
    return assemble(objects)


def sentence(i: int) -> str:
    return f"Página {i}: la matriz de confusión cruza las clases reales con las predichas y resume los aciertos."


fixtures: dict[str, bytes] = {}
fixtures["valid_3_pages"] = pdf_from_pages([text_content([sentence(i)] * 5) for i in range(3)])
fixtures["scanned_no_text"] = pdf_from_pages([b"q 612 0 0 792 0 0 cm Q" for _ in range(3)])
valid = fixtures["valid_3_pages"]
fixtures["truncated"] = valid[: int(len(valid) * 0.6)]
broken = bytearray(valid)
broken[broken.rfind(b"startxref") + 10: broken.rfind(b"startxref") + 14] = b"9999"
fixtures["bad_startxref"] = bytes(broken)
fixtures["garbage"] = b"%PDF-1.4\n" + os.urandom(20000)
fixtures["pages_300"] = pdf_from_pages([text_content([sentence(i)]) for i in range(300)], flate=True)
fixtures["pages_301"] = pdf_from_pages([text_content([sentence(i)]) for i in range(301)], flate=True)
fixtures["pages_5000_empty"] = pdf_from_pages([b"" for _ in range(5000)], flate=True)
# decompression bombs (compressed stream expands to hundreds of MB / 2 GB of zeros)
for label, mb in (("bomb_200mb", 200), ("bomb_2gb", 2048)):
    comp = zlib.compressobj(9)
    chunks = []
    block = b"0 " * 524288  # 1 MiB of harmless operands
    for _ in range(mb):
        chunks.append(comp.compress(block))
    chunks.append(comp.flush())
    data = b"".join(chunks)
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 3 0 R >> >> >>",
               b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream"]
    fixtures[label] = assemble(objects)
# page tree loop (Kids points to itself) and parent loop
fixtures["page_tree_loop"] = assemble([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [2 0 R] /Count 1 >>"])
fixtures["page_tree_deep"] = assemble([b"<< /Type /Catalog /Pages 2 0 R >>"] + [b"<< /Type /Pages /Kids [%d 0 R] /Count 1 /Parent %d 0 R >>" % (i + 1, i - 1) for i in range(2, 4000)] + [b"<< /Type /Pages /Kids [] /Count 0 >>"])
# a very large single page of text (about 6 MB of text drawn operators, compressed)
fixtures["huge_page_ops"] = pdf_from_pages([text_content([sentence(i) for i in range(60000)])], flate=True)
# 10 MB of extractable text over 40 pages
fixtures["text_10mb"] = pdf_from_pages([text_content([sentence(i) * 3 for i in range(900)]) for _ in range(40)], flate=True)
# many tiny objects
fixtures["objects_200k"] = assemble([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [] /Count 0 >>"] + [b"<< >>" for _ in range(200000)])
# encrypted
try:
    from pypdf import PdfReader, PdfWriter
    import io

    for label, user in (("encrypted_user_password", "secreto"), ("encrypted_empty_user_password", "")):
        reader = PdfReader(io.BytesIO(valid))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(user_password=user, owner_password="owner-pass", algorithm="RC4-128")
        buf = io.BytesIO()
        writer.write(buf)
        fixtures[label] = buf.getvalue()
except Exception as exc:  # noqa: BLE001
    print("encryption fixtures failed:", type(exc).__name__, exc)

# JavaScript / launch actions and embedded oddities: must simply yield text or an error
fixtures["with_openaction_js"] = assemble([b"<< /Type /Catalog /Pages 2 0 R /OpenAction << /S /JavaScript /JS (app.alert\\('x'\\)) >> >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                                           b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"])

for name, data in fixtures.items():
    with open(f"{OUT}/{name}.pdf", "wb") as handle:
        handle.write(data)


def run_child(path: str, timeout: float, env_extra: dict[str, str]) -> dict:
    data = open(path, "rb").read()
    env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/nonexistent", **env_extra}
    start = time.time()
    proc = subprocess.Popen([sys.executable, "-I", "/spike/pdf_child.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=env, close_fds=True)
    captured = bytearray()
    over = {"flag": False}
    cap = 8 * 1024 * 1024

    def feed():
        try:
            proc.stdin.write(data)
            proc.stdin.close()
        except OSError:
            pass

    def drain():
        while True:
            block = proc.stdout.read(65536)
            if not block:
                return
            if len(captured) + len(block) > cap:
                over["flag"] = True
                try:
                    os.kill(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return
            captured.extend(block)

    threading.Thread(target=feed, daemon=True).start()
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    killed = None
    status = None
    rusage = None
    while True:
        pid, st, ru = os.wait4(proc.pid, os.WNOHANG)
        if pid:
            status, rusage = st, ru
            break
        if time.time() - start > timeout:
            os.kill(proc.pid, signal.SIGKILL)
            killed = "wall-clock timeout"
            _, status, rusage = os.wait4(proc.pid, 0)
            break
        time.sleep(0.01)
    reader.join(2)
    elapsed = time.time() - start
    lines = []
    for l in captured.decode("utf-8", "replace").splitlines():
        if l.startswith("{"):
            try:
                lines.append(json.loads(l))
            except ValueError:
                pass  # last line cut by the stdout cap
    outcome = next((l for l in reversed(lines) if "error" in l or "done" in l), None)
    sig = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
    return {
        "elapsed": elapsed, "peak_mb": rusage.ru_maxrss / 1024, "cpu_s": rusage.ru_utime + rusage.ru_stime,
        "outcome": ("ok pages=%s chars=%s" % (outcome.get("pages"), outcome.get("chars"))) if outcome and "done" in outcome else (outcome or {}).get("error", "no result"),
        "killed": killed, "signal": sig, "stdout_over_cap": over["flag"], "out_bytes": len(captured),
    }


timeout = float(os.environ.get("H6_TIMEOUT", 30))
env_extra = {k: v for k, v in os.environ.items() if k.startswith("CHILD_")}
print(f"limits: wall {timeout}s, child env {env_extra}, container limits from docker run")
print(f"{'fixture':32}{'file KB':>9}{'wall s':>8}{'cpu s':>7}{'peak MB':>9}  outcome")
only = [x for x in os.environ.get("H6_ONLY", "").split(",") if x]
for name in fixtures:
    if only and name not in only:
        continue
    path = f"{OUT}/{name}.pdf"
    res = run_child(path, timeout, env_extra)
    note = ""
    if res["killed"]:
        note += f" KILLED({res['killed']})"
    if res["signal"]:
        note += f" signal={res['signal']}"
    if res["stdout_over_cap"]:
        note += " STDOUT-CAP"
    print(f"{name:32}{os.path.getsize(path) / 1024:9.0f}{res['elapsed']:8.2f}{res['cpu_s']:7.2f}{res['peak_mb']:9.0f}  {res['outcome']}{note}")
