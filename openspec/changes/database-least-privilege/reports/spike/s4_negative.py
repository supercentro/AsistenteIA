from common import *
import psycopg
DB = "spk_clean"
# role attributes
with connect("admin", DB) as a:
    attrs = a.execute("select rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit from pg_roles where rolname in ('spk_app','spk_worker','spk_migrator') order by 1").fetchall()
    members = a.execute("select count(*) from pg_auth_members m join pg_roles r on r.oid=m.member where r.rolname in ('spk_app','spk_worker','spk_migrator')").fetchone()[0]
rec("NEG", all(not any(r[1:6]) for r in attrs) and members == 0, f"role attributes all false and no role memberships (not even pg_* predefined roles): {[(r[0]) for r in attrs]} memberships={members}")

ADMIN_OPS = [
    ("CREATE TABLE", "create table public.x(a int)", "42501"),
    ("CREATE TEMP TABLE", "create temp table x(a int)", "42501"),
    ("CREATE SCHEMA", "create schema s_x", "42501"),
    ("CREATE EXTENSION", "create extension if not exists pg_trgm", "42501"),
    ("CREATE FUNCTION", "create function public.f() returns int language sql as 'select 1'", "42501"),
    ("DROP TABLE users", "drop table public.users", "42501"),
    ("ALTER TABLE users", "alter table public.users add column z int", "42501"),
    ("TRUNCATE documents", "truncate public.documents", "42501"),
    ("COPY ... TO PROGRAM", "copy (select 1) to program 'id'", "42501"),
    ("COPY ... FROM PROGRAM", "copy public.t_none from program 'id'", None),
    ("COPY ... TO file", "copy (select 1) to '/tmp/spk_out.txt'", "42501"),
    ("pg_read_file", "select pg_read_file('/etc/passwd')", "42501"),
    ("pg_ls_dir", "select pg_ls_dir('/')", "42501"),
    ("lo_import (server file)", "select lo_import('/etc/passwd')", "42501"),
    ("ALTER SYSTEM", "alter system set work_mem='64MB'", "42501"),
    ("CREATE ROLE", "create role spk_evil login", "42501"),
    ("SET ROLE migrator", "set role spk_migrator", "42501"),
    ("read pg_authid", "select rolpassword from pg_authid limit 1", "42501"),
    ("pg_terminate_backend", "select pg_terminate_backend(pid) from pg_stat_activity where usename='spk_admin' limit 1", "42501"),
    ("CREATE DATABASE", "create database spk_evil", "42501"),
    ("GRANT to self", "grant select on public.users to spk_worker", None),
]
for who in ("app", "worker"):
    for label, stmt, code in ADMIN_OPS:
        if code is None:
            continue
        expect_error(who, DB, stmt, "NEG", f"{USERS[who]}: {label}", code)
for label, stmt, code in [("COPY FROM PROGRAM", "create table public.t_n(a text)", None)]:
    pass
# the migrator is not a superuser either
expect_error("mig", DB, "copy (select 1) to program 'id'", "NEG", "migrator: COPY TO PROGRAM", "42501")
expect_error("mig", DB, "select pg_read_file('/etc/passwd')", "NEG", "migrator: pg_read_file", "42501")
expect_error("mig", DB, "alter system set work_mem='64MB'", "NEG", "migrator: ALTER SYSTEM", "42501")
expect_error("mig", DB, "create role spk_evil2 login", "NEG", "migrator: CREATE ROLE", "42501")
expect_error("mig", DB, "create extension pg_trgm", "NEG", "migrator: CREATE EXTENSION", "42501")
expect_error("mig", DB, "select rolpassword from pg_authid limit 1", "NEG", "migrator: pg_authid", "42501")

# table-level negatives (matrix)
T = [
    ("worker", "select count(*) from users", "worker SELECT users"),
    ("worker", "insert into users(id) values (gen_random_uuid())", "worker INSERT users"),
    ("worker", "select count(*) from subjects", "worker SELECT subjects"),
    ("worker", "select count(*) from enrollments", "worker SELECT enrollments"),
    ("worker", "insert into documents(id) values (gen_random_uuid())", "worker INSERT documents"),
    ("worker", "delete from documents", "worker DELETE documents"),
    ("worker", "update documents set filename='x'", "worker UPDATE documents.filename"),
    ("worker", "update documents set subject_id=subject_id", "worker UPDATE documents.subject_id"),
    ("worker", "select content from document_chunks", "worker SELECT document_chunks"),
    ("worker", "delete from document_chunks", "worker DELETE document_chunks"),
    ("worker", "insert into ingestion_jobs(id) values (gen_random_uuid())", "worker INSERT ingestion_jobs"),
    ("worker", "delete from ingestion_jobs", "worker DELETE ingestion_jobs"),
    ("worker", "update ingestion_jobs set document_id=document_id", "worker UPDATE ingestion_jobs.document_id"),
    ("worker", "select version_num from alembic_version", "worker SELECT alembic_version"),
    ("app", "update documents set status='ready'", "app UPDATE documents"),
    ("app", "update ingestion_jobs set payload=null", "app UPDATE ingestion_jobs"),
    ("app", "delete from ingestion_jobs", "app DELETE ingestion_jobs"),
    ("app", "insert into document_chunks(id) values (gen_random_uuid())", "app INSERT document_chunks"),
    ("app", "delete from document_chunks", "app DELETE document_chunks"),
    ("app", "update document_chunks set content='x'", "app UPDATE document_chunks"),
    ("app", "update users set role='teacher'", "app UPDATE users.role (privilege escalation of an account)"),
    ("app", "update users set password_hash='x'", "app UPDATE users.password_hash"),
    ("app", "update subjects set teacher_id=teacher_id", "app UPDATE subjects.teacher_id"),
    ("app", "update enrollments set student_id=student_id", "app UPDATE enrollments"),
    ("app", "select version_num from alembic_version", "app SELECT alembic_version"),
]
for who, stmt, label in T:
    expect_error(who, DB, stmt, "NEG", label, "42501")
# what is allowed (documented, INFO): USERSET parameters can be reset by the roles
for stmt, label in [("set statement_timeout = 0", "SET statement_timeout"), ("set search_path = public", "SET search_path"), ("select pg_sleep(0.01)", "pg_sleep"), ("select lo_create(0)", "lo_create")]:
    try:
        with connect("app", DB) as c:
            c.execute(stmt)
        rec("A-24", None, f"app can run {label} (allowed by default; availability only, not a control)")
    except psycopg.Error as e:
        rec("A-24", None, f"app cannot run {label}: {e.sqlstate}")
try:
    with connect("app", DB) as c:
        c.execute("alter role spk_app password 'x'")
    rec("NEG", None, "app can change its OWN password (default PostgreSQL behaviour): with SCRAM it can lock itself out but cannot touch other roles")
except psycopg.Error as e:
    rec("NEG", None, f"app cannot change its own password: {e.sqlstate}")
