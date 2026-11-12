"""A stand-in for the PDF child, to test the parent wrapper's protocol and process handling.

The wrapper runs `python -I <script>` with the same arguments, environment and pipes as the real
child. Tests point it at a small script (`install`) that misbehaves in one chosen way.
"""

import textwrap
from pathlib import Path

import pytest

from app.rag import loaders

PREAMBLE = "import json, os, signal, sys, time\n"


def install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> Path:
    """Make the wrapper run `body` (Python source) instead of the real child."""
    script = tmp_path / "fake_child.py"
    script.write_text(PREAMBLE + textwrap.dedent(body), encoding="utf-8")
    monkeypatch.setattr(loaders, "_CHILD_SCRIPT", script)
    return script


def emit(*lines: str) -> str:
    """Source that prints the given JSON lines (already serialised) and exits normally."""
    return "".join(f"print({line!r})\n" for line in lines)


PAGE_ONE = '{"page": 1, "text": "hello"}'
END = '{"end": true}'
