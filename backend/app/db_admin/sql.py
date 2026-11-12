"""Quoting, the client-side SCRAM verifier and the `Step` that carries a statement.

Identifiers are validated against a strict pattern before they reach a statement; literals are
only the SCRAM verifier. Statements are plain strings sent without parameters, so `%` and `$` in
them are never interpreted by the driver.
"""

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from typing import Final, LiteralString

from app.db_admin.errors import DbAdminError

IDENTIFIER: Final = re.compile(r"[a-z_][a-z0-9_]{0,62}")
VERIFIER_PATTERN: Final = r"SCRAM-SHA-256\$\d{1,7}:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+"
SCRAM_ITERATIONS: Final = 4096


class UnsafeIdentifierError(DbAdminError, ValueError):
    """A name is not a plain lowercase identifier; the value is not echoed."""


def quote_ident(name: str) -> str:
    """Quote a role or application database name chosen by us (strict pattern)."""
    if not IDENTIFIER.fullmatch(name):
        raise UnsafeIdentifierError(
            f"an identifier ({len(name)} characters) is not a lowercase [a-z0-9_] name"
        )
    return f'"{name}"'


def quote_catalog_name(name: str) -> str:
    """Quote a name that already exists in the cluster (any database name is legal in PostgreSQL).

    Refuses the characters that cannot be quoted safely instead of trying to escape them.
    """
    if (
        not name
        or len(name.encode("utf-8")) > 63
        or any(c in name for c in '"\\')
        or any(c < " " for c in name)
    ):
        raise UnsafeIdentifierError(f"a catalog name ({len(name)} characters) cannot be quoted")
    return f'"{name}"'


def quote_qualified(schema: str, name: str) -> str:
    """`"schema"."name"`: the sessions run with `search_path = pg_catalog`, so the tables and
    types of the application are always named with their schema."""
    return f"{quote_ident(schema)}.{quote_catalog_name(name)}"


def quote_literal(value: str) -> str:
    if any(c in value for c in "\x00\n\r\\"):
        raise DbAdminError("a literal contains characters that are not allowed")
    return "'" + value.replace("'", "''") + "'"


def _b64(raw_bytes: bytes) -> str:
    return base64.b64encode(raw_bytes).decode("ascii")


def scram_verifier(
    password: str, *, iterations: int = SCRAM_ITERATIONS, salt: bytes | None = None
) -> str:
    """SCRAM-SHA-256 verifier computed here (RFC 5802), so the clear text never reaches the server.

    ASCII only: SASLprep is the identity for it, and anything else would be hashed differently
    from what a client sends.
    """
    if not password.isascii():
        raise DbAdminError("a role password must be ASCII")
    salt = os.urandom(16) if salt is None else salt
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("ascii"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    return f"SCRAM-SHA-256${iterations}:{_b64(salt)}${_b64(stored_key)}:{_b64(server_key)}"


@dataclass(frozen=True)
class Step:
    """One statement with a description that is safe to print.

    `scope` is `cluster` (run from the `postgres` database) or `database` (run inside the
    application database). A `sensitive` step carries a verifier: only its description is shown.
    """

    description: str
    sql: str
    sensitive: bool = False
    scope: str = "cluster"

    def display(self) -> str:
        return self.description if self.sensitive else self.sql

    def __repr__(self) -> str:
        return f"Step({self.description!r})"


def raw(sql: str) -> LiteralString:
    """psycopg types its queries as literal strings; ours are validated before they get here."""
    return sql
