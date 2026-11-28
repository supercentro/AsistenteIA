"""Who may touch the topic tables (change `frequent-questions-and-topics`, design D7)."""

import pytest

from app.db_privileges import APP, CLI, MATRIX, WORKER, TableGrant

SETS = "document_topic_sets"
TOPICS = "document_topics"


def test_the_api_reads_inserts_updates_the_set_and_replaces_the_topics() -> None:
    sets, topics = MATRIX[APP][SETS], MATRIX[APP][TOPICS]
    assert sets.insert == {"document_id", "subject_id", "source", "revision"}
    assert sets.update == {"source", "revision", "ranges_changed_at"}
    assert not sets.delete  # the marker must outlive an emptied set
    assert topics.insert == {"document_id", "position", "title", "start_page", "end_page"}
    assert topics.update == frozenset() and topics.delete


def test_the_worker_only_creates_them() -> None:
    for table in (SETS, TOPICS):
        grant = MATRIX[WORKER][table]
        assert grant.insert and not grant.update and not grant.delete
    assert "ranges_changed_at" not in MATRIX[WORKER][SETS].insert


@pytest.mark.parametrize("table", [SETS, TOPICS])
def test_the_cli_has_no_access(table: str) -> None:
    assert MATRIX[CLI][table] == TableGrant()
