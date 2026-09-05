# Mastitis external interval-censoring study

This is an optional, frozen external-cohort extension to the Survival
DR-COSARC Gate 3 study. It has not been executed on the cohort. Inspect
`config/study.json`, `data/PROVENANCE.md`, and `src/external_interval.py`
before deciding whether to run it.

## What is tested

The cohort contains 400 udder quarters nested within exactly 100 dairy cows.
There are 317 finite infection intervals, including 26 left-censored
infections, and 83 right-censored observations. The analysis compares:

1. `naive_upper`: treat the recorded upper endpoint as the event time.
2. `midpoint`: use the midpoint of each finite infection interval.
3. `interval_aware`: fit left-, interval-, and right-censored observations
   directly and use conditional medians for conformal calibration.

Cow is the indivisible unit for resampling and train/calibration/test splitting.
All four quarters from a cow remain together. This prevents cow leakage and
pseudoreplication in the uncertainty analysis. The primary predictive endpoint
is held-out natural interval negative log likelihood. Coverage is reported as
an identified range because exact infection times are unobserved.

The frozen output classification is `SUPPORTIVE_*`, `NEUTRAL`, or
`CONTRARY_OR_MIXED`. Support requires a positive lower 95% bootstrap bound for
the proper-score improvement and all guardrails in `config/study.json`.

## Run

Upload this directory's ZIP and its companion launcher to `/workspace`, then:

```bash
bash /workspace/run_mastitis_external.sh
```

Defaults: 500 paired cow-cluster bootstrap replicates, eight CPU workers,
resume enabled. No GPU is used. The final archive is written to:

```text
/workspace/survival_mastitis_external_results.zip
```

Useful overrides:

```bash
JOBS=4 REPLICATES=500 bash /workspace/run_mastitis_external.sh
```

An eight-replicate engineering smoke run is available, but its scientific
decision is not valid:

```bash
MODE=smoke bash /workspace/run_mastitis_external.sh
```

## Interpretation boundary

The external cohort can test whether interval-aware handling improves proper
out-of-cow prediction under a natural visit schedule. It cannot reveal exact
infection times and therefore cannot reproduce the clean-time coverage
analysis from Gate 3. Run results should be described as external directional
evidence, with neutral or contrary outcomes retained if this extension is
represented as a completed study.

License: GPL-3.0. Dataset provenance and original package documentation are in
`data/`.
