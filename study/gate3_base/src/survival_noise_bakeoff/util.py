from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=json_default
    )


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def fingerprint(value: Any, length: int = 16) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:length]


def implementation_hash() -> str:
    """Hash Python and R scientific source to invalidate stale results."""
    project_root = Path(__file__).resolve().parents[2]
    paths = list(project_root.glob("src/survival_noise_bakeoff/*.py"))
    paths.extend(project_root.glob("r/*.R"))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(project_root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def scientific_config_payload(config: dict[str, Any]) -> dict[str, Any]:
    """Return assumptions that determine trials or the preregistered gate.

    Operational settings such as worker count, output name, and fail-fast do
    not alter the hash. Bootstrap repetitions do, because they affect the gate.
    """
    return {
        "scientific_schema": "survival-drcosarc-gate3-expansion-v1",
        "implementation_sha256": implementation_hash(),
        "run_kind": config["run"]["kind"],
        "bootstrap_reps": int(config["run"].get("bootstrap_reps", 0)),
        "experiment": config["experiment"],
        "correction": config["correction"],
        "gate": config["gate"],
    }


def scientific_config_hash(config: dict[str, Any]) -> str:
    return fingerprint(scientific_config_payload(config), length=32)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path, json.dumps(value, indent=2, sort_keys=True, default=json_default) + "\n"
    )


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def environment_manifest(root: Path) -> dict[str, Any]:
    try:
        import sklearn

        sklearn_version = sklearn.__version__
    except Exception:
        sklearn_version = None
    try:
        import scipy

        scipy_version = scipy.__version__
    except Exception:
        scipy_version = None
    return {
        "created_utc": utc_now(),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "numpy": np.__version__,
        "scipy": scipy_version,
        "scikit_learn": sklearn_version,
        "git_commit": git_commit(root),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "slurm_cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
    }


def validate_probability(name: str, value: float) -> None:
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
