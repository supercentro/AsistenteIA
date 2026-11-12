# Spike scripts (group 1)

Scripts used on 2026-11-08 to produce the reports in the parent folder. They ran in disposable containers, outside the repository, and are kept only to make the measurements repeatable. They are not product code and are not tested or linted by the project.

- `Dockerfile.api` and `Dockerfile.worker-final`: the two image candidates (`uv` 0.12.9, `python:3.12-slim`, CPU `torch` index, model baked from the pinned revision).
- `h1_lock.sh`: lock resolution with the new dependencies (run from the `api` image against a copy of `pyproject.toml`).
- `h2_model.py`: file listing, double download with hashes, offline load.
- `h3_h4_h5.py` and `corpus_es.py`: throughput (`throughput`), retrieval (`retrieval`, `longdoc`) and vector checks (`compat`). They import `vv.py`, a copy of `backend/app/core/vector_validation.py` at commit `3960132` that is not duplicated here.
- `h5_pg.py`, `h8_pg.py`, `h8_vf.py`: checks against a scratch PostgreSQL; the connection string comes from the environment variable `SPIKE_DSN` (a throw-away container on a private network); no credentials are stored.
- `h6_all.py` and `pdf_child.py`: hostile PDF generator, harness and child process prototype (run in a Linux container with CPU, memory and process limits).
- `h9_server.py` and `h9_client.py`: throw-away ASGI application with the upload guard and the raw-socket client.

The fixture passwords in `h6_all.py` (`secreto`, `owner-pass`) belong to generated test PDFs and protect nothing.
