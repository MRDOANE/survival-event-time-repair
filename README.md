# Repairing conformal survival lower prediction bounds under event-time coarsening

Reproducibility repository for a planned submission to *Statistics in Medicine*.

The study asks what happens when a conformal survival procedure designed for
ordinary right-censored event times is trained and calibrated using recorded
event times that have been rounded, grouped, or observed only between visits.
It evaluates two simple **observed-data interface repairs**—a midpoint proxy and
a conditional interval-model proxy—without altering the published DR-COSARC
implementation.

## Headline result

The frozen Gate 3 simulation and semi-synthetic expansion completed all 1,200
planned trials and returned `ADVANCE_BOTH`.

| Quantity | Naive upper endpoint | Midpoint repair | Conditional interval repair |
|---|---:|---:|---:|
| Anchor latent-time coverage | 0.8554 | 0.9070 | 0.8996 |
| Anchor repair vs naive | — | 0.0516 | 0.0442 |
| Pooled repair vs naive | — | 0.0373 | 0.0319 |
| Lower 95% seed-clustered bound for pooled repair | — | 0.0357 | 0.0303 |
| Pooled successful expansion cells | — | 27/35 | 32/35 |
| Clean-regime geometric LPB ratio | 1.000 | 0.990 | 1.027 |

Two interval-censored cohort analyses were prespecified and completed with 500
bootstrap replicates each. Both were formally `NEUTRAL`, although mean changes
in held-out interval log score, certain-miss rate, and target compatibility were
generally directionally favorable. Exact latent event times are unavailable in
these cohorts, so they cannot validate latent-time coverage.

## Claim boundary

This repository does **not** claim:

- the first conformal method for interval-censored survival data;
- a new validity theorem under event-time recording error;
- that midpoint or conditional-median imputation is itself novel;
- that the repairs are part of published DR-COSARC;
- a completed comparison with recent IPCW/AIPCW conformal baselines.

The defensible contribution is an empirical diagnosis and repair study for
lower prediction bounds targeting latent event time when training and
calibration event records are coarsened. See [NOVELTY_AUDIT.md](NOVELTY_AUDIT.md)
for the literature comparison and recommended claim language.

## Repository map

| Path | Contents |
|---|---|
| `study/gate3_base/` | Frozen v0.6.0 source used for the original 960 completed trials |
| `study/gate3_hotfix/` | Narrow v0.6.1 GBSG2 reference-coding resume hotfix |
| `study/external_mastitis/` | Mastitis cohort source, frozen data, tests, and provenance |
| `study/external_hemophilia_hiv/` | Hemophilia/HIV cohort source, frozen data, tests, and provenance |
| `results/gate3/` | Final decision, report, resolved configuration, and manifest |
| `results/mastitis/full/` | Complete 500-replicate mastitis output |
| `results/hemophilia_hiv/full/` | Complete 500-replicate hemophilia/HIV output |
| `RESULTS.md` | Reader-oriented result summary and interpretation |
| `REPRODUCIBILITY.md` | Exact historical replay and verification instructions |
| `RELEASE_GUIDE_UI.md` | GitHub Desktop and Zenodo web-interface instructions |

## Reproduction in brief

Gate 3 was completed historically in two locked stages: the base run produced
960 valid trials and a coding defect stopped all 240 GBSG2 trials; the hotfix
changed only GBSG2 reference coding and resumed that exact missing block. The
two source snapshots are retained separately so this history is auditable.

Each sub-study is self-contained. Read its own README before running. The
Gate 3 launcher downloads the authors' official DR-COSARC repository at commit
`5b2cd20354e42105c980eabb4650240ae76dc866` and verifies registered file hashes;
the upstream code is not redistributed here because the pinned repository did
not contain a license file.

No additional cloud computation is needed to inspect or cite the completed
results in this release.

## Citation and release

Add your ORCID to `CITATION.cff` and `.zenodo.json` if applicable, then follow
[RELEASE_GUIDE_UI.md](RELEASE_GUIDE_UI.md). Cite both the archived
software DOI and the eventual article.

## License

This aggregate release is distributed under GPL-3.0-or-later because it includes
the external-analysis components and their bundled `icensBKL` data. Gate 3 code
retains its MIT license. See [LICENSES.md](LICENSES.md) and the component license
files. No license is asserted over the separately downloaded upstream
DR-COSARC source.
