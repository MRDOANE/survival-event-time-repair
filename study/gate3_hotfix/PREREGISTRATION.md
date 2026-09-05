# Gate 3 analysis lock

## Post-execution implementation amendment

The first execution produced no GBSG2 metrics because all 240 trials in that
data world encountered the same non-identifiable interval-model fit.  The
all-level dummy encoding plus intercept had 13 columns and rank 10.  Hotfix
`gate3-gbsg2-reference-coding-v1` replaces only that encoding with the
equivalent full-rank reference-level parameterization.  No scientific rule,
data-generating mechanism, seed, split, threshold, or completed trial is
changed.  The 960 completed trials remain immutable, and only the 240 trials
that previously emitted no metrics may be rerun.  Full details and hashes are
in `HOTFIX.md`.

Status: frozen before execution of the Gate 3 paper-scale expansion. Gate 2.7
is treated as branch-confirmation evidence. Gate 3 uses no Gate 2.5, 2.6, or
2.7 seed.

## Prior evidence

Gate 2.7 completed 120/120 fresh trials with zero execution, source, public
data, raw-result, manifest, or binding failures and returned
`ADVANCE_BOTH`. In the selected 20%-width known ceiling-grid condition:

- clean coverage: 0.905867;
- naive corrupted coverage: 0.853000;
- midpoint coverage and repair: 0.907733 and 0.054733;
- midpoint seed-clustered repair lower 95% bound: approximately 0.0513;
- conditional interval coverage and repair: 0.900067 and 0.047067;
- conditional interval seed-clustered repair lower 95% bound: approximately
  0.0431;
- midpoint and conditional interval positive trials: 24/24 each;
- positive trials across the three-condition ceiling family: 72/72 each.

These results fix the two Gate 3 branches and the anchor condition.

## Estimands and aggregation

For each dataset-regime-condition-seed trial:

`midpoint repair = midpoint adaptive coverage - naive adaptive coverage`

`interval repair = conditional interval adaptive coverage - naive adaptive coverage`

`matched naive loss = clean adaptive coverage - naive adaptive coverage`

Coverage is evaluated against latent event times in the untouched test split.
One dataset-regime-condition-seed trial is the base aggregation unit. Each
condition-regime cell weights its 30 trials equally.

Uncertainty bounds use a 10,000-replicate nonparametric bootstrap of the six
seed clusters. Each resampled cluster contains all five data worlds in a cell.
This treats reuse of a seed label across data worlds conservatively. The
reported lower bound is the 2.5th percentile of bootstrap means.

## Fixed methods and information boundary

For a recorded event interval `(L, U]`:

1. Midpoint correction uses `(L + U) / 2` for survival fitting, censoring
   fitting, and adaptive calibration.
2. Conditional interval correction fits a log-normal interval-censored
   survival model. Its fitted conditional median restricted to `(L, U]`
   supplies event-time proxies for censoring fitting and calibration.
3. The authors' pinned adaptive, doubly robust `predict_drcosarc`
   implementation is called without modification. Finite-sample correction is
   disabled.

Known-grid methods receive declared width and origin. The estimated-grid
condition estimates width and origin using observed event endpoints in the
held-out 10% protocol split; it receives no clean records or simulated error
flags. Visit-schedule methods receive each subject's recorded last-negative and
first-positive visit endpoints. Latent times, clean labels, corruption flags,
and test outcomes are unavailable to all corrections.

The stopped Gate 2.6 lower-calibration hybrid, lower edge, midpoint span
sensitivities, interval-midpoint calibration, wrong direction, uncalibrated
models, and zero bound are fixed diagnostics. They cannot replace a failed
branch.

## Frozen data worlds

1. Linear log-normal AFT synthetic data, correctly specified by the survival
   model family.
2. Nonlinear log-normal AFT synthetic data, with functional misspecification.
3. Nonlinear Weibull proportional-hazards synthetic data, with functional and
   distributional misspecification.
4. Public Rossi covariates with nonlinear log-logistic semi-synthetic outcomes.
5. Public GBSG2 covariates with nonlinear mixture-log-normal semi-synthetic
   outcomes.

Public-covariate fallback makes the complete result inconclusive.

## Frozen regimes

| Regime | N | Target coverage | Censoring | Censoring mechanism | Cell coverage tolerance |
|---|---:|---:|---:|---|---:|
| main | 2,500 | 0.90 | 0.35 | independent log-normal | 0.035 |
| high censoring | 3,000 | 0.90 | 0.55 | independent log-normal | 0.040 |
| target95 | 3,200 | 0.95 | 0.35 | independent log-normal | 0.035 |
| small sample | 1,400 | 0.90 | 0.35 | independent log-normal | 0.050 |
| dependent censoring | 3,000 | 0.90 | 0.45 | nonlinear covariate-dependent | 0.040 |

Clean-reference tolerances are 0.025, 0.030, 0.025, 0.040, and 0.030,
respectively.

## Frozen recording conditions

The seven primary conditions are:

1. 20%-scale known ceiling grid, zero origin, all events; anchor.
2. 20%-scale known ceiling grid applied to 60% of events.
3. 20%-scale known ceiling grid with origin at 0.37 grid widths.
4. The same shifted grid with width and origin estimated from the protocol
   split.
5. Regular subject-level visit brackets at 20% scale.
6. Irregular subject-level visit brackets with gap CV 0.45.
7. Outcome-informative visit brackets with gap CV 0.55.

A known 15% multiplicative event delay is secondary transport evidence and
cannot supply a missing primary success.

All corruptions affect training, protocol-estimation, and calibration records.
Test records remain clean. The full grid contains 1,200 trials.

## Cell success

A primary condition-regime cell first requires mean matched naive loss of at
least 0.012. Both branches then require coverage inside the regime-specific
window, positive repair in at least 65% of trials, repair success in at least
three of five datasets, and a lower prediction bound at least 80% of clean.

Midpoint additionally requires mean repair at least 0.008, a seed-clustered
repair lower bound above 0.0015, and target-coverage accuracy improvement over
naive of at least 0.003.

Conditional interval correction requires mean repair at least 0.007, a
seed-clustered lower bound above 0.001, and target-coverage accuracy improvement
of at least 0.0025.

Dataset success within a cell means mean repair of at least 0.005.

## Anchor prerequisite and branch rules

The main-regime known-grid anchor must have mean naive loss at least 0.025,
naive undercoverage relative to target at least 0.020, and a seed-clustered
naive-loss lower bound above 0.015.

Midpoint anchor advancement requires all of:

- repair at least 0.025 and seed-clustered lower bound above 0.015;
- coverage within 0.030 of target;
- positive repair in at least 80% of trials;
- dataset success in at least four data worlds;
- mean lower prediction bound at least 88% of clean;
- coverage-accuracy gain over the stopped hybrid at least 0.015;
- recovery of 65% through 140% of the matched naive loss.

Conditional interval anchor advancement independently requires:

- repair at least 0.022 and seed-clustered lower bound above 0.012;
- coverage within 0.030 of target;
- positive repair in at least 80% of trials;
- dataset success in at least four data worlds;
- mean lower prediction bound at least 88% of clean;
- coverage-accuracy gain over the stopped hybrid at least 0.012.

## Expansion core

Each advancing branch must pass every expansion-core check:

1. at least 23 of 35 primary condition-regime cells succeed;
2. at least five of seven primary conditions succeed in the main regime;
3. at least four regimes each contain four successful conditions;
4. at least six conditions each succeed in three regimes;
5. at least four data worlds have pooled repair at least 0.005, positive repair
   in at least 60% of trials, and positive mean accuracy gain;
6. the seed-clustered lower bound for pooled primary-condition repair exceeds
   0.004;
7. no more than 10% of primary cells have absolute coverage error above 0.065.

## Expansion support

Midpoint requires at least five of eight support checks. Conditional interval
correction requires at least five of nine:

1. the estimated-grid condition succeeds in at least three regimes;
2. at least nine of fifteen visit-schedule cells succeed;
3. pooled positive-repair fraction is at least 0.68;
4. at least 68% of primary cells improve target-coverage accuracy over naive;
5. pooled mean lower-bound ratio to clean is at least 0.82;
6. both 0.75x and 1.25x span variants remain within 0.050 of target in the
   anchor;
7. corrected anchor coverage exceeds wrong-direction coverage by at least
   0.025;
8. anchor zero-bound fraction is at most 0.10.

The interval branch has a ninth support check: across recorded-visit cells its
mean absolute coverage error may exceed midpoint by no more than 0.010, and its
mean lower prediction bound must be at least 95% of midpoint.

## Decisions

- `ADVANCE_BOTH`: both independent branches pass.
- `ADVANCE_MIDPOINT`: only midpoint passes.
- `ADVANCE_INTERVAL_AWARE`: only conditional interval correction passes.
- `HOLD`: an anchor effect remains but breadth or support misses the frozen
  rule.
- `STOP`: neither branch retains the required anchor and expansion evidence.
- `INCONCLUSIVE`: execution, source, data, completeness, binding, fallback,
  or clean-reference checks prevent inference.
- `SMOKE_ONLY`: software and interface verification only.

## Integrity lock

A scientific decision requires the exact hash-derived trial grid, zero
execution errors, no required-public fallback, the pinned upstream commit and
source hashes, hash-valid raw R outputs and prepared-input manifests,
raw-to-input fingerprint agreement, clean-reference calibration in every
regime, and exact clean repeatability within dataset-regime-seed cohorts.

The scientific hash binds Python and R scientific source, regimes, datasets,
recording conditions, correction specifications, gate thresholds, run kind,
and bootstrap count. Worker count is operational and does not alter the hash.
