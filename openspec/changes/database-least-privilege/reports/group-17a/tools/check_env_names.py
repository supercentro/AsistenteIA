"""Compare the variable NAMES of the real env files with their examples (group 17A tool; prints names only).

usage: python check_env_names.py <backend directory>

Checks `.env` against `.env.example` and `.env.worker` against `.env.worker.example`: it reports the names
that the example documents and the real file lacks (the code may rely on a default or fail) and the names
the real file has that the example does not know (a leftover that the settings ignore, or a typo). It reads
the files but never prints a value. Exit 0 when nothing differs, 1 otherwise (a difference is not an error
by itself: the owner reads the list before 17B).
"""

import re
import sys
from pathlib import Path

PAIRS = ((".env", ".env.example"), (".env.worker", ".env.worker.example"))


def names(path: Path, commented: bool = False) -> set[str]:
    pattern = r"^#?\s*([A-Z][A-Z0-9_]*)=" if commented else r"^([A-Z][A-Z0-9_]*)="
    found = set()
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            match = re.match(pattern, line)
            if match:
                found.add(match.group(1))
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    folder = Path(argv[0])
    status = 0
    for real, example in PAIRS:
        if not (folder / real).is_file() or not (folder / example).is_file():
            print(f"{real}: missing file ({real} or {example})")
            status = 1
            continue
        mine, documented = names(folder / real), names(folder / example, commented=True)
        required = names(folder / example)  # the uncommented names of the example
        lacking, extra = sorted(required - mine), sorted(mine - documented)
        print(f"{real}: {len(mine)} names; lacking vs {example}: {lacking or 'none'}; unknown to {example}: {extra or 'none'}")
        status = status or (1 if lacking or extra else 0)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
