from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from survival_noise_bakeoff.data import load_dataset, make_splits
from survival_noise_bakeoff.noise import corrupt_labels
from survival_noise_bakeoff.official import (
    REQUIRED_METHODS,
    UPSTREAM_COMMIT,
    prepare_official_bundle,
    validate_official_result,
)


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundle_contains_hash_bound_interval_and_proxy_views(tmp_path: Path) -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "full.yaml").read_text(encoding="utf-8")
    )
    dataset = {
        "name": "synthetic_bundle_lognormal",
        "n": 800,
        "p": 8,
        "mechanism": "linear",
        "outcome_distribution": "lognormal",
        "target_censoring": 0.35,
        "censoring_mechanism": "independent_lognormal",
    }
    noise = config["experiment"]["noise_scenarios"][5]
    regime = config["experiment"]["regimes"][0]
    data = load_dataset(dataset, 503, config["experiment"]["split"])
    splits = make_splits(800, config["experiment"]["split"], 503)
    corrupted = corrupt_labels(data, splits, noise, 503)
    upstream = {"commit": UPSTREAM_COMMIT, "source_sha256": {}}
    manifest = prepare_official_bundle(
        tmp_path / "bundle",
        data,
        splits,
        corrupted,
        noise,
        regime,
        config,
        503,
        upstream,
    )
    assert manifest["schema_version"] == "3.0"
    assert manifest["correction_protocol"]["source"] == ("subject_level_visit_brackets")
    assert manifest["alpha"] == regime["alpha"]
    assert len(manifest["input_fingerprint"]) == 32
    bundle = tmp_path / "bundle"

    def check_records(value: object) -> None:
        if isinstance(value, dict) and {"file", "rows", "sha256"} <= set(value):
            path = bundle / str(value["file"])
            assert path.is_file()
            assert sha256(path) == value["sha256"]
            assert len(value["numeric_sha256"]) == 64
        elif isinstance(value, dict):
            for nested in value.values():
                check_records(nested)

    check_records(manifest["files"])
    interval_record = manifest["files"]["interval_primary"]["interval_train"]
    interval = pd.read_csv(bundle / interval_record["file"])
    assert interval.loc[interval["status"] == 0, "time_upper"].isna().all()
    assert interval.loc[interval["status"] == 1, "time_upper"].notna().all()
    assert (
        interval.loc[interval["status"] == 1, "time_lower"]
        <= interval.loc[interval["status"] == 1, "time_upper"]
    ).all()
    interval_cal_record = manifest["files"]["interval_primary"]["interval_cal"]
    assert (bundle / interval_cal_record["file"]).is_file()


def test_official_result_requires_exact_methods_and_view_binding() -> None:
    n = 12
    manifest = {"input_fingerprint": "abc123"}
    result = {
        "status": "complete",
        "algorithm": "adaptive",
        "official_source_commit": UPSTREAM_COMMIT,
        "input_fingerprint": "abc123",
        "bounds": {name: np.zeros(n).tolist() for name in REQUIRED_METHODS},
    }
    validate_official_result(result, n, manifest)
    missing = copy.deepcopy(result)
    missing["bounds"].pop("interval_conditional_cal_drcosarc_adaptive")
    with pytest.raises(ValueError, match="method mismatch"):
        validate_official_result(missing, n, manifest)
    unbound = copy.deepcopy(result)
    unbound["input_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="not bound"):
        validate_official_result(unbound, n, manifest)
    malformed = copy.deepcopy(result)
    malformed["bounds"]["trivial_zero_bound"] = [0.0]
    with pytest.raises(ValueError, match="returned shape"):
        validate_official_result(malformed, n, manifest)


def test_manifest_file_is_canonical_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"b": 2, "a": 1}), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
