import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest, normalize_email

NON_ASCII_EMAILS = [
    "ünï@example.com",
    "josé@example.com",
    "ｕｓｅｒ@example.com",
    "user@bücher.com",
    "ΣΑΣ@example.com",
    "аdmin@example.com",  # first letter is Cyrillic
    "İstanbul@example.com",
    "user@exämple.com",
]


@pytest.mark.parametrize("email", NON_ASCII_EMAILS)
def test_register_request_rejects_non_ascii_emails(email: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(name="N", email=email, password="a-very-long-password")


@pytest.mark.parametrize("email", NON_ASCII_EMAILS)
def test_login_request_rejects_non_ascii_emails(email: str) -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email=email, password="whatever")


def test_validation_errors_do_not_echo_the_submitted_email() -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(name="N", email="ünï@example.com", password="a-very-long-password")

    assert "ünï" not in str(exc.value.errors(include_input=False))


def test_uppercase_ascii_is_lowercased_and_trimmed() -> None:
    request = RegisterRequest(
        name="N", email="  Ana.Perez@Example.COM ", password="a-very-long-password"
    )

    assert request.email == "ana.perez@example.com"


def test_punycode_domains_are_accepted() -> None:
    request = LoginRequest(email="User@XN--BCHER-KVA.com", password="x")

    assert request.email == "user@xn--bcher-kva.com"


def test_normalize_email_rejects_non_ascii_directly() -> None:
    with pytest.raises(ValueError, match="ASCII"):
        normalize_email("ñ@example.com")
