"""The activity probe attributes locks and transactions to the service under test.

Flaky CI run after the archive of `document-ingestion`: `test_no_transaction_lock_or_connection_
while_the_pdf_child_runs` saw `[(0, 0, 4, 0)]` instead of `[(0, 0, 0, 0)]`. The probe counted the
locks of every backend connected to the test database, while the service held nothing: a
maintenance session (for example an autovacuum or analyze pass after the bulk inserts of the
previous tests, which locks a table and its indexes) is enough to make the count positive. The
probe now looks only at the backends opened by the service under test (`Built.backends`).
"""

from sqlalchemy import text

from app.core.database import create_db_engine
from app.rag.chunker import Page
from app.services.ingestion_service import Outcome
from tests.ingestion_support import insert_pending, make_scene
from tests.service_support import activity, built_service, checked_out


def test_a_lock_held_by_an_unrelated_session_is_not_attributed_to_the_service(
    clean_db: str,
) -> None:
    stranger = create_db_engine(clean_db)
    try:
        with built_service(clean_db) as built, stranger.connect() as other:
            other.execute(text("LOCK TABLE ingestion_jobs IN ACCESS SHARE MODE"))

            everyone = activity(clean_db)
            service_only = activity(clean_db, built.backends)

        assert everyone.locks >= 1  # the old, database-wide probe: a false positive
        assert (service_only.idle_in_transaction, service_only.open_transactions) == (0, 0)
        assert service_only.locks == 0
    finally:
        stranger.dispose()


def test_a_transaction_held_by_an_unrelated_session_is_not_attributed_to_the_service(
    clean_db: str,
) -> None:
    stranger = create_db_engine(clean_db)
    try:
        with built_service(clean_db) as built, stranger.connect() as other:
            other.execute(text("SELECT 1"))  # opens a transaction that stays open

            service_only = activity(clean_db, built.backends)

        assert (service_only.idle_in_transaction, service_only.open_transactions) == (0, 0)
        assert service_only.stuck_in_transaction == 0
    finally:
        stranger.dispose()


def test_a_lock_and_a_transaction_held_by_the_service_are_detected(clean_db: str) -> None:
    # The negative case: the probe still catches what the requirement forbids.
    with built_service(clean_db) as built, built.factory() as session:
        session.execute(text("LOCK TABLE ingestion_jobs IN ACCESS SHARE MODE"))

        seen = activity(clean_db, built.backends)
        held = checked_out(built.engine)

    assert seen.locks >= 1
    assert seen.open_transactions == 1
    assert seen.idle_in_transaction == 1
    assert held == 1


def test_the_service_backends_are_known_while_they_are_open_and_forgotten_when_closed(
    clean_db: str,
) -> None:
    with built_service(clean_db) as built:
        assert built.backends == set()  # nothing is connected before the first use

        with built.factory() as session:
            session.execute(text("SELECT 1"))
            assert len(built.backends) == 1

        built.engine.dispose()
        assert built.backends == set()


def test_the_scenario_of_the_flaky_run_passes_with_a_maintenance_session_holding_locks(
    clean_db: str,
) -> None:
    scene = make_scene(clean_db)
    insert_pending(scene.url, scene.subject)  # application/pdf, the bytes are irrelevant
    stranger = create_db_engine(clean_db)
    samples: list[tuple[int, int, int, int]] = []
    database_wide: list[int] = []

    def loader(payload: bytes) -> list[Page]:
        seen = activity(scene.url, built.backends)
        held = checked_out(built.engine)
        samples.append((seen.idle_in_transaction, seen.open_transactions, seen.locks, held))
        database_wide.append(activity(scene.url).locks)
        return [Page(1, "page text")]

    try:
        with built_service(scene.url, pdf_loader=loader) as built, stranger.connect() as other:
            other.execute(text("LOCK TABLE ingestion_jobs IN ACCESS SHARE MODE"))
            outcome = built.service.run_once()
    finally:
        stranger.dispose()

    assert outcome is Outcome.READY
    assert samples == [(0, 0, 0, 0)]
    assert database_wide[0] >= 1  # what the old probe reported as a violation
