"""The role-bound mode connects the code under test as its production role (task 9.3).

Without `--least-privilege` the code under test connects with the guarded test URL (a superuser of
the disposable cluster). With it, the API connects as the application role and the ingestion
service as the worker role, neither of which is a superuser: the existing tests that carry the
marker `least_privilege` therefore prove something only because this test passes.
"""

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.database import create_db_engine
from app.db_admin.names import RoleNames
from tests.integration.helpers import build_settings
from tests.least_privilege import enabled
from tests.role_support import TEST_ROLE_PREFIX
from tests.service_support import built_service


def current_role(url: str) -> tuple[str, bool]:
    engine = create_db_engine(url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT current_user, r.rolsuper FROM pg_roles r WHERE r.rolname = current_user"
                )
            ).one()
        return str(row[0]), bool(row[1])
    finally:
        engine.dispose()


def test_the_code_under_test_connects_as_its_production_role(clean_db: str) -> None:
    names = RoleNames.with_prefix(TEST_ROLE_PREFIX)
    api_url = str(build_settings(clean_db).database_url)
    with built_service(clean_db) as built:
        worker_url = built.engine.url.render_as_string(hide_password=False)

    api_user, api_super = current_role(api_url)
    worker_user, worker_super = current_role(worker_url)

    if enabled():
        assert (api_user, worker_user) == (names.app, names.worker)
        assert not api_super and not worker_super
        assert make_url(api_url).database == make_url(clean_db).database
    else:
        assert not api_user.startswith(TEST_ROLE_PREFIX)
        assert not worker_user.startswith(TEST_ROLE_PREFIX)
