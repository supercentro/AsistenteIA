"""Migration 0009: `document_topic_sets` and `document_topics`.

Change `frequent-questions-and-topics`.

Built from scratch on the guarded test database; fictitious rows only.
"""

import uuid

import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from tests.db_support import alembic_config, drop_everything
from tests.sql_support import count, insert_chunk, run, scalar, seed_basic

TABLES = ("document_topic_sets", "document_topics")


def _exists(url: str, table: str) -> bool:
    return scalar(url, "SELECT to_regclass(:name) IS NOT NULL", name=table) is True


def _migrated(url: str) -> str:
    drop_everything(url)
    command.upgrade(alembic_config(url), "head")
    return url


def _insert_set(
    url: str, document: uuid.UUID, subject: uuid.UUID, source: str = "teacher", revision: int = 1
) -> None:
    run(
        url,
        "INSERT INTO document_topic_sets (document_id, subject_id, source, revision) "
        "VALUES (:d, :s, :source, :revision)",
        d=document,
        s=subject,
        source=source,
        revision=revision,
    )


def _insert_topic(
    url: str,
    document: uuid.UUID,
    position: int = 0,
    title: str = "Normalization",
    start: int = 1,
    end: int = 2,
) -> None:
    run(
        url,
        "INSERT INTO document_topics (document_id, position, title, start_page, end_page) "
        "VALUES (:d, :position, :title, :start, :end)",
        d=document,
        position=position,
        title=title,
        start=start,
        end=end,
    )


def test_upgrade_creates_the_tables_and_downgrade_removes_only_them(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0008")
    seed = seed_basic(test_db_url)
    insert_chunk(test_db_url, seed.document_id, seed.subject_id)
    assert not any(_exists(test_db_url, table) for table in TABLES)

    command.upgrade(config, "0009")
    assert all(_exists(test_db_url, table) for table in TABLES)

    command.downgrade(config, "0008")
    assert not any(_exists(test_db_url, table) for table in TABLES)
    assert count(test_db_url, "documents") == 1 and count(test_db_url, "document_chunks") == 1
    command.upgrade(config, "head")
    command.check(config)


def test_deleting_the_document_removes_its_set_and_topics(test_db_url: str) -> None:
    url = _migrated(test_db_url)
    seed = seed_basic(url)
    _insert_set(url, seed.document_id, seed.subject_id)
    _insert_topic(url, seed.document_id)

    run(url, "DELETE FROM documents WHERE id = :id", id=seed.document_id)

    assert count(url, "document_topic_sets") == 0 and count(url, "document_topics") == 0


def test_a_set_cannot_carry_another_subject_than_its_document(test_db_url: str) -> None:
    url = _migrated(test_db_url)
    seed, other = seed_basic(url), seed_basic(url)

    with pytest.raises(IntegrityError):
        _insert_set(url, seed.document_id, other.subject_id)


@pytest.mark.parametrize(
    ("position", "title", "start", "end"),
    [(-1, "t", 1, 1), (0, "   ", 1, 1), (0, "t", 0, 1), (0, "t", 3, 2)],
)
def test_invalid_topic_rows_are_refused(
    test_db_url: str, position: int, title: str, start: int, end: int
) -> None:
    url = _migrated(test_db_url)
    seed = seed_basic(url)
    _insert_set(url, seed.document_id, seed.subject_id)

    with pytest.raises(IntegrityError):
        _insert_topic(url, seed.document_id, position, title, start, end)


@pytest.mark.parametrize(("source", "revision"), [("model", 1), ("teacher", 0)])
def test_invalid_set_rows_are_refused(test_db_url: str, source: str, revision: int) -> None:
    url = _migrated(test_db_url)
    seed = seed_basic(url)

    with pytest.raises(IntegrityError):
        _insert_set(url, seed.document_id, seed.subject_id, source, revision)


def test_positions_are_unique_and_topics_need_a_set(test_db_url: str) -> None:
    url = _migrated(test_db_url)
    seed = seed_basic(url)
    with pytest.raises(IntegrityError):
        _insert_topic(url, seed.document_id)
    _insert_set(url, seed.document_id, seed.subject_id)
    _insert_topic(url, seed.document_id)
    with pytest.raises(IntegrityError):
        _insert_topic(url, seed.document_id)
