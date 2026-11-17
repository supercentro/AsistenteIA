"""The chat rate limit over real HTTP, on a server started with the production arguments.

`--no-proxy-headers` is what makes the client address the connection peer. `TestClient` has no
Uvicorn in front of the application, so only a real process proves that forged forwarding headers
cannot give each request its own budget (docs/base-standards.md section 9.2).
"""

import json
from collections.abc import Iterator

import pytest

from tests.server_support import Reply, Server, request, running_server

LIMIT = 3


@pytest.fixture(scope="module")
def server(migrated_db: str) -> Iterator[Server]:
    with running_server(migrated_db, LLM_BACKEND="fake", CHAT_RATE_LIMIT=f"{LIMIT}/minute") as s:
        yield s


def _chat(server: Server, forwarded: str) -> Reply:
    body = json.dumps({"subject_id": "00000000-0000-4000-8000-000000000001", "message": "hi"})
    return request(
        server,
        "POST",
        "/api/v1/chat",
        body=body.encode(),
        headers={
            "X-Forwarded-For": forwarded,
            "X-Real-IP": forwarded,
            "Forwarded": f"for={forwarded}",
        },
    )


def test_forged_forwarding_headers_do_not_give_each_request_its_own_budget(
    server: Server, clean_db: str
) -> None:
    replies = [_chat(server, f"203.0.113.{index}") for index in range(1, LIMIT + 3)]

    assert [reply.status for reply in replies] == [401] * LIMIT + [429] * 2
    assert int(replies[-1].headers["retry-after"]) > 0
