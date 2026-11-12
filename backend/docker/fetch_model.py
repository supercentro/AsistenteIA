"""Download the embedding model at image build time from a pinned revision and verify it.

Run only by the `worker` Docker target. The files are checked against SHA-256 values recorded
by the spike (two independent downloads gave identical hashes), so a changed or tampered
revision fails the build instead of reaching production. At runtime the worker runs with the
hub offline and never downloads anything.
"""

import hashlib
import shutil
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

REPOSITORY = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
SHA256 = {
    "model.safetensors": "eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b",
    "tokenizer.json": "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8",
    "sentencepiece.bpe.model": "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
    "1_Pooling/config.json": "4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23",
    "config.json": "6300193cb75e01cf80c96decef7187dfb33094d97cc1490b7ead6ff134476e4e",
    "config_sentence_transformers.json": (
        "b8c64b5cece00d8424b4896ea75b512b6008576088497609dfeb6bd63e6d36b8"
    ),
    "modules.json": "8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460",
    "sentence_bert_config.json": (
        "70f4448f31320443fe3557cacea5abf2dcc4915dda8c80646bec9f3bb0aa5a1f"
    ),
    "special_tokens_map.json": "378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d",
    "tokenizer_config.json": "5036ea374ffedd706e3bef33e2e0d6953cb868ef8a490e76e32ba0faa37a6b9b",
    "README.md": "1e98ea05b0de579fcaad3d625b62ea55647142ed674d5f5ebf1440e4bbbb6f23",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(target: Path) -> int:
    snapshot_download(
        repo_id=REPOSITORY,
        revision=REVISION,
        local_dir=target,
        allow_patterns=list(SHA256),
    )
    shutil.rmtree(target / ".cache", ignore_errors=True)
    failures = [name for name, expected in SHA256.items() if sha256_of(target / name) != expected]
    extra = sorted(
        str(path.relative_to(target)).replace("\\", "/")
        for path in target.rglob("*")
        if path.is_file() and str(path.relative_to(target)).replace("\\", "/") not in SHA256
    )
    if failures or extra:
        print(f"model verification failed: changed={failures} unexpected={extra}", file=sys.stderr)
        return 1
    print(f"model {REPOSITORY}@{REVISION} verified ({len(SHA256)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
