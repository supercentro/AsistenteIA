"""Mutations of the role-bound suite (task 9.4), applied to a COPY of the code, never to the repo.

usage:
  python mutations.py check <backend dir>              every `old` text exists exactly once
  python mutations.py list                             one line per mutation: index, label
  python mutations.py apply <index> <backend copy>     edit the copy, print the test targets

A mutation may change several files (an entry is a list of edits): the first ones show that a
privilege removed behind a success status is caught by the persisted-state assertion. A mutation is
"caught" when the listed tests fail on the edited copy; the harness first runs the same tests on
the unedited copy to prove they pass.
"""

import sys
from pathlib import Path

ROUTES = "tests/integration/test_db_roles_api_routes.py"
COVERAGE = "tests/integration/test_least_privilege_coverage.py"
MODE = "tests/integration/test_least_privilege_mode.py --least-privilege -m least_privilege"
PATHS = "tests/integration/test_db_roles_paths.py"
TEACHER = "tests/integration/test_db_roles_teacher.py"

CONSENT_UPDATE = (
    'insert=_cols("name", "email", "password_hash"),\n'
    '            update=_cols("consent_version", "consent_accepted_at"),'
)
NO_CONSENT_UPDATE = 'insert=_cols("name", "email", "password_hash"),'
HELPER_COMMIT = "        db.commit()\n"
HELPER_NO_COMMIT = "        pass\n"
WORKER_DOCUMENT_UPDATE = (
    'update=_cols("status", "chunks_count", "error_code", "error_message"),'
)
APP_DOCUMENT_DELETE = (
    '            insert=_cols("subject_id", "filename", "content_type", "size_bytes", "status"),\n'
    "            delete=True,"
)
APP_DOCUMENT_NO_DELETE = (
    '            insert=_cols("subject_id", "filename", "content_type", "size_bytes", "status"),'
)
SCENARIO_ENTRY = (
    '    (\n        "DELETE",\n'
    '        f"{API}/subjects/{{subject_id}}/enrollments/{{student_id}}",\n'
    '    ): "test_subjects_and_enrollments_are_persisted_and_cascade",\n'
)
ROLE_URL_BODY = (
    "    if _cluster is None or _database is None:\n"
    "        return url\n"
    "    parts = make_url(url)\n"
    "    if parts.database != _database:\n"
    "        return url\n"
    "    return _cluster.role_url(logical, _database)"
)

Edit = tuple[str, str, str]  # file, old text, new text
MUTATIONS: list[tuple[str, list[Edit], list[str]]] = [
    (
        "the consent UPDATE privilege is removed AND the commit moves after the answer: the "
        "endpoint answers 200 and the persisted-state assertion is the only thing that fails",
        [
            ("app/db_privileges.py", CONSENT_UPDATE, NO_CONSENT_UPDATE),
            ("app/api/transaction.py", HELPER_COMMIT, HELPER_NO_COMMIT),
        ],
        [f"{ROUTES}::test_registration_login_profile_and_consent_are_persisted"],
    ),
    (
        "the consent UPDATE privilege is removed (the endpoint answers 500 instead)",
        [("app/db_privileges.py", CONSENT_UPDATE, NO_CONSENT_UPDATE)],
        [f"{ROUTES}::test_registration_login_profile_and_consent_are_persisted"],
    ),
    (
        "the worker loses UPDATE on documents",
        [("app/db_privileges.py", WORKER_DOCUMENT_UPDATE, "update=frozenset(),")],
        [f"{ROUTES}::test_text_and_markdown_are_uploaded_processed_retrieved_and_deleted"],
    ),
    (
        "the application role loses DELETE on documents",
        [("app/db_privileges.py", APP_DOCUMENT_DELETE, APP_DOCUMENT_NO_DELETE)],
        [f"{ROUTES}::test_text_and_markdown_are_uploaded_processed_retrieved_and_deleted"],
    ),
    (
        "a route loses its role-bound scenario",
        [(ROUTES, SCENARIO_ENTRY, "")],
        [f"{COVERAGE}::test_every_api_operation_has_a_role_bound_scenario"],
    ),
    (
        "the roles mode silently connects as the owner again",
        [("tests/least_privilege.py", ROLE_URL_BODY, "    return url")],
        [MODE],
    ),
    (
        "the CLI role loses INSERT on users.role (the CLI scenario must fail)",
        [
            (
                "app/db_privileges.py",
                '"name", "email", "password_hash", "role"),',
                '"name", "email", "password_hash"),',
            )
        ],
        [f"{TEACHER}::test_the_cli_role_creates_a_teacher_and_prints_no_secret"],
    ),
    (
        "a CLI subcommand loses its role-bound scenario",
        [
            (
                COVERAGE,
                '    "seed": ("test_db_roles_teacher", "test_the_seed_follows_the_same_path_under_the_cli_role"),\n',
                "",
            )
        ],
        [f"{COVERAGE}::test_every_cli_subcommand_has_a_role_bound_scenario"],
    ),
    (
        "a worker repository method loses its role-bound scenario",
        [
            (
                COVERAGE,
                '    "erase_payload": "test_the_worker_erases_a_payload_and_clears_the_lease_under_its_role",\n',
                "",
            )
        ],
        [f"{COVERAGE}::test_every_public_method_of_the_worker_repository_has_a_role_bound_scenario"],
    ),
    (
        "a scenario stops calling its route (the enrollment removal request disappears)",
        [
            (
                ROUTES,
                '        removed = client.delete(\n            f"{API}/subjects/{subject}/enrollments/{student.id}", headers=headers\n        )\n        assert removed.status_code == 204\n',
                "",
            )
        ],
        [f"{COVERAGE}::test_every_route_is_really_called_by_the_scenarios"],
    ),
    (
        "the worker role loses UPDATE on ingestion_jobs (erase and fail paths must fail)",
        [
            (
                "app/db_privileges.py",
                'update=_cols("payload", "attempts", "locked_by", "locked_until", "updated_at"),',
                "update=frozenset(),",
            )
        ],
        [f"{PATHS}::test_the_worker_erases_a_payload_and_clears_the_lease_under_its_role"],
    ),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check(backend: Path) -> int:
    missing = 0
    for index, (label, edits, _targets) in enumerate(MUTATIONS):
        for rel, old, _new in edits:
            found = _read(backend / rel).count(old)
            if found != 1:
                print(f"{index}: {found} occurrences of the text to mutate in {rel}: {label}")
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
        _label, edits, targets = MUTATIONS[index]
        for rel, old, new in edits:
            path = backend / rel
            text = _read(path)
            assert text.count(old) == 1, f"the text to mutate must appear exactly once in {rel}"
            path.write_text(text.replace(old, new), encoding="utf-8")
        print(" ".join(targets))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
