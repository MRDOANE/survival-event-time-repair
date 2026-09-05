#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from external_interval import (
    aggregate_results,
    dataframe_summaries,
    load_cohort,
    load_config,
    run_replicate,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_one(payload: tuple[Any, dict[str, Any], int]) -> dict[str, Any]:
    cohort, config, replicate = payload
    try:
        return run_replicate(cohort, config, replicate)
    except Exception as exc:  # retain failures as auditable output
        return {"replicate": replicate, "error": type(exc).__name__, "message": str(exc)}


def write_report(aggregate: dict[str, Any], config: dict[str, Any], path: Path) -> None:
    cohort = config["cohort"]
    lines = [
        f"# {cohort['title']}",
        "",
        f"Decision: **{aggregate['decision']}**",
        "",
        aggregate["interpretation"],
        "",
        "## Cohort and execution",
        "",
        f"- Rows: {cohort['expected_rows']}",
        f"- Independent resampling units: {cohort['expected_clusters']}",
        f"- Finite event intervals: {cohort['expected_finite_upper']}",
        f"- Bootstrap replicates completed: {aggregate['successful_replicates']}/{aggregate['planned_replicates']}",
        f"- Primary target coverage: {1.0 - float(config['analysis']['alpha']):.3f}",
        "",
        "## Method summaries",
        "",
        "| Method | Identified coverage lower | Identified coverage upper | Certain miss | Interval NLL | Geometric mean LPB | Target-compatible reps |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in ("naive_upper", "midpoint", "interval_aware"):
        m = aggregate["methods"][method]
        lines.append(
            f"| {method} | {m['coverage_identified_lower']['mean']:.4f} | "
            f"{m['coverage_identified_upper']['mean']:.4f} | {m['certain_miss_fraction']['mean']:.4f} | "
            f"{m['heldout_interval_nll']['mean']:.4f} | {m['geometric_mean_lpb']['mean']:.4f} | "
            f"{m['target_compatibility_fraction']:.3f} |"
        )
    lines += [
        "",
        "## Paired comparisons against naive upper-endpoint coding",
        "",
        "Positive interval-NLL improvement and positive certain-miss reduction favor the correction.",
        "",
        "| Branch | Classification | NLL improvement (mean; 95% bootstrap interval) | Certain-miss reduction (mean; 95% bootstrap interval) | Geometric LPB ratio |",
        "|---|---|---:|---:|---:|",
    ]
    for branch in ("midpoint", "interval_aware"):
        item = aggregate["comparisons"][branch]
        nll = item["metrics"]["interval_nll_improvement"]
        miss = item["metrics"]["certain_miss_reduction"]
        ratio = item["metrics"]["geometric_lpb_ratio"]
        lines.append(
            f"| {branch} | **{item['classification']}** | {nll['mean']:.4f} "
            f"[{nll['lower_95']:.4f}, {nll['upper_95']:.4f}] | {miss['mean']:.4f} "
            f"[{miss['lower_95']:.4f}, {miss['upper_95']:.4f}] | {ratio['mean']:.3f} |"
        )
    lines += [
        "",
        "## Interpretation guardrail",
        "",
        "The exact event times remain unknown. The held-out interval log score is the primary proper predictive score. "
        "Coverage is reported as a partially identified interval: a bound at or below the observed lower endpoint is "
        "certainly covering, a bound above a finite upper endpoint is certainly missing, and all other cases are ambiguous. "
        "These data can externally support the direction of the Gate 3 result, but they cannot recreate clean-event-time coverage.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_figures(results: list[dict[str, Any]], aggregate: dict[str, Any], output: Path) -> None:
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    methods = ["naive_upper", "midpoint", "interval_aware"]
    lower = [aggregate["methods"][m]["coverage_identified_lower"]["mean"] for m in methods]
    upper = [aggregate["methods"][m]["coverage_identified_upper"]["mean"] for m in methods]
    x = np.arange(len(methods))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.bar(x, np.asarray(upper) - np.asarray(lower), bottom=lower, color="#9ecae1", label="ambiguous portion")
    ax.bar(x, lower, color="#2171b5", label="certainly covered")
    ax.axhline(0.9, color="#b2182b", linestyle="--", linewidth=1.5, label="0.90 target")
    ax.set_xticks(x, ["Naive upper", "Midpoint", "Interval-aware"])
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Coverage identification interval")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(figures / "coverage_identification.png", dpi=180)
    plt.close(fig)

    valid = [r for r in results if "error" not in r]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0), sharey=True)
    for ax, branch, color in zip(axes, ("midpoint", "interval_aware"), ("#238b45", "#6a51a3"), strict=True):
        values = [r["comparisons"][branch]["interval_nll_improvement"] for r in valid]
        ax.hist(values, bins=30, color=color, alpha=0.85)
        ax.axvline(0.0, color="black", linestyle="--", linewidth=1.2)
        ax.set_title(branch.replace("_", " ").title())
        ax.set_xlabel("Held-out interval NLL improvement")
    axes[0].set_ylabel("Bootstrap replicates")
    fig.tight_layout()
    fig.savefig(figures / "paired_interval_score.png", dpi=180)
    plt.close(fig)


def package_results(output: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, Path(output.name) / path.relative_to(output))
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--results-zip", default=None)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    cohort = load_cohort(config, PROJECT_ROOT)
    output = Path(args.output).resolve()
    repeats_dir = output / "replicates"
    repeats_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, output / "config_resolved.json")
    reps = int(args.replicates or config["analysis"]["bootstrap_replicates"])

    manifest = {
        "schema_version": "1.0",
        "created_utc": utc_now(),
        "cohort": config["cohort"]["name"],
        "config_sha256": file_sha256(config_path),
        "data_sha256": file_sha256(PROJECT_ROOT / config["cohort"]["data_csv"]),
        "replicates": reps,
        "jobs": max(1, args.jobs),
        "resume": bool(args.resume),
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
    }
    atomic_json(output / "run_manifest.json", manifest)

    pending: list[int] = []
    completed: dict[int, dict[str, Any]] = {}
    for replicate in range(reps):
        checkpoint = repeats_dir / f"replicate_{replicate:04d}.json"
        if args.resume and checkpoint.exists():
            with checkpoint.open("r", encoding="utf-8") as handle:
                completed[replicate] = json.load(handle)
        else:
            pending.append(replicate)

    payloads = [(cohort, config, replicate) for replicate in pending]
    if max(1, args.jobs) == 1:
        iterator = map(execute_one, payloads)
        executor = None
    else:
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.jobs))
        iterator = executor.map(execute_one, payloads, chunksize=1)
    try:
        for result in iterator:
            completed[int(result["replicate"])] = result
            atomic_json(repeats_dir / f"replicate_{int(result['replicate']):04d}.json", result)
            status = "ERROR" if "error" in result else "ok"
            print(f"[{len(completed):04d}/{reps:04d}] replicate {result['replicate']:04d}: {status}", flush=True)
    finally:
        if executor is not None:
            executor.shutdown(wait=True)

    results = [completed[i] for i in range(reps)]
    aggregate = aggregate_results(results, config)
    aggregate["created_utc"] = utc_now()
    aggregate["data_audit"] = {
        "rows": len(cohort.frame),
        "clusters": int(len(np.unique(cohort.cluster))),
        "finite_upper": int(np.isfinite(cohort.upper).sum()),
        "right_censored": int((~np.isfinite(cohort.upper)).sum()),
        "left_censored": int((cohort.lower <= 1.0e-6).sum()),
    }
    atomic_json(output / "gate_decision.json", aggregate)
    method_frame, comparison_frame = dataframe_summaries(aggregate)
    method_frame.to_csv(output / "method_summary.csv", index=False)
    comparison_frame.to_csv(output / "comparison_summary.csv", index=False)
    write_report(aggregate, config, output / "gate_report.md")
    write_figures(results, aggregate, output)
    (output / "RUN_COMPLETE").write_text(utc_now() + "\n", encoding="utf-8")
    if args.results_zip:
        package_results(output, Path(args.results_zip).resolve())
        print(f"Results archive: {Path(args.results_zip).resolve()}")
    print(f"Decision: {aggregate['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
