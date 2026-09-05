from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .data import SplitIndices, SurvivalData


@dataclass(frozen=True)
class CorruptedLabels:
    observed_time: np.ndarray
    observed_event: np.ndarray
    p_event_to_censor: np.ndarray
    p_censor_to_event: np.ndarray
    flipped: np.ndarray
    time_errored: np.ndarray
    recorded_lower: np.ndarray
    recorded_upper: np.ndarray
    recorded_interval_available: np.ndarray
    scope: str
    metadata: dict[str, Any]


def _scope_indices(splits: SplitIndices, scope: str) -> np.ndarray:
    if scope == "train_cal":
        return np.concatenate(
            [splits.train, splits.noise_estimation, splits.calibration]
        )
    if scope == "calibration_only":
        return np.concatenate([splits.noise_estimation, splits.calibration])
    if scope == "train_only":
        return np.concatenate([splits.train, splits.noise_estimation])
    if scope == "none":
        return np.array([], dtype=int)
    raise ValueError(f"unknown corruption scope {scope!r}")


def _heap_ceiling(values: np.ndarray, width: float, origin: float) -> np.ndarray:
    heaped = origin + width * np.ceil((values - origin) / width)
    return np.maximum(heaped, 1e-4)


def _scheduled_intervals(
    data: SurvivalData,
    indices: np.ndarray,
    mode: str,
    width: float,
    origin: float,
    gap_cv: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    event_time = data.true_time[indices]
    if mode == "scheduled_regular":
        lower = origin + width * np.floor((event_time - origin) / width)
        upper = lower + width
    else:
        sigma = np.sqrt(np.log1p(gap_cv**2))
        meanlog = -0.5 * sigma**2
        gaps = width * rng.lognormal(mean=meanlog, sigma=sigma, size=len(indices))
        if mode == "scheduled_informative":
            risk_factor = np.exp(np.clip(0.28 * data.X[indices, 0], -0.55, 0.55))
            outcome_factor = np.clip(
                (event_time / max(float(np.median(data.true_time)), 1e-8)) ** 0.15,
                0.75,
                1.30,
            )
            gaps = gaps * risk_factor * outcome_factor
        elif mode != "scheduled_irregular":
            raise ValueError(f"unknown scheduled interval mode {mode!r}")
        phase = rng.uniform(0.05, 0.95, size=len(indices))
        lower = event_time - phase * gaps
        upper = event_time + (1.0 - phase) * gaps
    positive_floor = np.minimum(1e-6, 0.5 * event_time)
    lower = np.maximum(lower, positive_floor)
    upper = np.maximum(upper, event_time)
    if np.any(lower > event_time + 1e-12) or np.any(upper < event_time - 1e-12):
        raise AssertionError("scheduled interval does not contain the latent event")
    return lower, upper


def corrupt_labels(
    data: SurvivalData,
    splits: SplitIndices,
    spec: dict[str, Any],
    seed: int,
) -> CorruptedLabels:
    rng = np.random.default_rng(seed + 15_485_863)
    n = len(data.clean_time)
    observed_time = data.clean_time.copy()
    observed_event = data.clean_event.copy()
    flipped = np.zeros(n, dtype=bool)
    time_errored = np.zeros(n, dtype=bool)
    recorded_lower = data.clean_time.copy()
    recorded_upper = np.where(data.clean_event == 1, data.clean_time, np.nan)
    recorded_interval_available = np.zeros(n, dtype=bool)

    scope = str(spec.get("scope", "train_cal"))
    corruptible = _scope_indices(splits, scope)
    corruptible_mask = np.zeros(n, dtype=bool)
    corruptible_mask[corruptible] = True

    p10_base = float(spec.get("flip_event_to_censor", 0.0))
    p01_base = float(spec.get("flip_censor_to_event", 0.0))
    p10 = np.where(corruptible_mask, p10_base, 0.0)
    p01 = np.where(corruptible_mask, p01_base, 0.0)
    if len(corruptible):
        truth = data.clean_event[corruptible]
        probabilities = np.where(truth == 1, p10_base, p01_base)
        chosen = rng.random(len(corruptible)) < probabilities
        flip_idx = corruptible[chosen]
        observed_event[flip_idx] = 1 - observed_event[flip_idx]
        flipped[flip_idx] = True

    time_mode = str(spec.get("time_error_mode", "none"))
    time_fraction = float(spec.get("time_error_fraction", 0.0))
    time_probability = float(
        spec.get("time_error_probability", 1.0 if time_fraction > 0 else 0.0)
    )
    base_scale = float(np.median(data.clean_time[splits.train]))
    width = time_fraction * base_scale if time_fraction > 0 else 0.0
    origin = float(spec.get("grid_origin_fraction", 0.0)) * width
    selected_count = 0
    if len(corruptible) and time_fraction > 0 and time_mode != "none":
        candidates = corruptible[data.clean_event[corruptible] == 1]
        selected = rng.random(len(candidates)) < time_probability
        error_idx = candidates[selected]
        selected_count = len(error_idx)
        if time_mode == "heap_ceiling":
            observed_time[error_idx] = _heap_ceiling(
                observed_time[error_idx], width, origin
            )
        elif time_mode == "delay_fraction":
            observed_time[error_idx] *= 1.0 + time_fraction
        elif time_mode in {
            "scheduled_regular",
            "scheduled_irregular",
            "scheduled_informative",
        }:
            lower, upper = _scheduled_intervals(
                data,
                error_idx,
                time_mode,
                width,
                origin,
                float(spec.get("visit_gap_cv", 0.45)),
                rng,
            )
            observed_time[error_idx] = upper
            recorded_lower[error_idx] = lower
            recorded_upper[error_idx] = upper
            recorded_interval_available[error_idx] = True
        else:
            raise ValueError(f"unknown time_error_mode {time_mode!r}")
        time_errored[error_idx] = True

    # Exact event rows in a recorded-interval condition are supplied as
    # degenerate intervals. No simulated error flag is exposed to a method.
    if time_mode.startswith("scheduled_"):
        exact_event = corruptible_mask & (data.clean_event == 1) & ~time_errored
        recorded_lower[exact_event] = observed_time[exact_event]
        recorded_upper[exact_event] = observed_time[exact_event]
        recorded_interval_available[exact_event] = True

    # Keep recorded views aligned with any status flips even though Gate 3 does
    # not use status corruption in its frozen grid.
    now_censored = observed_event == 0
    recorded_lower[now_censored] = observed_time[now_censored]
    recorded_upper[now_censored] = np.nan
    recorded_interval_available[now_censored] = False
    new_events = (observed_event == 1) & ~np.isfinite(recorded_upper)
    recorded_lower[new_events] = observed_time[new_events]
    recorded_upper[new_events] = observed_time[new_events]

    if not np.array_equal(observed_time[splits.test], data.clean_time[splits.test]):
        raise AssertionError("test times were corrupted")
    if not np.array_equal(observed_event[splits.test], data.clean_event[splits.test]):
        raise AssertionError("test indicators were corrupted")

    event_mask = corruptible_mask & (data.clean_event == 1)
    censor_mask = corruptible_mask & (data.clean_event == 0)
    spans = recorded_upper - recorded_lower
    recorded = recorded_interval_available & np.isfinite(spans)
    metadata = {
        "scope": scope,
        "corruptible_count": len(corruptible),
        "requested_p10": p10_base,
        "requested_p01": p01_base,
        "mean_p10_event_rows": float(p10[event_mask].mean())
        if event_mask.any()
        else 0.0,
        "mean_p01_censor_rows": float(p01[censor_mask].mean())
        if censor_mask.any()
        else 0.0,
        "flipped_count": int(flipped.sum()),
        "time_error_count": int(time_errored.sum()),
        "time_error_mode": time_mode,
        "time_error_fraction": time_fraction,
        "time_error_probability": time_probability,
        "time_error_width": float(width),
        "grid_origin": float(origin),
        "recorded_interval_count": int(recorded.sum()),
        "recorded_interval_mean_span": float(spans[recorded].mean())
        if recorded.any()
        else 0.0,
        "recorded_interval_contains_latent_count": int(
            np.sum(
                recorded
                & (recorded_lower <= data.true_time + 1e-12)
                & (recorded_upper >= data.true_time - 1e-12)
            )
        ),
        "selected_time_error_count": int(selected_count),
    }
    return CorruptedLabels(
        observed_time=observed_time,
        observed_event=observed_event,
        p_event_to_censor=p10,
        p_censor_to_event=p01,
        flipped=flipped,
        time_errored=time_errored,
        recorded_lower=recorded_lower,
        recorded_upper=recorded_upper,
        recorded_interval_available=recorded_interval_available,
        scope=scope,
        metadata=metadata,
    )
