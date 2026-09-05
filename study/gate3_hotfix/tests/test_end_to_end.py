from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from survival_noise_bakeoff.aggregate import aggregate_results
from survival_noise_bakeoff.experiment import build_trial_specs, execute_trial
from survival_noise_bakeoff.official import REQUIRED_METHODS, UPSTREAM_COMMIT


ROOT = Path(__file__).resolve().parents[1]


def test_mocked_smoke_grid_exercises_all_protocol_paths(
    tmp_path: Path, monkeypatch
) -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "smoke.yaml").read_text(encoding="utf-8")
    )
    output = tmp_path / "outputs" / "smoke"
    output.mkdir(parents=True)
    upstream = {"commit": UPSTREAM_COMMIT, "source_sha256": {}}

    def fake_driver(
        bundle_dir: Path,
        output_json: Path,
        package_root: Path,
        upstream_root: Path,
        timeout_seconds: int,
    ) -> dict:
        manifest = json.loads(
            (bundle_dir / "manifest.json").read_text(encoding="utf-8")
        )
        n = int(manifest["test_n"])
        result = {
            "schema_version": "3.0",
            "status": "complete",
            "official_source_commit": UPSTREAM_COMMIT,
            "input_fingerprint": manifest["input_fingerprint"],
            "algorithm": "adaptive",
            "survival_model": "survreg_lognormal",
            "censoring_model": "survreg_lognormal",
            "bounds": {name: np.zeros(n).tolist() for name in REQUIRED_METHODS},
            "diagnostics": {},
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result), encoding="utf-8")
        return result

    monkeypatch.setattr(
        "survival_noise_bakeoff.experiment.run_official_driver", fake_driver
    )
    for spec in build_trial_specs(config):
        trial = execute_trial(
            spec,
            config,
            output,
            False,
            ROOT,
            tmp_path / "upstream",
            upstream,
        )
        assert trial["status"] == "complete"
        assert len(trial["metrics"]) == len(REQUIRED_METHODS)
    gate = aggregate_results(output, config)
    assert gate["decision"] == "SMOKE_ONLY"
    assert gate["trial_completeness"]["complete"]
    assert len(list((output / "input_manifests").glob("*.json"))) == 3
