"""Group 13.2: cosine-ordered search with the real model, as the owner, an enrolled student and others."""

import os
import time
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.rag.embedder import LocalEmbedder
from app.repositories.chunk_repository import ChunkRepository, SearchActor

engine = create_engine(os.environ["DATABASE_URL"])
t0 = time.monotonic()
embedder = LocalEmbedder.load(Path(os.environ["EMBEDDING_MODEL_PATH"]), threads=2, batch_size=16)
print(f"model loaded in {time.monotonic() - t0:.1f}s")

with Session(engine) as s:
    users = {r[0]: (r[1], r[2]) for r in s.execute(text("select email, id, role::text from users"))}
    subject = s.execute(text("select id from subjects limit 1")).scalar_one()


def actor(email: str, role: UserRole | None = None) -> SearchActor:
    uid, stored = users[email]
    return SearchActor(user_id=uid, role=role or UserRole(stored))


QUERIES = [
    ("Que es la derivada de una funcion?", ("derivada", "tangente", "cadena")),
    ("Cuando comenzo la Revolucion Francesa?", ("Revolucion", "Bastilla", "Napoleon", "Robespierre")),
    ("Como funciona la fotosintesis en las plantas?", ("fotosintesis", "clorofila", "Calvin")),
    ("Que es una pila en programacion?", ("pila", "cola", "hash", "binaria")),
    ("Quien fue ejecutado en la guillotina?", ("guillotina", "Luis XVI")),
]

ACTORS = {
    "owner teacher": actor("docente1@example.com"),
    "enrolled student": actor("alumna1@example.com"),
    "not enrolled student": actor("alumno2@example.com"),
    "other teacher": actor("docente2@example.com"),
    "student claiming teacher role": actor("alumna1@example.com", UserRole.TEACHER),
    "unknown user": SearchActor(user_id=uuid.uuid4(), role=UserRole.STUDENT),
}

hits = 0
for question, keywords in QUERIES:
    vector = embedder.embed([question])[0]
    for label, who in ACTORS.items():
        with Session(engine) as s:
            started = time.monotonic()
            found = ChunkRepository(s).find_similar(who, subject, vector, 3)
            ms = (time.monotonic() - started) * 1000
        if label in ("owner teacher", "enrolled student"):
            ordered = all(a.similarity >= b.similarity for a, b in zip(found, found[1:], strict=False))
            top = found[0] if found else None
            ok = bool(top) and any(k.lower() in top.content.lower() for k in keywords)
            hits += ok if label == "enrolled student" else 0
            print(
                f"{label:30s} {question[:38]:38s} n={len(found)} ordered={ordered} "
                f"top1={'HIT' if ok else 'miss'} sim={top.similarity:.3f} "
                f"file={top.document_filename} p={top.page_number} [{ms:.0f} ms]"
                if top
                else f"{label:30s} {question[:38]:38s} n=0"
            )
        else:
            print(f"{label:30s} {question[:38]:38s} n={len(found)} (must be 0)")
            assert not found, label
print(f"functional smoke (enrolled student, top-1 contains an expected term): {hits}/{len(QUERIES)}")

with Session(engine) as s:
    print("-- chunks by document status:")
    for r in s.execute(
        text(
            "select d.status::text, d.filename, count(c.id), d.chunks_count from documents d "
            "left join document_chunks c on c.document_id=d.id group by d.id order by d.created_at"
        )
    ):
        print("  ", tuple(r))
    print("orphan chunks:", s.execute(text("select count(*) from document_chunks c where not exists (select 1 from documents d where d.id=c.document_id)")).scalar_one())
    print("chunks of non-ready documents:", s.execute(text("select count(*) from document_chunks c join documents d on d.id=c.document_id where d.status<>'ready'")).scalar_one())
    print("ingestion_jobs rows:", s.execute(text("select count(*) from ingestion_jobs")).scalar_one(), "| leftover payload bytes:", s.execute(text("select count(*) from ingestion_jobs where payload is not null")).scalar_one())
