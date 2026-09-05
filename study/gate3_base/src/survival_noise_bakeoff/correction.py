from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .data import SplitIndices
from .noise import CorruptedLabels


@dataclass(frozen=True)
class IntervalView:
    """Observed-data view for exact, grid, delayed, or visit-bracket records."""

    lower: np.ndarray
    upper: np.ndarray
    lower_proxy: np.ndarray
    midpoint_proxy: np.ndarray
    wrong_direction_proxy: np.ndarray
    detected: np.ndarray
    metadata: dict[str, Any]


def estimate_ceiling_grid_protocol(
    observed_time: np.ndarray,
    observed_event: np.ndarray,
    estimation_indices: np.ndarray,
) -> dict[str, Any]:
    mask = np.zeros(len(observed_time), dtype=bool)
    mask[np.asarray(estimation_indices, dtype=int)] = True
    values = np.sort(
        np.unique(np.asarray(observed_time, dtype=float)[mask & (observed_event == 1)])
    )
    if len(values) < 4:
        raise ValueError("at least four unique estimation events are required")
    differences = np.diff(values)
    tolerance = max(float(np.median(values)) * 1e-10, 1e-10)
    differences = differences[differences > tolerance]
    if len(differences) < 2:
        raise ValueError("could not identify positive visit-grid differences")
    width = float(np.min(differences))
    angles = 2.0 * np.pi * np.mod(values, width) / width
    mean_angle = np.angle(np.mean(np.exp(1j * angles)))
    origin = float(np.mod(mean_angle, 2.0 * np.pi) * width / (2.0 * np.pi))
    scaled = (values - origin) / width
    alignment_error = float(np.max(np.abs(scaled - np.rint(scaled))))
    if not np.isfinite(width) or width <= 0 or alignment_error > 1e-5:
        raise ValueError(
            f"estimated grid failed alignment: width={width}, error={alignment_error}"
        )
    return {
        "mode": "ceiling_grid",
        "source": "estimated_from_protocol_split",
        "grid_origin": origin,
        "interval_width": width,
        "alignment_relative_tolerance": 1e-5,
        "estimation_event_count": int(np.sum(mask & (observed_event == 1))),
        "estimation_unique_endpoint_count": int(len(values)),
        "estimation_max_alignment_error": alignment_error,
    }


def recording_protocol(
    scenario: dict[str, Any],
    corrupted: CorruptedLabels,
    splits: SplitIndices,
) -> dict[str, Any]:
    mode = str(scenario.get("correction_interval_mode", ""))
    source = str(scenario.get("protocol_source", "known"))
    if mode == "ceiling_grid":
        if source == "estimated":
            return estimate_ceiling_grid_protocol(
                corrupted.observed_time,
                corrupted.observed_event,
                splits.noise_estimation,
            )
        width = float(corrupted.metadata.get("time_error_width", 0.0))
        if not np.isfinite(width) or width <= 0:
            raise ValueError(
                "ceiling-grid correction requires a positive protocol width"
            )
        return {
            "mode": mode,
            "source": "declared_recording_protocol",
            "grid_origin": float(corrupted.metadata.get("grid_origin", 0.0)),
            "interval_width": width,
            "alignment_relative_tolerance": float(
                scenario.get("alignment_relative_tolerance", 1e-7)
            ),
        }
    if mode == "multiplicative_delay":
        fraction = float(scenario.get("time_error_fraction", 0.0))
        if not 0 < fraction < 1:
            raise ValueError(
                "multiplicative-delay correction requires a fraction in (0, 1)"
            )
        return {
            "mode": mode,
            "source": "declared_recording_protocol",
            "delay_fraction": fraction,
        }
    if mode == "recorded_interval":
        return {
            "mode": mode,
            "source": "subject_level_visit_brackets",
            "interval_source": str(scenario.get("time_error_mode", "")),
        }
    raise ValueError(f"unsupported correction_interval_mode {mode!r}")


def build_interval_view(
    observed_time: np.ndarray,
    observed_event: np.ndarray,
    protocol: dict[str, Any],
    *,
    recorded_lower: np.ndarray | None = None,
    recorded_upper: np.ndarray | None = None,
    span_multiplier: float = 1.0,
    lower_floor: float = 1e-6,
    wrong_direction_multiplier: float = 0.5,
) -> IntervalView:
    """Build interval and fixed comparator views from observed records only."""

    time = np.asarray(observed_time, dtype=float)
    event = np.asarray(observed_event, dtype=np.int8)
    if time.ndim != 1 or event.shape != time.shape:
        raise ValueError("observed time and event arrays must be aligned vectors")
    if not np.all(np.isfinite(time)) or np.any(time <= 0):
        raise ValueError("observed event-time records must be positive and finite")
    if set(np.unique(event)) - {0, 1}:
        raise ValueError("observed event indicators must be binary")
    if not np.isfinite(span_multiplier) or span_multiplier <= 0:
        raise ValueError("span_multiplier must be positive and finite")

    event_mask = event == 1
    mode = str(protocol["mode"])
    if mode == "ceiling_grid":
        width = float(protocol["interval_width"])
        origin = float(protocol.get("grid_origin", 0.0))
        tolerance = float(protocol.get("alignment_relative_tolerance", 1e-7))
        scaled = (time - origin) / width
        detected = event_mask & (
            np.abs(scaled - np.rint(scaled))
            <= tolerance * np.maximum(1.0, np.abs(scaled))
        )
        minimum_endpoint = width if abs(origin) <= tolerance * width else origin
        detected &= time >= minimum_endpoint - tolerance * width
        span = np.full(len(time), width * span_multiplier, dtype=float)
        wrong_shift = np.full(
            len(time), width * wrong_direction_multiplier, dtype=float
        )
        protocol_value: float | str = width
    elif mode == "multiplicative_delay":
        fraction = float(protocol["delay_fraction"])
        detected = event_mask.copy()
        assumed_fraction = fraction * span_multiplier
        span = time - time / (1.0 + assumed_fraction)
        wrong_shift = time * fraction * wrong_direction_multiplier
        protocol_value = fraction
    elif mode == "recorded_interval":
        if recorded_lower is None or recorded_upper is None:
            raise ValueError("recorded-interval protocol requires row-level endpoints")
        supplied_lower = np.asarray(recorded_lower, dtype=float)
        supplied_upper = np.asarray(recorded_upper, dtype=float)
        if supplied_lower.shape != time.shape or supplied_upper.shape != time.shape:
            raise ValueError("recorded interval endpoints are misaligned")
        if np.any(~np.isfinite(supplied_lower)) or np.any(supplied_lower <= 0):
            raise ValueError("recorded lower endpoints must be positive and finite")
        if np.any(~np.isfinite(supplied_upper[event_mask])):
            raise ValueError("event records require finite recorded upper endpoints")
        if np.any(supplied_lower[event_mask] > supplied_upper[event_mask] + 1e-12):
            raise ValueError("recorded event interval is reversed")
        detected = event_mask.copy()
        raw_span = np.zeros(len(time), dtype=float)
        raw_span[event_mask] = supplied_upper[event_mask] - supplied_lower[event_mask]
        span = raw_span * span_multiplier
        wrong_shift = raw_span * wrong_direction_multiplier
        protocol_value = "row_specific"
    else:
        raise ValueError(f"unsupported interval protocol mode {mode!r}")

    lower = time.copy()
    lower[detected] = np.minimum(
        time[detected],
        np.maximum(time[detected] - span[detected], lower_floor),
    )
    upper = time.copy()
    upper[~event_mask] = np.nan
    lower_proxy = lower.copy()
    midpoint_proxy = time.copy()
    midpoint_proxy[detected] = 0.5 * (lower[detected] + time[detected])
    wrong_direction_proxy = time.copy()
    wrong_direction_proxy[detected] = time[detected] + wrong_shift[detected]

    if np.any(lower <= 0) or np.any(~np.isfinite(lower)):
        raise AssertionError("correction produced invalid lower endpoints")
    if np.any(lower[event_mask] > upper[event_mask] + 1e-12):
        raise AssertionError("event interval lower endpoint exceeds its upper endpoint")
    if np.any(np.isfinite(upper[~event_mask])):
        raise AssertionError("censored records must have open upper endpoints")
    if np.any(lower_proxy > time + 1e-12):
        raise AssertionError("lower proxy moved an observed time upward")
    if np.any(midpoint_proxy < lower - 1e-12) or np.any(midpoint_proxy > time + 1e-12):
        raise AssertionError("midpoint proxy lies outside its recording interval")

    detected_count = int(detected.sum())
    nondegenerate = detected & ((time - lower) > 1e-12)
    metadata = {
        "mode": mode,
        "protocol_source": protocol.get("source"),
        "protocol_value": protocol_value,
        "span_multiplier": float(span_multiplier),
        "event_count": int(event_mask.sum()),
        "detected_interval_count": detected_count,
        "nondegenerate_interval_count": int(nondegenerate.sum()),
        "detected_event_fraction": (
            float(detected_count / event_mask.sum()) if event_mask.any() else 0.0
        ),
        "mean_interval_span_detected": (
            float(np.mean(time[detected] - lower[detected])) if detected_count else 0.0
        ),
        "min_interval_lower": float(lower.min()),
        "wrong_direction_multiplier": float(wrong_direction_multiplier),
    }
    return IntervalView(
        lower=lower,
        upper=upper,
        lower_proxy=lower_proxy,
        midpoint_proxy=midpoint_proxy,
        wrong_direction_proxy=wrong_direction_proxy,
        detected=detected,
        metadata=metadata,
    )
