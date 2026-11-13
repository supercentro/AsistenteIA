"""The mandatory privilege gate of the CI workflow (change `database-least-privilege`, task 10.1).

The workflow file is parsed, not run: these tests fail when the job disappears, loses a step, gets
a way to hide a failure, or receives more rights than it needs. The behaviour of the gate itself
(a failing step fails the job, a missing prerequisite fails it, a table without a decision fails
it) is proved by `reports/group-10` against disposable clusters, because GitHub is not available
locally.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = Path(
    __import__("os").environ.get("CI_WORKFLOW_UNDER_TEST", REPO / ".github/workflows/ci.yml")
)
SCRIPTS = REPO / ".github" / "scripts"
GATE_STEPS = [
    "prerequisites",
    "clusters",
    "flow",
    "drift-selfcheck",
    "privilege-unit",
    "role-suites",
    "roles-mode",
    "summary",
]
ADMIN_VARIABLES = {
    "ADMIN_DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "DB_MIGRATOR_PASSWORD",
    "DB_APP_PASSWORD",
    "DB_WORKER_PASSWORD",
    "DB_CLI_PASSWORD",
    "TEST_ADMIN_DATABASE_URL",
    "TEST_CLUSTER_IS_DISPOSABLE",
}


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    loaded["on"] = loaded.pop(True, loaded.get("on"))  # YAML reads the key `on` as True
    return dict(loaded)


@pytest.fixture(scope="module")
def job(workflow: dict[str, Any]) -> dict[str, Any]:
    assert "privileges" in workflow["jobs"], "the privilege gate job is missing"
    return dict(workflow["jobs"]["privileges"])


def run_texts(job_: dict[str, Any]) -> list[str]:
    return [str(step.get("run", "")) for step in job_["steps"]]


def test_the_workflow_runs_on_push_and_pull_request_only(workflow: dict[str, Any]) -> None:
    assert set(workflow["on"]) == {"push", "pull_request"}  # never pull_request_target


def test_the_token_has_read_only_rights_everywhere(workflow: dict[str, Any]) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    for name, job_ in workflow["jobs"].items():
        assert job_.get("permissions", {"contents": "read"}) == {"contents": "read"}, name


def test_no_repository_or_organisation_secret_is_used() -> None:
    assert not re.search(r"\$\{\{\s*secrets\.", WORKFLOW.read_text(encoding="utf-8"))


def test_the_gate_runs_on_a_github_hosted_runner_with_a_time_limit(job: dict[str, Any]) -> None:
    assert (
        job["runs-on"] == "ubuntu-latest"
    )  # never a self-hosted runner with a persistent database
    assert 0 < int(job["timeout-minutes"]) <= 45


def test_the_gate_has_two_exclusive_pinned_clusters(job: dict[str, Any]) -> None:
    services = job["services"]

    assert set(services) == {"flow", "tests"}
    assert {s["image"] for s in services.values()} == {"pgvector/pgvector:0.8.7-pg15"}
    ports = [str(p).split(":")[0] for s in services.values() for p in s["ports"]]
    assert len(ports) == len(set(ports)) == 2  # the two clusters never share a port


def test_the_gate_steps_exist_in_order(job: dict[str, Any]) -> None:
    calls = []
    for text in run_texts(job):
        found = re.findall(r"privilege_gate\.sh\s+([a-z-]+)", text)
        calls.extend(found)

    assert calls == GATE_STEPS


def test_no_step_can_hide_a_failure(job: dict[str, Any]) -> None:
    assert "continue-on-error" not in yaml.safe_dump(job)
    for text in run_texts(job):
        assert "|| true" not in text and "set +e" not in text and "exit 0" not in text
    for step in job["steps"]:
        assert step.get("if") in (None, "always()"), step  # only the summary may run on failure


def test_the_summary_always_runs_and_is_the_last_step(job: dict[str, Any]) -> None:
    last = job["steps"][-1]

    assert last.get("if") == "always()" and "privilege_gate.sh summary" in last["run"]


def test_the_administrator_credentials_are_not_job_wide(job: dict[str, Any]) -> None:
    assert not ADMIN_VARIABLES & set(job.get("env", {}))
    assert job["env"]["APP_ENV"] == "test"


def test_the_disposable_flag_is_set_only_by_the_gate_after_the_cluster_proved_itself() -> None:
    assert "TEST_CLUSTER_IS_DISPOSABLE" not in WORKFLOW.read_text(encoding="utf-8")
    script = (SCRIPTS / "privilege_gate.sh").read_text(encoding="utf-8")
    body = script[script.index("tests_environment() {") :]
    body = body[: body.index("\n}\n")]

    assert body.index("assert_disposable_cluster.py") < body.index(
        "TEST_CLUSTER_IS_DISPOSABLE=true"
    )
    assert script.count("TEST_CLUSTER_IS_DISPOSABLE=true") == 1


def test_checkout_does_not_keep_the_token(job: dict[str, Any]) -> None:
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
    )

    assert checkout["with"]["persist-credentials"] is False


def test_every_action_is_pinned_to_a_version(workflow: dict[str, Any]) -> None:
    for name, job_ in workflow["jobs"].items():
        for step in job_["steps"]:
            if "uses" in step:
                assert re.search(r"@v?\d", step["uses"]), (name, step["uses"])


def test_the_backend_job_leaves_the_role_bound_tests_to_the_gate(workflow: dict[str, Any]) -> None:
    runs = [str(s.get("run", "")) for s in workflow["jobs"]["backend"]["steps"]]
    integration = next(r for r in runs if "pytest tests/integration" in r)

    assert "not role_bound" in integration and "continue-on-error" not in integration


def test_the_gate_scripts_fail_on_any_error() -> None:
    for name in ("privilege_gate.sh",):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "set -euo pipefail" in text.splitlines()  # the option itself, not a comment
        assert "|| true" not in text and "set +e" not in text
    assert (SCRIPTS / "check_results.py").is_file()
    assert (SCRIPTS / "assert_disposable_cluster.py").is_file()
