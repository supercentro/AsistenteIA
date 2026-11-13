"""Why the ORM needs INSERT on columns nobody sets, and ways to avoid it (analysis of group 6).

The owner accepted the six extra INSERT columns only provisionally. This file reproduces the cause
on throwaway tables (never the project tables) and measures four ways to build the same row under a
role that holds `INSERT` on the two columns the code really sets. It changes nothing in the
application: the outcome is a proposal in `reports/group-6/orm-insert-columns-analysis.md`.

- A, the models as they are today: the INSERT lists `locked_by` and `locked_until` as NULL because
  they have no default of any kind (SQLAlchemy sends every column without a server default); the
  role is refused.
- B, `server_default=FetchedValue()` on those columns plus `eager_defaults=False`: they are left out
  of the INSERT and nothing is returned for them, so no `SELECT` on them is needed either.
- C, a Core `insert().values(...)` with the two columns: nothing else is sent.
- D, a Python-side `default=None`: still sent (it does not help).
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import (
    DateTime,
    FetchedValue,
    LargeBinary,
    String,
    create_engine,
    event,
    insert,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)

ROLE = "tstrole_orm_probe"


class BaseA(DeclarativeBase):
    pass


class BaseB(DeclarativeBase):
    pass


class BaseD(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


class JobA(BaseA):  # the models of today
    __tablename__ = "tst_job"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_until: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)


class JobB(BaseB):  # FetchedValue + no eager fetch
    __tablename__ = "tst_job"
    __mapper_args__ = {"eager_defaults": False}
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True, server_default=FetchedValue()
    )
    locked_until: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=FetchedValue()
    )


class JobD(BaseD):  # a Python-side default of None
    __tablename__ = "tst_job"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    locked_until: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


def prepare(cluster: Cluster, database: str) -> str:
    with cluster.admin_connection(database) as conn:
        conn.execute(
            "CREATE TABLE public.tst_job (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "document_id uuid NOT NULL, payload bytea, locked_by varchar(64), "
            "locked_until timestamptz)"
        )
        conn.execute(f"CREATE ROLE {ROLE} LOGIN PASSWORD 'Probe-0123456789-abcdef' NOSUPERUSER")
        conn.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {ROLE}')
        conn.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
        # exactly what a minimal registration of a job needs: the two columns set, and the key back
        conn.execute(f"GRANT INSERT (document_id, payload) ON public.tst_job TO {ROLE}")
        conn.execute(f"GRANT SELECT (id) ON public.tst_job TO {ROLE}")
    return cluster.url(ROLE, "Probe-0123456789-abcdef", database)


def run(url: str, statements: list[str], action: Callable[[Session], None]) -> str | None:
    engine = create_engine(url)
    event.listen(
        engine,
        "before_cursor_execute",
        lambda conn, cur, stmt, params, ctx, many: statements.append(stmt),
    )
    try:
        with Session(engine) as session:
            action(session)
            session.commit()
        return None
    except ProgrammingError as exc:
        return str(getattr(exc.orig, "sqlstate", "?"))
    finally:
        engine.dispose()


def orm_insert(model: type[JobA] | type[JobB] | type[JobD]) -> Callable[[Session], None]:
    def action(session: Session) -> None:
        session.add(model(document_id=uuid.uuid4(), payload=b"abc"))
        session.flush()

    return action


def test_the_orm_variants_under_a_role_that_may_insert_only_the_columns_the_code_sets(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    url = prepare(cluster, database)
    sent: dict[str, list[str]] = {"A": [], "B": [], "C": [], "D": []}

    outcome_a = run(url, sent["A"], orm_insert(JobA))
    outcome_b = run(url, sent["B"], orm_insert(JobB))
    outcome_d = run(url, sent["D"], orm_insert(JobD))

    def core(session: Session) -> None:
        session.execute(
            insert(JobA).values(document_id=uuid.uuid4(), payload=b"abc").returning(JobA.id)
        )

    outcome_c = run(url, sent["C"], core)

    insert_a = next(s for s in sent["A"] if s.startswith("INSERT"))
    assert "locked_by" in insert_a and "locked_until" in insert_a  # the cause
    assert outcome_a == "42501"
    assert outcome_d == "42501" and "locked_by" in next(
        s for s in sent["D"] if s.startswith("INSERT")
    )

    insert_b = next(s for s in sent["B"] if s.startswith("INSERT"))
    assert "locked_by" not in insert_b and "locked_until" not in insert_b
    assert (
        "RETURNING tst_job.locked_by" not in insert_b
        and "RETURNING tst_job.locked_until" not in insert_b
    )
    assert outcome_b is None

    insert_c = next(s for s in sent["C"] if s.startswith("INSERT"))
    assert "locked_by" not in insert_c and outcome_c is None

    with cluster.admin_connection(database) as conn:
        rows = conn.execute("SELECT count(*) FROM tst_job").fetchone()
    assert rows == (2,)  # B and C stored a row; A and D stored nothing
