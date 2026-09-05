# Survival DR-COSARC Gate 3 expansion

Gate 3 is the paper-scale stress expansion of two observed-data corrections for
one-sided event-time recording error around the authors' adaptive DR-COSARC
implementation.

Gate 2.7 advanced both branches on fresh seeds. In its selected 20%-width
ceiling-grid condition, clean coverage was 0.9059 and naive corrupted coverage
was 0.8530. Midpoint correction reached 0.9077 coverage with 0.0547 repair.
Conditional interval-aware correction reached 0.9001 with 0.0471 repair and a
mean lower prediction bound 1.028 times the clean reference. Every selected
trial and all 72 ceiling-family trials had positive repair.

Gate 3 retains that condition as a frozen anchor and tests whether the result
survives substantially broader observation and modeling conditions.

## Fixed branches

The midpoint primary replaces a recorded event interval `(L, U]` with
`(L + U) / 2` for survival fitting, censoring fitting, and calibration.

The interval-aware branch fits a log-normal interval-censored survival model,
then uses the fitted conditional median within each training and calibration
interval as the censoring and calibration proxy. Both branches call the pinned
authors' adaptive, doubly robust `predict_drcosarc` function without editing
its source.

## Expansion grid

- Five outcome worlds: correctly specified log-normal linear AFT, nonlinear
  log-normal, nonlinear Weibull proportional hazards, Rossi-covariate
  log-logistic, and GBSG2-covariate mixture log-normal.
- Five regimes: main, 55% censoring, 95% target coverage, small sample, and
  nonlinear covariate-dependent censoring.
- Eight recording conditions: known ceiling grid, partial heaping, shifted
  origin, estimated grid metadata, regular visit intervals, irregular visit
  intervals, outcome-informative visit intervals, and multiplicative delay.
- Six new seeds: 2377, 2503, 2621, 2749, 2879, and 3001.
- Total: 5 datasets x 5 regimes x 8 conditions x 6 seeds = 1,200 trials.

The 10% protocol-estimation partition is used only by the estimated-grid
condition. Training, protocol-estimation, calibration, and test partitions are
disjoint. Test records are never corrupted.

## Decision structure

Midpoint and interval-aware branches retain independent advancement rules.
Each must reproduce the strong anchor result and satisfy the same paper-scale
breadth structure across condition-regime cells, regimes, conditions, data
worlds, seed-clustered uncertainty, calibration safety, and informativeness.
Protocol estimation and subject-level visit intervals are registered support
checks. A branch cannot substitute for the other after results are observed.

See `PREREGISTRATION.md` for the frozen rules and `METHOD_SCOPE.md` for the
permitted scientific claims.

## Run on RunPod

Use a root-capable Ubuntu or Debian CPU pod with at least 16 modern vCPUs,
32 GB RAM, and 40 GB free disk. A GPU is not used.

```bash
cd /workspace
unzip survival-drcosarc-gate3-v1.0.zip
cd survival_drcosarc_gate3
bash run_gate3.sh smoke
N_JOBS=12 bash run_gate3.sh full
bash scripts/package_results.sh
```

The launcher installs R and Python dependencies, retrieves the authors' source
at commit `5b2cd20354e42105c980eabb4650240ae76dc866`, verifies its registered
hashes, runs Python and R preflights, and resumes only hash-compatible trials.
The expected full-study wall time is approximately 14 to 24 hours with 12
workers. Using `N_JOBS=16` on a 24-vCPU machine should take approximately
10 to 18 hours. BLAS threads remain fixed at one per worker.

The default result archive is
`/workspace/survival_drcosarc_gate3_results.zip`.
