from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from survival_noise_bakeoff.aggregate import (
    _cell_summary,
    _dataset_summary,
    _decision,
)


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (2377, 2503, 2621, 2749, 2879, 3001)


def config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "full.yaml").read_text(encoding="utf-8"))


def make_paired() -> pd.DataFrame:
    cfg = config()
    rows = []
    for condition in cfg["experiment"]["noise_scenarios"]:
        for regime in cfg["experiment"]["regimes"]:
            target = 1.0 - regime["alpha"]
            clean = target + 0.005
            anchor = condition["name"] == cfg["gate"]["anchor_condition"]
            naive = clean - (0.050 if anchor else 0.035)
            primary_repair = 0.050 if anchor else 0.030
            interval_repair = 0.045 if anchor else 0.028
            for dataset in cfg["experiment"]["datasets"]:
                for seed in SEEDS:
                    primary = naive + primary_repair
                    interval = naive + interval_repair
                    stopped = target + 0.060
                    rows.append(
                        {
                            "trial_id": (
                                f"{condition['name']}-{regime['name']}-"
                                f"{dataset['name']}-{seed}"
                            ),
                            "status": "complete",
                            "dataset": dataset["name"],
                            "mechanism": dataset["mechanism"],
                            "outcome_distribution": dataset["outcome_distribution"],
                            "regime": regime["name"],
                            "alpha": regime["alpha"],
                            "target_coverage": target,
                            "n": regime["n"],
                            "target_censoring": regime["target_censoring"],
                            "censoring_mechanism": regime["censoring_mechanism"],
                            "condition": condition["name"],
                            "condition_family": condition["family"],
                            "gate_role": condition["gate_role"],
                            "severity": condition["severity"],
                            "protocol_source": (
                                "estimated_from_protocol_split"
                                if condition.get("protocol_source") == "estimated"
                                else (
                                    "subject_level_visit_brackets"
                                    if condition["correction_interval_mode"]
                                    == "recorded_interval"
                                    else "declared_recording_protocol"
                                )
                            ),
                            "seed": seed,
                            "fallback_used": False,
                            "require_public": bool(
                                dataset.get("require_public", False)
                            ),
                            "realized_time_errors": 400,
                            "clean_coverage": clean,
                            "naive_coverage": naive,
                            "primary_coverage": primary,
                            "interval_aware_coverage": interval,
                            "interval_midpoint_coverage": interval - 0.001,
                            "stopped_coverage": stopped,
                            "lower_edge_coverage": target + 0.090,
                            "under75_coverage": target - 0.010,
                            "over125_coverage": target + 0.020,
                            "wrong_direction_coverage": naive - 0.040,
                            "clean_worst_x0_quartile_coverage": target - 0.015,
                            "naive_worst_x0_quartile_coverage": naive - 0.025,
                            "primary_worst_x0_quartile_coverage": target - 0.015,
                            "interval_worst_x0_quartile_coverage": target - 0.018,
                            "matched_naive_coverage_drop": clean - naive,
                            "primary_coverage_repair": primary_repair,
                            "interval_aware_coverage_repair": interval_repair,
                            "interval_midpoint_coverage_repair": (
                                interval_repair - 0.001
                            ),
                            "stopped_coverage_repair": stopped - naive,
                            "lower_edge_coverage_repair": (target + 0.090 - naive),
                            "under75_coverage_repair": (target - 0.010 - naive),
                            "over125_coverage_repair": (target + 0.020 - naive),
                            "wrong_direction_coverage_repair": -0.040,
                            "loss_recovery_fraction": (
                                primary_repair / (clean - naive)
                            ),
                            "clean_mean_lpb": 10.0,
                            "naive_mean_lpb": 11.0,
                            "primary_mean_lpb": 9.8,
                            "interval_aware_mean_lpb": 9.7,
                            "interval_midpoint_mean_lpb": 9.6,
                            "stopped_mean_lpb": 7.7,
                            "lower_edge_mean_lpb": 4.0,
                            "primary_lpb_ratio_clean": 0.98,
                            "primary_lpb_ratio_lower_edge": 2.45,
                            "primary_zero_bound_fraction": 0.0,
                            "interval_aware_lpb_ratio_clean": 0.97,
                            "interval_aware_zero_bound_fraction": 0.0,
                        }
                    )
    return pd.DataFrame(rows)


def completeness(n: int) -> dict:
    return {
        "complete": True,
        "expected_trial_count": n,
        "observed_trial_file_count": n,
        "observed_unique_trial_count": n,
        "missing_trial_count": 0,
        "unexpected_trial_count": 0,
        "duplicate_trial_id_count": 0,
        "filename_mismatch_count": 0,
        "raw_integrity_failure_count": 0,
        "input_manifest_failure_count": 0,
        "input_binding_failure_count": 0,
    }


def decide(paired: pd.DataFrame) -> dict:
    cfg = config()
    cells = _cell_summary(paired, cfg)
    datasets = _dataset_summary(paired, cfg)
    trials = [{"status": "complete"} for _ in range(len(paired))]
    return _decision(
        trials,
        paired,
        cells,
        datasets,
        cfg,
        completeness(len(paired)),
    )


def test_both_independent_branches_advance() -> None:
    decision = decide(make_paired())
    assert decision["decision"] == "ADVANCE_BOTH"
    assert decision["midpoint_advance"]
    assert decision["interval_aware_advance"]
    assert decision["midpoint_diagnostics"]["success_cell_count"] == 35


def test_interval_branch_can_advance_without_midpoint_substitution() -> None:
    paired = make_paired()
    mask = (paired["condition"] == "ceiling_grid20_known") & (
        paired["regime"] == "main"
    )
    paired.loc[mask, "primary_coverage_repair"] = 0.015
    paired.loc[mask, "primary_coverage"] = paired.loc[mask, "naive_coverage"] + 0.015
    paired.loc[mask, "loss_recovery_fraction"] = 0.30
    decision = decide(paired)
    assert decision["decision"] == "ADVANCE_INTERVAL_AWARE"
    assert not decision["midpoint_advance"]
    assert decision["interval_aware_advance"]


def test_anchor_failure_stops_both_branches() -> None:
    paired = make_paired()
    mask = (paired["condition"] == "ceiling_grid20_known") & (
        paired["regime"] == "main"
    )
    for prefix in ("primary", "interval_aware"):
        paired.loc[mask, f"{prefix}_coverage_repair"] = 0.005
        paired.loc[mask, f"{prefix}_coverage"] = (
            paired.loc[mask, "naive_coverage"] + 0.005
        )
    paired.loc[mask, "loss_recovery_fraction"] = 0.10
    decision = decide(paired)
    assert decision["decision"] == "STOP"
    assert not decision["midpoint_advance"]
    assert not decision["interval_aware_advance"]


def test_anchor_without_expansion_breadth_holds() -> None:
    paired = make_paired()
    failing = {
        "ceiling_grid20_shifted",
        "ceiling_grid20_estimated",
        "visits_irregular20",
        "visits_informative20",
    }
    mask = paired["condition"].isin(failing)
    for prefix in ("primary", "interval_aware"):
        paired.loc[mask, f"{prefix}_coverage_repair"] = 0.002
        paired.loc[mask, f"{prefix}_coverage"] = (
            paired.loc[mask, "naive_coverage"] + 0.002
        )
    decision = decide(paired)
    assert decision["decision"] == "HOLD"
    assert not decision["midpoint_advance"]
    assert not decision["interval_aware_advance"]
