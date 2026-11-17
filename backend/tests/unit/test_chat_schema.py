"""ChatRequest validation (adversarial review finding 4)."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest


@pytest.mark.parametrize("message", ["   ", "\t\n", "\u200b", "\x00\x00", " \x00 "])
def test_blank_messages_are_rejected(message: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(subject_id=uuid.uuid4(), message=message)


def test_message_is_trimmed() -> None:
    request = ChatRequest(subject_id=uuid.uuid4(), message="  hello  ")
    assert request.message == "hello"
