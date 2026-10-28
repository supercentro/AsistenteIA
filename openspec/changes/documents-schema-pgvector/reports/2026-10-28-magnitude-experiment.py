"""Experiment I3: cosine distance behaviour of pgvector 0.8.7 across magnitudes. Scratch DB only; no vector values printed."""
import math
import random
import struct

import psycopg

DSN = "postgresql://postgres:spikepw@127.0.0.1:55439/spike"
assert "55439" in DSN
DIM = 384


def f32(x: float) -> float:
    try:
        return struct.unpack("f", struct.pack("f", x))[0]
    except OverflowError:
        return math.inf


def unit(seed: int) -> list[float]:
    r = random.Random(seed)
    v = [r.gauss(0, 1) for _ in range(DIM)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def lit(v: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in v) + "]"


def ref_cos_dist(a: list[float], b: list[float]) -> float:
    a = [f32(x) for x in a]
    b = [f32(x) for x in b]
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 1.0 - dot / (na * nb)


U1, U2 = unit(1), unit(2)
SCALES = [1e-40, 1e-38, 1e-30, 1e-25, 1e-22, 1e-21, 1e-20, 1e-19, 1e-18, 1e-15, 1e-10, 1e-6, 1e-3, 1.0, 1e3, 1e6, 1e10, 1e15, 1e17, 1e18, 1e19, 1e20, 1e30, 1e38]

conn = psycopg.connect(DSN, autocommit=True)


def q(sql: str, *params):
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0], None
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__ + ": " + str(e).splitlines()[0][:50]


print("scale | vector_norm | dist(scaled a, unit b): err vs float64 | dist(both scaled): err")
for s in SCALES:
    a = [x * s for x in U1]
    b = [x * s for x in U2]
    norm, e0 = q("select vector_norm(%s::vector)", lit(a))
    d1, e1 = q("select %s::vector <=> %s::vector", lit(a), lit(U2))
    d2, e2 = q("select %s::vector <=> %s::vector", lit(a), lit(b))
    ref1 = ref_cos_dist(a, U2)
    ref2 = ref_cos_dist(a, b)

    def fmt(d, e, ref):
        if e:
            return e
        if d is None or (isinstance(d, float) and math.isnan(d)):
            return "NaN"
        return f"ok err={abs(d - ref):.1e}"

    nm = e0 or ("inf" if norm == math.inf else f"{norm:.2e}")
    print(f"{s:7.0e} | {nm:>10} | {fmt(d1, e1, ref1):<22} | {fmt(d2, e2, ref2)}")

# zero query / zero stored
print("zero:", q("select %s::vector <=> %s::vector", lit([0.0] * DIM), lit(U1))[0])
# mixed: single huge component among small ones
mixed = [1e-3] * DIM
mixed[0] = 1e19
print("mixed huge component:", q("select vector_norm(%s::vector)", lit(mixed)))
# index build / ordering with extreme rows present
conn.execute("create table t(id int, e vector(384))")
for i, s in enumerate([1e-30, 1e-19, 1e-10, 1.0, 1e10, 1e17, 1e19, 1e30]):
    conn.execute("insert into t values (%s, %s::vector)", (i, lit([x * s for x in U1 if True])))
conn.execute("create index on t using hnsw (e vector_cosine_ops)")
rows = conn.execute("select id, e <=> %s::vector from t order by e <=> %s::vector, id", (lit(U1), lit(U1))).fetchall()
print("order with unit query (id: dist is NaN?):", [(i, "NaN" if (d is None or d != d) else round(d, 6)) for i, d in rows])
