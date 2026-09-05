from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .util import (
    GATE3_BASE_SCIENTIFIC_CONFIG_HASH,
    GATE3_HOTFIX_DATASET,
    GATE3_HOTFIX_ERROR_FRAGMENT,
    GATE3_HOTFIX_ID,
    atomic_write_json,
    compatibility_hotfix,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required hotfix resume file is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"hotfix resume file is not a JSON object: {path}")
    return value


def _load_trials(output: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((output / "trials").glob("*.json")):
        record = _read_json(path)
        record["_source_path"] = str(path)
        records.append(record)
    return records


def _validate_original_state(
    output: Path,
    config: dict[str, Any],
    trials: list[dict[str, Any]],
) -> dict[str, Any]:
    hotfix = compatibility_hotfix(config)
    if hotfix is None:
        raise RuntimeError("original-state validation requires hotfix metadata")
    manifest_path = output / "run_manifest.json"
    decision_path = output / "gate_decision.json"
    config_path = output / "config_resolved.yaml"
    manifest = _read_json(manifest_path)
    decision = _read_json(decision_path)
    complete = [row for row in trials if row.get("status") == "complete"]
    errors = [row for row in trials if row.get("status") == "error"]
    if manifest.get("scientific_config_hash") != GATE3_BASE_SCIENTIFIC_CONFIG_HASH:
        raise RuntimeError("the prior run does not have the frozen Gate 3 hash")
    if len(trials) != 1200 or len(complete) != 960 or len(errors) != 240:
        raise RuntimeError(
            "the first hotfix resume requires the audited 960-complete/240-error state"
        )
    if decision.get("decision") != "INCONCLUSIVE" or decision.get("errors") != 240:
        raise RuntimeError(
            "the prior Gate 3 decision is not the audited inconclusive result"
        )
    if any(
        row.get("dataset", {}).get("name") == GATE3_HOTFIX_DATASET for row in complete
    ):
        raise RuntimeError("the prior run unexpectedly contains completed GBSG2 trials")
    if any(
        row.get("dataset", {}).get("name") != GATE3_HOTFIX_DATASET
        or GATE3_HOTFIX_ERROR_FRAGMENT not in str(row.get("error", ""))
        or row.get("metrics")
        for row in errors
    ):
        raise RuntimeError(
            "the prior errors do not match the audited GBSG2-only failure"
        )

    audit = output / "hotfix_audit"
    audit.mkdir(parents=True, exist_ok=True)
    copies = {
        "prior_run_manifest": manifest_path,
        "prior_gate_decision": decision_path,
        "prior_config_resolved": config_path,
    }
    copy_hashes: dict[str, str] = {}
    for label, source in copies.items():
        target = audit / f"{label}{source.suffix}"
        shutil.copy2(source, target)
        copy_hashes[target.name] = _sha256(target)
    record = {
        "hotfix_id": GATE3_HOTFIX_ID,
        "base_scientific_config_hash": GATE3_BASE_SCIENTIFIC_CONFIG_HASH,
        "affected_dataset": GATE3_HOTFIX_DATASET,
        "prior_completed_trials": len(complete),
        "prior_error_trials": len(errors),
        "prior_error_signature": GATE3_HOTFIX_ERROR_FRAGMENT,
        "snapshot_sha256": copy_hashes,
    }
    atomic_write_json(audit / "baseline.json", record)
    return record


def validate_hotfix_resume_state(
    output: Path, config: dict[str, Any]
) -> dict[str, Any] | None:
    hotfix = compatibility_hotfix(config)
    if hotfix is None:
        return None
    trials = _load_trials(output)
    baseline_path = output / "hotfix_audit" / "baseline.json"
    if baseline_path.exists():
        baseline = _read_json(baseline_path)
        if (
            baseline.get("hotfix_id") != GATE3_HOTFIX_ID
            or baseline.get("base_scientific_config_hash")
            != GATE3_BASE_SCIENTIFIC_CONFIG_HASH
            or baseline.get("prior_completed_trials") != 960
            or baseline.get("prior_error_trials") != 240
        ):
            raise RuntimeError("the preserved hotfix baseline audit is invalid")
    else:
        baseline = _validate_original_state(output, config, trials)

    nonaffected_complete = 0
    affected_complete = 0
    affected_errors = 0
    for row in trials:
        if row.get("scientific_config_hash") != GATE3_BASE_SCIENTIFIC_CONFIG_HASH:
            raise RuntimeError("hotfix resume found a stale trial hash")
        dataset = row.get("dataset", {}).get("name")
        status = row.get("status")
        if dataset != GATE3_HOTFIX_DATASET:
            if status != "complete" or row.get("compatibility_hotfix_id") is not None:
                raise RuntimeError("hotfix scope would alter a non-GBSG2 trial")
            nonaffected_complete += 1
        elif status == "complete":
            if row.get("compatibility_hotfix_id") != GATE3_HOTFIX_ID:
                raise RuntimeError(
                    "a completed GBSG2 trial is not bound to this hotfix"
                )
            affected_complete += 1
        elif status == "error":
            affected_errors += 1
        else:
            raise RuntimeError("hotfix resume found an unsupported trial status")
    if len(trials) != 1200 or nonaffected_complete != 960:
        raise RuntimeError("hotfix resume no longer contains the 960 preserved trials")
    if affected_complete + affected_errors != 240:
        raise RuntimeError("hotfix resume no longer contains the 240-trial GBSG2 block")
    return {
        **baseline,
        "preserved_nonaffected_complete": nonaffected_complete,
        "current_affected_complete": affected_complete,
        "current_affected_errors": affected_errors,
    }
