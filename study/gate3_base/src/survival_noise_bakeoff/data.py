from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class SurvivalData:
    X: np.ndarray
    true_time: np.ndarray
    censor_time: np.ndarray
    clean_time: np.ndarray
    clean_event: np.ndarray
    provenance: dict[str, Any]


@dataclass(frozen=True)
class SplitIndices:
    train: np.ndarray
    noise_estimation: np.ndarray
    calibration: np.ndarray
    test: np.ndarray

    def as_dict(self) -> dict[str, list[int]]:
        return {
            "train": self.train.tolist(),
            "noise_estimation": self.noise_estimation.tolist(),
            "calibration": self.calibration.tolist(),
            "test": self.test.tolist(),
        }


def make_splits(n: int, fractions: list[float], seed: int) -> SplitIndices:
    if len(fractions) != 4:
        raise ValueError(
            "split must have four fractions: train, protocol estimation, "
            "calibration, and test"
        )
    if not np.isclose(sum(fractions), 1.0):
        raise ValueError(f"split fractions must sum to 1, got {fractions}")
    if min(fractions) <= 0:
        raise ValueError("all split fractions must be positive")
    rng = np.random.default_rng(seed + 104729)
    order = rng.permutation(n)
    cuts = np.cumsum([int(n * f) for f in fractions[:-1]])
    train, noise, cal, test = np.split(order, cuts)
    union = np.concatenate([train, noise, cal, test])
    if len(np.unique(union)) != n:
        raise AssertionError("split indices overlap or omit observations")
    return SplitIndices(train=train, noise_estimation=noise, calibration=cal, test=test)


def _stable_offset(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def _synthetic_covariates(n: int, p: int, rng: np.random.Generator) -> np.ndarray:
    z = rng.normal(size=(n, p))
    if p >= 4:
        z[:, 1] = 0.45 * z[:, 0] + np.sqrt(1 - 0.45**2) * z[:, 1]
        z[:, 3] = 0.30 * z[:, 2] + np.sqrt(1 - 0.30**2) * z[:, 3]
    return z


def _event_linear_predictor(X: np.ndarray, mechanism: str) -> np.ndarray:
    p = X.shape[1]
    if mechanism == "linear":
        beta = np.zeros(p)
        beta[: min(p, 6)] = np.array([-0.55, 0.35, -0.25, 0.20, -0.15, 0.10])[
            : min(p, 6)
        ]
        return X @ beta
    if mechanism == "nonlinear":
        x0 = X[:, 0]
        x1 = X[:, min(1, p - 1)]
        x2 = X[:, min(2, p - 1)]
        x3 = X[:, min(3, p - 1)]
        return -0.75 * np.sin(x0) + 0.35 * x1 * x2 - 0.22 * (x3**2 - 1) + 0.15 * x1
    raise ValueError(f"unknown mechanism {mechanism!r}")


def _event_times(
    X: np.ndarray,
    mechanism: str,
    distribution: str,
    rng: np.random.Generator,
) -> np.ndarray:
    eta = np.clip(_event_linear_predictor(X, mechanism), -3.0, 3.0)
    if distribution == "lognormal":
        return np.exp(2.45 + eta + rng.normal(scale=0.62, size=len(X)))
    if distribution == "weibull_ph":
        shape = 1.55
        uniform = np.clip(rng.random(len(X)), 1e-12, 1 - 1e-12)
        return np.exp(2.45) * (-np.log(uniform) / np.exp(np.clip(-eta, -8, 8))) ** (
            1.0 / shape
        )
    if distribution == "loglogistic":
        uniform = np.clip(rng.random(len(X)), 1e-12, 1 - 1e-12)
        logistic_noise = np.log(uniform / (1.0 - uniform))
        return np.exp(2.45 + eta + 0.42 * logistic_noise)
    if distribution == "mixture_lognormal":
        component = X[:, 0] + 0.5 * X[:, min(1, X.shape[1] - 1)] > 0
        location_shift = np.where(component, 0.32, -0.12)
        scale = np.where(component, 0.88, 0.45)
        return np.exp(2.35 + eta + location_shift + rng.normal(size=len(X)) * scale)
    raise ValueError(f"unknown outcome distribution {distribution!r}")


def _generate_times(
    X: np.ndarray,
    mechanism: str,
    distribution: str,
    target_censoring: float,
    censoring_mechanism: str,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    true_time = _event_times(X, mechanism, distribution, rng)
    if censoring_mechanism == "independent_lognormal":
        censor_lp = np.zeros(len(X))
    elif censoring_mechanism == "covariate_dependent_nonlinear":
        x0 = X[:, 0]
        x1 = X[:, min(1, X.shape[1] - 1)]
        x2 = X[:, min(2, X.shape[1] - 1)]
        censor_lp = 0.42 * x0 - 0.28 * np.sin(x1) + 0.16 * x2**2
    else:
        raise ValueError(f"unknown censoring mechanism {censoring_mechanism!r}")
    censor_base = np.exp(2.30 + censor_lp + rng.normal(scale=0.85, size=len(X)))
    desired_event_fraction = 1.0 - float(target_censoring)
    scale = np.quantile(true_time / censor_base, desired_event_fraction)
    censor_time = censor_base * max(float(scale), 1e-6)

    clean_time = np.minimum(true_time, censor_time)
    clean_event = (true_time <= censor_time).astype(np.int8)
    time_scale = np.median(clean_time) / 10.0
    true_time = true_time / time_scale
    censor_time = censor_time / time_scale
    clean_time = clean_time / time_scale
    return true_time, censor_time, clean_time, clean_event


def _load_public_covariates(
    source: str, n: int, rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    try:
        import pandas as pd
        from lifelines import datasets

        if source == "rossi":
            frame = datasets.load_rossi()
            feature_frame = frame.drop(columns=["week", "arrest"])
            display_name = "Rossi recidivism"
            loader = "lifelines.datasets.load_rossi"
        elif source == "gbsg2":
            frame = datasets.load_gbsg2()
            feature_frame = frame.drop(columns=["time", "cens"])
            feature_frame = pd.get_dummies(feature_frame, drop_first=False, dtype=float)
            display_name = "German Breast Cancer Study Group 2"
            loader = "lifelines.datasets.load_gbsg2"
        else:
            raise ValueError(f"unknown public covariate source {source!r}")
        base = feature_frame.to_numpy(dtype=float)
        take = rng.integers(0, len(base), size=n)
        X = base[take].copy()
        for j in range(X.shape[1]):
            unique = np.unique(base[:, j])
            if len(unique) > 8:
                X[:, j] += rng.normal(
                    scale=max(float(np.std(base[:, j])), 1e-6) * 0.02,
                    size=n,
                )
        return X, {
            "kind": "public_covariates_semisynthetic_outcomes",
            "dataset": display_name,
            "loader": loader,
            "source_url": "https://lifelines.readthedocs.io/en/latest/lifelines.datasets.html",
            "original_rows": len(base),
            "bootstrapped_rows": int(n),
            "fallback_used": False,
        }
    except Exception as exc:
        p = 7 if source == "rossi" else 12
        return _synthetic_covariates(n, p, rng), {
            "kind": "synthetic_fallback",
            "dataset": source,
            "loader": f"lifelines.datasets.load_{source}",
            "fallback_used": True,
            "fallback_reason": f"{type(exc).__name__}: {exc}",
        }


def load_dataset(
    spec: dict[str, Any],
    seed: int,
    split_fractions: list[float] | None = None,
) -> SurvivalData:
    name = str(spec["name"])
    rng = np.random.default_rng(seed + 7919 + _stable_offset(name))
    n = int(spec["n"])
    mechanism = str(spec.get("mechanism", "linear"))
    distribution = str(spec.get("outcome_distribution", "lognormal"))
    target_censoring = float(spec.get("target_censoring", 0.35))
    censoring_mechanism = str(spec.get("censoring_mechanism", "independent_lognormal"))

    if name.startswith("synthetic_"):
        p = int(spec.get("p", 12))
        X = _synthetic_covariates(n, p, rng)
        provenance = {
            "kind": "fully_synthetic",
            "dataset": name,
            "fallback_used": False,
        }
    elif str(spec.get("public_covariates", "")) in {"rossi", "gbsg2"}:
        X, provenance = _load_public_covariates(str(spec["public_covariates"]), n, rng)
    else:
        raise ValueError(f"unknown dataset {name!r}")

    fractions = split_fractions or [0.40, 0.10, 0.25, 0.25]
    provisional_splits = make_splits(n, fractions, seed)
    scaler = StandardScaler().fit(X[provisional_splits.train])
    X = scaler.transform(X).astype(np.float64)
    true_time, censor_time, clean_time, clean_event = _generate_times(
        X,
        mechanism,
        distribution,
        target_censoring,
        censoring_mechanism,
        rng,
    )
    provenance = {
        **provenance,
        "name": name,
        "n": n,
        "p": int(X.shape[1]),
        "mechanism": mechanism,
        "outcome_distribution": distribution,
        "censoring_mechanism": censoring_mechanism,
        "requested_censoring": target_censoring,
        "realized_censoring": float(1.0 - clean_event.mean()),
        "require_public": bool(spec.get("require_public", False)),
        "feature_scaler_fit_split": "train_only",
    }
    return SurvivalData(
        X=X,
        true_time=true_time,
        censor_time=censor_time,
        clean_time=clean_time,
        clean_event=clean_event,
        provenance=provenance,
    )
