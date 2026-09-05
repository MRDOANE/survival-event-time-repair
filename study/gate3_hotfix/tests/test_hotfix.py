from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import yaml

from survival_noise_bakeoff.aggregate import _hotfix_integrity
from survival_noise_bakeoff.data import load_dataset, make_splits
from survival_noise_bakeoff.hotfix import validate_hotfix_resume_state
from survival_noise_bakeoff.util import (
    GATE3_BASE_SCIENTIFIC_CONFIG_HASH,
    GATE3_HOTFIX_DATASET,
    GATE3_HOTFIX_ERROR_FRAGMENT,
    GATE3_HOTFIX_ID,
    implementation_hash,
    scientific_config_hash,
)


ROOT = Path(__file__).resolve().parents[1]


def full_config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "full.yaml").read_text())


def test_gbsg2_reference_encoding_is_full_rank() -> None:
    config = full_config()
    dataset = {
        **config["experiment"]["datasets"][-1],
        **config["experiment"]["regimes"][0],
    }
    seed = int(config["experiment"]["seeds"][0])
    data = load_dataset(dataset, seed, config["experiment"]["split"])
    splits = make_splits(len(data.X), config["experiment"]["split"], seed)
    design = np.column_stack([np.ones(len(splits.train)), data.X[splits.train]])
    assert not data.provenance["fallback_used"]
    assert data.X.shape[1] == 9
    assert np.linalg.matrix_rank(design) == design.shape[1]


def test_hotfix_keeps_frozen_scientific_hash_and_detects_science_change() -> None:
    config = full_config()
    assert scientific_config_hash(config) == GATE3_BASE_SCIENTIFIC_CONFIG_HASH
    changed = copy.deepcopy(config)
    changed["experiment"]["regimes"][0]["target_censoring"] = 0.36
    assert scientific_config_hash(changed) != GATE3_BASE_SCIENTIFIC_CONFIG_HASH


def _write_original_resume_state(output: Path) -> None:
    output.mkdir(parents=True)
    (output / "trials").mkdir()
    (output / "run_manifest.json").write_text(
        json.dumps({"scientific_config_hash": GATE3_BASE_SCIENTIFIC_CONFIG_HASH})
    )
    (output / "gate_decision.json").write_text(
        json.dumps({"decision": "INCONCLUSIVE", "errors": 240})
    )
    (output / "config_resolved.yaml").write_text("run:\n  kind: full\n")
    for index in range(1200):
        affected = index >= 960
        record = {
            "trial_id": f"trial-{index:04d}",
            "scientific_config_hash": GATE3_BASE_SCIENTIFIC_CONFIG_HASH,
            "dataset": {"name": GATE3_HOTFIX_DATASET if affected else "preserved"},
            "status": "error" if affected else "complete",
        }
        if affected:
            record["error"] = GATE3_HOTFIX_ERROR_FRAGMENT
        (output / "trials" / f"trial-{index:04d}.json").write_text(json.dumps(record))


def test_resume_audit_accepts_only_the_audited_gbsg2_block(tmp_path: Path) -> None:
    output = tmp_path / "full"
    _write_original_resume_state(output)
    config = full_config()
    audit = validate_hotfix_resume_state(output, config)
    assert audit is not None
    assert audit["preserved_nonaffected_complete"] == 960
    assert audit["current_affected_errors"] == 240
    assert (output / "hotfix_audit" / "baseline.json").is_file()

    trial = output / "trials" / "trial-0960.json"
    record = json.loads(trial.read_text())
    record.update(
        {
            "status": "complete",
            "compatibility_hotfix_id": GATE3_HOTFIX_ID,
            "execution_implementation_sha256": implementation_hash(),
        }
    )
    trial.write_text(json.dumps(record))
    resumed = validate_hotfix_resume_state(output, config)
    assert resumed is not None
    assert resumed["current_affected_complete"] == 1
    assert resumed["current_affected_errors"] == 239


def test_final_hotfix_integrity_requires_exact_execution_scope(tmp_path: Path) -> None:
    config = full_config()
    baseline = tmp_path / "hotfix_audit" / "baseline.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        json.dumps(
            {
                "hotfix_id": GATE3_HOTFIX_ID,
                "base_scientific_config_hash": GATE3_BASE_SCIENTIFIC_CONFIG_HASH,
                "prior_completed_trials": 960,
                "prior_error_trials": 240,
            }
        )
    )
    preserved = [
        {"status": "complete", "dataset": {"name": "preserved"}} for _ in range(960)
    ]
    repaired = [
        {
            "status": "complete",
            "dataset": {"name": GATE3_HOTFIX_DATASET},
            "compatibility_hotfix_id": GATE3_HOTFIX_ID,
            "execution_implementation_sha256": implementation_hash(),
        }
        for _ in range(240)
    ]
    result = _hotfix_integrity(preserved + repaired, config, tmp_path)
    assert result["pass"]
    repaired[0]["execution_implementation_sha256"] = "wrong"
    assert not _hotfix_integrity(preserved + repaired, config, tmp_path)["pass"]
