"""A-01 debug: does POST /users/me/consent really need UPDATE on users.consent_*?"""
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request

from common import *  # noqa: F401,F403

DB = "spk_clean"
BASE = "http://127.0.0.1:8000/api/v1"
env = dict(os.environ)
env.update(DATABASE_URL=dsn("app", DB, driver=True), APP_ENV="development", LOG_LEVEL="INFO")
srv = subprocess.Popen(["python", "-m", "uvicorn", "app.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", "8000"], cwd="/app", env=env, stdout=open("/spike/out/api2.log", "w"), stderr=subprocess.STDOUT)


def api(method, path, token=None, body=None):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, None


try:
    for _ in range(40):
        try:
            if urllib.request.urlopen(BASE + "/health", timeout=2).status == 200:
                break
        except Exception:
            time.sleep(1)
    from app.core.config import load_settings

    os.environ.update(DATABASE_URL=dsn("app", DB, driver=True), APP_ENV="development")
    version = load_settings().privacy_policy_version
    pw = secrets.token_urlsafe(16)
    tag = "con" + secrets.token_hex(3)
    emails = [f"{tag}-a@example.com", f"{tag}-b@example.com"]
    for em in emails:
        s, _ = api("POST", "/auth/register", body={"name": tag, "email": em, "password": pw})
        assert s == 201, s
    tok = {}
    for em in emails:
        s, js = api("POST", "/auth/login", body={"email": em, "password": pw})
        tok[em] = js["access_token"]
    with connect("admin", DB) as a:
        acl = a.execute("select attname, attacl::text from pg_attribute where attrelid='users'::regclass and attacl is not null").fetchall()
        tacl = a.execute("select relacl::text from pg_class where relname='users'").fetchone()[0]
    rec("A-01dbg", None, f"before: table ACL={tacl}; column ACL={acl}")
    # user A: remove EVERY UPDATE privilege of the app on users (table and column level)
    with connect("mig", DB) as m:
        m.execute("REVOKE UPDATE ON users FROM spk_app")
        m.execute("REVOKE UPDATE (consent_version, consent_accepted_at) ON users FROM spk_app")
    with connect("admin", DB) as a:
        can = a.execute("select has_column_privilege('spk_app','users','consent_version','UPDATE')").fetchone()[0]
    s, js = api("POST", "/users/me/consent", tok[emails[0]], {"consent_version": version})
    with connect("admin", DB) as a:
        stored = a.execute("select consent_version from users where email=%s", (emails[0],)).fetchone()[0]
    rec("N-1", s == 200 and stored is None, f"SILENT FAILURE: app WITHOUT any UPDATE privilege on users.consent_*: POST /users/me/consent -> HTTP {s} but stored consent_version={stored} (the commit of get_db fails after the response left)")
    with connect("mig", DB) as m:
        m.execute("GRANT UPDATE (consent_version, consent_accepted_at) ON users TO spk_app")
    s, js = api("POST", "/users/me/consent", tok[emails[0]], {"consent_version": version})
    with connect("admin", DB) as a:
        stored = a.execute("select consent_version from users where email=%s", (emails[0],)).fetchone()[0]
    rec("A-01", s == 200 and stored == version, f"app WITH UPDATE(consent_version, consent_accepted_at) only: HTTP {s}, stored={stored}")
    with connect("admin", DB) as a:
        a.execute("delete from users where email like %s", (f"{tag}-%",))
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
