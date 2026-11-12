import os, time, psycopg
c = psycopg.connect(os.environ["SPIKE_DSN"], autocommit=True)
c.execute("truncate jobs")
for i in range(20):
    c.execute("insert into jobs (document_id, payload) values (%s, %s)", (i, os.urandom(10 * 1024 * 1024)))
c.execute("update jobs set payload = null")
time.sleep(1)
t = time.time(); c.execute("vacuum full jobs"); print(f"VACUUM FULL of a jobs table after 20 nulled 10 MB payloads: {1000 * (time.time() - t):.0f} ms")
print("size after:", c.execute("select pg_size_pretty(pg_total_relation_size('jobs'))").fetchone()[0])
