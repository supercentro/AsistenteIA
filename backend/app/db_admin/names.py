"""Physical role names, passwords and the per-role constants shared by the commands."""

from dataclasses import dataclass, field
from typing import Final

from app.db_privileges import APP, CLI, WORKER

# Persistent `search_path` of the runtime roles: they need `public` for the vector type and its
# operators. The administrator sessions of the commands use `pg_catalog` only (planting, B-01).
EXPECTED_SEARCH_PATH: Final = "pg_catalog, public"
# The migrator creates objects with unqualified names, and an unqualified CREATE lands in the first
# schema of the path: with `pg_catalog` first it would try to create in the catalog (found by the
# first run against a real server). It is a trusted role, so it keeps `public` (the catalog is
# always searched first anyway) while the runtime roles, which never create, list the catalog first.
SEARCH_PATHS: Final[dict[str, str]] = {
    "migrator": "public",
    "app": EXPECTED_SEARCH_PATH,
    "worker": EXPECTED_SEARCH_PATH,
    "cli": EXPECTED_SEARCH_PATH,
}

# Derived from the pools: the API engine holds up to 15 connections (5 + 10 overflow) plus
# maintenance; the worker keeps one session per job step plus the sweep; the migrator and the CLI
# are short-lived one-shots.
CONNECTION_LIMITS: Final[dict[str, int]] = {"migrator": 5, "app": 20, "worker": 10, "cli": 3}


@dataclass(frozen=True)
class RoleNames:
    migrator: str
    app: str
    worker: str
    cli: str

    @classmethod
    def with_prefix(cls, prefix: str) -> "RoleNames":
        return cls(
            migrator=f"{prefix}migrator",
            app=f"{prefix}app",
            worker=f"{prefix}worker",
            cli=f"{prefix}cli",
        )

    def all(self) -> tuple[str, str, str, str]:
        return (self.migrator, self.app, self.worker, self.cli)

    def runtime(self) -> tuple[str, str, str]:
        return (self.app, self.worker, self.cli)

    def for_logical(self, logical: str) -> str:
        return {APP: self.app, WORKER: self.worker, CLI: self.cli}[logical]


DEFAULT_NAMES: Final = RoleNames(
    migrator="asistente_migrator",
    app="asistente_app",
    worker="asistente_worker",
    cli="asistente_cli",
)


@dataclass(frozen=True)
class RolePasswords:
    """Clear-text passwords of the four roles; never printed."""

    migrator: str = field(repr=False)
    app: str = field(repr=False)
    worker: str = field(repr=False)
    cli: str = field(repr=False)

    def __str__(self) -> str:
        return "RolePasswords(<hidden>)"

    def __repr__(self) -> str:
        return "RolePasswords(<hidden>)"
