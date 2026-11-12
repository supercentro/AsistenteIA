"""H9: throw-away ASGI app with the upload guard of design A8 (not the project code)."""
import asyncio
import os
import time

from fastapi import Depends, FastAPI, Header, Request
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

MAX_BYTES = int(os.environ.get("MAX_BYTES", 10 * 1024 * 1024))
OVERHEAD = 64 * 1024
BODY_DEADLINE = float(os.environ.get("BODY_DEADLINE", 5))
IDLE_GAP = float(os.environ.get("IDLE_GAP", 3))
STATE: dict[str, float] = {}

app = FastAPI()


async def respond(send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class UploadGuard:
    """Counts the bytes really received, enforces a total deadline and an idle gap, answers 413 / 408 itself."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/upload"):
            return await self.inner(scope, receive, send)
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BYTES + OVERHEAD:
            return await respond(send, 413, b'{"code":"FILE_TOO_LARGE"}')
        state = {"received": 0, "responded": False}
        started = time.monotonic()

        async def guarded_receive():
            if state["responded"]:
                return {"type": "http.disconnect"}
            remaining = BODY_DEADLINE - (time.monotonic() - started)
            try:
                if remaining <= 0:
                    raise asyncio.TimeoutError
                message = await asyncio.wait_for(receive(), timeout=min(IDLE_GAP, remaining))
            except asyncio.TimeoutError:
                state["responded"] = True
                await respond(send, 408, b'{"code":"REQUEST_TIMEOUT"}')
                return {"type": "http.disconnect"}
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > MAX_BYTES + OVERHEAD:
                    state["responded"] = True
                    await respond(send, 413, b'{"code":"FILE_TOO_LARGE"}')
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not state["responded"]:
                await send(message)

        try:
            await self.inner(scope, guarded_receive, guarded_send)
        except ClientDisconnect:
            pass  # the client left, or the guard already answered: nothing else to send


def rss_mb(key: str = "VmRSS") -> float:
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith(key):
                return int(line.split()[1]) / 1024
    return -1.0


@app.get("/ping")
async def ping():
    return {"ok": True}


@app.get("/rss")
async def rss():
    return {"rss_mb": rss_mb(), "hwm_mb": rss_mb("VmHWM"), "tmp_files": len(os.listdir("/tmp"))}


@app.post("/upload")
async def upload(request: Request, authorization: str | None = Header(None)):
    if authorization != "Bearer ok":
        return JSONResponse({"code": "UNAUTHORIZED"}, status_code=401)  # decided before the body is read
    form = await request.form(max_files=1, max_fields=2)
    item = form.get("file")
    if item is None or not hasattr(item, "read"):
        await form.close()
        return JSONResponse({"code": "VALIDATION_ERROR"}, status_code=422)
    data = await item.read()
    await form.close()
    return JSONResponse({"size": len(data)}, status_code=202)


def get_db_like():
    """Mirrors get_db: a sync generator dependency whose exit does work (a commit)."""
    yield "session"
    time.sleep(1.0)
    STATE["teardown_done"] = time.time()


@app.get("/order")
def order(_session: str = Depends(get_db_like)):
    STATE["handler_returned"] = time.time()
    return {"handler_returned": STATE["handler_returned"]}


@app.get("/state")
async def state():
    return STATE


app = UploadGuard(app)  # outermost, as in the design
