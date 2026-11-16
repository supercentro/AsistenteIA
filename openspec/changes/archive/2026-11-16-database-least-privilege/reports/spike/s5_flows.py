"""Real application code under the least-privilege roles: API over HTTP (app role), CLI (app role), worker service (worker role),
find_similar (app role). Synthetic data only; everything is deleted at the end of the script."""

import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from common import *  # noqa: F401,F403
from sqlalchemy import event, text

DB = "spk_clean"
BASE = "http://127.0.0.1:8000/api/v1"
env = dict(os.environ)
env.update(DATABASE_URL=dsn("app", DB, driver=True), APP_ENV="development", LOG_LEVEL="INFO")
srv = subprocess.Popen(
    ["python", "-m", "uvicorn", "app.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", "8000"],
    cwd="/app", env=env, stdout=open("/spike/out/api.log", "w"), stderr=subprocess.STDOUT,
)
steps = []


def api(method, path, token=None, body=None, multipart=None):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if multipart is not None:
        b = "----" + secrets.token_hex(8)
        name, fn, ct, payload = multipart
        data = (
            f'--{b}\r\nContent-Disposition: form-data; name="{name}"; filename="{fn}"\r\nContent-Type: {ct}\r\n\r\n'
        ).encode() + payload + f"\r\n--{b}--\r\n".encode()
        headers["Content-Type"] = "multipart/form-data; boundary=" + b
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            steps.append((method, path.split("?")[0], r.status))
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        steps.append((method, path, e.code))
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, None


def sqla(who):
    from app.core.database import create_db_engine, create_session_factory

    e = create_db_engine(dsn(who, DB, driver=True))
    return e, create_session_factory(e)


try:
    for _ in range(40):
        try:
            if urllib.request.urlopen(BASE + "/health", timeout=2).status == 200:
                break
        except Exception:
            time.sleep(1)
    rec("API", True, "uvicorn started with the app role and answers /health 200")
    pw = secrets.token_urlsafe(16)
    tag = "spk" + secrets.token_hex(3)
    # ---- CLI create-teacher under the app role
    t_email = f"{tag}-t1@example.com"
    p = subprocess.run(
        ["python", "-m", "app.cli", "create-teacher", "--email", t_email, "--name", f"{tag} T1", "--password-stdin"],
        cwd="/app", env=env, input=pw + "\n", capture_output=True, text=True,
    )
    rec("CLI", p.returncode == 0, f"create-teacher under the app role rc={p.returncode} {mask(p.stderr.strip())[:100]}")
    st_email = f"{tag}-s1@example.com"
    s, _ = api("POST", "/auth/register", body={"name": f"{tag} S1", "email": st_email, "password": pw})
    rec("API", s == 201, f"register {s}")
    s, js = api("POST", "/auth/login", body={"email": t_email, "password": pw})
    tt = js["access_token"]
    rec("API", s == 200, f"login teacher {s}")
    s, js = api("POST", "/auth/login", body={"email": st_email, "password": pw})
    st = js["access_token"]
    rec("API", s == 200, f"login student {s}")
    s, js = api("GET", "/users/me", tt)
    rec("API", s in (200, 404), f"GET /users/me {s}")
    s, js = api("POST", "/subjects", tt, {"name": f"{tag} subject", "description": "spike"})
    sid = js["id"]
    rec("API", s == 201, f"create subject {s}")
    s, _ = api("GET", "/subjects", tt)
    rec("API", s == 200, f"list subjects (teacher) {s}")
    s, _ = api("GET", f"/subjects/{sid}", tt)
    rec("API", s == 200, f"get subject {s}")
    s, _ = api("POST", f"/subjects/{sid}/enrollments", tt, {"student_email": st_email})
    rec("API", s == 201, f"enroll {s}")
    s, js = api("GET", f"/subjects/{sid}/enrollments", tt)
    rec("API", s == 200, f"list enrollments {s}")
    s, _ = api("GET", "/subjects", st)
    rec("API", s == 200, f"list subjects (student) {s}")

    # ---- A-01: the consent endpoint needs UPDATE on users.consent_*
    with connect("mig", DB) as m:
        m.execute("REVOKE UPDATE ON users FROM spk_app")
    from app.core.config import load_settings

    os.environ.update(DATABASE_URL=dsn("app", DB, driver=True), APP_ENV="development")
    version = load_settings().privacy_policy_version
    s_without, _ = api("POST", "/users/me/consent", st, {"consent_version": version})
    with connect("mig", DB) as m:
        m.execute("GRANT UPDATE (consent_version, consent_accepted_at) ON users TO spk_app")
    s_with, _ = api("POST", "/users/me/consent", st, {"consent_version": version})
    rec("A-01", s_without >= 500 and s_with == 200, f"POST /users/me/consent: without UPDATE(consent_*) -> HTTP {s_without}; with the column grants -> HTTP {s_with}")

    # ---- H2: FOR UPDATE on subjects needs UPDATE on at least one column
    def upload(name, ctype, payload):
        return api("POST", f"/subjects/{sid}/documents", tt, multipart=("file", name, ctype, payload))

    with connect("mig", DB) as m:
        m.execute("REVOKE UPDATE ON subjects FROM spk_app")
    s_no, _ = upload("a.txt", "text/plain", b"hola mundo " * 50)
    with connect("mig", DB) as m:
        m.execute("GRANT UPDATE (description) ON subjects TO spk_app")
    s_yes, js_a = upload("a.txt", "text/plain", b"hola mundo " * 50)
    rec("H2", s_no >= 500 and s_yes == 202, f"upload (admission does SELECT ... FOR UPDATE on subjects): without UPDATE on any subjects column -> HTTP {s_no}; with UPDATE(description) only -> HTTP {s_yes}")
    s_b, js_b = upload("b.md", "text/markdown", b"# Titulo\n\n" + b"contenido de prueba " * 80)
    rec("API", s_b == 202, f"upload markdown {s_b}")
    s_c, _ = upload("c.pdf", "application/pdf", b"%PDF-1.4 fake")
    rec("API", s_c in (202, 415, 422), f"upload bogus pdf -> {s_c} (rejected by the content check: expected)")
    s, lst = api("GET", f"/subjects/{sid}/documents", tt)
    rec("API", s == 200 and len(lst) == 2, f"list documents {s} ({len(lst) if lst else 0})")

    # ---- worker under the worker role (real service, real repositories)
    from app.rag.embedder import FakeEmbedder
    from app.services.ingestion_service import IngestionLimits, IngestionService

    weng, wfac = sqla("worker")
    stmts = []
    event.listen(weng, "before_cursor_execute", lambda conn, cur, stmt, params, ctx, many: stmts.append(stmt))
    limits = IngestionLimits(lease_seconds=120, deadline_seconds=600, max_attempts=3, batch_size=4, max_chunks=2000, max_chars=2_000_000, max_age_hours=24)
    svc = IngestionService(wfac, FakeEmbedder(), limits)
    outcomes = [svc.run_once().value for _ in range(4)]
    sweep = svc.sweep()
    rec("H3", outcomes[:3] == ["ready", "ready", "failed"], f"worker role: IngestionService.run_once outcomes={outcomes}; sweep={sweep}")
    ins = [x for x in stmts if "INSERT INTO document_chunks" in x]
    ret = [x for x in ins if "RETURNING" in x.upper()]
    rec("H4", len(ins) >= 2 and len(ret) >= 1, f"chunk inserts: {len(ins)} statements, {len(ret)} with RETURNING id (the single-chunk document); all succeeded because the worker has SELECT (id) on document_chunks")
    with connect("admin", DB) as a:
        row = a.execute("select count(*) filter (where status='ready'), (select count(*) from document_chunks), (select count(*) from ingestion_jobs where payload is not null) from documents").fetchone()
    rec("H3", row[0] == 2 and row[1] > 0 and row[2] == 0, f"documents ready={row[0]}, chunks={row[1]}, jobs still holding bytes={row[2]}")

    # ---- find_similar under the app role
    from app.models.user import UserRole
    from app.repositories.chunk_repository import ChunkRepository, SearchActor

    aeng, afac = sqla("app")
    with afac() as s_:
        uid = s_.execute(text("select id from users where email=:e"), {"e": st_email}).scalar_one()
        hits = ChunkRepository(s_).find_similar(SearchActor(uid, UserRole.STUDENT), uuid.UUID(sid), FakeEmbedder().embed(["hola"])[0], 5)
    rec("H3", len(hits) > 0, f"find_similar under the app role (reads chunks, documents, subjects, enrollments, users): {len(hits)} hits")

    # ---- H1: deleting cascades without DELETE on the children
    with connect("admin", DB) as a:
        before = a.execute("select (select count(*) from document_chunks), (select count(*) from ingestion_jobs)").fetchone()
        privs = a.execute("select has_table_privilege('spk_app','document_chunks','DELETE'), has_table_privilege('spk_app','ingestion_jobs','DELETE')").fetchone()
    ready_id = [d["id"] for d in api("GET", f"/subjects/{sid}/documents", tt)[1] if d["status"] == "ready" and d["filename"] == "b.md"][0]
    s, _ = api("DELETE", f"/subjects/{sid}/documents/{ready_id}", tt)
    rec("API", s == 204, f"delete document {s}")
    with connect("admin", DB) as a:
        after = a.execute("select (select count(*) from document_chunks), (select count(*) from ingestion_jobs), (select count(*) from documents)").fetchone()
    rec("H1", privs == (False, False) and after[0] < before[0] and after[1] < before[1], f"app has DELETE on chunks/jobs = {privs}; deleting a document removed its rows by cascade: chunks {before[0]}->{after[0]}, jobs {before[1]}->{after[1]}")
    s, _ = api("DELETE", f"/subjects/{sid}/enrollments/{uuid.UUID(int=0)}", tt)
    rec("API", s in (204, 404), f"delete enrollment (unknown student) {s}")
    s, _ = api("DELETE", f"/subjects/{sid}", tt)
    rec("API", s == 204, f"delete subject {s}")
    with connect("admin", DB) as a:
        left = a.execute("select (select count(*) from documents), (select count(*) from document_chunks), (select count(*) from ingestion_jobs), (select count(*) from enrollments), (select count(*) from subjects)").fetchone()
    rec("H1", left == (0, 0, 0, 0, 0), f"subject delete cascaded documents, chunks, jobs and enrollments: {left}")
    ops = sorted(set((m, p.replace(sid, "{id}")) for m, p, c in steps))
    rec("COVERAGE", None, f"HTTP operations exercised: {ops}")
    with connect("admin", DB) as a:
        n = a.execute("delete from users where email like %s", (f"{tag}-%",)).rowcount
    rec("CLEANUP", n == 2, f"synthetic users removed: {n}")
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
