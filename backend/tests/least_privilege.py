"""Run the existing API and ingestion integration tests under the least-privilege roles.

Change `database-least-privilege`, task 9.3. With `pytest --least-privilege -m least_privilege` the
guarded test database is built the way production is (bootstrap with the reserved test role
names, Alembic as the migrator, the grants) instead of by a superuser, and the code under test
connects as the role it uses in production:

- `build_settings` (the API, through `create_app`) uses the application role;
- `built_service` (the ingestion service) uses the worker role;
- seeding and inspection helpers keep the guarded administrator URL, so the assertions of the
  existing tests are untouched.

Nothing here changes an assertion: the same tests run twice, as the owner and under the roles. The
cluster must be disposable (`TEST_CLUSTER_IS_DISPOSABLE=true`), exactly as for the other role-bound
tests, because the bootstrap closes `PUBLIC` on every database of the cluster.
"""

import os
import secrets

from sqlalchemy.engine import make_url

from app.db_admin.bootstrap import bootstrap
from app.db_admin.migrate import migrate
from app.db_admin.names import RoleNames, RolePasswords
from tests.db_admin_support import DISPOSABLE_FLAG, Cluster, assert_cluster_is_disposable
from tests.db_support import (
    MissingTestDatabaseError,
    drop_everything,
    require_test_admin_database_url,
)
from tests.role_support import TEST_ROLE_PREFIX, sweep_test_roles

ENV_FLAG = "LEAST_PRIVILEGE_ROLES"

_cluster: Cluster | None = None
_database: str | None = None


def enabled() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def activate(test_db_url: str) -> Cluster:
    """Build the guarded test database under the roles; the cluster must be disposable."""
    global _cluster, _database
    if os.environ.get(DISPOSABLE_FLAG, "").lower() != "true":
        raise MissingTestDatabaseError(
            f"{DISPOSABLE_FLAG}=true is required: the bootstrap closes PUBLIC on every database "
            "of the cluster, so the role-bound mode runs only against a disposable cluster"
        )
    cluster = Cluster(
        admin_url=require_test_admin_database_url(),
        names=RoleNames.with_prefix(TEST_ROLE_PREFIX),
        passwords=RolePasswords(
            migrator=secrets.token_urlsafe(24),
            app=secrets.token_urlsafe(24),
            worker=secrets.token_urlsafe(24),
            cli=secrets.token_urlsafe(24),
        ),
    )
    assert_cluster_is_disposable(cluster)
    database = make_url(test_db_url).database
    assert database is not None
    drop_everything(test_db_url)  # first: the objects an earlier run left to its roles
    with cluster.admin_connection() as conn:
        sweep_test_roles(conn)  # then the leftover roles of that run
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    migrate(cluster.migrator_url(database), names=cluster.names)
    _cluster, _database = cluster, database
    return cluster


def deactivate(test_db_url: str) -> None:
    global _cluster, _database
    _cluster = _database = None
    drop_everything(test_db_url)


def role_url(logical: str, url: str) -> str:
    """The same database with the credential of `logical` (app, worker, cli); a no-op otherwise."""
    if _cluster is None or _database is None:
        return url
    parts = make_url(url)
    if parts.database != _database:
        return url
    return _cluster.role_url(logical, _database)
