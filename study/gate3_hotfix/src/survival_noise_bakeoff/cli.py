from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from .aggregate import aggregate_results
from .experiment import build_trial_specs, run_trials
from .hotfix import validate_hotfix_resume_state
from .official import validate_upstream
from .preflight import run_preflight
from .util import (
    atomic_write_json,
    atomic_write_text,
    environment_manifest,
    fingerprint,
    implementation_hash,
    scientific_config_hash,
    scientific_config_payload,
    utc_now,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a mapping")
    return value


def _configure_logging(output: Path) -> None:
    output.joinpath("logs").mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(output / "logs" / "run.log", mode="a", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def assert_output_compatible(output: Path, expected_scientific_hash: str) -> None:
    """Hard-refuse reuse of an output directory under changed assumptions."""
    manifest_path = output / "run_manifest.json"
    trial_paths = (
        list((output / "trials").glob("*.json")) if (output / "trials").exists() else []
    )
    if not manifest_path.exists():
        if trial_paths:
            raise RuntimeError(
                f"output {output} contains {len(trial_paths)} trial file(s) but no hash-bound manifest; "
                "choose a new RUN_NAME/output directory"
            )
        return
    with manifest_path.open("r", encoding="utf-8") as handle:
        existing = json.load(handle)
    found = existing.get("scientific_config_hash")
    if found != expected_scientific_hash:
        raise RuntimeError(
            f"output scientific configuration mismatch for {output}: found {found!r}, "
            f"expected {expected_scientific_hash!r}. Use a new RUN_NAME or OUT_DIR; "
            "stale results will not be reused."
        )


def command_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _configure_logging(output)
    logger = logging.getLogger(__name__)
    config = _load_yaml(config_path)
    if args.n_jobs is not None:
        config["run"]["n_jobs"] = int(args.n_jobs)
    n_jobs = int(config["run"].get("n_jobs", 1))
    root = Path(__file__).resolve().parents[2]

    science_hash = scientific_config_hash(config)
    assert_output_compatible(output, science_hash)
    hotfix_resume = validate_hotfix_resume_state(output, config)

    atomic_write_text(
        output / "config_resolved.yaml", yaml.safe_dump(config, sort_keys=False)
    )
    atomic_write_json(output / "environment.json", environment_manifest(root))
    upstream_root = Path(
        os.environ.get(
            "DRCOSARC_UPSTREAM_DIR", root / "external" / "conformal_survival"
        )
    ).resolve()
    upstream_manifest = validate_upstream(upstream_root)
    preflight = run_preflight(config, output, root, upstream_root, upstream_manifest)
    specs = build_trial_specs(config)
    manifest = {
        "schema_version": "3.0",
        "created_utc": utc_now(),
        "config_path": str(config_path),
        "config_sha256_prefix": fingerprint(config, 24),
        "scientific_config_hash": science_hash,
        "scientific_config": scientific_config_payload(config),
        "run_kind": config["run"]["kind"],
        "planned_trials": len(specs),
        "trial_ids": [s.trial_id for s in specs],
        "resume": bool(args.resume),
        "n_jobs": n_jobs,
        "preflight_status": preflight["status"],
        "method_scope": (
            "Paper-scale stress expansion of separately gated midpoint and "
            "conditional interval-aware observed-data interfaces around the "
            "pinned authors' adaptive DR-COSARC functions"
        ),
        "official_source": upstream_manifest,
        "execution_implementation_sha256": implementation_hash(),
    }
    if hotfix_resume is not None:
        manifest["compatibility_hotfix"] = config["run"]["compatibility_hotfix"]
        manifest["hotfix_resume_state_before_run"] = hotfix_resume
    atomic_write_json(output / "run_manifest.json", manifest)
    logger.info(
        "starting run kind=%s planned_trials=%d", config["run"]["kind"], len(specs)
    )
    results = run_trials(
        config,
        output,
        bool(args.resume),
        n_jobs,
        root,
        upstream_root,
        upstream_manifest,
    )
    completed = sum(r.get("status") == "complete" for r in results)
    errors = len(results) - completed
    manifest.update(
        {
            "completed_utc": utc_now(),
            "completed_trials": completed,
            "error_trials": errors,
        }
    )
    atomic_write_json(output / "run_manifest.json", manifest)
    gate = aggregate_results(output, config)
    logger.info(
        "completed=%d errors=%d decision=%s", completed, errors, gate["decision"]
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "completed": completed,
                "errors": errors,
                "gate": gate["decision"],
            },
            indent=2,
        )
    )
    return 0 if errors == 0 else 1


def command_aggregate(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    config_path = (
        Path(args.config).resolve() if args.config else output / "config_resolved.yaml"
    )
    config = _load_yaml(config_path)
    assert_output_compatible(output, scientific_config_hash(config))
    gate = aggregate_results(output, config)
    print(json.dumps(gate, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gate 3 midpoint and interval-aware DR-COSARC expansion"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run or resume trials and aggregate")
    run.add_argument("--config", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--n-jobs", type=int)
    run.set_defaults(func=command_run)
    aggregate = sub.add_parser("aggregate", help="rebuild aggregate outputs")
    aggregate.add_argument("--output", required=True)
    aggregate.add_argument("--config")
    aggregate.set_defaults(func=command_aggregate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
