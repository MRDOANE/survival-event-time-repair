from __future__ import annotations

import copy
from pathlib import Path

import yaml

from survival_noise_bakeoff.experiment import build_trial_specs
from survival_noise_bakeoff.preflight import _validate_config
from survival_noise_bakeoff.util import scientific_config_hash


ROOT = Path(__file__).resolve().parents[1]


def load_config(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


def test_full_grid_is_exact_and_held_out() -> None:
    config = load_config("full.yaml")
    _validate_config(config)
    specs = build_trial_specs(config)
    assert len(specs) == 1200
    assert len({spec.trial_id for spec in specs}) == 1200
    seeds = set(config["experiment"]["seeds"])
    prior = set(config["experiment"]["prohibited_prior_seeds"])
    assert seeds.isdisjoint(prior)
    assert len(config["experiment"]["datasets"]) == 5
    assert len(config["experiment"]["regimes"]) == 5
    assert len(config["experiment"]["noise_scenarios"]) == 8
    assert config["gate"]["anchor_condition"] == "ceiling_grid20_known"
    assert config["correction"]["primary_method"] == (
        "midpoint_proxy_drcosarc_adaptive"
    )


def test_smoke_configuration_is_valid() -> None:
    config = load_config("smoke.yaml")
    _validate_config(config)
    assert len(build_trial_specs(config)) == 3


def test_scientific_hash_ignores_workers_but_binds_method_regime_and_gate() -> None:
    config = load_config("full.yaml")
    baseline = scientific_config_hash(config)
    workers = copy.deepcopy(config)
    workers["run"]["n_jobs"] = 4
    assert scientific_config_hash(workers) == baseline
    method = copy.deepcopy(config)
    method["correction"]["interval_imputation"] = "interval_midpoint"
    assert scientific_config_hash(method) != baseline
    regime = copy.deepcopy(config)
    regime["experiment"]["regimes"][1]["target_censoring"] = 0.50
    assert scientific_config_hash(regime) != baseline
    threshold = copy.deepcopy(config)
    threshold["gate"]["midpoint"]["anchor"]["min_repair"] = 0.024
    assert scientific_config_hash(threshold) != baseline
