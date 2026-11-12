"""H9 client: raw sockets against the throw-away server (127.0.0.1:18765 inside the container)."""
import json
import os
import socket
import threading
import time
import urllib.request

HOST, PORT = "127.0.0.1", 18765
BOUNDARY = "----f6spike"
FILE_PREFIX = b"--" + BOUNDARY.encode() + b"\r\n" + b'Content-Disposition: form-data; name="file"; filename="a.pdf"' + b"\r\n\r\n"


def multipart(parts: list[tuple[str, str | None, bytes]], preamble: bytes = b"") -> bytes:
    body = bytearray(preamble)
    for name, filename, data in parts:
        body += f"--{BOUNDARY}\r\n".encode()
        disp = f'Content-Disposition: form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        body += disp.encode() + b"\r\n"
        if filename:
            body += b"Content-Type: application/pdf\r\n"
        body += b"\r\n" + data + b"\r\n"
    body += f"--{BOUNDARY}--\r\n".encode()
    return bytes(body)


def head(method: str, path: str, extra: list[str]) -> bytes:
    lines = [f"{method} {path} HTTP/1.1", f"Host: {HOST}:{PORT}", "Authorization: Bearer ok",
             f"Content-Type: multipart/form-data; boundary={BOUNDARY}"] + extra
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def read_status(sock: socket.socket, wait: float = 15.0) -> str:
    sock.settimeout(wait)
    data = b""
    try:
        while b"\r\n" not in data:
            block = sock.recv(4096)
            if not block:
                break
            data += block
    except (socket.timeout, ConnectionResetError, OSError) as exc:
        return f"<{type(exc).__name__}> {data[:40]!r}"
    return data.split(b"\r\n")[0].decode("latin-1") if data else "<closed without response>"


def connect() -> socket.socket:
    s = socket.create_connection((HOST, PORT), timeout=10)
    return s


def get(path: str) -> dict:
    with urllib.request.urlopen(f"http://{HOST}:{PORT}{path}", timeout=10) as r:
        return json.loads(r.read())


def tmp_count() -> int:
    return len(os.listdir("/tmp"))


results: list[tuple[str, str]] = []


def record(name: str, outcome: str) -> None:
    results.append((name, outcome))
    print(f"{name:58} {outcome}", flush=True)


# T1 valid small upload
body = multipart([("file", "a.pdf", b"%PDF-1.4 small")])
s = connect(); s.sendall(head("POST", "/upload", [f"Content-Length: {len(body)}"]) + body)
record("T1 valid small upload", read_status(s)); s.close()

# T1b no credentials: 401 decided before the body is read (send only headers, huge declared length)
s = connect(); s.sendall(("POST /upload HTTP/1.1\r\nHost: x\r\nContent-Length: 1000\r\nContent-Type: multipart/form-data; boundary=x\r\n\r\n").encode())
record("T1b no Authorization, body never sent", read_status(s, 5)); s.close()

# T2 declared length above the limit, no body sent
t = time.time(); s = connect(); s.sendall(head("POST", "/upload", ["Content-Length: 52428800"]))
status = read_status(s, 10); record("T2 Content-Length 50 MB, no body sent", f"{status} after {time.time() - t:.2f} s"); s.close()

# T3 chunked 30 MB, no Content-Length
s = connect(); s.sendall(head("POST", "/upload", ["Transfer-Encoding: chunked"]))
t = time.time(); sent = 0; err = None
chunk = os.urandom(65536)
try:
    prelude = FILE_PREFIX
    s.sendall(f"{len(prelude):x}\r\n".encode() + prelude + b"\r\n")
    for _ in range(480):
        s.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n"); sent += len(chunk)
except OSError as exc:
    err = type(exc).__name__
record("T3 chunked 30 MB: client stopped after", f"{sent / 1048576:.1f} MB, error={err}, first line: {read_status(s, 5)}"); s.close()

# T4 lying Content-Length: declares 200 bytes, sends 20 MB
s = connect()
payload = b"x" * 20_000_000
try:
    s.sendall(head("POST", "/upload", ["Content-Length: 200"]) + payload[:200]); s.sendall(payload[200:])
    outcome = read_status(s, 10)
except OSError as exc:
    outcome = f"send error {type(exc).__name__}"
record("T4 declared 200 bytes, sent 20 MB", outcome); s.close()

# T5 stalled: declares 50 KB, sends 1 KB, then silence
s = connect(); s.sendall(head("POST", "/upload", ["Content-Length: 50000"]) + FILE_PREFIX + b"a" * 500)
t = time.time(); status = read_status(s, 15)
record("T5 stalled connected client (deadline 5 s, idle gap 3 s)", f"{status} after {time.time() - t:.1f} s"); s.close()

# T6 slow drip: 1 byte per second keeps the idle gap alive, the total deadline must still apply
s = connect(); s.sendall(head("POST", "/upload", ["Content-Length: 100000"]) + FILE_PREFIX)
t = time.time(); status = None
s.settimeout(0.5)
for _ in range(12):
    try:
        s.sendall(b"a")
    except OSError:
        break
    try:
        data = s.recv(100)
        if data:
            status = data.split(b"\r\n")[0].decode("latin-1"); break
    except socket.timeout:
        pass
    time.sleep(0.5)
record("T6 slow drip 1 byte / 1 s", f"{status} after {time.time() - t:.1f} s"); s.close()

# T7 client disconnects mid-body; temporary files and health afterwards
before = tmp_count(); body = multipart([("file", "half.pdf", os.urandom(5_000_000))])
s = connect(); s.sendall(head("POST", "/upload", [f"Content-Length: {len(body)}"]) + body[:3_000_000]); time.sleep(0.5); s.close()
time.sleep(1.5)
record("T7 disconnect after 3 of 5 MB", f"tmp files before {before}, after {tmp_count()}, server answers: {get('/ping')}")

# T8 multipart structure abuse, all below the byte limit
def post(body: bytes, label: str) -> None:
    s = connect(); t = time.time()
    try:
        s.sendall(head("POST", "/upload", [f"Content-Length: {len(body)}"]) + body)
        outcome = read_status(s, 60)
    except OSError as exc:
        outcome = f"send error {type(exc).__name__}"
    record(label, f"{outcome} in {time.time() - t:.2f} s"); s.close()

post(multipart([("f%d" % i, None, b"v") for i in range(5000)] + [("file", "a.pdf", b"%PDF")]), "T8a 5000 form fields")
post(multipart([("file", "f%d.pdf" % i, b"x") for i in range(3000)]), "T8b 3000 file parts")
big_header = b"X-Junk: " + b"j" * 9_000_000 + b"\r\n"
raw = f"--{BOUNDARY}\r\n".encode() + b'Content-Disposition: form-data; name="file"; filename="a.pdf"\r\n' + big_header + b"\r\nDATA\r\n" + f"--{BOUNDARY}--\r\n".encode()
post(raw, "T8c one 9 MB part header")
post(multipart([("file", "a.pdf", b"%PDF")], preamble=b"p" * 9_500_000), "T8d 9.5 MB preamble")
post(multipart([("file", "a.pdf", b"%PDF"), ("file", "b.pdf", b"%PDF")]), "T8e two file parts")
post(multipart([("other", None, b"x")]), "T8f no file part")
post(multipart([("file", "empty.pdf", b"")]), "T8g empty file part")

# T9 exactly at the limit and 10 MB upload memory
before_rss = get("/rss")
data = os.urandom(10 * 1024 * 1024)
body = multipart([("file", "ten.pdf", data)])
s = connect(); s.sendall(head("POST", "/upload", [f"Content-Length: {len(body)}"]) + body)
status = read_status(s, 30); s.close(); after_rss = get("/rss")
record("T9 10 MB file (at the limit)", f"{status}; server RSS {before_rss['rss_mb']:.0f} -> {after_rss['rss_mb']:.0f} MB, peak (VmHWM) {before_rss['hwm_mb']:.0f} -> {after_rss['hwm_mb']:.0f} MB; /tmp files {before_rss['tmp_files']} -> {after_rss['tmp_files']}")
data = os.urandom(10 * 1024 * 1024 + 70000)
body = multipart([("file", "over.pdf", data)])
s = connect(); s.sendall(head("POST", "/upload", [f"Content-Length: {len(body)}"]) + body[:200])
try:
    s.sendall(body[200:])
except OSError:
    pass
record("T9b 10 MB + 70 KB file (over the limit)", read_status(s, 30)); s.close()
record("T9c server RSS after the over-limit upload", f"{get('/rss')}")

# T10 order of the dependency exit and the response (D2)
t0 = time.time()
r = get("/order"); elapsed = time.time() - t0
time.sleep(1.5); state = get("/state")
record("T10 sync yield dependency whose exit takes 1 s", f"response received after {elapsed:.2f} s; teardown finished {state['teardown_done'] - t0:.2f} s after the request")

# T11 slow uploaders do not block other requests
holders = []
for _ in range(20):
    h = connect(); h.sendall(head("POST", "/upload", ["Content-Length: 100000"]) + FILE_PREFIX); holders.append(h)
t = time.time(); [get("/ping") for _ in range(20)]
record("T11 20 stalled uploads open, 20 pings", f"{(time.time() - t) / 20 * 1000:.1f} ms per ping")
time.sleep(6)
codes = [read_status(h, 2) for h in holders]
record("T11b the stalled uploads after the deadline", f"{sum(c.startswith('HTTP/1.1 408') for c in codes)} got 408 of 20; sample: {codes[0]!r}")
for h in holders:
    h.close()
print("DONE")
