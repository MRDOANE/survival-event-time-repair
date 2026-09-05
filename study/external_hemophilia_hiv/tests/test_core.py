import numpy as np

from external_interval import (
    conditional_median,
    fit_aft,
    grouped_split,
    interval_coverage_metrics,
    natural_interval_loglik,
)


def test_conditional_medians_respect_intervals():
    mu = np.log(np.array([3.0, 4.0, 5.0]))
    lower = np.array([1.0, 2.0, 6.0])
    upper = np.array([4.0, np.inf, 9.0])
    answer = conditional_median(mu, 0.7, lower, upper)
    assert np.all(answer >= lower)
    assert answer[0] <= 4.0
    assert answer[2] <= 9.0


def test_partial_identification_is_exact_for_resolved_cases():
    bound = np.array([1.0, 5.0, 8.0, 3.0])
    lower = np.array([2.0, 3.0, 4.0, 1.0])
    upper = np.array([4.0, 6.0, 7.0, np.inf])
    result = interval_coverage_metrics(bound, lower, upper, 0.9)
    assert result["coverage_identified_lower"] == 0.25
    assert result["certain_miss_fraction"] == 0.25
    assert result["coverage_identified_upper"] == 0.75
    assert result["ambiguous_fraction"] == 0.5


def test_group_split_keeps_clusters_intact():
    cluster = np.repeat(np.arange(30).astype(str), 4)
    stratum = np.repeat(np.tile(np.array(["a", "b", "c"]), 10), 4)
    masks = grouped_split(cluster, stratum, np.random.default_rng(7), (0.6, 0.2, 0.2))
    sets = [set(cluster[m]) for m in masks]
    assert sets[0].isdisjoint(sets[1])
    assert sets[0].isdisjoint(sets[2])
    assert sets[1].isdisjoint(sets[2])
    assert sum(int(m.sum()) for m in masks) == len(cluster)


def test_interval_aft_smoke_is_finite():
    rng = np.random.default_rng(19)
    x = rng.normal(size=(80, 1))
    design = np.column_stack([np.ones(80), x])
    truth = np.exp(1.2 + 0.3 * x[:, 0] + rng.normal(0, 0.35, size=80))
    lower = np.floor(truth)
    upper = np.ceil(truth) + 0.25
    upper[::7] = np.inf
    fit = fit_aft(design, lower, upper, mode="interval", maxiter=400)
    assert fit.success
    ll = natural_interval_loglik(fit.beta, fit.sigma, design, lower, upper)
    assert np.isfinite(ll).all()
