import json, os, sys, time
import psycopg

HOST = "g26-db"
PW = {k: os.environ["PW_" + k] for k in ("ADMIN", "MIG", "APP", "WORKER")}
USERS = {"admin": "spk_admin", "mig": "spk_migrator", "app": "spk_app", "worker": "spk_worker"}
OUT = "/spike/out/results.jsonl"


def dsn(who: str, db: str, driver: bool = False) -> str:
    base = "postgresql+psycopg" if driver else "postgresql"
    return f"{base}://{USERS[who]}:{PW[who.upper() if who != 'mig' else 'MIG']}@{HOST}:5432/{db}"


def connect(who: str, db: str, autocommit: bool = True):
    return psycopg.connect(dsn(who, db), autocommit=autocommit, connect_timeout=5)


def mask(text: str) -> str:
    for v in PW.values():
        text = text.replace(v, "***")
    return text


def rec(h: str, ok, msg: str = "") -> None:
    line = {"h": h, "ok": ok, "msg": mask(str(msg))[:2000]}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(("PASS " if ok is True else ("FAIL " if ok is False else "INFO ")) + h + " | " + mask(str(msg))[:300], flush=True)


def expect_error(who: str, db: str, sql: str, h: str, label: str, code: str | None = None, params=None):
    """Run `sql`; PASS if it raises (optionally with a given SQLSTATE)."""
    try:
        with connect(who, db) as c:
            c.execute(sql, params)
        rec(h, False, f"{label}: NOT blocked")
        return False
    except psycopg.Error as e:
        got = getattr(e, "sqlstate", None)
        ok = code is None or got == code or (got is None and 'permission denied' in str(e))
        rec(h, ok, f"{label}: blocked ({got}) {str(e).splitlines()[0][:110]}")
        return ok


def expect_ok(who: str, db: str, sql: str, h: str, label: str, params=None):
    try:
        with connect(who, db) as c:
            cur = c.execute(sql, params)
            rows = cur.fetchall() if cur.description else None
        rec(h, True, f"{label}: ok" + (f" {rows}" if rows is not None and len(str(rows)) < 120 else ""))
        return True
    except psycopg.Error as e:
        rec(h, False, f"{label}: FAILED ({getattr(e,'sqlstate',None)}) {str(e).splitlines()[0][:120]}")
        return False


import subprocess


def alembic(who: str, db: str, *args: str, timeout: int = 120):
    env = dict(os.environ)
    env.update(DATABASE_URL=dsn(who, db, driver=True), APP_ENV="development", LOG_LEVEL="WARNING")
    p = subprocess.run(["python", "-m", "alembic", *args], cwd="/app", env=env, capture_output=True, text=True, timeout=timeout)
    out = mask((p.stdout or "") + (p.stderr or ""))
    return p.returncode, out


def last_line(text: str) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    key = [l for l in lines if any(k in l.lower() for k in ("permission denied", "must be owner", "insufficientprivilege", "no new upgrade", "0005", "0004"))]
    pick = key[0] if key else (lines[-1] if lines else "")
    return pick[:200]


def catalog_fingerprint(who: str, db: str) -> list[str]:
    q = """
    select 'COL '||table_name||'.'||column_name||' '||data_type||' '||is_nullable||' '||coalesce(column_default,'') from information_schema.columns where table_schema='public'
    union all select 'CON '||conrelid::regclass||' '||conname||' '||pg_get_constraintdef(oid) from pg_constraint where connamespace='public'::regnamespace
    union all select 'IDX '||indexdef from pg_indexes where schemaname='public'
    union all select 'ENUM '||t.typname||' '||string_agg(e.enumlabel,',' order by e.enumsortorder) from pg_type t join pg_enum e on e.enumtypid=t.oid group by t.typname
    union all select 'ALEMBIC '||version_num from alembic_version
    order by 1"""
    with connect(who, db) as c:
        return [r[0] for r in c.execute(q).fetchall()]


def owners(db: str) -> dict:
    q = """select 'rel:'||c.relname||':'||c.relkind::text, pg_get_userbyid(c.relowner) from pg_class c where c.relnamespace='public'::regnamespace
           union all select 'type:'||t.typname, pg_get_userbyid(t.typowner) from pg_type t where t.typnamespace='public'::regnamespace and t.typtype='e'"""
    with connect("admin", db) as c:
        return dict(c.execute(q).fetchall())


MATRIX = [
    "GRANT SELECT, INSERT ON users TO spk_app",
    "GRANT UPDATE (consent_version, consent_accepted_at) ON users TO spk_app",
    "GRANT SELECT, INSERT, DELETE ON subjects TO spk_app",
    "GRANT UPDATE (description) ON subjects TO spk_app",
    "GRANT SELECT, INSERT, DELETE ON enrollments TO spk_app",
    "GRANT SELECT, INSERT, DELETE ON documents TO spk_app",
    "GRANT SELECT, INSERT ON ingestion_jobs TO spk_app",
    "GRANT SELECT ON document_chunks TO spk_app",
    "GRANT SELECT (id, subject_id, filename, content_type, status) ON documents TO spk_worker",
    "GRANT UPDATE (status, chunks_count, error_code, error_message) ON documents TO spk_worker",
    "GRANT SELECT (id, document_id, payload, attempts, locked_by, locked_until, available_at, created_at) ON ingestion_jobs TO spk_worker",
    "GRANT UPDATE (payload, attempts, locked_by, locked_until, updated_at) ON ingestion_jobs TO spk_worker",
    "GRANT INSERT ON document_chunks TO spk_worker",
    "GRANT SELECT (id) ON document_chunks TO spk_worker",
]


def apply_matrix(who: str, db: str):
    with connect(who, db) as c:
        for s in MATRIX:
            c.execute(s)
