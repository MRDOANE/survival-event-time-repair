from __future__ import annotations

import hashlib
import json
import logging
import math
import resource
import shutil
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from joblib import Parallel, delayed

from .data import load_dataset, make_splits
from .noise import corrupt_labels
from .official import (
    prepare_official_bundle,
    run_official_driver,
    validate_official_result,
)
from .util import (
    atomic_write_json,
    fingerprint,
    scientific_config_hash,
    seed_everything,
    utc_now,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrialSpec:
    dataset: dict[str, Any]
    regime: dict[str, Any]
    noise: dict[str, Any]
    seed: int
    scientific_config_hash: str

    def key(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "regime": self.regime,
            "noise": self.noise,
            "seed": self.seed,
            "scientific_config_hash": self.scientific_config_hash,
        }

    @property
    def trial_id(self) -> str:
        return fingerprint(self.key())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wilson_lower(successes: int, n: int, z: float = 1.959963984540054) -> float:
    if n <= 0:
        return float("nan")
    p = successes / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    radius = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return float(max(0.0, (center - radius) / denom))


def _subgroup_metrics(
    X: np.ndarray, covered: np.ndarray
) -> tuple[float, dict[str, Any]]:
    feature = X[:, 0]
    cuts = np.quantile(feature, [0.25, 0.50, 0.75])
    groups = np.digitize(feature, cuts)
    results: dict[str, Any] = {}
    coverages: list[float] = []
    for group in range(4):
        mask = groups == group
        value = float(covered[mask].mean()) if mask.any() else float("nan")
        results[f"x0_quartile_{group}"] = {"n": int(mask.sum()), "coverage": value}
        if mask.any():
            coverages.append(value)
    return float(min(coverages)), results


def _method_metrics(
    method: str,
    lower_bound: np.ndarray,
    true_time: np.ndarray,
    X_test: np.ndarray,
) -> dict[str, Any]:
    lower_bound = np.maximum(np.asarray(lower_bound, dtype=float), 0.0)
    covered = lower_bound <= true_time
    worst, subgroup = _subgroup_metrics(X_test, covered)
    n = len(covered)
    coverage = float(covered.mean())
    mean_true = float(np.mean(true_time))
    return {
        "method": method,
        "n_test": n,
        "coverage": coverage,
        "coverage_se": float(np.sqrt(coverage * (1 - coverage) / n)),
        "coverage_wilson_lower_95": _wilson_lower(int(covered.sum()), n),
        "mean_lpb": float(lower_bound.mean()),
        "median_lpb": float(np.median(lower_bound)),
        "p10_lpb": float(np.quantile(lower_bound, 0.10)),
        "normalized_mean_lpb": float(lower_bound.mean() / max(mean_true, 1e-12)),
        "zero_bound_fraction": float(np.mean(lower_bound <= 1e-10)),
        "worst_x0_quartile_coverage": worst,
        "subgroups": subgroup,
        "finite_bounds": bool(np.all(np.isfinite(lower_bound))),
        "max_bound": float(lower_bound.max()),
    }


def _effective_dataset(spec: TrialSpec) -> dict[str, Any]:
    return {
        **spec.dataset,
        "n": int(spec.regime["n"]),
        "target_censoring": float(spec.regime["target_censoring"]),
        "censoring_mechanism": str(spec.regime["censoring_mechanism"]),
    }


def _split_record(spec: TrialSpec, splits, n: int) -> dict[str, Any]:
    record = {
        "dataset": spec.dataset["name"],
        "regime": spec.regime["name"],
        "seed": spec.seed,
        "n": n,
        "split_seed_offset": 104729,
        "indices": splits.as_dict(),
    }
    record["fingerprint"] = fingerprint(record["indices"])
    return record


def execute_trial(
    spec: TrialSpec,
    config: dict[str, Any],
    output: Path,
    resume: bool,
    package_root: Path,
    upstream_root: Path,
    upstream_manifest: dict[str, Any],
) -> dict[str, Any]:
    path = output / "trials" / f"{spec.trial_id}.json"
    if resume and path.exists():
        with path.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if existing.get("scientific_config_hash") != spec.scientific_config_hash:
            raise RuntimeError(
                f"stale trial hash mismatch for {path}: "
                f"found {existing.get('scientific_config_hash')!r}, "
                f"expected {spec.scientific_config_hash!r}"
            )
        raw_path = output / str(existing.get("official_raw_result", ""))
        input_manifest_path = output / str(existing.get("official_input_manifest", ""))
        if existing.get("status") == "complete" and raw_path.exists():
            if _sha256(raw_path) != existing.get("official_raw_sha256"):
                raise RuntimeError(f"official raw-result hash mismatch for {raw_path}")
            if not input_manifest_path.is_file() or _sha256(
                input_manifest_path
            ) != existing.get("official_input_manifest_sha256"):
                raise RuntimeError(
                    f"official input-manifest hash mismatch for {input_manifest_path}"
                )
            return existing

    start = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    child_cpu_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    seed_everything(spec.seed)
    result: dict[str, Any] = {
        "schema_version": "3.0",
        "trial_id": spec.trial_id,
        "status": "running",
        "started_utc": utc_now(),
        "scientific_config_hash": spec.scientific_config_hash,
        **spec.key(),
    }
    bundle_dir = output / "work" / spec.trial_id
    raw_path = output / "official_raw" / f"{spec.trial_id}.json"
    try:
        experiment = config["experiment"]
        effective_dataset = _effective_dataset(spec)
        data = load_dataset(effective_dataset, spec.seed, list(experiment["split"]))
        splits = make_splits(len(data.X), list(experiment["split"]), spec.seed)
        split_record = _split_record(spec, splits, len(data.X))
        split_path = (
            output
            / "splits"
            / (f"{spec.dataset['name']}_{spec.regime['name']}_seed{spec.seed}.json")
        )
        if not split_path.exists():
            atomic_write_json(split_path, split_record)
        result["split_fingerprint"] = split_record["fingerprint"]

        corrupted = corrupt_labels(data, splits, spec.noise, spec.seed)
        bundle_manifest = prepare_official_bundle(
            bundle_dir,
            data,
            splits,
            corrupted,
            spec.noise,
            spec.regime,
            config,
            spec.seed,
            upstream_manifest,
        )
        input_manifest_path = output / "input_manifests" / f"{spec.trial_id}.json"
        atomic_write_json(input_manifest_path, bundle_manifest)
        official = run_official_driver(
            bundle_dir,
            raw_path,
            package_root,
            upstream_root,
            int(config["run"].get("trial_timeout_seconds", 3600)),
        )
        validate_official_result(official, len(splits.test), bundle_manifest)

        metrics = [
            _method_metrics(
                method,
                np.asarray(bound, dtype=float),
                data.true_time[splits.test],
                data.X[splits.test],
            )
            for method, bound in official["bounds"].items()
        ]
        method_map = {row["method"]: row for row in metrics}
        clean = method_map["clean_reference_drcosarc_adaptive"]
        naive = method_map["naive_corrupt_drcosarc_adaptive"]
        primary = method_map["midpoint_proxy_drcosarc_adaptive"]
        interval = method_map["interval_conditional_cal_drcosarc_adaptive"]
        interval_midpoint = method_map["interval_midpoint_cal_drcosarc_adaptive"]
        stopped = method_map["stopped_interval_lower_cal_drcosarc_adaptive"]
        lower = method_map["lower_edge_proxy_drcosarc_adaptive"]
        under = method_map["midpoint_under75_drcosarc_adaptive"]
        over = method_map["midpoint_over125_drcosarc_adaptive"]
        wrong = method_map["wrong_upper_shift_drcosarc_adaptive"]
        target_coverage = 1.0 - float(spec.regime["alpha"])
        naive_drop = clean["coverage"] - naive["coverage"]
        primary_repair = primary["coverage"] - naive["coverage"]
        interval_repair = interval["coverage"] - naive["coverage"]
        paired = {
            "clean_coverage": clean["coverage"],
            "target_coverage": target_coverage,
            "naive_coverage": naive["coverage"],
            "primary_coverage": primary["coverage"],
            "interval_aware_coverage": interval["coverage"],
            "interval_midpoint_coverage": interval_midpoint["coverage"],
            "stopped_coverage": stopped["coverage"],
            "lower_edge_coverage": lower["coverage"],
            "under75_coverage": under["coverage"],
            "over125_coverage": over["coverage"],
            "wrong_direction_coverage": wrong["coverage"],
            "clean_worst_x0_quartile_coverage": clean["worst_x0_quartile_coverage"],
            "naive_worst_x0_quartile_coverage": naive["worst_x0_quartile_coverage"],
            "primary_worst_x0_quartile_coverage": primary["worst_x0_quartile_coverage"],
            "interval_worst_x0_quartile_coverage": interval[
                "worst_x0_quartile_coverage"
            ],
            "matched_naive_coverage_drop": naive_drop,
            "primary_coverage_repair": primary_repair,
            "interval_aware_coverage_repair": interval_repair,
            "interval_midpoint_coverage_repair": interval_midpoint["coverage"]
            - naive["coverage"],
            "stopped_coverage_repair": stopped["coverage"] - naive["coverage"],
            "lower_edge_coverage_repair": lower["coverage"] - naive["coverage"],
            "under75_coverage_repair": under["coverage"] - naive["coverage"],
            "over125_coverage_repair": over["coverage"] - naive["coverage"],
            "wrong_direction_coverage_repair": wrong["coverage"] - naive["coverage"],
            "loss_recovery_fraction": (
                primary_repair / naive_drop if naive_drop > 1e-12 else None
            ),
            "clean_mean_lpb": clean["mean_lpb"],
            "naive_mean_lpb": naive["mean_lpb"],
            "primary_mean_lpb": primary["mean_lpb"],
            "interval_aware_mean_lpb": interval["mean_lpb"],
            "interval_midpoint_mean_lpb": interval_midpoint["mean_lpb"],
            "stopped_mean_lpb": stopped["mean_lpb"],
            "lower_edge_mean_lpb": lower["mean_lpb"],
            "primary_lpb_ratio_clean": primary["mean_lpb"]
            / max(clean["mean_lpb"], 1e-12),
            "primary_lpb_ratio_lower_edge": primary["mean_lpb"]
            / max(lower["mean_lpb"], 1e-12),
            "primary_zero_bound_fraction": primary["zero_bound_fraction"],
            "interval_aware_lpb_ratio_clean": interval["mean_lpb"]
            / max(clean["mean_lpb"], 1e-12),
            "interval_aware_zero_bound_fraction": interval["zero_bound_fraction"],
        }

        cpu_end = resource.getrusage(resource.RUSAGE_SELF)
        child_cpu_end = resource.getrusage(resource.RUSAGE_CHILDREN)
        result.update(
            {
                "status": "complete",
                "completed_utc": utc_now(),
                "data_provenance": data.provenance,
                "effective_dataset": effective_dataset,
                "noise_realization": corrupted.metadata,
                "correction_protocol": bundle_manifest["correction_protocol"],
                "correction_view_diagnostics": bundle_manifest["view_diagnostics"],
                "official_input_fingerprint": bundle_manifest["input_fingerprint"],
                "official_input_manifest": str(input_manifest_path.relative_to(output)),
                "official_input_manifest_sha256": _sha256(input_manifest_path),
                "split_sizes": {
                    "train": len(splits.train),
                    "protocol_estimation": len(splits.noise_estimation),
                    "calibration": len(splits.calibration),
                    "test": len(splits.test),
                },
                "official_source": upstream_manifest,
                "official_algorithm": official["algorithm"],
                "official_models": {
                    "survival": official["survival_model"],
                    "censoring": official["censoring_model"],
                },
                "official_diagnostics": official.get("diagnostics", {}),
                "official_raw_result": str(raw_path.relative_to(output)),
                "official_raw_sha256": _sha256(raw_path),
                "metrics": metrics,
                "paired_effect": paired,
                "resources": {
                    "wall_seconds": float(time.perf_counter() - start),
                    "python_user_cpu_seconds": float(
                        cpu_end.ru_utime - cpu_start.ru_utime
                    ),
                    "python_system_cpu_seconds": float(
                        cpu_end.ru_stime - cpu_start.ru_stime
                    ),
                    "r_child_user_cpu_seconds": float(
                        child_cpu_end.ru_utime - child_cpu_start.ru_utime
                    ),
                    "r_child_system_cpu_seconds": float(
                        child_cpu_end.ru_stime - child_cpu_start.ru_stime
                    ),
                    "max_rss_kb": float(cpu_end.ru_maxrss),
                    "r_child_max_rss_kb": float(child_cpu_end.ru_maxrss),
                },
            }
        )
        shutil.rmtree(bundle_dir)
    except Exception as exc:
        result.update(
            {
                "status": "error",
                "completed_utc": utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "failed_bundle": str(bundle_dir.relative_to(output))
                if bundle_dir.exists()
                else None,
                "resources": {"wall_seconds": float(time.perf_counter() - start)},
            }
        )
    atomic_write_json(path, result)
    return result


def build_trial_specs(config: dict[str, Any]) -> list[TrialSpec]:
    exp = config["experiment"]
    science_hash = scientific_config_hash(config)
    specs = [
        TrialSpec(
            dataset=dataset,
            regime=regime,
            noise=noise,
            seed=int(seed),
            scientific_config_hash=science_hash,
        )
        for dataset in exp["datasets"]
        for regime in exp["regimes"]
        for noise in exp["noise_scenarios"]
        for seed in exp["seeds"]
    ]
    ids = [spec.trial_id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate trial specifications")
    return specs


def run_trials(
    config: dict[str, Any],
    output: Path,
    resume: bool,
    n_jobs: int,
    package_root: Path,
    upstream_root: Path,
    upstream_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    specs = build_trial_specs(config)
    LOGGER.info("planned_trials=%d n_jobs=%d resume=%s", len(specs), n_jobs, resume)
    args = (config, output, resume, package_root, upstream_root, upstream_manifest)
    if n_jobs == 1:
        results = []
        for index, spec in enumerate(specs, start=1):
            LOGGER.info(
                "trial=%d/%d id=%s dataset=%s regime=%s noise=%s seed=%d",
                index,
                len(specs),
                spec.trial_id,
                spec.dataset["name"],
                spec.regime["name"],
                spec.noise["name"],
                spec.seed,
            )
            row = execute_trial(spec, *args)
            results.append(row)
            if row["status"] == "error" and config["run"].get("fail_fast", False):
                raise RuntimeError(row["error"])
        return results
    return Parallel(n_jobs=n_jobs, backend="loky", verbose=10)(
        delayed(execute_trial)(spec, *args) for spec in specs
    )
