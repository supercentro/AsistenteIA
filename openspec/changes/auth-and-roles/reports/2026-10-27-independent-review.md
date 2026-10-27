# Independent Adversarial Review - auth-and-roles (PR #2)

- Date: 2026-10-27
- Reviewer: a separate Claude subagent started with a clean context (no access to the implementation session), read-only on the repository, probes run only against the isolated `asistenteia_test` database. Its report is summarised here; probe scripts stayed in the session scratchpad.
- Verdict of the reviewer: **PASS WITH GAPS** - no blockers, two majors (F1, F2), five minors (F3-F7) and one question (F8). It judged merging advisable only after F1 and F2 were fixed or explicitly accepted.

## What the reviewer tried (summary)
Full diff and OpenSpec read; 274 tests run; fuzzing of register/login with surrogates, NUL, bidi and odd Unicode (including an exhaustive Python-versus-PostgreSQL `lower()` comparison against the email check constraint); a real Uvicorn on loopback with rotating `X-Forwarded-For`/`Forwarded`/`X-Real-IP`; 40 concurrent logins against a 5/min limit; JWT probes (aud list, non-canonical sub, NaN/Infinity exp, nbf, kid, huge header); database-unreachable behaviour; server log capture on a statement-level error; CLI parser abuse; secrets scan; spec-versus-test-versus-contract walk-through.

## Findings and resolution
| ID | Severity | Finding | Resolution (this change) |
|---|---|---|---|
| F1 | Major | A statement-level database error wrote the full SQLAlchemy traceback, including bound parameters (email, Argon2id hash), to the server log: Starlette re-raises after the 500 handler and Uvicorn logs it | Engine uses `hide_parameters=True`; new outermost `UnhandledErrorMiddleware` answers the 500 itself and logs only type, method and path, so no traceback reaches the server log (PostgreSQL `DETAIL: Failing row contains (...)` text is covered too). Tests: `test_error_hardening.py`, `test_review_hardening.py` |
| F2 | Major | With the TCP peer on loopback, Uvicorn's default proxy-header handling rewrote the client address from `X-Forwarded-For`, so rotating the header bypassed both limiters (reproduced) | `--no-proxy-headers` in the Dockerfile CMD and the compose command; tests start the real server with the Dockerfile's own arguments and show 5/5 rotating-header requests are limited, plus a guard test on the flag. Mutation (flag removed) makes all three tests fail. Documented in the development guide |
| F3 | Minor | Names accepted U+2028/U+2029 and bidi overrides (display spoofing) | Names reject `Cc`, `Zl`, `Zp` and bidi controls (U+200E/F, U+202A-E, U+2066-9); ZWNJ/ZWJ remain allowed (tests with Persian and emoji names) |
| F4 | Minor | CLI `--name` had no control-character check; a dead helper existed | CLI applies the same name rule; dead helper removed |
| F5 | Minor | argparse echoed an unsupported `--password <value>` into stderr | `SafeArgumentParser` hides unrecognized argument values (exit code 2) |
| F6 | Minor | Login `maxLength` 128 missing from the contract | `docs/api-spec.yml`: login email `maxLength` 255, password `minLength` 1 / `maxLength` 128 |
| F7 | Minor | Database outage on login/register returned 500 | `OperationalError`/`InterfaceError` map to 503 `SERVICE_UNAVAILABLE` on every endpoint; contract documents 503 on login/register |
| F8 | Question | Emails use `str.lower()` without Unicode normalisation, so look-alike non-ASCII addresses (for example `ΣΑΣ` -> `σας` versus `σασ`) can be separate accounts; passwords are not NFC-normalised | **Resolved by the user's decision (2026-10-27): emails are ASCII-only and lowercased.** One shared validator (`ascii_email`) for registration, login and the CLI (non-ASCII input is rejected before validation because `email-validator` would otherwise turn punycode domains back into Unicode); database check `ck_users_email_ascii` (`octet_length = char_length`) in migration `0002`. Tests: accented, full-width, Greek/Cyrillic look-alike and Unicode-domain emails -> 422 / non-zero exit; uppercase ASCII lowercased; duplicates 409; punycode accepted; direct non-ASCII insert rejected by the database. Compatibility: the development database has 0 users (0 non-ASCII) and `0002` was never merged or applied elsewhere, so the constraint was added to `0002`; local databases re-run `downgrade -1` / `upgrade head`. Passwords remain un-normalised (documented) |

Discarded by the reviewer after checking: surrogate/NUL 500s, Python-vs-PostgreSQL lowercasing mismatches (0 code points), login enumeration, JWT variants (all 401; NaN/Infinity `exp`, `nbf`, `kid` only reachable with a valid server-side signature), limiter concurrency (exactly 5 of 40 allowed; limiter runs before body validation and hashing), self-assignment of the teacher role, consent and drift mechanism, repository secrets, migration versus data model.

Not verified by the reviewer: the client address seen inside the Docker Desktop container (probably the gateway, hence not loopback). With `--no-proxy-headers` the address is always the TCP peer, so the question no longer matters.

## Verification after the fixes
(F1-F7 round) Full suite 305 passed (97 % coverage), ruff / format / `mypy --strict` clean, `alembic check` clean in the container, live stack: rotating `X-Forwarded-For` produced `401 x10` then `429`.

## Final verification (after F8)
Full suite **344 passed** (97 % coverage), ruff / format / `mypy --strict` clean, `pip-audit` and `npm audit` clean, Vitest 3 + Playwright 2 passing, `alembic check` clean, `openspec validate auth-and-roles --strict` valid, `docs/` relative links all resolve. The regression tests for F1-F7 (`test_error_hardening.py`, `test_review_hardening.py`, `test_cli.py`, `test_cli_process.py`) still pass; F8 is covered by `test_email_normalization.py`, `test_email_ascii.py`, the migration test and the CLI tests. No new blocking findings.
