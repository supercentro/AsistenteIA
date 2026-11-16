import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
files = subprocess.check_output(
    ["git", "ls-tree", "-r", "main", "--name-only", "--", "backend/tests"], text=True
).split()
changed = set(
    subprocess.check_output(
        ["git", "diff", "main..HEAD", "--name-only", "--diff-filter=M", "--", "backend/tests", "backend/pyproject.toml"],
        text=True,
    ).split()
)
terms = {
    "env": r"\.env|dotenv|env_file|load_test_environment|_env_file",
    "guard": r"db_safety|assert_safe_test_database|UnsafeTestDatabase|require_test_database_url|require_test_admin|TEST_DATABASE_URL",
    "alembic": r"alembic/env|alembic_config|command\.(upgrade|downgrade|check)",
    "compose": r"docker-compose|compose",
    "settings": r"load_settings|load_worker_settings|Settings\(|WorkerSettings|build_settings|database_url",
}
rows = []
for f in files:
    if not f.endswith(".py"):
        continue
    path = ROOT / f
    if not path.exists():
        print("MISSING in HEAD:", f)
        continue
    text = path.read_text(encoding="utf-8")
    hits = {k: len(re.findall(v, text)) for k, v in terms.items()}
    if any(hits.values()):
        rows.append((f, hits, f in changed))
for f, hits, was_changed in sorted(rows):
    summary = " ".join(f"{k}={n}" for k, n in hits.items() if n)
    print(("M " if was_changed else "  ") + f.replace("backend/tests/", "") + "  " + summary)
print(len(rows), "existing files touch these areas;", sum(1 for r in rows if r[2]), "modified;", len(files), "existing test files in main")
