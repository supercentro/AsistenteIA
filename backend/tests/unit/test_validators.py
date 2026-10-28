import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.subject import SubjectCreate
from app.schemas.validators import (
    Description,
    Email,
    Name,
    SubjectName,
    ensure_no_control_characters,
    normalize_email,
)

BAD_SINGLE_LINE = [
    "a\x00b",
    "a\nb",
    "a\rb",
    "a\tb",
    "a\u2028b",
    "a\u2029b",
    "a\u202eb",
    "a\u2066b",
    "a\u200fb",
]


class NameModel(BaseModel):
    name: Name


class SubjectNameModel(BaseModel):
    name: SubjectName


class DescriptionModel(BaseModel):
    description: Description | None = None


class EmailModel(BaseModel):
    email: Email


@pytest.mark.parametrize("value", BAD_SINGLE_LINE)
def test_single_line_names_reject_control_line_and_direction_characters(value: str) -> None:
    for model in (NameModel, SubjectNameModel):
        with pytest.raises(ValidationError):
            model(name=value)
    with pytest.raises(ValueError):
        ensure_no_control_characters(value)


def test_names_are_trimmed_and_joiners_stay_allowed() -> None:
    assert NameModel(name="  Algebra  ").name == "Algebra"
    assert SubjectNameModel(name="\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645").name


def test_name_limits_are_100_for_users_and_150_for_subjects() -> None:
    assert NameModel(name="a" * 100).name == "a" * 100
    with pytest.raises(ValidationError):
        NameModel(name="a" * 101)
    assert SubjectNameModel(name="a" * 150).name == "a" * 150
    with pytest.raises(ValidationError):
        SubjectNameModel(name="a" * 151)


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_names_are_rejected(value: str) -> None:
    for model in (NameModel, SubjectNameModel):
        with pytest.raises(ValidationError):
            model(name=value)


def test_description_allows_line_breaks_and_tabs_and_keeps_them() -> None:
    text = "line one\nline two\r\n\tindented"
    assert DescriptionModel(description=text).description == text


def test_description_is_optional_and_defaults_to_none() -> None:
    assert DescriptionModel().description is None


def test_description_is_trimmed_at_both_ends_but_keeps_inner_line_breaks() -> None:
    assert DescriptionModel(description="\n a\nb \t").description == "a\nb"


def test_subject_create_turns_a_blank_description_into_none() -> None:
    assert SubjectCreate(name="A", description="  \n ").description is None
    assert SubjectCreate(name="A", description="").description is None
    assert SubjectCreate(name="A", description=" text ").description == "text"


@pytest.mark.parametrize(
    "value", ["a\x00b", "a\x01b", "a\x7fb", "a\u2028b", "a\u2029b", "a\u202eb", "a\u200eb"]
)
def test_description_rejects_nul_other_controls_separators_and_bidi(value: str) -> None:
    with pytest.raises(ValidationError):
        DescriptionModel(description=value)


def test_description_limit_is_2000_characters() -> None:
    assert DescriptionModel(description="a" * 2000).description == "a" * 2000
    with pytest.raises(ValidationError):
        DescriptionModel(description="a" * 2001)


def test_description_rejects_lone_surrogates_without_server_errors() -> None:
    with pytest.raises(ValidationError):
        DescriptionModel(description="a\ud800b")


def test_validation_errors_do_not_echo_names_or_descriptions() -> None:
    with pytest.raises(ValidationError) as exc:
        DescriptionModel(description="secret\x00text")
    assert "secret" not in str(exc.value.errors(include_input=False))


def test_email_is_lowercased_trimmed_and_ascii_only() -> None:
    assert EmailModel(email="  Student@Example.COM ").email == "student@example.com"
    assert normalize_email(" A@B.C ") == "a@b.c"
    for value in (
        "jos\u00e9@example.com",
        "user@b\u00fccher.com",
        "not-an-email",
        "a" * 250 + "@x.com",
    ):
        with pytest.raises(ValidationError):
            EmailModel(email=value)
