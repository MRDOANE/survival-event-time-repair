# Reproducibility guide

## What is frozen

The archived evidence consists of:

- final Gate 3 aggregate decision/report/configuration/provenance files;
- complete 500-replicate mastitis outputs;
- complete 500-replicate hemophilia/HIV outputs;
- source snapshots and tests for each completed study.

The completed Gate 3 run used the official DR-COSARC repository pinned at
commit `5b2cd20354e42105c980eabb4650240ae76dc866`. Registered upstream source hashes
are under `study/gate3_base/vendor_lock/` and
`study/gate3_hotfix/vendor_lock/`. Upstream source is fetched at run time and is
not redistributed because the pinned repository did not include a license.

## Exact historical Gate 3 replay

Gate 3 is retained as two snapshots because the inference-preserving execution
history matters:

1. `study/gate3_base/` (v0.6.0) generated 960 valid non-GBSG2 trials. All 240
   GBSG2 trials failed before producing metrics because a full dummy-coded
   design matrix was rank deficient.
2. `study/gate3_hotfix/` (v0.6.1) introduced reference-level coding only for
   GBSG2 and resumed exactly those 240 missing trials. Its resume checks reject
   missing non-GBSG2 records or any incompatible prior archive.

The hotfix did not change the estimand, data generation, censoring, recording
mechanisms, methods, learners, seeds, splits, sample sizes, targets, bootstrap
count, or gates. See `study/gate3_hotfix/HOTFIX.md`.

To reproduce the historical path on a new system, follow the base README and
launcher first, retain the resulting archive, then follow the hotfix README and
provide that archive to its resume launcher. A from-scratch run of only the
hotfix snapshot is intentionally not represented as the historical experiment.

## External analyses

The external subdirectories contain their frozen `icensBKL` data extracts,
provenance records, configurations, requirements, tests, and launchers. Follow:

- `study/external_mastitis/README.md`
- `study/external_hemophilia_hiv/README.md`

Their existing completed outputs are under `results/`. Re-running is optional
and is not needed to inspect or cite the archived results.

## Lightweight verification

From the repository root, run `bash verify_repository.sh`. This validates JSON
files, confirms expected completion markers and decisions, checks replicate
counts, runs the offline-safe tests, and verifies `MANIFEST.sha256` when
present. It does not launch the expensive study. One hotfix test that fetches
the live GBSG2 source through `lifelines` is excluded from this offline check;
the full hotfix launcher runs that public-data preflight and refuses fallback.

## Hardware expectations

Inspection and lightweight tests require roughly 2 CPU cores, 4 GB RAM, and
less than 1 GB free disk. Full Gate 3 reproduction is CPU-oriented and was
packaged for a multi-core Linux pod; a practical configuration is 24–32 vCPU,
64 GB RAM, and 30 GB free disk. The two external bootstrap studies are much
smaller and can run on 8–16 vCPU with 16–32 GB RAM. No GPU is required.

## Reproducibility boundary

No completed faithful-baseline comparison with the 2026 IPCW/AIPCW procedures
is included. Do not infer or report comparative superiority from an unfinished
package. Likewise, the external cohorts do not reveal latent event times, so
their coverage claims remain partially identified.
