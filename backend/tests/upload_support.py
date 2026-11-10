"""Helpers for the document endpoint tests (change 6, group 9).

Requests are built here so every test states only what is special about it. Rows are counted and
read with SQL (never with the repositories under test).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi.testclient import TestClient
from httpx2 import Response

from app.models.user import UserRole
from tests.integration.helpers import TestUser, bearer, insert_subject, insert_user, login_token
from tests.sql_support import count

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
TEXT = "Las derivadas miden el cambio de una función. Ñandú.".encode()


def documents_url(subject: str | uuid.UUID) -> str:
    return f"/api/v1/subjects/{subject}/documents"


def document_url(subject: str | uuid.UUID, document: str | uuid.UUID) -> str:
    return f"/api/v1/subjects/{subject}/documents/{document}"


@dataclass(frozen=True)
class World:
    """A teacher with a subject, another teacher with a subject, and a student."""

    url: str
    teacher: TestUser
    subject: str
    other_teacher: TestUser
    other_subject: str
    student: TestUser


def make_world(url: str) -> World:
    teacher = insert_user(url, "teacher@example.com", UserRole.TEACHER)
    other = insert_user(url, "other.teacher@example.com", UserRole.TEACHER)
    student = insert_user(url, "student@example.com", UserRole.STUDENT)
    return World(
        url,
        teacher,
        insert_subject(url, teacher.id, "Algebra"),
        other,
        insert_subject(url, other.id, "Physics"),
        student,
    )


def auth(client: TestClient, user: TestUser) -> dict[str, str]:
    return bearer(login_token(client, user.email))


def upload(
    client: TestClient,
    headers: Mapping[str, str] | None,
    subject: str | uuid.UUID,
    name: str = "notes.txt",
    content: bytes = TEXT,
    client_type: str = "application/octet-stream",
) -> Response:
    """POST one file part named `file`."""
    response: Response = client.post(
        documents_url(subject),
        files={"file": (name, content, client_type)},
        headers=dict(headers or {}),
    )
    return response


def raw_upload(
    client: TestClient,
    headers: Mapping[str, str],
    subject: str | uuid.UUID,
    body: bytes,
    content_type: str,
    extra: Mapping[str, str] | None = None,
) -> Response:
    """POST an exact body (for malformed and abusive multipart structures)."""
    response: Response = client.post(
        documents_url(subject),
        content=body,
        headers={**headers, "Content-Type": content_type, **(extra or {})},
    )
    return response


BOUNDARY = "testboundary7f3a"
MULTIPART = f"multipart/form-data; boundary={BOUNDARY}"


def part(name: str, value: bytes, filename: str | None = None) -> bytes:
    disposition = f'form-data; name="{name}"'
    if filename is not None:
        disposition += f'; filename="{filename}"'
    return f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n\r\n".encode() + value + b"\r\n"


def multipart_body(*parts: bytes) -> bytes:
    return b"".join(parts) + f"--{BOUNDARY}--\r\n".encode()


def stored(url: str) -> dict[str, int]:
    """How many rows of each table that an upload writes (all zero means nothing was stored)."""
    return {
        "documents": count(url, "documents"),
        "jobs": count(url, "ingestion_jobs"),
        "payloads": count(url, "ingestion_jobs", "payload IS NOT NULL"),
        "chunks": count(url, "document_chunks"),
    }


NOTHING = {"documents": 0, "jobs": 0, "payloads": 0, "chunks": 0}
