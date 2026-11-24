"""Only one place deletes an enrolment, and it is the one that writes the marker.

Change `activity-privacy-hardening` (A2). The guarantee of the marker is "every removal sets it":
a second way to delete an enrolment would silently break it. The deletion of a subject or of an
account removes enrolments through the foreign keys (a cascade), which is not a route and is
covered by the right of erasure, so it is not looked for here.

This is a **best-effort tripwire** on the text of `app/`, not a proof: it cannot see a deletion
built from strings or outside the package. The behaviour is shown by the integration tests (the
route sets the marker); a database-level trigger would be sturdier but would also fire on the
cascade of an erased account, which the owner excluded.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
DELETIONS = re.compile(
    r"delete\(\s*(?:\w+\.)?Enrollment\b|Enrollment\.__table__|DELETE\s+FROM\s+(?:public\.)?enrollments"
    r"|TRUNCATE[^;]*enrollments|session\.delete\(\s*enrol|\.delete\(\s*enrollment"
    r"|query\(\s*(?:\w+\.)?Enrollment\b[^)]*\)[^\n]*\.delete\(",
    re.IGNORECASE,
)


def test_the_only_deletion_of_an_enrolment_is_the_repository_method_that_sets_the_marker() -> None:
    found = {
        path.relative_to(APP).as_posix(): len(DELETIONS.findall(path.read_text(encoding="utf-8")))
        for path in APP.rglob("*.py")
        if DELETIONS.search(path.read_text(encoding="utf-8"))
    }

    assert found == {"repositories/enrollment_repository.py": 1}


def test_that_method_writes_the_marker_before_it_deletes() -> None:
    source = (APP / "repositories" / "enrollment_repository.py").read_text(encoding="utf-8")
    body = source[source.index("def delete_for_teacher_subject") :]

    assert body.index("last_unenrolment_at") < body.index("delete(Enrollment)")
    assert body.index("lock_student_subject") < body.index("last_unenrolment_at")
