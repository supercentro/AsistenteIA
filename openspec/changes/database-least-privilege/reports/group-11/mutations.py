"""Mutation of the CLI process test (group 11, review M2), applied to a COPY of the code.

usage:
  python mutations.py check <backend dir>
  python mutations.py list
  python mutations.py apply <index> <backend copy>

The administrative command must not take its database URL from the API variable. The mutation lets
`CliSettings` accept `DATABASE_URL` as an alias of `CLI_DATABASE_URL` (the shape of a fallback that
an emptied variable would hide): the real-process test that REMOVES `CLI_DATABASE_URL` must fail.
"""

import sys
from pathlib import Path

PROCESS = "tests/integration/test_cli_process.py"
ALIASED = (
    '    cli_database_url: SecretStr = Field(\n'
    '        validation_alias=__import__("pydantic").AliasChoices("CLI_DATABASE_URL", "DATABASE_URL")\n'
    "    )\n"
)

MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "CliSettings falls back to DATABASE_URL",
        "app/core/config.py",
        "    cli_database_url: SecretStr\n    # Fail closed",
        ALIASED + "    # Fail closed",
        [f"{PROCESS}::test_the_command_refuses_the_api_credentials_and_creates_nothing"],
    ),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check(backend: Path) -> int:
    missing = 0
    for index, (label, rel, old, _new, _targets) in enumerate(MUTATIONS):
        found = _read(backend / rel).count(old)
        if found != 1:
            print(f"{index}: {found} occurrences of the text to mutate: {label}")
            missing += 1
    print(f"{len(MUTATIONS)} mutations, {missing} problem(s)")
    return 1 if missing else 0


def main() -> int:
    command = sys.argv[1]
    if command == "list":
        for index, (label, *_rest) in enumerate(MUTATIONS):
            print(f"{index}\t{label}")
        return 0
    if command == "check":
        return check(Path(sys.argv[2]))
    if command == "apply":
        index, backend = int(sys.argv[2]), Path(sys.argv[3])
        _label, rel, old, new, targets = MUTATIONS[index]
        path = backend / rel
        text = _read(path)
        assert text.count(old) == 1, "the text to mutate must appear exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(" ".join(targets))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
