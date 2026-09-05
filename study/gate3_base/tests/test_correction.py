from __future__ import annotations

import numpy as np
import pytest

from survival_noise_bakeoff.correction import (
    build_interval_view,
    recording_protocol,
)
from survival_noise_bakeoff.data import load_dataset, make_splits
from survival_noise_bakeoff.noise import corrupt_labels


def synthetic(n: int = 1200):
    return load_dataset(
        {
            "name": "synthetic_test_lognormal",
            "n": n,
            "p": 8,
            "mechanism": "linear",
            "outcome_distribution": "lognormal",
            "target_censoring": 0.35,
            "censoring_mechanism": "independent_lognormal",
        },
        503,
    )


def test_ceiling_grid_detection_uses_observed_alignment() -> None:
    protocol = {
        "mode": "ceiling_grid",
        "source": "declared_recording_protocol",
        "interval_width": 1.0,
        "grid_origin": 0.0,
        "alignment_relative_tolerance": 1e-7,
    }
    time = np.array([1.0, 2.0, 2.3, 4.0])
    event = np.array([1, 1, 1, 0])
    view = build_interval_view(time, event, protocol)
    assert view.detected.tolist() == [True, True, False, False]
    assert np.allclose(view.lower, [1e-6, 1.0, 2.3, 4.0])
    assert np.allclose(view.midpoint_proxy, [0.5000005, 1.5, 2.3, 4.0])
    assert np.all(view.wrong_direction_proxy[:2] > time[:2])
    assert np.isnan(view.upper[3])


def test_span_sensitivity_holds_detection_fixed() -> None:
    protocol = {
        "mode": "ceiling_grid",
        "source": "declared_recording_protocol",
        "interval_width": 2.0,
        "grid_origin": 0.0,
    }
    time = np.array([4.0, 5.3, 8.0])
    event = np.array([1, 1, 1])
    primary = build_interval_view(time, event, protocol)
    under = build_interval_view(time, event, protocol, span_multiplier=0.75)
    over = build_interval_view(time, event, protocol, span_multiplier=1.25)
    assert np.array_equal(primary.detected, under.detected)
    assert np.array_equal(primary.detected, over.detected)
    assert np.all(under.lower[primary.detected] > primary.lower[primary.detected])
    assert np.all(over.lower[primary.detected] < primary.lower[primary.detected])


def test_multiplicative_delay_recovers_declared_lower_edge() -> None:
    true = np.array([3.0, 7.0, 4.0])
    event = np.array([1, 1, 0])
    observed = true.copy()
    observed[event == 1] *= 1.15
    view = build_interval_view(
        observed,
        event,
        {
            "mode": "multiplicative_delay",
            "source": "declared_recording_protocol",
            "delay_fraction": 0.15,
        },
    )
    assert np.allclose(view.lower[event == 1], true[event == 1])
    assert np.isnan(view.upper[event == 0]).all()


def test_partial_shifted_ceiling_detects_only_observed_grid_rows() -> None:
    spec = {
        "name": "partial",
        "scope": "train_cal",
        "time_error_mode": "heap_ceiling",
        "time_error_fraction": 0.20,
        "time_error_probability": 0.60,
        "correction_interval_mode": "ceiling_grid",
        "grid_origin_fraction": 0.37,
        "protocol_source": "known",
    }
    data = synthetic()
    splits = make_splits(1200, [0.40, 0.10, 0.25, 0.25], 503)
    corrupted = corrupt_labels(data, splits, spec, 503)
    idx = np.concatenate([splits.train, splits.calibration])
    protocol = recording_protocol(spec, corrupted, splits)
    view = build_interval_view(
        corrupted.observed_time[idx], corrupted.observed_event[idx], protocol
    )
    assert np.array_equal(view.detected, corrupted.time_errored[idx])
    errored = view.detected
    assert np.all(view.lower[errored] <= data.true_time[idx][errored])
    assert np.all(data.true_time[idx][errored] <= view.upper[errored])


def test_grid_width_and_origin_are_estimated_without_error_flags() -> None:
    spec = {
        "name": "estimated",
        "scope": "train_cal",
        "time_error_mode": "heap_ceiling",
        "time_error_fraction": 0.20,
        "time_error_probability": 1.0,
        "correction_interval_mode": "ceiling_grid",
        "grid_origin_fraction": 0.37,
        "protocol_source": "estimated",
    }
    data = synthetic()
    splits = make_splits(1200, [0.40, 0.10, 0.25, 0.25], 503)
    corrupted = corrupt_labels(data, splits, spec, 503)
    protocol = recording_protocol(spec, corrupted, splits)
    true_width = corrupted.metadata["time_error_width"]
    true_origin = corrupted.metadata["grid_origin"]
    assert protocol["source"] == "estimated_from_protocol_split"
    assert abs(protocol["interval_width"] / true_width - 1) < 1e-6
    delta = abs(protocol["grid_origin"] - true_origin)
    assert min(delta, abs(delta - true_width)) / true_width < 1e-6


def test_recorded_irregular_intervals_contain_latent_events() -> None:
    spec = {
        "name": "visits",
        "scope": "train_cal",
        "time_error_mode": "scheduled_irregular",
        "time_error_fraction": 0.20,
        "time_error_probability": 1.0,
        "visit_gap_cv": 0.45,
        "correction_interval_mode": "recorded_interval",
    }
    data = synthetic()
    splits = make_splits(1200, [0.40, 0.10, 0.25, 0.25], 503)
    corrupted = corrupt_labels(data, splits, spec, 503)
    idx = np.concatenate([splits.train, splits.calibration])
    protocol = recording_protocol(spec, corrupted, splits)
    view = build_interval_view(
        corrupted.observed_time[idx],
        corrupted.observed_event[idx],
        protocol,
        recorded_lower=corrupted.recorded_lower[idx],
        recorded_upper=corrupted.recorded_upper[idx],
    )
    affected = corrupted.time_errored[idx]
    assert affected.any()
    assert np.all(view.lower[affected] <= data.true_time[idx][affected])
    assert np.all(data.true_time[idx][affected] <= view.upper[affected])


def test_invalid_records_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        build_interval_view(
            np.array([0.0]),
            np.array([1]),
            {"mode": "multiplicative_delay", "delay_fraction": 0.1},
        )
    with pytest.raises(ValueError, match="row-level endpoints"):
        build_interval_view(
            np.array([2.0]),
            np.array([1]),
            {"mode": "recorded_interval"},
        )
