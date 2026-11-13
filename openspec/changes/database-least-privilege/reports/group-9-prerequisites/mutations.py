"""Mutations of the group 9 prerequisites (task 8A.8), applied to a COPY of the code, never to the repo.

usage:
  python mutations.py check <backend dir>              every `old` text exists exactly once
  python mutations.py list                             one line per mutation: index, label
  python mutations.py apply <index> <backend copy>     edit the copy, print the test targets

A mutation is "caught" when the listed tests fail on the edited copy; the harness also runs the
same tests on the unedited copy first to prove they pass.
"""

import sys
from pathlib import Path

SQL = "tests/integration/test_orm_insert_sql.py"
UNIT_FETCHED = "tests/unit/test_fetched_value_columns.py"
UNIT_COMMITS = "tests/unit/test_endpoint_commits.py"
HTTP = "tests/integration/test_endpoint_commit_persistence.py"
DENIED = "tests/integration/test_db_roles_paths.py"
MATRIX = "tests/unit/test_db_privileges_matrix.py"
PATHS = "tests/integration/test_db_roles_paths.py"

# (label, file, old text, new text, pytest targets relative to the backend directory)
MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "pair 1: the job lease columns lose FetchedValue",
        "app/models/ingestion.py",
        "        String(CLAIM_TOKEN_MAX_LENGTH), nullable=True, server_default=FetchedValue()\n",
        "        String(CLAIM_TOKEN_MAX_LENGTH), nullable=True\n",
        [f"{UNIT_FETCHED}::test_the_column_is_a_fetched_server_value", f"{SQL}::test_a_job_insert_omits_the_fencing_token_and_asks_nothing_back_about_it"],
    ),
    (
        "pair 1: the job mapper fetches defaults eagerly again",
        "app/models/ingestion.py",
        '    __mapper_args__ = {"eager_defaults": False}\n',
        "",
        [f"{UNIT_FETCHED}::test_the_job_mapper_does_not_ask_for_the_server_values_back", f"{SQL}::test_a_job_insert_omits_the_fencing_token_and_asks_nothing_back_about_it"],
    ),
    (
        "pair 1: the matrix gives the application role INSERT on locked_by again",
        "app/db_privileges.py",
        '            insert=_cols("document_id", "payload"),',
        '            insert=_cols("document_id", "payload", "locked_by"),',
        [f"{UNIT_FETCHED}::test_the_matrix_grants_the_application_role_only_what_the_job_insert_sets", f"{MATRIX}::test_matrix_equals_what_the_code_needs"],
    ),
    (
        "pair 1: the matrix lets the application role read the fencing token",
        "app/db_privileges.py",
        '            select=_cols("id", "payload"),',
        '            select=_cols("id", "payload", "locked_by"),',
        [f"{MATRIX}::test_matrix_equals_what_the_code_needs"],
    ),
    (
        "pair 2: the document error columns lose FetchedValue",
        "app/models/document.py",
        "        String(40), nullable=True, server_default=FetchedValue()\n",
        "        String(40), nullable=True\n",
        [f"{UNIT_FETCHED}::test_the_column_is_a_fetched_server_value", f"{SQL}::test_a_document_insert_omits_the_error_columns"],
    ),
    (
        "pair 2: the matrix gives the application role INSERT on error_message again",
        "app/db_privileges.py",
        '            insert=_cols("subject_id", "filename", "content_type", "size_bytes", "status"),',
        '            insert=_cols(\n                "subject_id", "filename", "content_type", "size_bytes", "status", "error_message"\n            ),',
        [f"{UNIT_FETCHED}::test_the_matrix_grants_the_application_role_only_what_the_document_insert_sets", f"{MATRIX}::test_matrix_equals_what_the_code_needs"],
    ),
    (
        "pair 3: the user consent columns lose FetchedValue",
        "app/models/user.py",
        "        String(20), nullable=True, server_default=FetchedValue()\n",
        "        String(20), nullable=True\n",
        [f"{UNIT_FETCHED}::test_the_column_is_a_fetched_server_value", f"{SQL}::test_a_registration_insert_omits_the_consent_and_the_role"],
    ),
    (
        "pair 3: the matrix gives the application role INSERT on consent_version again",
        "app/db_privileges.py",
        '            insert=_cols("name", "email", "password_hash"),\n            update=_cols("consent_version", "consent_accepted_at"),',
        '            insert=_cols("name", "email", "password_hash", "consent_version"),\n            update=_cols("consent_version", "consent_accepted_at"),',
        [f"{UNIT_FETCHED}::test_the_matrix_grants_the_runtime_roles_only_what_the_user_insert_sets", f"{MATRIX}::test_matrix_equals_what_the_code_needs"],
    ),
    (
        "TD-039: registration does not commit before the response",
        "app/api/v1/endpoints/auth.py",
        "    commit_or_rollback(db)\n",
        "",
        [f"{UNIT_COMMITS}::test_the_commit_follows_the_service_and_precedes_the_response", f"{HTTP}::test_registration_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "TD-039: create subject does not commit before the response",
        "app/api/v1/endpoints/subjects.py",
        "    commit_or_rollback(db)  # stored before the 201 is built\n",
        "",
        [f"{UNIT_COMMITS}::test_the_commit_follows_the_service_and_precedes_the_response", f"{HTTP}::test_a_subject_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "TD-039: delete subject does not commit before the response",
        "app/api/v1/endpoints/subjects.py",
        "    commit_or_rollback(db)  # the deletion is durable before the 204 is built\n",
        "",
        [f"{UNIT_COMMITS}::test_the_commit_follows_the_service_and_precedes_the_response", f"{HTTP}::test_a_subject_deletion_is_stored_when_it_answers_204_and_keeps_the_row_when_refused"],
    ),
    (
        "TD-039: enrollment does not commit before the response",
        "app/api/v1/endpoints/enrollments.py",
        "    commit_or_rollback(db)  # stored before the 201 is built\n",
        "",
        [f"{UNIT_COMMITS}::test_the_commit_follows_the_service_and_precedes_the_response", f"{HTTP}::test_an_enrollment_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "TD-039: enrollment removal does not commit before the response",
        "app/api/v1/endpoints/enrollments.py",
        "    commit_or_rollback(db)  # the removal is durable before the 204 is built\n",
        "",
        [f"{UNIT_COMMITS}::test_the_commit_follows_the_service_and_precedes_the_response", f"{HTTP}::test_an_enrollment_removal_is_stored_when_it_answers_204_and_keeps_the_row_when_refused"],
    ),
    (
        "TD-039: the helper no longer rolls back",
        "app/api/transaction.py",
        "        db.rollback()\n        raise\n",
        "        raise\n",
        [f"{UNIT_COMMITS}::test_a_refused_commit_rolls_back_and_never_returns_a_response"],
    ),
    (
        "TD-039: the helper swallows the database error",
        "app/api/transaction.py",
        "        db.rollback()\n        raise\n",
        "        db.rollback()\n",
        [f"{UNIT_COMMITS}::test_a_refused_commit_rolls_back_and_never_returns_a_response", f"{HTTP}::test_registration_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "TD-039: the helper commits twice",
        "app/api/transaction.py",
        "    try:\n        db.commit()\n",
        "    try:\n        db.commit()\n        db.commit()\n",
        [f"{UNIT_COMMITS}::test_the_commit_follows_the_service_and_precedes_the_response"],
    ),
    # ---- integration-level and inventory mutations (review M1): the integration target comes first,
    # so the harness (which stops at the first failure) is caught by the integration test.
    (
        "integration: the job lease column locked_until loses FetchedValue",
        "app/models/ingestion.py",
        "        DateTime(timezone=True), nullable=True, server_default=FetchedValue()\n    )\n    available_at",
        "        DateTime(timezone=True), nullable=True\n    )\n    available_at",
        [f"{SQL}::test_a_job_insert_omits_the_fencing_token_and_asks_nothing_back_about_it"],
    ),
    (
        "integration: documents.error_message loses FetchedValue",
        "app/models/document.py",
        "        Text, nullable=True, server_default=FetchedValue()\n",
        "        Text, nullable=True\n",
        [f"{SQL}::test_a_document_insert_omits_the_error_columns"],
    ),
    (
        "integration: users.consent_accepted_at loses FetchedValue",
        "app/models/user.py",
        "        DateTime(timezone=True), nullable=True, server_default=FetchedValue()\n",
        "        DateTime(timezone=True), nullable=True\n",
        [f"{SQL}::test_a_registration_insert_omits_the_consent_and_the_role"],
    ),
    (
        "integration: the application role may insert locked_by (the refusal test must fail)",
        "app/db_privileges.py",
        '            insert=_cols("document_id", "payload"),',
        '            insert=_cols("document_id", "payload", "locked_by"),',
        [f"{PATHS}::test_columns_and_operations_that_are_not_granted_are_refused_and_change_nothing"],
    ),
    (
        "integration: registration does not commit before the response",
        "app/api/v1/endpoints/auth.py",
        "    commit_or_rollback(db)\n",
        "",
        [f"{HTTP}::test_registration_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "integration: create subject does not commit before the response",
        "app/api/v1/endpoints/subjects.py",
        "    commit_or_rollback(db)  # stored before the 201 is built\n",
        "",
        [f"{HTTP}::test_a_subject_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "integration: delete subject does not commit before the response",
        "app/api/v1/endpoints/subjects.py",
        "    commit_or_rollback(db)  # the deletion is durable before the 204 is built\n",
        "",
        [f"{HTTP}::test_a_subject_deletion_is_stored_when_it_answers_204_and_keeps_the_row_when_refused"],
    ),
    (
        "integration: enrollment does not commit before the response",
        "app/api/v1/endpoints/enrollments.py",
        "    commit_or_rollback(db)  # stored before the 201 is built\n",
        "",
        [f"{HTTP}::test_an_enrollment_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused"],
    ),
    (
        "integration: enrollment removal does not commit before the response",
        "app/api/v1/endpoints/enrollments.py",
        "    commit_or_rollback(db)  # the removal is durable before the 204 is built\n",
        "",
        [f"{HTTP}::test_an_enrollment_removal_is_stored_when_it_answers_204_and_keeps_the_row_when_refused"],
    ),
    (
        "inventory: RETURNING always asks for the server-generated columns",
        "tests/privilege_inventory.py",
        "{_PRIMARY_KEY[name]} | (set() if name in _EAGER_FALSE else _SERVER_GENERATED[name])",
        "{_PRIMARY_KEY[name]} | _SERVER_GENERATED[name]",
        [f"{UNIT_FETCHED}::test_the_api_inventory_needs_no_insert_on_the_pair_of_ingestion_jobs"],
    ),
    (
        "helper: only ValueError is rolled back",
        "app/api/transaction.py",
        "    except Exception:\n",
        "    except ValueError:\n",
        [f"{UNIT_COMMITS}::test_a_refused_commit_rolls_back_and_never_returns_a_response"],
    ),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check(backend: Path) -> int:
    missing = 0
    for index, (label, rel, old, _new, _targets) in enumerate(MUTATIONS):
        found = _read(backend / rel).count(old)
        if found != 1:
            print(f"{index}: {found} occurrences of the text to mutate: {label}")
            missing += 1
    print(f"{len(MUTATIONS)} mutations, {missing} problem(s)")
    return 1 if missing else 0


def main() -> int:
    command = sys.argv[1]
    if command == "list":
        for index, (label, *_rest) in enumerate(MUTATIONS):
            print(f"{index}\t{label}")
        return 0
    if command == "check":
        return check(Path(sys.argv[2]))
    if command == "apply":
        index, backend = int(sys.argv[2]), Path(sys.argv[3])
        _label, rel, old, new, targets = MUTATIONS[index]
        path = backend / rel
        text = _read(path)
        assert text.count(old) == 1, "the text to mutate must appear exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(" ".join(targets))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
