# Spike H6: hostile PDFs under strict limits

Date: 2026-11-08. Task 1.6. The experiment ran only in a disposable **Linux** container: `--cpus 1 --memory 1g --memory-swap 1g --pids-limit 64 --network none --read-only` with a 512 MB tmpfs, never on the Windows host. The candidate child process (`reports/spike-scripts/pdf_child.py`, harness `h6_all.py`) reads the file from stdin, applies its own limits first (`RLIMIT_AS` 768 MB, `RLIMIT_CPU` 20 s, `RLIMIT_FSIZE` 0, `RLIMIT_CORE` 0, `RLIMIT_NOFILE` 16), runs `pypdf` with `strict=False`, rejects encrypted files, checks the page count (300) and a character cap (2,000,000) and writes JSON lines with fixed error codes only (never the exception text). The parent harness has a wall-clock timeout of 30 s, caps `stdout` at 8 MB, starts the child with `python -I`, a minimal environment, `stderr` discarded, and reads the child's peak memory and CPU time with `wait4`. Both `pypdf` 6.21.4 and 7.0.0 were run.

## Results (pypdf 7.0.0; 6.21.4 gave the same outcome on every file)

| Fixture | File | Wall | Peak memory | Outcome |
|---|---|---|---|---|
| valid, 3 pages | 3 KB | 0.11 s | 66 MB | ok, text extracted |
| scanned, no text | 1 KB | 0.12 s | 66 MB | ok, 0 characters (the service maps it to `NO_EXTRACTABLE_TEXT`) |
| truncated at 60 % | 2 KB | 0.12 s | 66 MB | `CORRUPT_FILE` |
| wrong `startxref` | 3 KB | 0.13 s | 66 MB | ok (pypdf repaired it) |
| 20 KB of random bytes after the header | 20 KB | 0.11 s | 66 MB | `CORRUPT_FILE` |
| 300 pages | 112 KB | 0.23 s | 66 MB | ok, 300 pages |
| 301 pages | 113 KB | 0.13 s | 66 MB | `TOO_MANY_PAGES` |
| 5,000 empty pages | 1.3 MB | 0.37 s | 66 MB | `TOO_MANY_PAGES` |
| decompression bomb: 200 MB of zeros in a 200 KB stream | 200 KB | 0.43 s | 175 MB | `CORRUPT_FILE` (pypdf refuses to inflate it) |
| decompression bomb: 2 GB of zeros in a 2 MB stream | 2.0 MB | 0.46 s | 182 MB | `CORRUPT_FILE` |
| page tree whose `Kids` points to itself | 1 KB | 0.13 s | 66 MB | `CORRUPT_FILE` |
| page tree nested 4,000 levels | 387 KB | 0.15 s | 66 MB | `CORRUPT_FILE` |
| **one page with 60,000 text lines** | 163 KB | **20.0 s** | 83 MB | **killed by the CPU limit (`SIGXCPU`)**, no result |
| 40 pages with 10 MB of text | 215 KB | 1.0 s | 66 MB | `TEXT_TOO_LARGE` |
| 200,000 empty objects | 8.9 MB | 0.62 s | 94 MB | ok, 0 pages |
| encrypted, user password | 3 KB | 0.13 s | 66 MB | `ENCRYPTED_PDF` |
| encrypted, **empty** user password (opens without a password) | 3 KB | 0.14 s | 66 MB | `ENCRYPTED_PDF` |
| `OpenAction` with JavaScript | 0.5 KB | 0.12 s | 66 MB | ok (nothing executed; 0 characters) |

`pypdf` 6.21.4: same outcomes; baseline memory 90 MB instead of 66 MB and slower start (0.45 to 0.65 s per file in the first run, a cold file cache effect). Encryption fixtures used RC4-128 because AES needs the optional `cryptography` package, which the image does not contain: `is_encrypted` is true either way, and such files are rejected before decrypting.

## Limit mechanisms verified

- **CPU limit:** the 163 KB page with 60,000 text lines burned the whole 20 s of CPU time and was stopped by `SIGXCPU`. This is the most realistic denial of service among the fixtures (tiny file, large compute). The service maps a child killed by `SIGXCPU` or the wall-clock timeout to `PROCESSING_TIMEOUT`.
- **Wall-clock timeout** (limit raised so only the parent acts; 5 s): the parent killed the child with `SIGKILL` at 5.00 s.
- **Memory limit** (`RLIMIT_AS` 120 MB): the two decompression bombs ended with `RESOURCE_LIMIT_EXCEEDED` (peaks 103 and 111 MB) while the normal 3-page and 300-page files still worked (59 MB peak).
- **Output cap** (character cap raised to 100 M so the child tries to print about 10 MB): the parent's 8 MB cap on `stdout` triggered and killed the child (`SIGKILL`, 3.6 s); the truncated last line was ignored.
- **Cannot write files:** `RLIMIT_FSIZE` 0 plus a read-only root file system; nothing was written by any fixture.
- The child's start-up cost is 0.1 s per file (warm cache), which is negligible against embedding.

## Conclusions

- Recommended child limits: memory 768 MB (peaks stay below 190 MB for legitimate and for bomb files, so 512 MB is also workable), CPU 20 s, wall clock 30 s, output cap 8 MB, character cap 2,000,000, pages 300. Legitimate 300-page and 10 MB-text documents finish in 0.2 to 1.4 s, a margin of more than ten.
- Both `pypdf` versions behave the same on this corpus, so the choice is made on advisories and fixes (see the H7 report): 7.0.0.
- Not covered: crafted cross-reference streams with identical offsets, XFA forms and JPEG image data, which the November advisories describe; they need purpose-made files and the limits above are the generic defence. Encrypted PDFs that really use AES were not generated.
- On a non-Linux host the `resource` limits do not exist, which is why the worker only parses PDFs inside the Linux container.
