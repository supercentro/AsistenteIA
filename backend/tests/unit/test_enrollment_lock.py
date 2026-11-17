"""The advisory lock that serialises persisting a chat turn with removing an enrollment (M2)."""

import uuid
from typing import Any
from unittest.mock import MagicMock

from app.repositories.enrollment_repository import (
    ENROLLMENT_LOCK_SPACE,
    EnrollmentRepository,
    enrollment_lock_key,
)

STUDENT = uuid.UUID("11111111-1111-1111-1111-111111111111")
SUBJECT = uuid.UUID("22222222-2222-2222-2222-222222222222")


def test_the_key_is_stable() -> None:
    assert enrollment_lock_key(STUDENT, SUBJECT) == enrollment_lock_key(STUDENT, SUBJECT)
    assert enrollment_lock_key(STUDENT, SUBJECT) == enrollment_lock_key(
        uuid.UUID(str(STUDENT)), uuid.UUID(str(SUBJECT))
    )


def test_the_key_is_a_signed_32_bit_integer_and_the_space_fits_too() -> None:
    keys = [enrollment_lock_key(uuid.uuid5(STUDENT, str(i)), SUBJECT) for i in range(500)]

    assert all(-(2**31) <= key < 2**31 for key in keys)
    assert any(key < 0 for key in keys) and any(key > 0 for key in keys)
    assert 0 < ENROLLMENT_LOCK_SPACE < 2**31


def test_different_pairs_get_different_keys_and_the_order_matters() -> None:
    pairs = [(uuid.uuid5(STUDENT, str(i)), uuid.uuid5(SUBJECT, str(i))) for i in range(300)]

    assert len({enrollment_lock_key(student, subject) for student, subject in pairs}) == 300
    assert enrollment_lock_key(STUDENT, SUBJECT) != enrollment_lock_key(SUBJECT, STUDENT)


def test_removing_an_enrollment_takes_the_lock_before_it_deletes() -> None:
    session = MagicMock()
    seen: list[tuple[str, Any]] = []

    def execute(statement: Any, params: Any = None) -> MagicMock:
        seen.append((str(statement), params))
        return MagicMock(first=MagicMock(return_value=("row",)))

    session.execute.side_effect = execute

    removed = EnrollmentRepository(session).delete_for_teacher_subject(
        SUBJECT, uuid.uuid4(), STUDENT
    )

    assert removed is True
    assert "pg_advisory_xact_lock" in seen[0][0]
    assert seen[0][1] == {
        "space": ENROLLMENT_LOCK_SPACE,
        "key": enrollment_lock_key(STUDENT, SUBJECT),
    }
    assert "DELETE" in seen[1][0].upper()
    assert len(seen) == 2


def test_locking_executes_one_advisory_lock_statement() -> None:
    session = MagicMock()

    EnrollmentRepository(session).lock_student_subject(STUDENT, SUBJECT)

    assert session.execute.call_count == 1
    statement = str(session.execute.call_args.args[0])
    assert "pg_advisory_xact_lock(:space, :key)" in statement
