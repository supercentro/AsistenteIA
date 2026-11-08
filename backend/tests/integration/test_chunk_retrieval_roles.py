"""`find_similar` checks the real role of the user in SQL (F7) and rejects bad subject ids (F8).

The declared `SearchActor.role` only chooses the branch; the database decides. Rows are written
with raw SQL because the services that keep roles consistent belong to later changes.
"""

import uuid
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.vector_validation import InvalidSearchInputError
from app.models.user import UserRole
from app.repositories.chunk_repository import ChunkRepository, SearchActor
from tests import embeddings as emb
from tests.catalog import Catalog, build_catalog
from tests.sql_support import insert_enrollment, insert_subject, insert_user, run

SECRET_TEXT = "secret-subject-text"


@pytest.fixture
def catalog(clean_db: str) -> Catalog:
    return build_catalog(clean_db)


def hits(session: Session, actor: SearchActor, subject: uuid.UUID, catalog: Catalog) -> int:
    return len(ChunkRepository(session).find_similar(actor, subject, catalog.query, 10))


def test_control_genuine_actors_still_get_results(db_session: Session, catalog: Catalog) -> None:
    assert hits(
        db_session, SearchActor(catalog.student_algebra, UserRole.STUDENT), catalog.algebra, catalog
    )
    assert hits(
        db_session, SearchActor(catalog.teacher_one, UserRole.TEACHER), catalog.algebra, catalog
    )


def test_a_teacher_enrolled_as_a_student_cannot_search_by_declaring_student(
    clean_db: str, db_session: Session, catalog: Catalog
) -> None:
    insert_enrollment(clean_db, catalog.chemistry, catalog.teacher_one)  # teacher_one is a teacher
    actor = SearchActor(catalog.teacher_one, UserRole.STUDENT)
    assert hits(db_session, actor, catalog.chemistry, catalog) == 0


def test_the_owner_of_a_subject_enrolled_in_it_cannot_search_by_declaring_student(
    clean_db: str, db_session: Session, catalog: Catalog
) -> None:
    insert_enrollment(clean_db, catalog.algebra, catalog.teacher_one)
    actor = SearchActor(catalog.teacher_one, UserRole.STUDENT)
    assert hits(db_session, actor, catalog.algebra, catalog) == 0


def test_a_student_who_owns_a_subject_cannot_search_by_declaring_teacher(
    clean_db: str, db_session: Session, catalog: Catalog
) -> None:
    run(
        clean_db,
        "UPDATE subjects SET teacher_id = :student WHERE id = :subject",
        student=catalog.student_algebra,
        subject=catalog.algebra,
    )
    actor = SearchActor(catalog.student_algebra, UserRole.TEACHER)
    assert hits(db_session, actor, catalog.algebra, catalog) == 0


def test_a_student_cannot_search_a_subject_by_declaring_teacher(
    db_session: Session, catalog: Catalog
) -> None:
    actor = SearchActor(catalog.student_both, UserRole.TEACHER)
    assert hits(db_session, actor, catalog.algebra, catalog) == 0


def test_a_teacher_cannot_search_another_teachers_subject_by_declaring_student(
    db_session: Session, catalog: Catalog
) -> None:
    actor = SearchActor(catalog.teacher_two, UserRole.STUDENT)
    assert hits(db_session, actor, catalog.algebra, catalog) == 0


def test_an_actor_that_does_not_exist_gets_nothing_with_either_role(
    db_session: Session, catalog: Catalog
) -> None:
    ghost = uuid.uuid4()
    for role in (UserRole.STUDENT, UserRole.TEACHER):
        assert hits(db_session, SearchActor(ghost, role), catalog.algebra, catalog) == 0


def test_a_user_whose_role_was_changed_in_the_database_loses_access(
    clean_db: str, db_session: Session, catalog: Catalog
) -> None:
    run(
        clean_db,
        "UPDATE users SET role = CAST('teacher' AS user_role) WHERE id = :uid",
        uid=catalog.student_algebra,
    )
    actor = SearchActor(catalog.student_algebra, UserRole.STUDENT)
    assert hits(db_session, actor, catalog.algebra, catalog) == 0


def test_a_new_teacher_with_a_new_subject_is_authorized_by_the_database(
    clean_db: str, db_session: Session, catalog: Catalog
) -> None:
    teacher = insert_user(clean_db, "late-teacher@example.test", "teacher")
    insert_subject(clean_db, teacher, "Empty")
    actor = SearchActor(teacher, UserRole.TEACHER)
    assert hits(db_session, actor, catalog.algebra, catalog) == 0  # someone else's subject


# ---------------------------------------------------------------- F8: malformed subject ids


@pytest.mark.parametrize(
    "bad",
    [SECRET_TEXT, "", 42, None, b"abc", object(), "00000000-0000-0000-0000-000000000000x"],
)
def test_a_subject_id_that_is_not_a_uuid_is_rejected_before_any_statement(bad: object) -> None:
    session = MagicMock()
    actor = SearchActor(uuid.uuid4(), UserRole.TEACHER)
    with pytest.raises(InvalidSearchInputError) as caught:
        ChunkRepository(session).find_similar(actor, cast(Any, bad), emb.basis(0), 5)
    session.execute.assert_not_called()
    assert SECRET_TEXT not in str(caught.value)
    assert "0000" not in str(caught.value)


def test_an_unknown_but_well_formed_subject_still_returns_an_empty_list(
    db_session: Session, catalog: Catalog
) -> None:
    actor = SearchActor(catalog.teacher_one, UserRole.TEACHER)
    assert ChunkRepository(db_session).find_similar(actor, uuid.uuid4(), catalog.query, 5) == []
