"""pytest options of the whole suite: the role-bound mode of the existing integration tests.

`pytest --least-privilege -m least_privilege tests/integration` runs the API and ingestion
integration tests of `LEAST_PRIVILEGE_MODULES` with the code under test connected as its
production role (see `tests/least_privilege.py`). Without the option the same tests run as
before. Change `database-least-privilege`, task 9.3.
"""

import gc
import os
from collections.abc import Iterator

import pytest

from tests.least_privilege import ENV_FLAG, enabled

# The existing API and ingestion modules that also run under the roles (marker `least_privilege`).
LEAST_PRIVILEGE_MODULES = frozenset(
    {
        "test_auth_register",
        "test_auth_login",
        "test_auth_logging",
        "test_users_me",
        "test_consent",
        "test_subjects_api",
        "test_enrollments_api",
        "test_documents_api",
        "test_documents_leaks",
        "test_role_guards",
        "test_transaction",
        "test_error_text_exposure",
        "test_review_hardening",
        "test_adversarial_probes",
        "test_email_ascii",
        "test_health",
        "test_least_privilege_mode",
        "test_ingestion_end_to_end",
        "test_ingestion_service",
        "test_ingestion_final_transaction",
        "test_ingestion_lease_fencing",
        "test_ingestion_heartbeat",
        "test_ingestion_job_repository",
        "test_chat_endpoint",
        "test_conversations_api",
        "test_chat_errors",
        "test_chat_failures_and_citations",
        "test_chat_rate_limit",
        "test_rag_quality",
    }
)


# Integration tests that build their own clusters, roles and databases: they need the disposable
# cluster of the privilege gate (marker `role_bound`) and are left out of the ordinary backend job.
ROLE_BOUND_PREFIXES = (
    "test_db_",
    "test_orm_insert_",
    "test_consent_persistence",
    "test_endpoint_commit_persistence",
    "test_least_privilege_coverage",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--least-privilege",
        action="store_true",
        default=False,
        help="run the marked integration tests with the code under test as its production role",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "least_privilege: also runs under the least-privilege database roles"
    )
    config.addinivalue_line(
        "markers",
        "role_bound: needs the disposable cluster of the privilege gate (CI job privileges)",
    )
    if config.getoption("--least-privilege"):
        os.environ[ENV_FLAG] = "1"
    os.environ.setdefault("GOOGLE_API_KEY", "AIza-test-key-for-unit-tests-only")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    kept: list[pytest.Item] = []
    dropped: list[pytest.Item] = []
    for item in items:
        if item.path.stem.startswith(ROLE_BOUND_PREFIXES):
            item.add_marker(pytest.mark.role_bound)
        if item.path.stem in LEAST_PRIVILEGE_MODULES:
            item.add_marker(pytest.mark.least_privilege)
        elif config.getoption("--least-privilege"):
            dropped.append(item)
            continue
        kept.append(item)
    if dropped:  # the role-bound mode runs the marked modules only
        config.hook.pytest_deselected(items=dropped)
        items[:] = kept


@pytest.fixture(autouse=True)
def release_leaked_connections() -> Iterator[None]:
    """Roles mode only: the roles have connection limits (application 20), and a test that leaves
    an engine to the garbage collector would hold slots until the next collection. The limits are
    part of the design and are not raised; the leaked engines are collected before each test."""
    if enabled():
        gc.collect()
    yield
