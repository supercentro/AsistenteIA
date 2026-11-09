"""Effective CPU quota of the process, used to size the inference threads.

On a container limited with a CPU quota, `torch` must use as many threads as the quota: with its
default thread count (the CPUs of the host) inference was about 33 times slower in the spike.
"""

import math
import os
from pathlib import Path

DEFAULT_CGROUP_ROOT = Path("/sys/fs/cgroup")


def _usable_cpus() -> int:
    """CPUs the process may run on (affinity when available), never below one."""
    affinity = getattr(os, "sched_getaffinity", None)  # absent on Windows and macOS
    if affinity is not None:
        return max(1, len(affinity(0)))
    return max(1, os.cpu_count() or 1)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _quota_to_cpus(quota: str, period: str) -> float | None:
    try:
        quota_value = int(quota)
        period_value = int(period)
    except ValueError:
        return None
    if quota_value <= 0 or period_value <= 0:
        return None
    return quota_value / period_value


def _cgroup_cpus(cgroup_root: Path) -> float | None:
    """Return the CPU limit of the cgroup (v2, then v1), or None when there is none."""
    v2 = _read(cgroup_root / "cpu.max")
    if v2 is not None:
        parts = v2.split()
        if len(parts) == 2 and parts[0] != "max":
            return _quota_to_cpus(parts[0], parts[1])
        return None
    quota = _read(cgroup_root / "cpu" / "cpu.cfs_quota_us")
    period = _read(cgroup_root / "cpu" / "cpu.cfs_period_us")
    if quota is not None and period is not None:
        return _quota_to_cpus(quota, period)
    return None


def detect_cpu_quota(cgroup_root: Path = DEFAULT_CGROUP_ROOT) -> int:
    """Number of CPUs the process can really use: the cgroup quota rounded down, capped by the
    usable CPUs, and never below one. Without a readable limit, the usable CPUs."""
    usable = _usable_cpus()
    limit = _cgroup_cpus(cgroup_root)
    if limit is None:
        return usable
    return max(1, min(usable, math.floor(limit)))
