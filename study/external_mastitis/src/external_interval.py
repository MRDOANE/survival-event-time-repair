"""Core routines for a preregistered external interval-censoring analysis.

The module deliberately uses only NumPy/SciPy/Pandas.  It fits log-normal AFT
models under three observation contracts, calibrates lower prediction bounds,
and evaluates those bounds without pretending that latent event times are
observed.  Test-set coverage is therefore reported as an identified interval.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import log_ndtr, ndtr, ndtri


EPS_TIME = 1.0e-6
EPS_PROB = 1.0e-12


@dataclass
class Cohort:
    frame: pd.DataFrame
    lower: np.ndarray
    upper: np.ndarray
    features: np.ndarray
    feature_names: list[str]
    cluster: np.ndarray
    stratum: np.ndarray
    subgroup: np.ndarray


@dataclass
class Standardizer:
    mean: np.ndarray
    scale: np.ndarray

    @classmethod
    def fit(cls, x: np.ndarray) -> "Standardizer":
        mean = np.mean(x, axis=0)
        scale = np.std(x, axis=0)
        scale = np.where(scale > 1.0e-12, scale, 1.0)
        return cls(mean=mean, scale=scale)

    def transform(self, x: np.ndarray) -> np.ndarray:
        z = (x - self.mean) / self.scale
        return np.column_stack([np.ones(len(z)), z])


@dataclass
class AFTFit:
    beta: np.ndarray
    sigma: float
    success: bool
    objective: float
    iterations: int
    message: str

    def mu(self, design: np.ndarray) -> np.ndarray:
        return design @ self.beta


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_cohort(config: dict[str, Any], project_root: Path) -> Cohort:
    spec = config["cohort"]
    frame = pd.read_csv(project_root / spec["data_csv"])
    if spec["name"] == "hemophilia_hiv":
        frame["treat_low_dose"] = (frame["treat"] == "low dose").astype(float)
        features = frame[["treat_low_dose"]].to_numpy(float)
        lower = frame["low"].to_numpy(float)
        upper = frame["upp"].to_numpy(float)
        cluster = frame["id"].astype(str).to_numpy()
        event = np.isfinite(upper).astype(int)
        stratum = (frame["treat"].astype(str) + "|e" + pd.Series(event).astype(str)).to_numpy()
        subgroup = frame["treat"].astype(str).to_numpy()
        feature_names = ["treat_low_dose"]
    elif spec["name"] == "mastitis":
        features = frame[["rear", "par24", "par56"]].to_numpy(float)
        lower = frame["ll"].to_numpy(float)
        lower = np.where(np.isfinite(lower), lower, 0.0)
        upper = frame["ul"].to_numpy(float)
        cluster = frame["cow"].astype(str).to_numpy()
        # Parity is cow-level and is safe for grouped stratification.
        stratum = frame["fpar"].astype(str).to_numpy()
        subgroup = (frame["frear"].astype(str) + "|par=" + frame["fpar"].astype(str)).to_numpy()
        feature_names = ["rear", "parity_2_to_4", "parity_over_4"]
    else:
        raise ValueError(f"unsupported cohort: {spec['name']}")

    cohort = Cohort(
        frame=frame,
        lower=np.maximum(lower, 0.0),
        upper=upper,
        features=features,
        feature_names=feature_names,
        cluster=cluster,
        stratum=stratum,
        subgroup=subgroup,
    )
    validate_cohort(cohort, spec)
    return cohort


def validate_cohort(cohort: Cohort, spec: dict[str, Any]) -> None:
    n = len(cohort.frame)
    if n != int(spec["expected_rows"]):
        raise ValueError(f"expected {spec['expected_rows']} rows; found {n}")
    n_clusters = len(np.unique(cohort.cluster))
    if n_clusters != int(spec["expected_clusters"]):
        raise ValueError(f"expected {spec['expected_clusters']} clusters; found {n_clusters}")
    finite_upper = np.isfinite(cohort.upper)
    if int(finite_upper.sum()) != int(spec["expected_finite_upper"]):
        raise ValueError("finite-upper count differs from the frozen cohort manifest")
    if np.any(finite_upper & (cohort.upper <= cohort.lower)):
        raise ValueError("every finite event interval must satisfy upper > lower")
    if np.any(~np.isfinite(cohort.lower)) or np.any(cohort.lower < 0):
        raise ValueError("lower endpoints must be finite and nonnegative after left-censor coding")
    if len(cohort.features) != n or not np.isfinite(cohort.features).all():
        raise ValueError("feature matrix is invalid")


def _log_interval_probability(z_lower: np.ndarray, z_upper: np.ndarray) -> np.ndarray:
    """Stable log(Phi(z_upper) - Phi(z_lower))."""
    log_fu = log_ndtr(z_upper)
    log_fl = log_ndtr(z_lower)
    ratio = np.exp(np.minimum(log_fl - log_fu, -EPS_PROB))
    return log_fu + np.log1p(-ratio)


def natural_interval_loglik(
    beta: np.ndarray,
    sigma: float,
    design: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    mu = design @ beta
    lower_safe = np.maximum(lower, EPS_TIME)
    z_lower = (np.log(lower_safe) - mu) / sigma
    result = np.empty(len(lower), dtype=float)
    finite = np.isfinite(upper)
    left = finite & (lower <= EPS_TIME)
    interval = finite & ~left
    right = ~finite
    if np.any(left):
        z_upper = (np.log(np.maximum(upper[left], EPS_TIME)) - mu[left]) / sigma
        result[left] = log_ndtr(z_upper)
    if np.any(interval):
        z_upper = (np.log(np.maximum(upper[interval], EPS_TIME)) - mu[interval]) / sigma
        result[interval] = _log_interval_probability(z_lower[interval], z_upper)
    if np.any(right):
        result[right] = log_ndtr(-z_lower[right])
    return np.maximum(result, math.log(1.0e-300))


def _working_loglik(
    params: np.ndarray,
    design: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    mode: str,
    ridge: float,
) -> float:
    beta = params[:-1]
    sigma = float(np.exp(params[-1]))
    mu = design @ beta
    finite = np.isfinite(upper)
    right = ~finite
    ll = np.empty(len(lower), dtype=float)

    if mode == "interval":
        ll = natural_interval_loglik(beta, sigma, design, lower, upper)
    else:
        if mode == "naive_upper":
            exact = upper[finite]
        elif mode == "midpoint":
            exact = 0.5 * (lower[finite] + upper[finite])
        else:
            raise ValueError(f"unsupported fitting mode: {mode}")
        exact = np.maximum(exact, EPS_TIME)
        z = (np.log(exact) - mu[finite]) / sigma
        ll[finite] = -0.5 * z * z - np.log(sigma) - np.log(exact) - 0.5 * np.log(2.0 * np.pi)
        if np.any(right):
            z_lower = (np.log(np.maximum(lower[right], EPS_TIME)) - mu[right]) / sigma
            ll[right] = log_ndtr(-z_lower)

    penalty = 0.5 * ridge * float(np.sum(beta[1:] ** 2))
    return -float(np.sum(ll)) + penalty


def fit_aft(
    design: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    mode: str,
    ridge: float = 1.0e-5,
    maxiter: int = 800,
) -> AFTFit:
    finite = np.isfinite(upper)
    pseudo = np.where(
        finite,
        np.where(mode == "naive_upper", upper, 0.5 * (lower + upper)),
        lower * 1.25,
    )
    pseudo = np.maximum(np.where(np.isfinite(pseudo), pseudo, lower + 1.0), EPS_TIME)
    y = np.log(pseudo)
    beta0 = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ beta0
    sigma0 = float(np.clip(np.std(residual), 0.25, 2.5))
    initial = np.r_[beta0, np.log(sigma0)]
    objective = lambda p: _working_loglik(p, design, lower, upper, mode, ridge)
    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        bounds=[(None, None)] * design.shape[1] + [(-4.0, 3.0)],
        options={"maxiter": maxiter, "ftol": 1.0e-10},
    )
    if not result.success or not np.isfinite(result.fun):
        result = minimize(
            objective,
            initial,
            method="Powell",
            bounds=[(-20.0, 20.0)] * design.shape[1] + [(-4.0, 3.0)],
            options={"maxiter": maxiter * 2, "ftol": 1.0e-9},
        )
    return AFTFit(
        beta=np.asarray(result.x[:-1], dtype=float),
        sigma=float(np.exp(result.x[-1])),
        success=bool(result.success and np.isfinite(result.fun)),
        objective=float(result.fun),
        iterations=int(getattr(result, "nit", -1)),
        message=str(result.message),
    )


def conditional_median(
    mu: np.ndarray,
    sigma: float,
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    lower_cdf = np.where(
        lower <= EPS_TIME,
        0.0,
        ndtr((np.log(np.maximum(lower, EPS_TIME)) - mu) / sigma),
    )
    upper_cdf = np.where(
        np.isfinite(upper),
        ndtr((np.log(np.maximum(upper, EPS_TIME)) - mu) / sigma),
        1.0,
    )
    probability = np.clip(lower_cdf + 0.5 * (upper_cdf - lower_cdf), 1.0e-8, 1.0 - 1.0e-8)
    time = np.exp(np.clip(mu + sigma * ndtri(probability), -20.0, 20.0))
    finite = np.isfinite(upper)
    time = np.maximum(time, np.maximum(lower, EPS_TIME))
    time[finite] = np.minimum(time[finite], upper[finite])
    return time


def calibration_times(
    fit: AFTFit,
    design: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    mode: str,
) -> np.ndarray:
    finite = np.isfinite(upper)
    times = conditional_median(fit.mu(design), fit.sigma, lower, upper)
    if mode == "naive_upper":
        times[finite] = upper[finite]
    elif mode == "midpoint":
        times[finite] = 0.5 * (lower[finite] + upper[finite])
    elif mode != "interval":
        raise ValueError(mode)
    return np.maximum(times, EPS_TIME)


def lower_prediction_bounds(
    fit: AFTFit,
    cal_design: np.ndarray,
    cal_lower: np.ndarray,
    cal_upper: np.ndarray,
    test_design: np.ndarray,
    mode: str,
    alpha: float,
) -> tuple[np.ndarray, float]:
    representative = calibration_times(fit, cal_design, cal_lower, cal_upper, mode)
    residual = np.log(representative) - fit.mu(cal_design)
    quantile = float(np.quantile(residual, alpha, method="linear"))
    bound = np.exp(np.clip(fit.mu(test_design) + quantile, -20.0, 20.0))
    return bound, quantile


def interval_coverage_metrics(
    bound: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    target: float,
) -> dict[str, float | bool]:
    finite = np.isfinite(upper)
    certainly_covered = bound <= lower + 1.0e-12
    certainly_missed = finite & (bound > upper + 1.0e-12)
    low = float(np.mean(certainly_covered))
    miss = float(np.mean(certainly_missed))
    high = 1.0 - miss
    return {
        "coverage_identified_lower": low,
        "coverage_identified_upper": high,
        "certain_miss_fraction": miss,
        "ambiguous_fraction": float(1.0 - low - miss),
        "resolved_fraction": float(low + miss),
        "target_compatible": bool(low - 1.0e-12 <= target <= high + 1.0e-12),
        "mean_lpb": float(np.mean(bound)),
        "geometric_mean_lpb": float(np.exp(np.mean(np.log(np.maximum(bound, EPS_TIME))))),
        "median_lpb": float(np.median(bound)),
    }


def grouped_split(
    cluster: np.ndarray,
    stratum: np.ndarray,
    rng: np.random.Generator,
    proportions: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    unit_frame = pd.DataFrame({"cluster": cluster, "stratum": stratum}).drop_duplicates("cluster")
    assignments: dict[str, str] = {}
    for _, part in unit_frame.groupby("stratum", sort=True):
        units = part["cluster"].astype(str).to_numpy().copy()
        rng.shuffle(units)
        n = len(units)
        n_train = max(1, int(round(proportions[0] * n)))
        n_cal = max(1, int(round(proportions[1] * n))) if n >= 3 else max(0, n - n_train)
        if n_train + n_cal >= n:
            n_train = max(1, n - 2) if n >= 3 else max(1, n - 1)
            n_cal = 1 if n >= 3 else max(0, n - n_train)
        for u in units[:n_train]:
            assignments[u] = "train"
        for u in units[n_train : n_train + n_cal]:
            assignments[u] = "cal"
        for u in units[n_train + n_cal :]:
            assignments[u] = "test"
    labels = np.array([assignments[str(u)] for u in cluster])
    return labels == "train", labels == "cal", labels == "test"


def cluster_bootstrap(cohort: Cohort, rng: np.random.Generator) -> Cohort:
    units = pd.DataFrame({"cluster": cohort.cluster, "stratum": cohort.stratum}).drop_duplicates("cluster")
    sampled_positions: list[int] = []
    for _, part in units.groupby("stratum", sort=True):
        candidates = part["cluster"].astype(str).to_numpy()
        draws = rng.choice(candidates, size=len(candidates), replace=True)
        sampled_positions.extend(draws.tolist())
    frames: list[pd.DataFrame] = []
    lowers: list[np.ndarray] = []
    uppers: list[np.ndarray] = []
    features: list[np.ndarray] = []
    clusters: list[np.ndarray] = []
    strata: list[np.ndarray] = []
    subgroups: list[np.ndarray] = []
    for copy_index, unit in enumerate(sampled_positions):
        mask = cohort.cluster.astype(str) == str(unit)
        count = int(mask.sum())
        frames.append(cohort.frame.loc[mask].copy())
        lowers.append(cohort.lower[mask])
        uppers.append(cohort.upper[mask])
        features.append(cohort.features[mask])
        clusters.append(np.repeat(f"{unit}#boot{copy_index}", count))
        strata.append(cohort.stratum[mask])
        subgroups.append(cohort.subgroup[mask])
    return Cohort(
        frame=pd.concat(frames, ignore_index=True),
        lower=np.concatenate(lowers),
        upper=np.concatenate(uppers),
        features=np.vstack(features),
        feature_names=cohort.feature_names,
        cluster=np.concatenate(clusters),
        stratum=np.concatenate(strata),
        subgroup=np.concatenate(subgroups),
    )


def run_replicate(cohort: Cohort, config: dict[str, Any], replicate: int) -> dict[str, Any]:
    seed = int(config["analysis"]["seed"]) + 104729 * replicate
    rng = np.random.default_rng(seed)
    sample = cluster_bootstrap(cohort, rng)
    proportions = tuple(float(x) for x in config["analysis"]["split"])
    train, cal, test = grouped_split(sample.cluster, sample.stratum, rng, proportions)
    if min(int(train.sum()), int(cal.sum()), int(test.sum())) < 5:
        raise RuntimeError("bootstrap split produced an unusably small partition")

    scaler = Standardizer.fit(sample.features[train])
    design = scaler.transform(sample.features)
    alpha = float(config["analysis"]["alpha"])
    target = 1.0 - alpha
    methods = {
        "naive_upper": "naive_upper",
        "midpoint": "midpoint",
        "interval_aware": "interval",
    }
    output: dict[str, Any] = {
        "replicate": replicate,
        "seed": seed,
        "split_rows": {"train": int(train.sum()), "cal": int(cal.sum()), "test": int(test.sum())},
        "split_clusters": {
            "train": int(len(np.unique(sample.cluster[train]))),
            "cal": int(len(np.unique(sample.cluster[cal]))),
            "test": int(len(np.unique(sample.cluster[test]))),
        },
        "methods": {},
    }
    for label, mode in methods.items():
        fit = fit_aft(
            design[train],
            sample.lower[train],
            sample.upper[train],
            mode=mode,
            ridge=float(config["analysis"]["ridge"]),
            maxiter=int(config["analysis"]["maxiter"]),
        )
        if not fit.success:
            raise RuntimeError(f"{label} AFT optimization did not converge: {fit.message}")
        bound, quantile = lower_prediction_bounds(
            fit,
            design[cal],
            sample.lower[cal],
            sample.upper[cal],
            design[test],
            mode,
            alpha,
        )
        metrics = interval_coverage_metrics(bound, sample.lower[test], sample.upper[test], target)
        natural_ll = natural_interval_loglik(
            fit.beta, fit.sigma, design[test], sample.lower[test], sample.upper[test]
        )
        metrics["heldout_interval_nll"] = float(-np.mean(natural_ll))
        metrics["calibration_quantile_log_residual"] = quantile
        subgroup_metrics: dict[str, Any] = {}
        for group in sorted(np.unique(sample.subgroup[test]).tolist()):
            group_mask = test & (sample.subgroup == group)
            if int(group_mask.sum()) >= int(config["analysis"]["min_subgroup_rows"]):
                local_bound = bound[sample.subgroup[test] == group]
                subgroup_metrics[group] = interval_coverage_metrics(
                    local_bound, sample.lower[group_mask], sample.upper[group_mask], target
                )
                subgroup_metrics[group]["n"] = int(group_mask.sum())
        output["methods"][label] = {
            "fit": {
                "success": fit.success,
                "objective": fit.objective,
                "iterations": fit.iterations,
                "message": fit.message,
                "sigma": fit.sigma,
                "beta": fit.beta.tolist(),
            },
            "metrics": metrics,
            "subgroups": subgroup_metrics,
        }

    naive = output["methods"]["naive_upper"]["metrics"]
    output["comparisons"] = {}
    for branch in ("midpoint", "interval_aware"):
        corrected = output["methods"][branch]["metrics"]
        output["comparisons"][branch] = {
            "certain_cover_gain": corrected["coverage_identified_lower"] - naive["coverage_identified_lower"],
            "certain_miss_reduction": naive["certain_miss_fraction"] - corrected["certain_miss_fraction"],
            "interval_nll_improvement": naive["heldout_interval_nll"] - corrected["heldout_interval_nll"],
            "geometric_lpb_ratio": corrected["geometric_mean_lpb"] / max(naive["geometric_mean_lpb"], EPS_TIME),
            "target_compatibility_gain": int(corrected["target_compatible"]) - int(naive["target_compatible"]),
        }
    return output


def percentile_summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "lower_95": float(np.quantile(array, 0.025)),
        "upper_95": float(np.quantile(array, 0.975)),
        "positive_fraction": float(np.mean(array > 0.0)),
    }


def aggregate_results(results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    valid = [r for r in results if "error" not in r]
    total = len(results)
    success_fraction = len(valid) / max(total, 1)
    aggregate: dict[str, Any] = {
        "cohort": config["cohort"]["name"],
        "planned_replicates": total,
        "successful_replicates": len(valid),
        "successful_replicate_fraction": success_fraction,
        "estimand": config["analysis"]["estimand"],
        "methods": {},
        "comparisons": {},
    }
    metric_names = [
        "coverage_identified_lower",
        "coverage_identified_upper",
        "certain_miss_fraction",
        "ambiguous_fraction",
        "resolved_fraction",
        "mean_lpb",
        "geometric_mean_lpb",
        "median_lpb",
        "heldout_interval_nll",
    ]
    for method in ("naive_upper", "midpoint", "interval_aware"):
        aggregate["methods"][method] = {
            metric: percentile_summary([r["methods"][method]["metrics"][metric] for r in valid])
            for metric in metric_names
        }
        aggregate["methods"][method]["target_compatibility_fraction"] = float(
            np.mean([r["methods"][method]["metrics"]["target_compatible"] for r in valid])
        )

    thresholds = config["gate"]
    for branch in ("midpoint", "interval_aware"):
        comparison_names = [
            "certain_cover_gain",
            "certain_miss_reduction",
            "interval_nll_improvement",
            "geometric_lpb_ratio",
            "target_compatibility_gain",
        ]
        summaries = {
            metric: percentile_summary([r["comparisons"][branch][metric] for r in valid])
            for metric in comparison_names
        }
        checks = {
            "replicate_completion": success_fraction >= float(thresholds["min_successful_replicate_fraction"]),
            "proper_score_mean_improves": summaries["interval_nll_improvement"]["mean"] > 0.0,
            "proper_score_lower_95_positive": summaries["interval_nll_improvement"]["lower_95"] > 0.0,
            "proper_score_directional_breadth": summaries["interval_nll_improvement"]["positive_fraction"] >= float(thresholds["min_nll_positive_fraction"]),
            "certain_miss_noninferiority": summaries["certain_miss_reduction"]["lower_95"] >= -float(thresholds["max_certain_miss_increase"]),
            "informativeness_retained": summaries["geometric_lpb_ratio"]["mean"] >= float(thresholds["min_geometric_lpb_ratio"]),
            "target_compatibility": aggregate["methods"][branch]["target_compatibility_fraction"] >= float(thresholds["min_target_compatibility_fraction"]),
        }
        supportive = all(checks.values())
        contrary = (
            summaries["interval_nll_improvement"]["upper_95"] < 0.0
            or summaries["certain_miss_reduction"]["upper_95"] < -float(thresholds["max_certain_miss_increase"])
        )
        classification = "supportive" if supportive else ("contrary" if contrary else "neutral")
        aggregate["comparisons"][branch] = {
            "metrics": summaries,
            "checks": checks,
            "classification": classification,
        }
    classifications = [aggregate["comparisons"][b]["classification"] for b in ("midpoint", "interval_aware")]
    if classifications == ["supportive", "supportive"]:
        decision = "SUPPORTIVE_BOTH"
    elif "supportive" in classifications:
        decision = "SUPPORTIVE_" + ("MIDPOINT" if classifications[0] == "supportive" else "INTERVAL_AWARE")
    elif "contrary" in classifications:
        decision = "CONTRARY_OR_MIXED"
    else:
        decision = "NEUTRAL"
    aggregate["decision"] = decision
    aggregate["interpretation"] = (
        "External interval-censored evidence is evaluated with held-out interval log score and "
        "partially identified lower-bound coverage. No latent event time is treated as observed."
    )
    aggregate["gate_thresholds"] = thresholds
    return aggregate


def dataframe_summaries(aggregate: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    method_rows: list[dict[str, Any]] = []
    for method, metrics in aggregate["methods"].items():
        row: dict[str, Any] = {"method": method}
        for metric, summary in metrics.items():
            if isinstance(summary, dict):
                for key, value in summary.items():
                    row[f"{metric}_{key}"] = value
            else:
                row[metric] = summary
        method_rows.append(row)
    comparison_rows: list[dict[str, Any]] = []
    for branch, item in aggregate["comparisons"].items():
        row = {"branch": branch, "classification": item["classification"]}
        for metric, summary in item["metrics"].items():
            for key, value in summary.items():
                row[f"{metric}_{key}"] = value
        row.update({f"check_{k}": v for k, v in item["checks"].items()})
        comparison_rows.append(row)
    return pd.DataFrame(method_rows), pd.DataFrame(comparison_rows)
