"""H2: reproducible download of the pinned model revision, offline load, dimension and tokenizer counts."""
import hashlib
import json
import os
import sys
import time

REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PATTERNS = [
    "config.json", "config_sentence_transformers.json", "modules.json", "sentence_bert_config.json",
    "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors",
    "1_Pooling/config.json", "sentencepiece.bpe.model", "README.md",
]


def rss_mb() -> float:
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024
    return -1.0


def tree(root: str) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".cache"]
        for name in files:
            path = os.path.join(base, name)
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            out[os.path.relpath(path, root)] = (os.path.getsize(path), digest.hexdigest())
    return out


mode = sys.argv[1]
if mode == "list":
    from huggingface_hub import HfApi

    info = HfApi().model_info(REPO, files_metadata=True)
    print("revision", info.sha, "license", info.card_data.get("license") if info.card_data else None)
    for item in sorted(info.siblings, key=lambda s: s.rfilename):
        print(f"{item.size or 0:>12} {item.rfilename}")
elif mode == "download":
    from huggingface_hub import HfApi, snapshot_download

    sha = HfApi().model_info(REPO).sha
    print("pinned revision", sha)
    for tag in ("a", "b"):
        start = time.time()
        snapshot_download(REPO, revision=sha, local_dir=f"/models/{tag}", allow_patterns=PATTERNS)
        print(f"download {tag}: {time.time() - start:.1f} s")
    first, second = tree("/models/a"), tree("/models/b")
    print("files", len(first), "total bytes", sum(v[0] for v in first.values()))
    print("identical hashes between the two downloads:", first == second)
    for name, (size, digest) in sorted(first.items()):
        print(f"{size:>12} {digest} {name}")
    with open("/models/revision.txt", "w") as handle:
        handle.write(sha)
elif mode == "offline":
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import socket

    try:
        socket.create_connection(("huggingface.co", 443), timeout=3)
        print("NETWORK REACHABLE (unexpected)")
    except OSError as exc:
        print("network unreachable as expected:", type(exc).__name__)
    import torch
    from sentence_transformers import SentenceTransformer

    print("torch", torch.__version__, "cuda available", torch.cuda.is_available(), "threads", torch.get_num_threads())
    before = rss_mb()
    start = time.time()
    model = SentenceTransformer("/models/a", device="cpu")
    load_s = time.time() - start
    print(f"load {load_s:.2f} s, RSS before import-load {before:.0f} MB, after {rss_mb():.0f} MB")
    print("max_seq_length", model.max_seq_length, "dimension", model.get_sentence_embedding_dimension())
    texts = ["Este es un texto de prueba en español.", "This is a test sentence in English."]
    start = time.time()
    vectors = model.encode(texts)
    print(f"first encode {time.time() - start:.3f} s shape {vectors.shape}")
    start = time.time()
    for _ in range(10):
        model.encode(texts)
    print(f"steady encode of 2 texts: {(time.time() - start) / 10 * 1000:.1f} ms")
    tok = model.tokenizer
    samples = {
        "spanish prose": "La Constitución de 1978 fue ratificada en referéndum y establece una monarquía parlamentaria.",
        "long word": "electroencefalografista" * 6,
        "url": "https://www.ejemplo.org/ruta/larga/con/muchos/segmentos?parametro=valor&otro=123456789",
        "digits": "3141592653589793238462643383279502884197169399375105820974944592307816406286",
        "emoji": "😀😃😄😁😆😅😂🤣🥲☺️😊😇🙂🙃😉😌😍🥰😘",
        "cjk": "自然语言处理是人工智能的一个重要方向，研究如何让计算机理解人类语言。",
        "rtl": "معالجة اللغات الطبيعية هي فرع من فروع الذكاء الاصطناعي",
    }
    for name, text in samples.items():
        without = len(tok(text, add_special_tokens=False)["input_ids"])
        with_special = len(tok(text, add_special_tokens=True)["input_ids"])
        print(f"tokens {name:14} chars {len(text):4} without special {without:4} with special {with_special:4}")
    print("probe vector norm", float((vectors[0] ** 2).sum() ** 0.5))
    print("peak RSS MB", rss_mb())
