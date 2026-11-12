"""H5 (database part): the real embeddings against the real CHECK of document_chunks on a scratch PostgreSQL."""
import os
import sys

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

sys.path.insert(0, "/spike")
from vv import validate_embedding  # copy of app/core/vector_validation.py  # noqa: E402

vectors = np.load("/out/compat_vectors.npy")
with psycopg.connect(os.environ["SPIKE_DSN"], autocommit=True) as conn:
    conn.execute("create extension if not exists vector")
    register_vector(conn)
    conn.execute("drop table if exists chunks_h5")
    conn.execute("""create table chunks_h5 (id serial primary key, embedding vector(384) not null,
                    constraint ck_norm check (vector_norm(embedding) between 1e-6 and 1e6))""")
    accepted_by_db = rejected = 0
    mismatches = 0
    for v in vectors:
        values = validate_embedding([float(x) for x in v])  # the validated (single precision) values are the ones bound
        try:
            conn.execute("insert into chunks_h5 (embedding) values (%s)", (np.array(values, dtype=np.float32),))
            accepted_by_db += 1
        except psycopg.errors.CheckViolation:
            rejected += 1
            mismatches += 1
    print(f"vectors {len(vectors)}: inserted {accepted_by_db}, CHECK rejected {rejected}; helper-accepted but rejected by the CHECK: {mismatches}")
    row = conn.execute("select min(vector_norm(embedding)), max(vector_norm(embedding)), count(*) from chunks_h5").fetchone()
    print("stored norms in the database:", f"min {row[0]:.4f} max {row[1]:.4f} rows {row[2]}")
    # cosine search sanity in the database against numpy for the first vector
    q = vectors[0]
    rows = conn.execute("select id, 1 - (embedding <=> %s) from chunks_h5 order by embedding <=> %s limit 3", (q, q)).fetchall()
    print("top-3 by cosine in PostgreSQL for vector 0:", [(r[0], round(float(r[1]), 4)) for r in rows])
