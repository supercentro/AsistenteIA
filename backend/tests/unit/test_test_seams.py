"""Test seams cannot be reached from production inputs (review of group 10).

`UploadSlots` takes an optional pause between the read and the write of its counter so that the
tests can force an interleaving. It must stay a constructor argument that only test code passes:
nothing read from a request, a file, the environment or the settings may feed it, and the
application builds its slots without it.
"""

import re
from pathlib import Path

from app.main import create_app
from tests.db_support import BACKEND_DIR
from tests.integration.helpers import build_settings

APP = BACKEND_DIR / "app"
SEAM = "pause_between_read_and_write"


def sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in APP.rglob("*.py")}


def test_only_the_slots_module_mentions_the_seam() -> None:
    mentioning = {path.name for path, text in sources().items() if SEAM in text}

    assert mentioning == {"upload_guard.py"}


def test_the_application_builds_its_slots_without_the_seam() -> None:
    app = create_app(build_settings("postgresql+psycopg://u:p@localhost:5432/seam_test"))

    slots = app.state.upload_slots
    assert slots._pause is None  # noqa: SLF001 - the point of the test


def test_the_seam_is_keyword_only_and_off_by_default() -> None:
    import inspect

    from app.core.upload_guard import UploadSlots

    parameter = inspect.signature(UploadSlots).parameters[SEAM]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_no_production_module_imports_test_support_code() -> None:
    offenders = [
        path.name
        for path, text in sources().items()
        if re.search(r"^(from|import) tests", text, re.M)
    ]

    assert offenders == []
