# Hemophilia/HIV external interval-censoring study

This is an optional, frozen external-cohort extension to the Survival
DR-COSARC Gate 3 study. It has not been executed on the cohort. Inspect
`config/study.json`, `data/PROVENANCE.md`, and `src/external_interval.py`
before deciding whether to run it.

## What is tested

The cohort contains 368 hemophilia patients followed for HIV-1 infection.
There are 103 finite infection intervals and 265 right-censored observations.
The analysis compares three prespecified observation contracts:

1. `naive_upper`: treat the recorded upper endpoint as the event time.
2. `midpoint`: use the midpoint of each finite infection interval.
3. `interval_aware`: fit the event interval directly and use a conditional
   median within the interval for conformal calibration.

Every bootstrap replicate resamples patients, then creates common
train/calibration/test partitions for all methods. The primary predictive
endpoint is held-out natural interval negative log likelihood. Lower-bound
coverage is only partially identifiable without exact infection times, so the
report separates certainly covered, certainly missed, and ambiguous cases.

The frozen output classification is `SUPPORTIVE_*`, `NEUTRAL`, or
`CONTRARY_OR_MIXED`. Support requires a positive lower 95% bootstrap bound for
the proper-score improvement and all guardrails in `config/study.json`.

## Run

Upload this directory's ZIP and its companion launcher to `/workspace`, then:

```bash
bash /workspace/run_hemophilia_hiv_external.sh
```

Defaults: 500 paired bootstrap replicates, eight CPU workers, resume enabled.
No GPU is used. The final archive is written to:

```text
/workspace/survival_hemophilia_hiv_external_results.zip
```

Useful overrides:

```bash
JOBS=4 REPLICATES=500 bash /workspace/run_hemophilia_hiv_external.sh
```

An eight-replicate engineering smoke run is available, but its scientific
decision is not valid:

```bash
MODE=smoke bash /workspace/run_hemophilia_hiv_external.sh
```

## Interpretation boundary

The external cohort can test whether interval-aware handling improves proper
out-of-sample prediction under a natural observation process. It cannot reveal
the exact latent infection times and therefore cannot reproduce the clean-time
coverage analysis from Gate 3. Run results should be described as external
directional evidence, with neutral or contrary outcomes retained if this
extension is represented as a completed study.

License: GPL-3.0. Dataset provenance and original package documentation are in
`data/`.
