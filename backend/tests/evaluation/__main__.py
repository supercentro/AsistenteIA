"""Command line of the RAG evaluation: `python -m tests.evaluation`.

Works only on the isolated test database, never calls the real model without `--allow-real-llm`
and never prints a secret. See `docs/development_guide.md` for how to run it in the container.
"""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import app as app_package
from app.core.config import Settings
from app.rag.embedder import Embedder, FakeEmbedder, build_embedder
from app.services.llm_service import FakeLLMService, LLMService
from tests.db_support import drop_everything
from tests.evaluation.budget import load_ledger, require_budget
from tests.evaluation.cases import GoldenSetError, load_golden_set, select_cases
from tests.evaluation.guards import (
    HarnessRefusedError,
    assert_isolated_database,
    require_cap_within_ceiling,
    require_real_model_permission,
    scrub,
)
from tests.evaluation.llm import HarnessGeminiService, build_gemini_service
from tests.evaluation.report import write_report
from tests.evaluation.runner import RunSettings, run_evaluation

DEFAULT_SET = Path(__file__).resolve().parent / "golden_set"
PLACEHOLDER_SECRET = "evaluation-harness-placeholder-secret-not-used"  # noqa: S105


def _ints(raw: str) -> list[int]:
    return sorted({int(part) for part in raw.split(",") if part.strip()})


def _floats(raw: str) -> list[float]:
    return sorted({float(part) for part in raw.split(",") if part.strip()})


def _password_forms(url: str) -> list[str]:
    """The password of a database URL as typed and in its URL-quoted form (both can be echoed)."""
    try:
        password = make_url(url).password if url else None
    except Exception:  # noqa: BLE001 - an unparsable URL has nothing to register
        return []
    return [password, quote(password, safe="")] if password else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tests.evaluation", description=__doc__)
    parser.add_argument("--golden-set", type=Path, default=DEFAULT_SET)
    parser.add_argument("--only", help="comma separated case ids: repeat only these cases")
    parser.add_argument("--mode", choices=["retrieval", "answers"], default="retrieval")
    parser.add_argument("--embedder", choices=["local", "fake"], default="local")
    parser.add_argument("--llm", choices=["fake", "gemini"], default="fake")
    parser.add_argument("--allow-real-llm", action="store_true")
    parser.add_argument("--max-calls", type=int, default=50)
    parser.add_argument(
        "--ledger", type=Path, help="ledger of the real requests (required with --llm gemini)"
    )
    parser.add_argument(
        "--pause-seconds", type=float, default=6.0, help="wait between real model requests"
    )
    parser.add_argument("--top-k", default="3,5,8", help="comma separated values")
    parser.add_argument("--thresholds", default="0.2,0.3,0.4,0.5", help="comma separated values")
    parser.add_argument("--out", type=Path, default=Path("evaluation-reports"))
    parser.add_argument("--revision", default="unknown")
    parser.add_argument(
        "--env-file", type=Path, action="append", default=[], help="file(s) with the URLs"
    )
    parser.add_argument("--db-host", help="replace the host of TEST_DATABASE_URL (e.g. db)")
    parser.add_argument("--db-port", type=int, help="replace the port of TEST_DATABASE_URL")
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="migrate an EMPTY test database for the run and drop the schema afterwards",
    )
    return parser


def _alembic_config(url: str) -> Config:
    backend = Path(app_package.__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def prepare_schema(url: str, *, create: bool) -> bool:
    """Make sure the test database is at the migration head; return True if this run built it.

    A database that already has a schema is never touched: it must already be at the head. An
    empty one is migrated only with `--create-schema`.
    """
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            tables = connection.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            ).scalar_one()
            version = None
            if connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar():
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
    finally:
        engine.dispose()
    config = _alembic_config(url)
    head = ScriptDirectory.from_config(config).get_current_head()
    if tables == 0:
        if not create:
            raise HarnessRefusedError(
                "the test database is empty: use --create-schema to migrate it for this run"
            )
        command.upgrade(config, "head")
        return True
    if version != head:
        raise HarnessRefusedError(
            "the test database has a schema that is not at the migration head"
        )
    return False


def _resolve_url(environ: Mapping[str, str], args: argparse.Namespace) -> str:
    url = environ.get("TEST_DATABASE_URL")
    if not url:
        raise HarnessRefusedError("TEST_DATABASE_URL is required (see backend/.env.test.example)")
    parsed = make_url(url)
    if args.db_host:
        parsed = parsed.set(host=args.db_host)
    if args.db_port:
        parsed = parsed.set(port=args.db_port)
    return parsed.render_as_string(hide_password=False)


def _settings(environ: Mapping[str, str], url: str, args: argparse.Namespace) -> Settings:
    values: dict[str, object] = {
        "database_url": url,
        "jwt_secret": PLACEHOLDER_SECRET,
        "cors_origins": ["http://localhost:5173"],
        "app_env": "test",
        "embedder_backend": args.embedder,
        "llm_backend": "gemini" if args.llm == "gemini" else "fake",
    }
    if environ.get("GOOGLE_API_KEY"):
        values["google_api_key"] = environ["GOOGLE_API_KEY"]
    return Settings(**values)  # type: ignore[arg-type]


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for env_file in args.env_file:
        load_dotenv(env_file, override=False)
    env: Mapping[str, str] = os.environ if environ is None else environ
    secrets: list[str] = [env.get("GOOGLE_API_KEY", ""), env.get("TEST_DATABASE_URL", "")]
    secrets += _password_forms(env.get("TEST_DATABASE_URL", "")) + _password_forms(
        env.get("DATABASE_URL", "")
    )
    created_schema = False
    url = ""
    try:
        require_real_model_permission(llm=args.llm, allow_real_llm=args.allow_real_llm)
        require_cap_within_ceiling(args.max_calls)
        if args.llm == "gemini" and args.mode == "answers":
            if args.ledger is None:
                raise HarnessRefusedError("--ledger is required with --llm gemini")
            require_budget(load_ledger(args.ledger), 1)  # nothing is left: stop before connecting
        url = _resolve_url(env, args)
        secrets.append(url)
        app_url = env.get("DATABASE_URL")
        if not app_url:
            raise HarnessRefusedError(
                "DATABASE_URL (the application database the guard compares with) is required"
            )
        secrets.append(app_url)
        assert_isolated_database(url, app_url, env.get("APP_ENV", ""))
        golden = load_golden_set(args.golden_set)
        if args.only:
            golden = select_cases(
                golden, [part.strip() for part in args.only.split(",") if part.strip()]
            )
        settings = _settings(env, url, args)
        embedder: Embedder = FakeEmbedder() if args.embedder == "fake" else build_embedder(settings)
        llm: LLMService = FakeLLMService() if args.llm == "fake" else build_gemini_service(settings)
        created_schema = prepare_schema(url, create=args.create_schema)
        print(
            f"mode={args.mode} embedder={args.embedder} model="
            f"{settings.chat_llm_model if args.llm == 'gemini' else 'fake'} "
            f"set={golden.version} cases={len(golden.cases)}"
        )
        report = run_evaluation(
            url,
            settings,
            golden,
            embedder,
            llm,
            RunSettings(
                mode=args.mode,
                top_ks=_ints(args.top_k),
                thresholds=_floats(args.thresholds),
                default_top_k=settings.chat_top_k,
                default_threshold=settings.chat_relevance_threshold,
                max_calls=args.max_calls,
                revision=args.revision,
                embedder_name=args.embedder,
                pause_seconds=args.pause_seconds if args.llm == "gemini" else 0.0,
                ledger_path=args.ledger
                if args.llm == "gemini" and args.mode == "answers"
                else None,
                model_name=settings.chat_llm_model if args.llm == "gemini" else "fake",
            ),
            announce=lambda message: print(message, flush=True),
        )
        if isinstance(llm, HarnessGeminiService) and llm.recorder.error_kinds:
            kinds = dict(sorted(llm.recorder.error_kinds.items()))
            report = replace(report, problems=[*report.problems, f"model error kinds: {kinds}"])
        markdown, structured = write_report(report, args.out, secrets)
        print(f"report: {markdown}\nreport: {structured}")
        for problem in report.problems:
            print(scrub(f"problem: {problem}", secrets))
        return 1 if report.problems else 0
    except (HarnessRefusedError, GoldenSetError) as refusal:
        print(scrub(f"refused: {refusal}", secrets), file=sys.stderr)
        return 2
    except Exception as failure:  # noqa: BLE001 - never let a traceback carry a secret
        # Library errors (settings validation, SQLAlchemy, the provider) can echo their input,
        # which holds the database URL: print the type and a scrubbed, shortened message only.
        text = scrub(str(failure), secrets)[:200]
        print(f"unexpected failure ({type(failure).__name__}): {text}", file=sys.stderr)
        return 2
    finally:
        if created_schema:
            try:
                drop_everything(url)
            except Exception as failure:  # noqa: BLE001 - never let a traceback carry a secret
                print(
                    f"could not drop the schema created for the run ({type(failure).__name__}): "
                    + scrub(str(failure), secrets)[:200],
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
