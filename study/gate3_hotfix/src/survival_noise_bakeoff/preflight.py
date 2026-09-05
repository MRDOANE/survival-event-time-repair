from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .correction import build_interval_view, recording_protocol
from .data import load_dataset, make_splits
from .noise import corrupt_labels
from .util import (
    atomic_write_json,
    compatibility_hotfix,
    utc_now,
    validate_compatibility_hotfix,
    validate_probability,
)


def _validate_config(config: dict[str, Any]) -> None:
    validate_compatibility_hotfix(config)
    exp = config["experiment"]
    kind = str(config["run"]["kind"])
    if kind not in {"smoke", "full"}:
        raise ValueError("run.kind must be smoke or full")
    if int(config["run"].get("bootstrap_reps", 0)) < 1:
        raise ValueError("run.bootstrap_reps must be positive")
    fractions = list(exp["split"])
    if (
        len(fractions) != 4
        or min(fractions) <= 0
        or not np.isclose(sum(fractions), 1.0)
    ):
        raise ValueError(
            "experiment.split must contain four positive fractions summing to one"
        )
    if set(exp["official_models"].values()) != {"survreg_lognormal"}:
        raise ValueError("Gate 3 locks both official models to survreg_lognormal")

    seeds = [int(seed) for seed in exp["seeds"]]
    prohibited = {int(seed) for seed in exp.get("prohibited_prior_seeds", [])}
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("experiment.seeds must be nonempty and unique")
    if set(seeds) & prohibited:
        raise ValueError("Gate 3 seeds overlap a prior gate")

    datasets = exp["datasets"]
    dataset_names = [str(dataset["name"]) for dataset in datasets]
    if not datasets or len(dataset_names) != len(set(dataset_names)):
        raise ValueError("datasets must be nonempty with unique names")
    for dataset in datasets:
        if dataset.get("outcome_distribution") not in {
            "lognormal",
            "weibull_ph",
            "loglogistic",
            "mixture_lognormal",
        }:
            raise ValueError(f"unknown outcome distribution in {dataset['name']}")

    regimes = exp["regimes"]
    regime_names = [str(regime["name"]) for regime in regimes]
    if not regimes or len(regime_names) != len(set(regime_names)):
        raise ValueError("regimes must be nonempty with unique names")
    for regime in regimes:
        alpha = float(regime["alpha"])
        validate_probability(f"{regime['name']}.alpha", alpha)
        if not 0 < alpha < 0.5:
            raise ValueError("each alpha must lie in (0, 0.5)")
        validate_probability(
            f"{regime['name']}.target_censoring",
            float(regime["target_censoring"]),
        )
        if int(regime["n"]) < (1000 if kind == "full" else 160):
            raise ValueError(f"regime sample size is too small: {regime['name']}")
        if regime["censoring_mechanism"] not in {
            "independent_lognormal",
            "covariate_dependent_nonlinear",
        }:
            raise ValueError(f"unknown censoring mechanism: {regime['name']}")

    scenarios = exp["noise_scenarios"]
    scenario_names = [str(scenario["name"]) for scenario in scenarios]
    if not scenarios or len(scenario_names) != len(set(scenario_names)):
        raise ValueError("noise scenarios must be nonempty with unique names")
    allowed_pairs = {
        ("heap_ceiling", "ceiling_grid"),
        ("delay_fraction", "multiplicative_delay"),
        ("scheduled_regular", "recorded_interval"),
        ("scheduled_irregular", "recorded_interval"),
        ("scheduled_informative", "recorded_interval"),
    }
    for scenario in scenarios:
        if scenario.get("scope") != "train_cal":
            raise ValueError(f"Gate 3 requires train_cal scope: {scenario['name']}")
        if scenario.get("gate_role") not in {
            "anchor",
            "primary_stress",
            "secondary_transport",
        }:
            raise ValueError(f"unknown gate role in {scenario['name']}")
        validate_probability(
            f"{scenario['name']}.time_error_probability",
            float(scenario["time_error_probability"]),
        )
        fraction = float(scenario["time_error_fraction"])
        if not 0 < fraction <= 0.25:
            raise ValueError(
                f"timing-error scale must lie in (0, .25]: {scenario['name']}"
            )
        pair = (
            str(scenario["time_error_mode"]),
            str(scenario["correction_interval_mode"]),
        )
        if pair not in allowed_pairs:
            raise ValueError(
                f"incompatible error/correction pair in {scenario['name']}"
            )
        if (
            float(scenario.get("flip_event_to_censor", 0.0)) != 0
            or float(scenario.get("flip_censor_to_event", 0.0)) != 0
        ):
            raise ValueError("Gate 3 isolates event-time errors from status errors")

    gate = config["gate"]
    anchor = str(gate["anchor_condition"])
    anchor_regime = str(gate["anchor_regime"])
    if anchor not in scenario_names or anchor_regime not in regime_names:
        raise ValueError("anchor condition or regime is missing")
    if scenarios[scenario_names.index(anchor)].get("gate_role") != "anchor":
        raise ValueError("anchor condition must have gate_role anchor")
    primary_names = {str(value) for value in gate["primary_conditions"]}
    if kind == "full" and not primary_names.issubset(scenario_names):
        raise ValueError("full configuration omits a primary condition")
    expected = len(datasets) * len(regimes) * len(scenarios) * len(seeds)
    if kind == "full" and expected != 1200:
        raise ValueError(
            f"frozen Gate 3 grid must contain exactly 1200 trials, got {expected}"
        )

    correction = config["correction"]
    if correction["primary_method"] != "midpoint_proxy_drcosarc_adaptive":
        raise ValueError("the Gate 3 midpoint primary changed")
    if (
        correction["interval_aware_method"]
        != "interval_conditional_cal_drcosarc_adaptive"
    ):
        raise ValueError("the Gate 3 interval-aware branch changed")
    if (
        correction["stopped_gate26_method"]
        != "stopped_interval_lower_cal_drcosarc_adaptive"
    ):
        raise ValueError("the frozen Gate 2.6 comparator changed")
    if correction["interval_imputation"] != "fitted_lognormal_conditional_median":
        raise ValueError("the interval imputation rule changed")
    sensitivity = correction["span_sensitivity_multipliers"]
    if not np.isclose(float(sensitivity["under"]), 0.75) or not np.isclose(
        float(sensitivity["over"]), 1.25
    ):
        raise ValueError("span sensitivity must remain fixed at 0.75 and 1.25")


def _view_for(
    data,
    splits,
    scenario: dict[str, Any],
    seed: int,
):
    corrupted = corrupt_labels(data, splits, scenario, seed)
    protocol = recording_protocol(scenario, corrupted, splits)
    checked = np.concatenate([splits.train, splits.calibration])
    view = build_interval_view(
        corrupted.observed_time[checked],
        corrupted.observed_event[checked],
        protocol,
        recorded_lower=corrupted.recorded_lower[checked],
        recorded_upper=corrupted.recorded_upper[checked],
    )
    return corrupted, protocol, checked, view


def run_preflight(
    config: dict[str, Any],
    output: Path,
    package_root: Path,
    upstream_root: Path,
    upstream_manifest: dict[str, Any],
) -> dict[str, Any]:
    _validate_config(config)
    fractions = list(config["experiment"]["split"])
    hotfix = compatibility_hotfix(config)
    gbsg2_full_rank = True
    gbsg2_rank_record: dict[str, Any] | None = None
    if hotfix is not None:
        experiment = config["experiment"]
        dataset = next(
            row
            for row in experiment["datasets"]
            if row["name"] == hotfix["affected_dataset"]
        )
        regime = next(row for row in experiment["regimes"] if row["name"] == "main")
        effective = {
            **dataset,
            "n": int(regime["n"]),
            "target_censoring": float(regime["target_censoring"]),
            "censoring_mechanism": str(regime["censoring_mechanism"]),
        }
        gbsg2 = load_dataset(
            effective,
            int(experiment["seeds"][0]),
            fractions,
        )
        gbsg2_splits = make_splits(len(gbsg2.X), fractions, int(experiment["seeds"][0]))
        design = np.column_stack(
            [np.ones(len(gbsg2_splits.train)), gbsg2.X[gbsg2_splits.train]]
        )
        rank = int(np.linalg.matrix_rank(design))
        columns = int(design.shape[1])
        gbsg2_full_rank = bool(
            not gbsg2.provenance.get("fallback_used", True) and rank == columns
        )
        gbsg2_rank_record = {
            "rows": int(design.shape[0]),
            "columns_with_intercept": columns,
            "rank": rank,
            "fallback_used": bool(gbsg2.provenance.get("fallback_used", True)),
            "pass": gbsg2_full_rank,
        }
    tiny = {
        "name": "synthetic_preflight",
        "n": 600,
        "p": 6,
        "mechanism": "linear",
        "outcome_distribution": "lognormal",
        "target_censoring": 0.35,
        "censoring_mechanism": "independent_lognormal",
    }
    data = load_dataset(tiny, 999, fractions)
    splits = make_splits(len(data.X), fractions, 999)
    known_spec = {
        "name": "preflight_ceiling",
        "scope": "train_cal",
        "time_error_mode": "heap_ceiling",
        "time_error_fraction": 0.20,
        "time_error_probability": 1.0,
        "correction_interval_mode": "ceiling_grid",
        "grid_origin_fraction": 0.37,
        "protocol_source": "known",
    }
    known, known_protocol, checked, known_view = _view_for(
        data, splits, known_spec, 999
    )
    actual = known.time_errored[checked]
    interval_detection_exact = bool(np.array_equal(known_view.detected, actual))
    known_containment = bool(
        actual.any()
        and np.all(known_view.lower[actual] <= data.true_time[checked][actual])
        and np.all(data.true_time[checked][actual] <= known_view.upper[actual])
    )

    estimated_spec = {
        **known_spec,
        "name": "preflight_estimated",
        "protocol_source": "estimated",
    }
    estimated, estimated_protocol, estimated_checked, estimated_view = _view_for(
        data, splits, estimated_spec, 999
    )
    estimated_actual = estimated.time_errored[estimated_checked]
    estimated_detection = bool(
        np.array_equal(estimated_view.detected, estimated_actual)
    )
    true_width = float(estimated.metadata["time_error_width"])
    true_origin = float(estimated.metadata["grid_origin"])
    estimated_width_error = abs(
        float(estimated_protocol["interval_width"]) / true_width - 1.0
    )
    origin_delta = abs(float(estimated_protocol["grid_origin"]) - true_origin)
    origin_error = min(origin_delta, abs(origin_delta - true_width)) / true_width
    estimated_protocol_exact = bool(
        estimated_width_error <= 1e-6 and origin_error <= 1e-6
    )

    visit_spec = {
        "name": "preflight_irregular_visits",
        "scope": "train_cal",
        "time_error_mode": "scheduled_irregular",
        "time_error_fraction": 0.20,
        "time_error_probability": 1.0,
        "visit_gap_cv": 0.45,
        "correction_interval_mode": "recorded_interval",
    }
    visits, _, visit_checked, visit_view = _view_for(data, splits, visit_spec, 999)
    visit_actual = visits.time_errored[visit_checked]
    visit_containment = bool(
        visit_actual.any()
        and np.all(
            visit_view.lower[visit_actual]
            <= data.true_time[visit_checked][visit_actual]
        )
        and np.all(
            data.true_time[visit_checked][visit_actual]
            <= visit_view.upper[visit_actual]
        )
    )

    split_sets = [
        set(splits.train),
        set(splits.noise_estimation),
        set(splits.calibration),
        set(splits.test),
    ]
    disjoint = all(
        not (split_sets[i] & split_sets[j]) for i in range(4) for j in range(i + 1, 4)
    )
    test_untouched = bool(
        np.array_equal(visits.observed_time[splits.test], data.clean_time[splits.test])
        and np.array_equal(
            visits.observed_event[splits.test], data.clean_event[splits.test]
        )
    )

    if shutil.which("Rscript") is None:
        raise RuntimeError("Rscript is unavailable; run scripts/bootstrap_official.sh")
    r_output = output / "preflight_official_r.json"
    completed = subprocess.run(
        [
            "Rscript",
            "--vanilla",
            str(package_root / "r" / "preflight_official.R"),
            str(upstream_root),
            str(r_output),
        ],
        cwd=package_root,
        text=True,
        capture_output=True,
        timeout=int(config["run"].get("preflight_timeout_seconds", 900)),
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(
            f"official/interval R preflight failed with exit {completed.returncode}:\n{tail}"
        )
    with r_output.open("r", encoding="utf-8") as handle:
        r_record = json.load(handle)
    if r_record.get("status") != "pass":
        raise RuntimeError(f"official/interval R preflight failed: {r_record}")

    scalar_pass = bool(
        interval_detection_exact
        and known_containment
        and estimated_detection
        and estimated_protocol_exact
        and visit_containment
        and disjoint
        and test_untouched
        and np.all(np.isfinite(data.true_time))
        and gbsg2_full_rank
    )
    record = {
        "created_utc": utc_now(),
        "status": "pass" if scalar_pass else "fail",
        "checks": {
            "config_valid": True,
            "fresh_seed_lock": True,
            "known_grid_detection_exact": interval_detection_exact,
            "known_grid_contains_latent_for_preflight_only": known_containment,
            "estimated_grid_detection_exact": estimated_detection,
            "estimated_grid_protocol_exact": estimated_protocol_exact,
            "estimated_grid_width_relative_error": estimated_width_error,
            "estimated_grid_origin_relative_error": origin_error,
            "recorded_visit_interval_contains_latent_for_preflight_only": visit_containment,
            "splits_disjoint": disjoint,
            "test_never_corrupted": test_untouched,
            "latent_times_finite": bool(np.all(np.isfinite(data.true_time))),
            "official_source_pinned": upstream_manifest,
            "official_and_interval_r_end_to_end": r_record,
            "gbsg2_reference_coding_full_rank": gbsg2_rank_record,
        },
    }
    atomic_write_json(output / "preflight.json", record)
    if record["status"] != "pass":
        raise RuntimeError(f"preflight failed: {record}")
    return record
