from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .correction import IntervalView, build_interval_view, recording_protocol
from .data import SplitIndices, SurvivalData
from .noise import CorruptedLabels
from .util import (
    atomic_write_json,
    compatibility_hotfix,
    fingerprint,
    implementation_hash,
)

UPSTREAM_COMMIT = "5b2cd20354e42105c980eabb4650240ae76dc866"
UPSTREAM_FILE_HASHES = {
    "utils_survival.R": "09d158eef9b75c1edd068a1d5bc8f717f03e93f5cafc019deb7d77aee8ecff67",
    "utils_censoring.R": "aa46002e97da67ca59814fe288482c192e14ce28cba0a40eab7f3d83c0ab7311",
    "utils_conformal.R": "f68f3693e2b76c4485afbdb2868e93a4bff4204e2372b0d4bfaaa80ef0973fb3",
}

REQUIRED_METHODS = {
    "clean_reference_drcosarc_adaptive",
    "naive_corrupt_drcosarc_adaptive",
    "lower_edge_proxy_drcosarc_adaptive",
    "midpoint_proxy_drcosarc_adaptive",
    "midpoint_under75_drcosarc_adaptive",
    "midpoint_over125_drcosarc_adaptive",
    "interval_conditional_cal_drcosarc_adaptive",
    "interval_midpoint_cal_drcosarc_adaptive",
    "stopped_interval_lower_cal_drcosarc_adaptive",
    "wrong_upper_shift_drcosarc_adaptive",
    "uncalibrated_corrupt_official_model",
    "uncalibrated_midpoint_model",
    "uncalibrated_interval_model",
    "trivial_zero_bound",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_upstream(path: Path) -> dict[str, Any]:
    root = path.resolve()
    code = root / "code" / "conf_surv"
    if not code.is_dir():
        raise RuntimeError(f"official DR-COSARC source directory is missing: {code}")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"cannot identify official DR-COSARC checkout at {root}: {exc}"
        ) from exc
    if commit != UPSTREAM_COMMIT:
        raise RuntimeError(
            f"official source commit mismatch: found {commit}, expected {UPSTREAM_COMMIT}"
        )
    hashes: dict[str, str] = {}
    for name, expected in UPSTREAM_FILE_HASHES.items():
        source = code / name
        found = _sha256(source)
        hashes[name] = found
        if found != expected:
            raise RuntimeError(
                f"official source hash mismatch for {name}: "
                f"found {found}, expected {expected}"
            )
    return {"root": str(root), "commit": commit, "source_sha256": hashes}


def _frame(X: np.ndarray, time: np.ndarray, status: np.ndarray) -> pd.DataFrame:
    X = np.asarray(X, dtype=float)
    frame = pd.DataFrame(X, columns=[f"X{j + 1}" for j in range(X.shape[1])])
    frame.insert(0, "status", np.asarray(status, dtype=np.int8))
    frame.insert(0, "time", np.maximum(np.asarray(time, dtype=float), 1e-8))
    if not np.all(np.isfinite(frame.to_numpy(dtype=float))):
        raise ValueError("official correction frame contains non-finite values")
    if set(np.unique(frame["status"])) - {0, 1}:
        raise ValueError("event indicators must be binary")
    return frame


def _interval_frame(
    X: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    status: np.ndarray,
) -> pd.DataFrame:
    X = np.asarray(X, dtype=float)
    frame = pd.DataFrame(X, columns=[f"X{j + 1}" for j in range(X.shape[1])])
    frame.insert(0, "status", np.asarray(status, dtype=np.int8))
    frame.insert(0, "time_upper", np.asarray(upper, dtype=float))
    frame.insert(0, "time_lower", np.asarray(lower, dtype=float))
    finite = frame.drop(columns=["time_upper"]).to_numpy(dtype=float)
    if not np.all(np.isfinite(finite)):
        raise ValueError("interval frame has invalid finite columns")
    censored = frame["status"].to_numpy() == 0
    if not np.all(np.isnan(frame.loc[censored, "time_upper"])):
        raise ValueError("right-censored rows require an open upper endpoint")
    event = ~censored
    if not np.all(np.isfinite(frame.loc[event, "time_upper"])):
        raise ValueError("event interval rows require finite upper endpoints")
    if np.any(
        frame.loc[event, "time_lower"].to_numpy()
        > frame.loc[event, "time_upper"].to_numpy() + 1e-12
    ):
        raise ValueError("event interval lower endpoint exceeds upper endpoint")
    return frame


def _numeric_sha256(frame: pd.DataFrame) -> str:
    """Hash the numerical table independently of CSV float formatting."""
    values = frame.to_numpy(dtype=np.float64)
    missing = np.isnan(values)
    canonical = np.where(missing, 0.0, values).astype("<f8", copy=False)
    header = json.dumps(
        {"columns": list(frame.columns), "shape": list(values.shape)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(header)
    digest.update(b"\0")
    digest.update(missing.astype(np.uint8).tobytes(order="C"))
    digest.update(b"\0")
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _write_frame(path: Path, frame: pd.DataFrame) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.17g", na_rep="")
    return {
        "file": path.name,
        "rows": len(frame),
        "sha256": _sha256(path),
        "numeric_sha256": _numeric_sha256(frame),
    }


def _proxy_files(
    bundle_dir: Path,
    label: str,
    X_train: np.ndarray,
    X_cal: np.ndarray,
    event_train: np.ndarray,
    event_cal: np.ndarray,
    time_train: np.ndarray,
    time_cal: np.ndarray,
) -> dict[str, Any]:
    return {
        "train": _write_frame(
            bundle_dir / f"{label}_train.csv",
            _frame(X_train, time_train, event_train),
        ),
        "cal": _write_frame(
            bundle_dir / f"{label}_cal.csv",
            _frame(X_cal, time_cal, event_cal),
        ),
    }


def _interval_suite_files(
    bundle_dir: Path,
    label: str,
    X_train: np.ndarray,
    X_cal: np.ndarray,
    event_train: np.ndarray,
    event_cal: np.ndarray,
    train_view: IntervalView,
    cal_view: IntervalView,
) -> dict[str, Any]:
    return {
        "interval_train": _write_frame(
            bundle_dir / f"{label}_interval_train.csv",
            _interval_frame(
                X_train,
                train_view.lower,
                train_view.upper,
                event_train,
            ),
        ),
        "interval_cal": _write_frame(
            bundle_dir / f"{label}_interval_cal.csv",
            _interval_frame(
                X_cal,
                cal_view.lower,
                cal_view.upper,
                event_cal,
            ),
        ),
        "lower_proxy_train": _write_frame(
            bundle_dir / f"{label}_lower_proxy_train.csv",
            _frame(X_train, train_view.lower_proxy, event_train),
        ),
        "lower_proxy_cal": _write_frame(
            bundle_dir / f"{label}_lower_proxy_cal.csv",
            _frame(X_cal, cal_view.lower_proxy, event_cal),
        ),
        "midpoint_proxy_train": _write_frame(
            bundle_dir / f"{label}_midpoint_proxy_train.csv",
            _frame(X_train, train_view.midpoint_proxy, event_train),
        ),
        "midpoint_proxy_cal": _write_frame(
            bundle_dir / f"{label}_midpoint_proxy_cal.csv",
            _frame(X_cal, cal_view.midpoint_proxy, event_cal),
        ),
    }


def prepare_official_bundle(
    bundle_dir: Path,
    data: SurvivalData,
    splits: SplitIndices,
    corrupted: CorruptedLabels,
    noise_spec: dict[str, Any],
    regime: dict[str, Any],
    config: dict[str, Any],
    seed: int,
    upstream: dict[str, Any],
) -> dict[str, Any]:
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)
    exp = config["experiment"]
    correction = config["correction"]
    tr, cal, te = splits.train, splits.calibration, splits.test
    X_train, X_cal = data.X[tr], data.X[cal]
    event_train = corrupted.observed_event[tr]
    event_cal = corrupted.observed_event[cal]
    time_train = corrupted.observed_time[tr]
    time_cal = corrupted.observed_time[cal]

    protocol = recording_protocol(noise_spec, corrupted, splits)
    floor = float(correction.get("lower_floor", 1e-6))
    wrong = float(correction.get("wrong_direction_multiplier", 0.5))
    sensitivity = correction["span_sensitivity_multipliers"]
    multipliers = {
        "primary": 1.0,
        "under75": float(sensitivity["under"]),
        "over125": float(sensitivity["over"]),
    }
    train_views = {
        label: build_interval_view(
            time_train,
            event_train,
            protocol,
            recorded_lower=corrupted.recorded_lower[tr],
            recorded_upper=corrupted.recorded_upper[tr],
            span_multiplier=multiplier,
            lower_floor=floor,
            wrong_direction_multiplier=wrong,
        )
        for label, multiplier in multipliers.items()
    }
    cal_views = {
        label: build_interval_view(
            time_cal,
            event_cal,
            protocol,
            recorded_lower=corrupted.recorded_lower[cal],
            recorded_upper=corrupted.recorded_upper[cal],
            span_multiplier=multiplier,
            lower_floor=floor,
            wrong_direction_multiplier=wrong,
        )
        for label, multiplier in multipliers.items()
    }

    files: dict[str, Any] = {
        "test": _write_frame(
            bundle_dir / "test.csv",
            _frame(data.X[te], data.clean_time[te], data.clean_event[te]),
        ),
        "clean": _proxy_files(
            bundle_dir,
            "clean",
            X_train,
            X_cal,
            data.clean_event[tr],
            data.clean_event[cal],
            data.clean_time[tr],
            data.clean_time[cal],
        ),
        "corrupt": _proxy_files(
            bundle_dir,
            "corrupt",
            X_train,
            X_cal,
            event_train,
            event_cal,
            time_train,
            time_cal,
        ),
        "lower_edge": _proxy_files(
            bundle_dir,
            "lower_edge",
            X_train,
            X_cal,
            event_train,
            event_cal,
            train_views["primary"].lower_proxy,
            cal_views["primary"].lower_proxy,
        ),
        "midpoint": _proxy_files(
            bundle_dir,
            "midpoint",
            X_train,
            X_cal,
            event_train,
            event_cal,
            train_views["primary"].midpoint_proxy,
            cal_views["primary"].midpoint_proxy,
        ),
        "wrong_direction": _proxy_files(
            bundle_dir,
            "wrong_direction",
            X_train,
            X_cal,
            event_train,
            event_cal,
            train_views["primary"].wrong_direction_proxy,
            cal_views["primary"].wrong_direction_proxy,
        ),
        "midpoint_under75": _proxy_files(
            bundle_dir,
            "midpoint_under75",
            X_train,
            X_cal,
            event_train,
            event_cal,
            train_views["under75"].midpoint_proxy,
            cal_views["under75"].midpoint_proxy,
        ),
        "midpoint_over125": _proxy_files(
            bundle_dir,
            "midpoint_over125",
            X_train,
            X_cal,
            event_train,
            event_cal,
            train_views["over125"].midpoint_proxy,
            cal_views["over125"].midpoint_proxy,
        ),
        "interval_primary": _interval_suite_files(
            bundle_dir,
            "interval_primary",
            X_train,
            X_cal,
            event_train,
            event_cal,
            train_views["primary"],
            cal_views["primary"],
        ),
    }

    view_diagnostics = {
        label: {
            "train": train_views[label].metadata,
            "calibration": cal_views[label].metadata,
        }
        for label in multipliers
    }
    input_payload = {
        "files": files,
        "protocol": protocol,
        "view_diagnostics": view_diagnostics,
        "noise_name": noise_spec["name"],
        "regime": regime,
        "seed": int(seed),
    }
    manifest = {
        "schema_version": "3.0",
        "official_source": upstream,
        "alpha": float(regime["alpha"]),
        "survival_model": str(exp["official_models"]["survival"]),
        "censoring_model": str(exp["official_models"]["censoring"]),
        "finite_sample_correction": bool(exp.get("finite_sample_correction", False)),
        "seed": int(seed),
        "regime": regime,
        "test_n": len(te),
        "files": files,
        "correction_protocol": protocol,
        "view_diagnostics": view_diagnostics,
        "input_fingerprint": fingerprint(input_payload, 32),
    }
    hotfix = compatibility_hotfix(config)
    if hotfix is not None:
        manifest.update(
            {
                "compatibility_hotfix_id": hotfix["id"],
                "execution_implementation_sha256": implementation_hash(),
            }
        )
    atomic_write_json(bundle_dir / "manifest.json", manifest)
    return manifest


def run_official_driver(
    bundle_dir: Path,
    output_json: Path,
    package_root: Path,
    upstream_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    driver = package_root / "r" / "official_trial.R"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DRCOSARC_UPSTREAM_DIR"] = str(upstream_root.resolve())
    command = ["Rscript", "--vanilla", str(driver), str(bundle_dir), str(output_json)]
    try:
        completed = subprocess.run(
            command,
            cwd=package_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Rscript is unavailable; run scripts/bootstrap_official.sh"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"official DR-COSARC trial timed out after {timeout_seconds}s"
        ) from exc
    (bundle_dir / "r_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (bundle_dir / "r_stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(
            f"official R driver failed with exit {completed.returncode}:\n{tail}"
        )
    if not output_json.exists():
        raise RuntimeError(
            "official R driver exited successfully without writing its result"
        )
    with output_json.open("r", encoding="utf-8") as handle:
        result = json.load(handle)
    if result.get("status") != "complete":
        raise RuntimeError(f"official R result is incomplete: {result}")
    return result


def validate_official_result(
    result: dict[str, Any], test_n: int, manifest: dict[str, Any]
) -> None:
    methods = result.get("bounds")
    if not isinstance(methods, dict) or REQUIRED_METHODS != set(methods):
        found = set(methods or {})
        raise ValueError(
            "official result method mismatch: "
            f"missing={sorted(REQUIRED_METHODS - found)}, "
            f"unexpected={sorted(found - REQUIRED_METHODS)}"
        )
    if result.get("status") != "complete" or result.get("algorithm") != "adaptive":
        raise ValueError("official result did not complete the adaptive code path")
    if result.get("input_fingerprint") != manifest["input_fingerprint"]:
        raise ValueError(
            "official result is not bound to the prepared correction views"
        )
    if result.get("official_source_commit") != UPSTREAM_COMMIT:
        raise ValueError("official result source commit is not the pinned commit")
    for name, values in methods.items():
        array = np.asarray(values, dtype=float)
        if array.shape != (test_n,):
            raise ValueError(
                f"{name} returned shape {array.shape}, expected {(test_n,)}"
            )
        if not np.all(np.isfinite(array)) or np.any(array < 0):
            raise ValueError(f"{name} returned invalid lower bounds")
