"""H8 (phased): bytea payload of 10 MB in PostgreSQL. Phases are run by the host script with server-side greps in between."""
import os
import statistics
import sys
import threading
import time

import psycopg

DSN = os.environ["SPIKE_DSN"]  # throw-away container on a private Docker network
MARK = b"F6SPIKE-MARKER-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-"
phase = sys.argv[1]


def q(conn, sql):
    return conn.execute(sql).fetchall()


def lsn(conn) -> int:
    return q(conn, "select pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0')")[0][0]


def sizes(conn):
    r = q(conn, "select pg_relation_size('jobs'), coalesce(pg_relation_size(reltoastrelid),0), pg_total_relation_size('jobs') from pg_class where oid='jobs'::regclass")[0]
    return {"heap": r[0], "toast": r[1], "total": r[2]}


def mb(n):
    return f"{n / 1048576:.2f} MB"


random_payload = MARK + os.urandom(10 * 1024 * 1024 - len(MARK))
c = psycopg.connect(DSN, autocommit=True)

if phase == "load":
    c.execute("drop table if exists jobs")
    c.execute("create table jobs (id serial primary key, document_id int, payload bytea, attempts int default 0)")
    print("postgres", q(c, "show server_version")[0][0], "| autovacuum", q(c, "show autovacuum")[0][0],
          "| autovacuum_vacuum_threshold", q(c, "show autovacuum_vacuum_threshold")[0][0],
          "| autovacuum_naptime", q(c, "show autovacuum_naptime")[0][0], "| wal_level", q(c, "show wal_level")[0][0],
          "| toast_tuple_target", q(c, "show default_toast_compression")[0][0])
    times = []
    for i in range(5):
        before = lsn(c)
        t = time.time()
        with c.transaction():
            c.execute("insert into jobs (document_id, payload) values (%s, %s)", (i, random_payload))
        times.append(time.time() - t)
        wal = lsn(c) - before
    print(f"insert 10 MB random: median {statistics.median(times) * 1000:.0f} ms (min {min(times) * 1000:.0f}, max {max(times) * 1000:.0f}); WAL of the last insert {mb(wal)}")
    text_payload = (b"F6SPIKE-TEXT-ONLY-" + "texto de prueba en español ".encode() * 500000)[: 10 * 1024 * 1024]
    before = lsn(c)
    t = time.time()
    c.execute("insert into jobs (document_id, payload) values (99, %s)", (text_payload,))
    print(f"insert 10 MB compressible text: {1000 * (time.time() - t):.0f} ms, WAL {mb(lsn(c) - before)}")
    t = time.time()
    got = q(c, "select payload from jobs where document_id=0")[0][0]
    print(f"read back 10 MB: {1000 * (time.time() - t):.0f} ms, {len(got)} bytes")
    print("sizes after 6 inserts", {k: mb(v) for k, v in sizes(c).items()})
    c.execute("checkpoint")

elif phase == "nullout":
    before = lsn(c)
    t = time.time()
    c.execute("update jobs set payload = null where document_id < 5")
    print(f"null-out of 5 rows: {1000 * (time.time() - t):.0f} ms, WAL {mb(lsn(c) - before)}")
    print("sizes after null-out, before vacuum", {k: mb(v) for k, v in sizes(c).items()})
    time.sleep(2)
    print("stats (heap):", q(c, "select n_live_tup, n_dead_tup, last_autovacuum from pg_stat_user_tables where relname='jobs'")[0])
    print("stats (toast):", q(c, "select t.relname, t.n_live_tup, t.n_dead_tup, t.last_autovacuum from pg_stat_all_tables t join pg_class r on r.reltoastrelid=t.relid where r.relname='jobs'")[0])
    c.execute("checkpoint")

elif phase == "autovac":
    time.sleep(int(sys.argv[2]))
    print("after waiting: sizes", {k: mb(v) for k, v in sizes(c).items()})
    print("stats (toast):", q(c, "select t.relname, t.n_live_tup, t.n_dead_tup, t.last_autovacuum from pg_stat_all_tables t join pg_class r on r.reltoastrelid=t.relid where r.relname='jobs'")[0])

elif phase == "vacuum":
    before = sizes(c)
    t = time.time()
    c.execute("vacuum jobs")
    print(f"VACUUM took {1000 * (time.time() - t):.0f} ms; sizes after", {k: mb(v) for k, v in sizes(c).items()}, "| before", {k: mb(v) for k, v in before.items()})
    c.execute("checkpoint")

elif phase == "vacuumfull":
    c.execute("vacuum full jobs")
    print("VACUUM FULL sizes", {k: mb(v) for k, v in sizes(c).items()})
    c.execute("checkpoint")

elif phase == "locks":
    c.execute("drop table if exists subj_lock")
    c.execute("create table subj_lock (id int primary key)")
    c.execute("insert into subj_lock values (1)")
    holds: list[tuple[float, float]] = []

    def upload(n: int):
        with psycopg.connect(DSN) as conn:
            t0 = time.time()
            with conn.transaction():
                conn.execute("select 1 from subj_lock where id=1 for update")
                conn.execute("select pg_advisory_xact_lock(424242)")
                acquired = time.time() - t0
                t1 = time.time()
                conn.execute("insert into jobs (document_id, payload) values (%s, %s)", (1000 + n, random_payload))
                holds.append((acquired, time.time() - t1))

    for parallel in (1, 4, 8):
        holds.clear()
        threads = [threading.Thread(target=upload, args=(i,)) for i in range(parallel)]
        t = time.time()
        [x.start() for x in threads]
        [x.join() for x in threads]
        total = time.time() - t
        waits = sorted(h[0] for h in holds)
        inserts = [h[1] for h in holds]
        print(f"{parallel} uploads at once (subject row lock then global advisory lock, 10 MB insert inside): total {total * 1000:.0f} ms, max lock wait {max(waits) * 1000:.0f} ms, insert under lock median {statistics.median(inserts) * 1000:.0f} ms")

elif phase == "timeouts":
    c.execute("set statement_timeout = '200ms'")
    try:
        c.execute("select pg_sleep(1)")
        print("statement_timeout: not applied")
    except psycopg.errors.QueryCanceled:
        print("statement_timeout 200ms cancels a 1 s statement: yes")
    c.execute("set statement_timeout = 0")
    c2 = psycopg.connect(DSN, autocommit=True)
    c2.execute("set idle_in_transaction_session_timeout = '1s'")
    c2.execute("begin")
    c2.execute("select 1")
    time.sleep(2)
    try:
        c2.execute("select 1")
        print("idle_in_transaction_session_timeout: not applied")
    except psycopg.Error as exc:
        print("   (error class:", type(exc).__name__ + ")")
        print("idle_in_transaction_session_timeout 1s closes an idle transaction: yes")
    # a typical final write: 2000 chunk rows with 384-dim vectors
    c.execute("create extension if not exists vector")
    c.execute("drop table if exists chunks_t")
    c.execute("create table chunks_t (id serial primary key, content text, embedding vector(384))")
    import random
    rows = [("texto de prueba " * 8, "[" + ",".join(f"{random.random():.6f}" for _ in range(384)) + "]") for _ in range(2000)]
    t = time.time()
    with c.transaction():
        with c.cursor().copy("copy chunks_t (content, embedding) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
    print(f"final write of 2000 chunks (copy, 384-dim vectors): {1000 * (time.time() - t):.0f} ms")
    t = time.time()
    with c.transaction():
        c.cursor().executemany("insert into chunks_t (content, embedding) values (%s, %s::vector)", rows[:500])
    print(f"500 chunks by executemany inserts: {1000 * (time.time() - t):.0f} ms")
print("phase", phase, "ok")
