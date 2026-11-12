set -e
rm -rf /tmp/proj && mkdir /tmp/proj && cd /tmp/proj
cp /app/pyproject.toml /app/uv.lock /app/.python-version .
cat >> pyproject.toml <<'TOML'

[project.optional-dependencies]
ingestion = ["pypdf==7.0.0", "langchain-text-splitters==1.1.3"]
embedding = ["sentence-transformers==6.2.0", "torch>=2.2"]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]
TOML
sed -i 's/^dependencies = \[/dependencies = [\n    "python-multipart==0.0.33",/' pyproject.toml
cp uv.lock uv.lock.before
s=$(date +%s); uv lock 2>&1 | tail -6; echo "uv lock took $(( $(date +%s) - s )) s"
echo "lock size before/after (bytes): $(wc -c < uv.lock.before) $(wc -c < uv.lock)"
echo "torch entries in the lock:"; grep -n -A1 '^name = "torch"' uv.lock | head -12
echo "torch wheels per platform:"; grep -o 'torch-[0-9.+a-z]*-cp312-[a-z0-9_]*-[a-z0-9_.]*\.whl' uv.lock | sort -u | head -12
echo "extras installed by sync into a throwaway venv (dry run):"
UV_PROJECT_ENVIRONMENT=/tmp/venv uv sync --frozen --no-dev --extra ingestion --dry-run 2>&1 | tail -4
UV_PROJECT_ENVIRONMENT=/tmp/venv uv sync --frozen --no-dev --extra ingestion --extra embedding --dry-run 2>&1 | grep -E "torch|nvidia|triton|sentence|pypdf" | head -8
echo "does the api target (no extras) stay free of torch/pypdf?"
UV_PROJECT_ENVIRONMENT=/tmp/venv uv sync --frozen --no-dev --dry-run 2>&1 | grep -c -E "torch|pypdf|sentence" || true
