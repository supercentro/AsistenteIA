"""Detection of the effective CPU quota (group 2, task 2.1)."""

from pathlib import Path

import pytest

from app.core import cpu_quota
from app.core.cpu_quota import detect_cpu_quota


@pytest.fixture(autouse=True)
def four_usable_cpus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpu_quota, "_usable_cpus", lambda: 4)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")


def test_without_cgroup_files_the_usable_cpus_are_returned(tmp_path: Path) -> None:
    assert detect_cpu_quota(cgroup_root=tmp_path) == 4


def test_cgroup_v2_quota_is_converted_to_cpus(tmp_path: Path) -> None:
    write(tmp_path, "cpu.max", "200000 100000\n")

    assert detect_cpu_quota(cgroup_root=tmp_path) == 2


def test_cgroup_v2_without_a_limit_uses_the_usable_cpus(tmp_path: Path) -> None:
    write(tmp_path, "cpu.max", "max 100000\n")

    assert detect_cpu_quota(cgroup_root=tmp_path) == 4


def test_a_fractional_quota_is_rounded_down_but_never_below_one(tmp_path: Path) -> None:
    write(tmp_path, "cpu.max", "150000 100000\n")
    assert detect_cpu_quota(cgroup_root=tmp_path) == 1

    write(tmp_path, "cpu.max", "50000 100000\n")
    assert detect_cpu_quota(cgroup_root=tmp_path) == 1


def test_a_quota_above_the_usable_cpus_is_capped(tmp_path: Path) -> None:
    write(tmp_path, "cpu.max", "1600000 100000\n")

    assert detect_cpu_quota(cgroup_root=tmp_path) == 4


def test_cgroup_v1_quota_is_used(tmp_path: Path) -> None:
    write(tmp_path, "cpu/cpu.cfs_quota_us", "300000\n")
    write(tmp_path, "cpu/cpu.cfs_period_us", "100000\n")

    assert detect_cpu_quota(cgroup_root=tmp_path) == 3


def test_cgroup_v1_without_a_limit_uses_the_usable_cpus(tmp_path: Path) -> None:
    write(tmp_path, "cpu/cpu.cfs_quota_us", "-1\n")
    write(tmp_path, "cpu/cpu.cfs_period_us", "100000\n")

    assert detect_cpu_quota(cgroup_root=tmp_path) == 4


@pytest.mark.parametrize("content", ["", "garbage", "100000", "0 100000", "100000 0", "-5 100"])
def test_unreadable_or_invalid_cgroup_content_falls_back(tmp_path: Path, content: str) -> None:
    write(tmp_path, "cpu.max", content)

    assert detect_cpu_quota(cgroup_root=tmp_path) == 4


def test_usable_cpus_never_returns_less_than_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()

    assert cpu_quota._usable_cpus() >= 1
