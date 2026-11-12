"""H3 throughput, H4 calibrated Spanish retrieval, H5 vector compatibility (run offline in the worker image)."""
import json
import math
import os
import random
import re
import sys
import time
import unicodedata

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, "/spike")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from corpus_es import QUESTIONS, SUBJECTS  # noqa: E402


def rss_mb() -> float:
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024
    return -1.0


def hwm_mb() -> float:
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith("VmHWM"):
                return int(line.split()[1]) / 1024
    return -1.0


mode = sys.argv[1]
model = SentenceTransformer("/models/a", device="cpu")
tok = model.tokenizer

if mode == "throughput":
    # ~100-token chunks built from the Spanish corpus; repeated to fill the batch sizes
    base = [p for subject in SUBJECTS.values() for p in subject.values()]
    texts: list[str] = []
    while len(texts) < 512:
        joined = ""
        for p in random.Random(len(texts)).sample(base, 3):
            joined += p + " "
        ids = tok(joined, add_special_tokens=False)["input_ids"][:100]
        texts.append(tok.decode(ids))
    lengths = [len(tok(t, add_special_tokens=True)["input_ids"]) for t in texts]
    print(f"chunks {len(texts)} tokens with special: min {min(lengths)} mean {sum(lengths)/len(lengths):.1f} max {max(lengths)}")
    print(f"threads {torch.get_num_threads()} cpus visible {os.cpu_count()} RSS after load {rss_mb():.0f} MB")
    model.encode(texts[:16], batch_size=16)  # warm-up
    for batch in (8, 16, 32, 64):
        start = time.time()
        model.encode(texts, batch_size=batch)
        elapsed = time.time() - start
        rate = len(texts) / elapsed
        print(f"batch {batch:3}: {rate:6.1f} chunks/s, 2000 chunks in {2000 / rate:6.1f} s, HWM {hwm_mb():.0f} MB")

elif mode == "retrieval":
    passages = {pid: text for subject in SUBJECTS.values() for pid, text in subject.items()}
    subject_of = {pid: sid for sid, subject in SUBJECTS.items() for pid in subject}
    pids = list(passages)
    p_emb = model.encode([passages[p] for p in pids], normalize_embeddings=False)
    q_emb = model.encode([q for _, _, q in QUESTIONS], normalize_embeddings=False)

    def unit(m):
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    sims = unit(q_emb) @ unit(p_emb).T
    index = {pid: i for i, pid in enumerate(pids)}

    def strip(text: str) -> list[str]:
        text = unicodedata.normalize("NFKD", text.lower())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.findall(r"[a-z0-9]+", text)

    stop = set("el la los las un una unos unas de del al y o u en a por para con sin que se su sus es son fue como cual cuales cuando donde quien quienes qué cómo cuál cuándo dónde mas muy lo le les ya no si e".split())
    docs = {pid: [t for t in strip(passages[pid]) if t not in stop] for pid in pids}
    avg = sum(len(d) for d in docs.values()) / len(docs)
    df: dict[str, int] = {}
    for d in docs.values():
        for term in set(d):
            df[term] = df.get(term, 0) + 1

    def bm25(query: str, pid: str, k1=1.5, b=0.75) -> float:
        terms = [t for t in strip(query) if t not in stop]
        d = docs[pid]
        score = 0.0
        for term in set(terms):
            if term not in df:
                continue
            tf = d.count(term)
            idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg))
        return score

    def ranks(scope: str):
        out = {"dense": [], "bm25": [], "random": []}
        rng = random.Random(1234)
        for qi, (sid, expected, question) in enumerate(QUESTIONS):
            candidates = [p for p in pids if scope == "all" or subject_of[p] == sid]
            dense = sorted(candidates, key=lambda p: -sims[qi, index[p]])
            lex = sorted(candidates, key=lambda p: (-bm25(question, p), p))
            rnd = candidates[:]
            rng.shuffle(rnd)
            out["dense"].append(dense.index(expected) + 1)
            out["bm25"].append(lex.index(expected) + 1)
            out["random"].append(rnd.index(expected) + 1)
        return out

    def metrics(r):
        n = len(r)
        return (sum(x == 1 for x in r) / n, sum(x <= 3 for x in r) / n, sum(1 / x for x in r) / n)

    def bootstrap(r, reps=4000):
        rng = np.random.default_rng(7)
        arr = np.array(r)
        res = []
        for _ in range(reps):
            sample = arr[rng.integers(0, len(arr), len(arr))]
            res.append((np.mean(sample == 1), np.mean(sample <= 3), np.mean(1 / sample)))
        res = np.array(res)
        return np.percentile(res, [2.5, 97.5], axis=0)

    print(f"questions {len(QUESTIONS)}, passages {len(pids)} ({len(SUBJECTS)} subjects)")
    for scope, label in (("subject", "within the subject (the production setting)"), ("all", "across all subjects (harder)")):
        print(f"\n== ranking {label}")
        rk = ranks(scope)
        for name in ("dense", "bm25", "random"):
            h1, h3, mrr = metrics(rk[name])
            ci = bootstrap(rk[name])
            print(f"{name:7} hit@1 {h1:.3f} [{ci[0][0]:.2f}-{ci[1][0]:.2f}]  hit@3 {h3:.3f} [{ci[0][1]:.2f}-{ci[1][1]:.2f}]  MRR {mrr:.3f} [{ci[0][2]:.2f}-{ci[1][2]:.2f}]")
        if scope == "subject":
            misses = [(QUESTIONS[i][2], QUESTIONS[i][1], r) for i, r in enumerate(rk["dense"]) if r > 3]
            print("dense misses (rank > 3):", len(misses))
            for q, exp, r in misses:
                print(f"   rank {r}: {exp} <- {q}")
    # similarity distributions: relevant vs irrelevant (same subject)
    rel, irr = [], []
    for qi, (sid, expected, _q) in enumerate(QUESTIONS):
        for p in pids:
            if subject_of[p] != sid:
                continue
            (rel if p == expected else irr).append(float(sims[qi, index[p]]))
    for name, values in (("relevant", rel), ("irrelevant same subject", irr)):
        a = np.array(values)
        print(f"cosine {name:24} n {len(a):4} min {a.min():.3f} p10 {np.percentile(a,10):.3f} median {np.median(a):.3f} p90 {np.percentile(a,90):.3f} max {a.max():.3f}")
    best_irr = float(np.max(irr))
    print(f"fraction of relevant above the 95th percentile of irrelevant: {np.mean(np.array(rel) > np.percentile(irr, 95)):.3f}")
    # effect of chunking at 100/20 tokens: split every passage and rank chunks, count a hit if a chunk of the expected passage is in the top k
    def chunk_ids(text: str, size=100, overlap=20):
        ids = tok(text, add_special_tokens=False)["input_ids"]
        out, start = [], 0
        while start < len(ids):
            out.append(tok.decode(ids[start:start + size]))
            if start + size >= len(ids):
                break
            start += size - overlap
        return out
    chunk_texts, chunk_owner = [], []
    for pid in pids:
        for c in chunk_ids(passages[pid]):
            chunk_texts.append(c)
            chunk_owner.append(pid)
    print(f"\nchunking 100/20: {len(pids)} passages -> {len(chunk_texts)} chunks")
    c_emb = unit(model.encode(chunk_texts))
    cs = unit(q_emb) @ c_emb.T
    hits1 = hits3 = 0
    for qi, (sid, expected, _q) in enumerate(QUESTIONS):
        cand = [j for j, o in enumerate(chunk_owner) if subject_of[o] == sid]
        order = sorted(cand, key=lambda j: -cs[qi, j])
        owners = [chunk_owner[j] for j in order]
        hits1 += owners[0] == expected
        hits3 += expected in owners[:3]
    print(f"chunked hit@1 {hits1 / len(QUESTIONS):.3f} hit@3 {hits3 / len(QUESTIONS):.3f}")

elif mode == "longdoc":
    # long documents (5 passages each) chunked at different sizes; hit = a top-k chunk overlaps the expected passage
    def unit(m):
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    rng = random.Random(99)
    q_emb = unit(model.encode([q for _, _, q in QUESTIONS]))
    for size, overlap in ((100, 20), (200, 40), (400, 40), (60, 12)):
        chunks, meta = [], []   # meta: (subject, doc, token_start, token_end, passage-span map)
        spans = {}
        for sid, subject in SUBJECTS.items():
            pids = list(subject)
            rng2 = random.Random(5)
            rng2.shuffle(pids)
            for d in range(0, len(pids), 5):
                group = pids[d:d + 5]
                ids, offset = [], 0
                for pid in group:
                    pid_ids = tok(subject[pid], add_special_tokens=False)["input_ids"]
                    spans[pid] = (offset, offset + len(pid_ids))
                    ids += pid_ids
                    offset += len(pid_ids)
                start = 0
                while start < len(ids):
                    end = min(start + size, len(ids))
                    chunks.append(tok.decode(ids[start:end]))
                    meta.append((sid, start, end, group))
                    if end == len(ids):
                        break
                    start += size - overlap
        c_emb = unit(model.encode(chunks, batch_size=16))
        sims = q_emb @ c_emb.T
        hit1 = hit3 = 0
        for qi, (sid, expected, _q) in enumerate(QUESTIONS):
            ps, pe = spans[expected]
            cand = [j for j, m in enumerate(meta) if m[0] == sid and expected in m[3]]
            order = sorted([j for j, m in enumerate(meta) if m[0] == sid], key=lambda j: -sims[qi, j])

            def relevant(j):
                _s, cs_, ce_, _g = meta[j]
                if expected not in meta[j][3]:
                    return False
                overlap_tokens = min(ce_, pe) - max(cs_, ps)
                # only the first 126 tokens of a chunk are seen by the model
                seen_end = min(ce_, cs_ + 126)
                seen_overlap = min(seen_end, pe) - max(cs_, ps)
                return seen_overlap >= min(30, pe - ps) and overlap_tokens > 0
            hit1 += relevant(order[0])
            hit3 += any(relevant(j) for j in order[:3])
        avg_tokens = np.mean([len(tok(c, add_special_tokens=True)["input_ids"]) for c in chunks])
        over = sum(len(tok(c, add_special_tokens=True)["input_ids"]) > 128 for c in chunks)
        print(f"chunk {size:3}/{overlap:2}: chunks {len(chunks):3}, mean tokens {avg_tokens:6.1f}, chunks over 128 tokens {over:3} -> hit@1 {hit1 / len(QUESTIONS):.3f} hit@3 {hit3 / len(QUESTIONS):.3f} (counting only the part the model sees)")

elif mode == "compat":
    sys.path.insert(0, "/spike")
    from vv import validate_embedding  # copy of app/core/vector_validation.py

    passages = [t for subject in SUBJECTS.values() for t in subject.values()]
    extra = ["a", " ", "0", "¿" * 50, "x" * 2000, "palabra " * 300, "😀" * 200]
    vectors = model.encode(passages + [q for _, _, q in QUESTIONS] + extra, normalize_embeddings=False)
    norms = np.linalg.norm(vectors, axis=1)
    print(f"vectors {len(vectors)} shape {vectors.shape} dtype {vectors.dtype}")
    print(f"norm min {norms.min():.4f} median {np.median(norms):.4f} max {norms.max():.4f}")
    failures = 0
    for v in vectors:
        try:
            out = validate_embedding([float(x) for x in v])
            assert len(out) == 384
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("validate_embedding failed:", type(exc).__name__, exc)
    print("validate_embedding failures:", failures)
    np.save("/out/compat_vectors.npy", vectors)
    # silent truncation: embedding of a long text equals the embedding of its first 126 tokens?
    long_text = " ".join(passages[:6])
    ids = tok(long_text, add_special_tokens=False)["input_ids"]
    print("long text tokens (no special):", len(ids))
    full = model.encode([long_text])[0]
    cut = model.encode([tok.decode(ids[:126])])[0]
    cosine = float(full @ cut / (np.linalg.norm(full) * np.linalg.norm(cut)))
    print(f"cosine(full text, first 126 tokens) = {cosine:.6f}  (about 1.0 means the tail is silently ignored)")
    tail = model.encode([tok.decode(ids[126:])])[0]
    print(f"cosine(full text, discarded tail) = {float(full @ tail / (np.linalg.norm(full) * np.linalg.norm(tail))):.4f}")
