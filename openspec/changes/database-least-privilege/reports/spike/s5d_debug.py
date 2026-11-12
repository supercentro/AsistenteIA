"""Find out which statement of the worker needs a privilege the matrix did not grant (H3/H4)."""
import uuid

from common import *  # noqa: F401,F403
from sqlalchemy import event, text

DB = "spk_clean"
from app.core.database import create_db_engine, create_session_factory
from app.rag.embedder import FakeEmbedder
from app.services.ingestion_service import IngestionLimits, IngestionService

# seed with the admin connection (synthetic rows; the API path was already proved)
tag = "dbg" + uuid.uuid4().hex[:4]
with connect("admin", DB) as a:
    cols = a.execute("select column_name, is_nullable, column_default from information_schema.columns where table_name='users' order by ordinal_position").fetchall()
    print("users columns:", [c[0] for c in cols])
    uid = uuid.uuid4()
    a.execute("insert into users(id, email, name, password_hash, role) values (%s,%s,%s,%s,'teacher')", (uid, f"{tag}@example.com", tag, "x"))
    sid = uuid.uuid4()
    a.execute("insert into subjects(id, teacher_id, name) values (%s,%s,%s)", (sid, uid, tag))
    docs = []
    for name, payload in (("one.txt", b"hola mundo " * 40), ("many.md", b"# t\n\n" + b"contenido de prueba " * 150)):
        did = uuid.uuid4()
        a.execute("insert into documents(id, subject_id, filename, content_type, size_bytes, status) values (%s,%s,%s,%s,%s,'pending')", (did, sid, name, "text/plain" if name.endswith("txt") else "text/markdown", len(payload)))
        a.execute("insert into ingestion_jobs(document_id, payload) values (%s,%s)", (did, payload))
        docs.append(did)

weng = create_db_engine(dsn("worker", DB, driver=True))
fac = create_session_factory(weng)
stmts = []
event.listen(weng, "before_cursor_execute", lambda conn, cur, stmt, params, ctx, many: stmts.append((stmt, many)))
errors = []
event.listen(weng, "handle_error", lambda ctx: errors.append((type(ctx.original_exception).__name__, str(ctx.original_exception).splitlines()[0], (ctx.statement or "")[:150])))
limits = IngestionLimits(lease_seconds=120, deadline_seconds=600, max_attempts=3, batch_size=4, max_chunks=2000, max_chars=2_000_000, max_age_hours=24)
svc = IngestionService(fac, FakeEmbedder(), limits)
outs = [svc.run_once().value for _ in range(3)]
rec("H4dbg", None, f"outcomes={outs}")
for e in errors:
    rec("H4dbg", None, f"ERROR {e[0]}: {e[1]} | {e[2]}")
for stmt, many in stmts:
    if "document_chunks" in stmt and stmt.lstrip().upper().startswith("INSERT"):
        rec("H4dbg", None, f"chunk insert executemany={many}: {stmt[:260].replace(chr(10), ' ')}")
with connect("admin", DB) as a:
    st = a.execute("select filename, status::text, chunks_count from documents where subject_id=%s order by filename", (sid,)).fetchall()
rec("H4dbg", None, f"documents after the worker: {st}")
# cleanup of this debug seed
with connect("admin", DB) as a:
    a.execute("delete from subjects where id=%s", (sid,))
    a.execute("delete from users where id=%s", (uid,))
