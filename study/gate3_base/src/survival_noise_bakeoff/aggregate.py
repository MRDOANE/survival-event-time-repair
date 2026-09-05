from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .util import atomic_write_json, atomic_write_text, scientific_config_hash, utc_now


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_trials(output: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((output / "trials").glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
        record["_source_filename"] = path.name
        records.append(record)
    return records


def _trial_completeness(
    trials: list[dict[str, Any]], config: dict[str, Any], output: Path
) -> dict[str, Any]:
    from .experiment import build_trial_specs

    expected_ids = [spec.trial_id for spec in build_trial_specs(config)]
    observed_ids = [str(trial.get("trial_id")) for trial in trials]
    expected_set, observed_set = set(expected_ids), set(observed_ids)
    counts = (
        pd.Series(observed_ids, dtype="object").value_counts()
        if observed_ids
        else pd.Series(dtype=int)
    )
    duplicates = sorted(str(value) for value in counts[counts > 1].index.tolist())
    filename_mismatches = sorted(
        str(trial.get("_source_filename"))
        for trial in trials
        if trial.get("_source_filename") != f"{trial.get('trial_id')}.json"
    )
    raw_failures: list[str] = []
    input_binding_failures: list[str] = []
    input_manifest_failures: list[str] = []
    for trial in trials:
        if trial.get("status") != "complete":
            continue
        relative = trial.get("official_raw_result")
        raw = output / str(relative or "")
        if (
            not relative
            or not raw.is_file()
            or _sha256(raw) != trial.get("official_raw_sha256")
        ):
            raw_failures.append(str(trial.get("trial_id")))
            continue
        with raw.open("r", encoding="utf-8") as handle:
            raw_record = json.load(handle)
        manifest_relative = trial.get("official_input_manifest")
        input_manifest = output / str(manifest_relative or "")
        if (
            not manifest_relative
            or not input_manifest.is_file()
            or _sha256(input_manifest) != trial.get("official_input_manifest_sha256")
        ):
            input_manifest_failures.append(str(trial.get("trial_id")))
            continue
        with input_manifest.open("r", encoding="utf-8") as handle:
            input_record = json.load(handle)
        expected_fingerprint = trial.get("official_input_fingerprint")
        if (
            raw_record.get("input_fingerprint") != expected_fingerprint
            or input_record.get("input_fingerprint") != expected_fingerprint
        ):
            input_binding_failures.append(str(trial.get("trial_id")))
    complete = bool(
        len(trials) == len(expected_ids)
        and observed_set == expected_set
        and not duplicates
        and not filename_mismatches
        and not raw_failures
        and not input_manifest_failures
        and not input_binding_failures
    )
    return {
        "complete": complete,
        "expected_trial_count": len(expected_ids),
        "observed_trial_file_count": len(trials),
        "observed_unique_trial_count": len(observed_set),
        "missing_trial_count": len(expected_set - observed_set),
        "unexpected_trial_count": len(observed_set - expected_set),
        "duplicate_trial_id_count": len(duplicates),
        "filename_mismatch_count": len(filename_mismatches),
        "raw_integrity_failure_count": len(raw_failures),
        "input_manifest_failure_count": len(input_manifest_failures),
        "input_binding_failure_count": len(input_binding_failures),
        "missing_trial_ids_preview": sorted(expected_set - observed_set)[:10],
        "unexpected_trial_ids_preview": sorted(observed_set - expected_set)[:10],
        "raw_integrity_failures_preview": raw_failures[:10],
        "input_manifest_failures_preview": input_manifest_failures[:10],
        "input_binding_failures_preview": input_binding_failures[:10],
    }


def _flatten(
    trials: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paired_rows, metric_rows, resource_rows = [], [], []
    for trial in trials:
        noise = trial.get("noise", {})
        dataset = trial.get("dataset", {})
        regime = trial.get("regime", {})
        effective = trial.get("effective_dataset", {})
        provenance = trial.get("data_provenance", {})
        protocol = trial.get("correction_protocol", {})
        base = {
            "trial_id": trial.get("trial_id"),
            "status": trial.get("status"),
            "dataset": dataset.get("name"),
            "mechanism": dataset.get("mechanism"),
            "outcome_distribution": dataset.get("outcome_distribution"),
            "regime": regime.get("name"),
            "alpha": regime.get("alpha"),
            "target_coverage": (
                1.0 - float(regime.get("alpha"))
                if regime.get("alpha") is not None
                else None
            ),
            "n": effective.get("n", regime.get("n")),
            "target_censoring": effective.get(
                "target_censoring", regime.get("target_censoring")
            ),
            "censoring_mechanism": effective.get(
                "censoring_mechanism", regime.get("censoring_mechanism")
            ),
            "condition": noise.get("name"),
            "condition_family": noise.get("family"),
            "gate_role": noise.get("gate_role"),
            "severity": noise.get("severity"),
            "protocol_source": protocol.get("source"),
            "seed": trial.get("seed"),
            "fallback_used": provenance.get("fallback_used", False),
            "require_public": provenance.get("require_public", False),
            "realized_time_errors": trial.get("noise_realization", {}).get(
                "time_error_count"
            ),
            "protocol_mode": protocol.get("mode"),
            "protocol_value": protocol.get(
                "interval_width", protocol.get("delay_fraction", "row_specific")
            ),
        }
        resource_rows.append(
            {**base, **trial.get("resources", {}), "error": trial.get("error")}
        )
        if trial.get("status") != "complete":
            continue
        paired_rows.append({**base, **trial["paired_effect"]})
        for metric in trial["metrics"]:
            metric_rows.append({**base, **metric})
    return (
        pd.DataFrame(paired_rows),
        pd.DataFrame(metric_rows),
        pd.DataFrame(resource_rows),
    )


def _bootstrap_lower(frame: pd.DataFrame, column: str, reps: int, seed: int) -> float:
    cluster_values = (
        frame.groupby("seed", sort=True)[column].mean().to_numpy(dtype=float)
    )
    if len(cluster_values) == 0:
        return float("nan")
    if len(cluster_values) == 1:
        return float(cluster_values[0])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(cluster_values), size=(reps, len(cluster_values)))
    return float(np.quantile(cluster_values[draws].mean(axis=1), 0.025))


def _cell_summary(paired: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    reps = int(config["run"].get("bootstrap_reps", 10000))
    breadth = config["gate"]["breadth"]
    branch_thresholds = {
        "primary": config["gate"]["midpoint"]["cell"],
        "interval": config["gate"]["interval_aware"]["cell"],
    }
    regime_map = {str(row["name"]): row for row in config["experiment"]["regimes"]}
    rows: list[dict[str, Any]] = []
    for (condition, regime), frame in paired.groupby(
        ["condition", "regime"], sort=False
    ):
        seed_bytes = hashlib.sha256(f"{condition}|{regime}".encode("utf-8")).digest()[
            :8
        ]
        bootstrap_seed = int.from_bytes(seed_bytes, "big") % (2**32 - 1)
        target = float(frame["target_coverage"].iloc[0])
        clean = float(frame["clean_coverage"].mean())
        naive = float(frame["naive_coverage"].mean())
        primary = float(frame["primary_coverage"].mean())
        interval = float(frame["interval_aware_coverage"].mean())
        stopped = float(frame["stopped_coverage"].mean())
        clean_lpb = float(frame["clean_mean_lpb"].mean())
        dataset_primary = frame.groupby("dataset")["primary_coverage_repair"].mean()
        dataset_interval = frame.groupby("dataset")[
            "interval_aware_coverage_repair"
        ].mean()
        row = {
            "condition": condition,
            "condition_family": frame["condition_family"].iloc[0],
            "gate_role": frame["gate_role"].iloc[0],
            "regime": regime,
            "protocol_source": frame["protocol_source"].iloc[0],
            "target_coverage": target,
            "coverage_tolerance": float(regime_map[str(regime)]["coverage_tolerance"]),
            "trials": len(frame),
            "datasets": int(frame["dataset"].nunique()),
            "clean_coverage": clean,
            "naive_coverage": naive,
            "primary_coverage": primary,
            "interval_aware_coverage": interval,
            "stopped_coverage": stopped,
            "matched_naive_coverage_drop": float(
                frame["matched_naive_coverage_drop"].mean()
            ),
            "naive_drop_lower_95_seed_clustered": _bootstrap_lower(
                frame, "matched_naive_coverage_drop", reps, bootstrap_seed
            ),
            "primary_coverage_repair": float(frame["primary_coverage_repair"].mean()),
            "primary_repair_lower_95_seed_clustered": _bootstrap_lower(
                frame, "primary_coverage_repair", reps, bootstrap_seed + 17
            ),
            "interval_aware_coverage_repair": float(
                frame["interval_aware_coverage_repair"].mean()
            ),
            "interval_repair_lower_95_seed_clustered": _bootstrap_lower(
                frame, "interval_aware_coverage_repair", reps, bootstrap_seed + 31
            ),
            "primary_positive_trial_fraction": float(
                np.mean(frame["primary_coverage_repair"] > 0)
            ),
            "interval_positive_trial_fraction": float(
                np.mean(frame["interval_aware_coverage_repair"] > 0)
            ),
            "primary_dataset_success_count": int(
                np.sum(dataset_primary >= float(breadth["min_dataset_cell_repair"]))
            ),
            "interval_dataset_success_count": int(
                np.sum(dataset_interval >= float(breadth["min_dataset_cell_repair"]))
            ),
            "primary_accuracy_gain_vs_naive": float(
                abs(naive - target) - abs(primary - target)
            ),
            "interval_accuracy_gain_vs_naive": float(
                abs(naive - target) - abs(interval - target)
            ),
            "primary_accuracy_gain_vs_stopped": float(
                abs(stopped - target) - abs(primary - target)
            ),
            "interval_accuracy_gain_vs_stopped": float(
                abs(stopped - target) - abs(interval - target)
            ),
            "primary_mean_lpb": float(frame["primary_mean_lpb"].mean()),
            "interval_aware_mean_lpb": float(frame["interval_aware_mean_lpb"].mean()),
            "clean_mean_lpb": clean_lpb,
            "primary_lpb_ratio_clean": float(
                frame["primary_mean_lpb"].mean() / max(clean_lpb, 1e-12)
            ),
            "interval_lpb_ratio_clean": float(
                frame["interval_aware_mean_lpb"].mean() / max(clean_lpb, 1e-12)
            ),
            "primary_zero_bound_fraction": float(
                frame["primary_zero_bound_fraction"].mean()
            ),
            "interval_zero_bound_fraction": float(
                frame["interval_aware_zero_bound_fraction"].mean()
            ),
            "primary_worst_quartile_coverage": float(
                frame["primary_worst_x0_quartile_coverage"].mean()
            ),
            "interval_worst_quartile_coverage": float(
                frame["interval_worst_x0_quartile_coverage"].mean()
            ),
            "under75_coverage": float(frame["under75_coverage"].mean()),
            "over125_coverage": float(frame["over125_coverage"].mean()),
            "wrong_direction_coverage": float(frame["wrong_direction_coverage"].mean()),
            "realized_time_errors_mean": float(frame["realized_time_errors"].mean()),
        }
        for branch, threshold in branch_thresholds.items():
            coverage = (
                row["primary_coverage"]
                if branch == "primary"
                else row["interval_aware_coverage"]
            )
            repair = (
                row["primary_coverage_repair"]
                if branch == "primary"
                else row["interval_aware_coverage_repair"]
            )
            lower = (
                row["primary_repair_lower_95_seed_clustered"]
                if branch == "primary"
                else row["interval_repair_lower_95_seed_clustered"]
            )
            positive = (
                row["primary_positive_trial_fraction"]
                if branch == "primary"
                else row["interval_positive_trial_fraction"]
            )
            dataset_count = (
                row["primary_dataset_success_count"]
                if branch == "primary"
                else row["interval_dataset_success_count"]
            )
            accuracy = (
                row["primary_accuracy_gain_vs_naive"]
                if branch == "primary"
                else row["interval_accuracy_gain_vs_naive"]
            )
            lpb = (
                row["primary_lpb_ratio_clean"]
                if branch == "primary"
                else row["interval_lpb_ratio_clean"]
            )
            row[f"{branch}_cell_success"] = bool(
                row["matched_naive_coverage_drop"]
                >= float(breadth["min_cell_naive_drop"])
                and repair >= float(threshold["min_repair"])
                and lower > float(threshold["min_repair_lower_95"])
                and abs(coverage - target) <= row["coverage_tolerance"]
                and positive >= float(threshold["min_positive_trial_fraction"])
                and dataset_count >= int(threshold["min_dataset_success_count"])
                and accuracy >= float(threshold["min_accuracy_gain_vs_naive"])
                and lpb >= float(threshold["min_lpb_ratio_clean"])
            )
        rows.append(row)
    condition_order = {
        row["name"]: i for i, row in enumerate(config["experiment"]["noise_scenarios"])
    }
    regime_order = {
        row["name"]: i for i, row in enumerate(config["experiment"]["regimes"])
    }
    result = pd.DataFrame(rows)
    result["_condition_order"] = result["condition"].map(condition_order)
    result["_regime_order"] = result["regime"].map(regime_order)
    return (
        result.sort_values(["_condition_order", "_regime_order"])
        .drop(columns=["_condition_order", "_regime_order"])
        .reset_index(drop=True)
    )


def _dataset_summary(paired: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    primary_names = set(map(str, config["gate"]["primary_conditions"]))
    threshold = float(config["gate"]["breadth"]["min_dataset_pooled_repair"])
    frame = paired[paired["condition"].isin(primary_names)].copy()
    frame["primary_accuracy_gain"] = (
        frame["naive_coverage"] - frame["target_coverage"]
    ).abs() - (frame["primary_coverage"] - frame["target_coverage"]).abs()
    frame["interval_accuracy_gain"] = (
        frame["naive_coverage"] - frame["target_coverage"]
    ).abs() - (frame["interval_aware_coverage"] - frame["target_coverage"]).abs()
    rows = []
    for dataset, group in frame.groupby("dataset", sort=False):
        row = {
            "dataset": dataset,
            "trials": len(group),
            "primary_mean_repair": float(group["primary_coverage_repair"].mean()),
            "interval_mean_repair": float(
                group["interval_aware_coverage_repair"].mean()
            ),
            "primary_positive_fraction": float(
                np.mean(group["primary_coverage_repair"] > 0)
            ),
            "interval_positive_fraction": float(
                np.mean(group["interval_aware_coverage_repair"] > 0)
            ),
            "primary_accuracy_gain": float(group["primary_accuracy_gain"].mean()),
            "interval_accuracy_gain": float(group["interval_accuracy_gain"].mean()),
        }
        row["primary_dataset_success"] = bool(
            row["primary_mean_repair"] >= threshold
            and row["primary_accuracy_gain"] > 0
            and row["primary_positive_fraction"] >= 0.60
        )
        row["interval_dataset_success"] = bool(
            row["interval_mean_repair"] >= threshold
            and row["interval_accuracy_gain"] > 0
            and row["interval_positive_fraction"] >= 0.60
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _native(value: Any) -> Any:
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _row_record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _native(value) for key, value in row.items()}


def _branch_decision(
    branch: str,
    anchor: dict[str, Any],
    primary_cells: pd.DataFrame,
    primary_trials: pd.DataFrame,
    datasets: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, bool], dict[str, Any]]:
    key = "primary" if branch == "midpoint" else "interval"
    branch_key = "midpoint" if branch == "midpoint" else "interval_aware"
    branch_config = config["gate"][branch_key]
    anchor_config = branch_config["anchor"]
    breadth = config["gate"]["breadth"]
    target = float(anchor["target_coverage"])
    anchor_coverage = float(
        anchor["primary_coverage" if key == "primary" else "interval_aware_coverage"]
    )
    anchor_repair = float(
        anchor[
            "primary_coverage_repair"
            if key == "primary"
            else "interval_aware_coverage_repair"
        ]
    )
    anchor_lower = float(
        anchor[
            "primary_repair_lower_95_seed_clustered"
            if key == "primary"
            else "interval_repair_lower_95_seed_clustered"
        ]
    )
    anchor_positive = float(
        anchor[
            "primary_positive_trial_fraction"
            if key == "primary"
            else "interval_positive_trial_fraction"
        ]
    )
    anchor_dataset_count = int(
        anchor[
            "primary_dataset_success_count"
            if key == "primary"
            else "interval_dataset_success_count"
        ]
    )
    anchor_lpb = float(
        anchor[
            "primary_lpb_ratio_clean"
            if key == "primary"
            else "interval_lpb_ratio_clean"
        ]
    )
    anchor_accuracy_stopped = float(
        anchor[
            "primary_accuracy_gain_vs_stopped"
            if key == "primary"
            else "interval_accuracy_gain_vs_stopped"
        ]
    )
    central = {
        "anchor_naive_drop": anchor["matched_naive_coverage_drop"]
        >= float(config["gate"]["anchor_failure"]["min_naive_drop"]),
        "anchor_naive_undercoverage": anchor["naive_coverage"]
        <= target - float(config["gate"]["anchor_failure"]["min_undercoverage"]),
        "anchor_naive_drop_lower": anchor["naive_drop_lower_95_seed_clustered"]
        > float(config["gate"]["anchor_failure"]["min_naive_drop_lower_95"]),
        "anchor_repair": anchor_repair >= float(anchor_config["min_repair"]),
        "anchor_repair_lower": anchor_lower
        > float(anchor_config["min_repair_lower_95"]),
        "anchor_coverage": abs(anchor_coverage - target)
        <= float(anchor_config["coverage_tolerance"]),
        "anchor_positive_trials": anchor_positive
        >= float(anchor_config["min_positive_trial_fraction"]),
        "anchor_dataset_breadth": anchor_dataset_count
        >= int(anchor_config["min_dataset_success_count"]),
        "anchor_informativeness": anchor_lpb
        >= float(anchor_config["min_lpb_ratio_clean"]),
        "anchor_accuracy_vs_stopped": anchor_accuracy_stopped
        >= float(anchor_config["min_accuracy_gain_vs_stopped"]),
    }
    if branch == "midpoint":
        recovery = anchor_repair / max(
            float(anchor["matched_naive_coverage_drop"]), 1e-12
        )
        central["anchor_loss_recovery"] = bool(
            recovery >= float(anchor_config["min_loss_recovery_fraction"])
            and recovery <= float(anchor_config["max_loss_recovery_fraction"])
        )

    success_column = f"{key}_cell_success"
    accuracy_column = f"{key}_accuracy_gain_vs_naive"
    coverage_column = (
        "primary_coverage" if key == "primary" else "interval_aware_coverage"
    )
    repair_column = (
        "primary_coverage_repair"
        if key == "primary"
        else "interval_aware_coverage_repair"
    )
    success_count = int(primary_cells[success_column].sum())
    main = primary_cells[
        primary_cells["regime"] == str(config["gate"]["anchor_regime"])
    ]
    main_success_count = int(main[success_column].sum())
    regime_counts = primary_cells.groupby("regime")[success_column].sum()
    condition_counts = primary_cells.groupby("condition")[success_column].sum()
    regime_breadth_count = int(
        np.sum(regime_counts >= int(breadth["min_success_conditions_per_regime"]))
    )
    condition_breadth_count = int(
        np.sum(condition_counts >= int(breadth["min_success_regimes_per_condition"]))
    )
    pooled_lower = _bootstrap_lower(
        primary_trials,
        repair_column,
        int(config["run"].get("bootstrap_reps", 10000)),
        731 if key == "primary" else 947,
    )
    catastrophic = np.abs(
        primary_cells[coverage_column] - primary_cells["target_coverage"]
    ) > float(breadth["catastrophic_coverage_error"])
    expansion_core = {
        "cell_breadth": success_count >= int(breadth["min_success_cells"]),
        "main_condition_breadth": main_success_count
        >= int(breadth["min_main_success_conditions"]),
        "regime_breadth": regime_breadth_count >= int(breadth["min_success_regimes"]),
        "condition_breadth": condition_breadth_count
        >= int(breadth["min_success_conditions"]),
        "dataset_breadth": int(datasets[f"{key}_dataset_success"].sum())
        >= int(breadth["min_success_datasets"]),
        "pooled_repair_lower": pooled_lower
        > float(breadth["min_pooled_repair_lower_95"]),
        "catastrophic_cell_control": float(np.mean(catastrophic))
        <= float(breadth["max_catastrophic_cell_fraction"]),
    }

    estimated = primary_cells[
        primary_cells["protocol_source"] == "estimated_from_protocol_split"
    ]
    visits = primary_cells[
        primary_cells["condition_family"] == "recorded_visit_interval"
    ]
    positive_fraction = float(np.mean(primary_trials[repair_column] > 0))
    cell_accuracy_fraction = float(np.mean(primary_cells[accuracy_column] > 0))
    pooled_lpb_column = (
        "primary_lpb_ratio_clean"
        if key == "primary"
        else "interval_aware_lpb_ratio_clean"
    )
    pooled_lpb = float(primary_trials[pooled_lpb_column].mean())
    support = {
        "estimated_protocol": int(estimated[success_column].sum())
        >= int(breadth["min_estimated_success_regimes"]),
        "recorded_visit_schedules": int(visits[success_column].sum())
        >= int(breadth["min_visit_success_cells"]),
        "pooled_positive_trials": positive_fraction
        >= float(breadth["min_pooled_positive_trial_fraction"]),
        "cell_accuracy_improvement": cell_accuracy_fraction
        >= float(breadth["min_accuracy_improved_cell_fraction"]),
        "pooled_informativeness": pooled_lpb
        >= float(breadth["min_pooled_lpb_ratio_clean"]),
        "span_sensitivity": bool(
            abs(float(anchor["under75_coverage"]) - target)
            <= float(breadth["anchor_sensitivity_coverage_tolerance"])
            and abs(float(anchor["over125_coverage"]) - target)
            <= float(breadth["anchor_sensitivity_coverage_tolerance"])
        ),
        "wrong_direction_falsification": (
            anchor_coverage - float(anchor["wrong_direction_coverage"])
        )
        >= float(breadth["min_correct_minus_wrong_coverage"]),
        "nonvacuity": float(
            anchor[
                "primary_zero_bound_fraction"
                if key == "primary"
                else "interval_zero_bound_fraction"
            ]
        )
        <= float(breadth["max_zero_bound_fraction"]),
    }
    if branch == "interval_aware":
        visit_midpoint_error = float(
            np.mean(np.abs(visits["primary_coverage"] - visits["target_coverage"]))
        )
        visit_interval_error = float(
            np.mean(
                np.abs(visits["interval_aware_coverage"] - visits["target_coverage"])
            )
        )
        visit_lpb_ratio = float(
            visits["interval_aware_mean_lpb"].mean()
            / max(float(visits["primary_mean_lpb"].mean()), 1e-12)
        )
        support["interval_visit_value"] = bool(
            visit_interval_error
            <= visit_midpoint_error
            + float(breadth["max_interval_visit_accuracy_disadvantage"])
            and visit_lpb_ratio
            >= float(breadth["min_interval_visit_lpb_ratio_midpoint"])
        )
    diagnostics = {
        "success_cell_count": success_count,
        "total_primary_cell_count": len(primary_cells),
        "main_success_condition_count": main_success_count,
        "regime_breadth_count": regime_breadth_count,
        "condition_breadth_count": condition_breadth_count,
        "dataset_success_count": int(datasets[f"{key}_dataset_success"].sum()),
        "pooled_repair": float(primary_trials[repair_column].mean()),
        "pooled_repair_lower_95_seed_clustered": pooled_lower,
        "pooled_positive_trial_fraction": positive_fraction,
        "accuracy_improved_cell_fraction": cell_accuracy_fraction,
        "catastrophic_cell_fraction": float(np.mean(catastrophic)),
        "pooled_lpb_ratio_clean": pooled_lpb,
        "estimated_success_count": int(estimated[success_column].sum()),
        "visit_success_count": int(visits[success_column].sum()),
        "support_passed": int(sum(support.values())),
        "support_total": len(support),
    }
    return (
        {name: bool(value) for name, value in {**central, **expansion_core}.items()},
        {name: bool(value) for name, value in support.items()},
        diagnostics,
    )


def _decision(
    trials: list[dict[str, Any]],
    paired: pd.DataFrame,
    cells: pd.DataFrame,
    datasets: pd.DataFrame,
    config: dict[str, Any],
    completeness: dict[str, Any],
) -> dict[str, Any]:
    gate = config["gate"]
    errors = int(sum(trial.get("status") != "complete" for trial in trials))
    fallback = bool(
        (
            paired["fallback_used"].astype(bool) & paired["require_public"].astype(bool)
        ).any()
    )
    clean_unique = paired.drop_duplicates(["dataset", "regime", "seed"])
    clean_ranges = paired.groupby(["dataset", "regime", "seed"])["clean_coverage"].agg(
        lambda values: float(values.max() - values.min())
    )
    clean_range = float(clean_ranges.max()) if len(clean_ranges) else float("nan")
    clean_reproducible = bool(np.isfinite(clean_range) and clean_range <= 1e-12)
    regime_records = []
    regime_config = {str(row["name"]): row for row in config["experiment"]["regimes"]}
    for regime, frame in clean_unique.groupby("regime", sort=False):
        target = float(frame["target_coverage"].iloc[0])
        coverage = float(frame["clean_coverage"].mean())
        tolerance = float(regime_config[str(regime)]["clean_coverage_tolerance"])
        regime_records.append(
            {
                "regime": regime,
                "coverage": coverage,
                "target": target,
                "tolerance": tolerance,
                "pass": bool(abs(coverage - target) <= tolerance),
            }
        )
    clean_ok = bool(regime_records and all(row["pass"] for row in regime_records))

    anchor_rows = cells[
        (cells["condition"] == str(gate["anchor_condition"]))
        & (cells["regime"] == str(gate["anchor_regime"]))
    ]
    if len(anchor_rows) != 1:
        raise RuntimeError("Gate 3 anchor cell is missing or duplicated")
    anchor = _row_record(anchor_rows.iloc[0])
    primary_names = set(map(str, gate["primary_conditions"]))
    primary_cells = cells[cells["condition"].isin(primary_names)].copy()
    primary_trials = paired[paired["condition"].isin(primary_names)].copy()

    midpoint_core, midpoint_support, midpoint_diag = _branch_decision(
        "midpoint", anchor, primary_cells, primary_trials, datasets, config
    )
    interval_core, interval_support, interval_diag = _branch_decision(
        "interval_aware", anchor, primary_cells, primary_trials, datasets, config
    )
    midpoint_advance = bool(
        all(midpoint_core.values())
        and sum(midpoint_support.values())
        >= int(gate["midpoint"]["min_support_checks_pass"])
    )
    interval_advance = bool(
        all(interval_core.values())
        and sum(interval_support.values())
        >= int(gate["interval_aware"]["min_support_checks_pass"])
    )
    integrity_ok = bool(
        completeness["complete"]
        and errors == 0
        and not fallback
        and clean_ok
        and clean_reproducible
    )
    kind = str(config["run"]["kind"])
    if not integrity_ok:
        decision = "INCONCLUSIVE"
    elif kind == "smoke":
        decision = "SMOKE_ONLY"
    elif midpoint_advance and interval_advance:
        decision = "ADVANCE_BOTH"
    elif midpoint_advance:
        decision = "ADVANCE_MIDPOINT"
    elif interval_advance:
        decision = "ADVANCE_INTERVAL_AWARE"
    elif all(
        midpoint_core.get(name, False)
        for name in (
            "anchor_naive_drop",
            "anchor_naive_undercoverage",
            "anchor_repair",
            "anchor_coverage",
        )
    ) or all(
        interval_core.get(name, False)
        for name in (
            "anchor_naive_drop",
            "anchor_naive_undercoverage",
            "anchor_repair",
            "anchor_coverage",
        )
    ):
        decision = "HOLD"
    else:
        decision = "STOP"
    interpretation = {
        "ADVANCE_BOTH": "Both correction branches retained their anchor effect and met the frozen paper-scale expansion rules.",
        "ADVANCE_MIDPOINT": "The midpoint branch met its anchor and expansion rules; the interval-aware branch did not independently qualify.",
        "ADVANCE_INTERVAL_AWARE": "The interval-aware branch met its anchor and expansion rules; the midpoint branch did not independently qualify.",
        "HOLD": "An anchor effect remains, but paper-scale breadth or supporting evidence missed the frozen rule.",
        "STOP": "Neither correction branch retained the required anchor effect and expansion evidence.",
        "INCONCLUSIVE": "Execution, source, data, completeness, binding, fallback, or clean-reference checks prevent inference.",
        "SMOKE_ONLY": "Software, source, protocol-estimation, and recorded-interval verification only.",
    }[decision]
    return {
        "schema_version": "3.0",
        "created_utc": utc_now(),
        "decision": decision,
        "interpretation": interpretation,
        "anchor_cell": anchor,
        "midpoint_advance": midpoint_advance,
        "interval_aware_advance": interval_advance,
        "midpoint_core_checks": midpoint_core,
        "midpoint_support_checks": midpoint_support,
        "midpoint_diagnostics": midpoint_diag,
        "interval_aware_core_checks": interval_core,
        "interval_aware_support_checks": interval_support,
        "interval_aware_diagnostics": interval_diag,
        "clean_reference": {
            "regimes": regime_records,
            "all_regimes_pass": clean_ok,
            "reproducibility_max_range": clean_range,
            "reproducibility_pass": clean_reproducible,
        },
        "errors": errors,
        "required_public_fallback": fallback,
        "trial_completeness": completeness,
        "gate_thresholds": gate,
    }


def _report(decision: dict[str, Any], cells: pd.DataFrame) -> str:
    completeness = decision["trial_completeness"]
    anchor = decision["anchor_cell"]
    lines = [
        "# Gate 3 paper-scale survival correction expansion",
        "",
        f"Decision: **{decision['decision']}**",
        "",
        decision["interpretation"],
        "",
        (
            f"Trial grid: {'complete' if completeness['complete'] else 'incomplete'}; "
            f"expected {completeness['expected_trial_count']}, "
            f"observed {completeness['observed_trial_file_count']}; "
            f"errors {decision['errors']}; required-public fallback "
            f"{decision['required_public_fallback']}."
        ),
        "",
        "## Anchor cell",
        "",
        "| Target | Clean | Naive | Midpoint | Interval-aware | Midpoint repair | Interval repair |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {anchor['target_coverage']:.4f} | {anchor['clean_coverage']:.4f} | "
            f"{anchor['naive_coverage']:.4f} | {anchor['primary_coverage']:.4f} | "
            f"{anchor['interval_aware_coverage']:.4f} | "
            f"{anchor['primary_coverage_repair']:.4f} | "
            f"{anchor['interval_aware_coverage_repair']:.4f} |"
        ),
        "",
        "## Branch checks",
        "",
        "| Branch | Core | Support | Advance |",
        "|---|---:|---:|---:|",
    ]
    for label, prefix in (
        ("Midpoint", "midpoint"),
        ("Interval-aware", "interval_aware"),
    ):
        core = decision[f"{prefix}_core_checks"]
        support = decision[f"{prefix}_support_checks"]
        lines.append(
            f"| {label} | {sum(core.values())}/{len(core)} | "
            f"{sum(support.values())}/{len(support)} | "
            f"{'yes' if decision[f'{prefix}_advance'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Expansion cells",
            "",
            "| Condition | Regime | Target | Naive | Midpoint | Interval | Midpoint success | Interval success |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in cells.iterrows():
        lines.append(
            f"| {row['condition']} | {row['regime']} | "
            f"{row['target_coverage']:.3f} | {row['naive_coverage']:.3f} | "
            f"{row['primary_coverage']:.3f} | "
            f"{row['interval_aware_coverage']:.3f} | "
            f"{'pass' if row['primary_cell_success'] else 'fail'} | "
            f"{'pass' if row['interval_cell_success'] else 'fail'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _plots(
    cells: pd.DataFrame,
    metrics: pd.DataFrame,
    output: Path,
    config: dict[str, Any],
) -> None:
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    condition_order = [row["name"] for row in config["experiment"]["noise_scenarios"]]
    regime_order = [row["name"] for row in config["experiment"]["regimes"]]
    for column, label, filename in (
        ("primary_coverage", "Midpoint coverage error", "midpoint_coverage_error.png"),
        (
            "interval_aware_coverage",
            "Interval-aware coverage error",
            "interval_coverage_error.png",
        ),
    ):
        values = cells.copy()
        values["error"] = values[column] - values["target_coverage"]
        pivot = values.pivot(
            index="condition", columns="regime", values="error"
        ).reindex(index=condition_order, columns=regime_order)
        fig, ax = plt.subplots(figsize=(9, 7))
        image = ax.imshow(pivot.to_numpy(), cmap="coolwarm", vmin=-0.08, vmax=0.08)
        ax.set_xticks(range(len(regime_order)), regime_order, rotation=30, ha="right")
        ax.set_yticks(range(len(condition_order)), condition_order)
        ax.set_title(label)
        fig.colorbar(image, ax=ax, label="coverage - target")
        fig.tight_layout()
        fig.savefig(plot_dir / filename, dpi=180)
        plt.close(fig)

    anchor_condition = str(config["gate"]["anchor_condition"])
    anchor_regime = str(config["gate"]["anchor_regime"])
    methods = [
        "clean_reference_drcosarc_adaptive",
        "naive_corrupt_drcosarc_adaptive",
        "midpoint_proxy_drcosarc_adaptive",
        "interval_conditional_cal_drcosarc_adaptive",
        "stopped_interval_lower_cal_drcosarc_adaptive",
        "uncalibrated_midpoint_model",
        "uncalibrated_interval_model",
    ]
    frame = metrics[
        (metrics["condition"] == anchor_condition)
        & (metrics["regime"] == anchor_regime)
        & metrics["method"].isin(methods)
    ]
    summary = frame.groupby("method").agg(
        coverage=("coverage", "mean"), mean_lpb=("mean_lpb", "mean")
    )
    fig, ax = plt.subplots(figsize=(8, 6))
    for method in methods:
        if method not in summary.index:
            continue
        row = summary.loc[method]
        ax.scatter(row["mean_lpb"], row["coverage"], s=58)
        ax.annotate(
            method.replace("_drcosarc_adaptive", "").replace("_", " "),
            (row["mean_lpb"], row["coverage"]),
            fontsize=8,
        )
    target = 1.0 - float(
        next(
            row["alpha"]
            for row in config["experiment"]["regimes"]
            if row["name"] == anchor_regime
        )
    )
    ax.axhline(target, color="black", linestyle="--")
    ax.set_xlabel("Mean lower prediction bound")
    ax.set_ylabel("Latent event-time coverage")
    fig.tight_layout()
    fig.savefig(plot_dir / "anchor_coverage_efficiency.png", dpi=180)
    plt.close(fig)


def aggregate_results(output: Path, config: dict[str, Any]) -> dict[str, Any]:
    trials = _load_trials(output)
    completeness = _trial_completeness(trials, config, output)
    expected_hash = scientific_config_hash(config)
    stale = [
        trial.get("trial_id")
        for trial in trials
        if trial.get("scientific_config_hash") != expected_hash
    ]
    if stale:
        raise RuntimeError(f"refusing to aggregate {len(stale)} stale trial(s)")
    paired, metrics, resources = _flatten(trials)
    if paired.empty:
        raise RuntimeError("no completed Gate 3 trials found")
    paired.to_csv(output / "paired_expansion_trials.csv", index=False)
    metrics.to_csv(output / "long_metrics.csv", index=False)
    resources.to_csv(output / "resources.csv", index=False)
    cells = _cell_summary(paired, config)
    cells.to_csv(output / "cell_summary.csv", index=False)
    datasets = _dataset_summary(paired, config)
    datasets.to_csv(output / "dataset_summary.csv", index=False)
    decision = _decision(trials, paired, cells, datasets, config, completeness)
    atomic_write_json(output / "gate_decision.json", decision)
    atomic_write_text(output / "gate_report.md", _report(decision, cells))
    _plots(cells, metrics, output, config)
    return decision
