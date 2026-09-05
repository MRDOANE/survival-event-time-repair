# Repository audit

Audit date: 2026-09-05

## Included evidence

| Evidence block | Completeness | Status | Files included |
|---|---:|---|---|
| Frozen Gate 3 | 1,200/1,200 trials; 0 errors | `ADVANCE_BOTH` | Final report, machine-readable gate decision, resolved configuration, and run manifest |
| Mastitis external analysis | 500/500 bootstrap replicates | `NEUTRAL` | Replicate-level JSON, summaries, figures, configuration, report, and decision |
| Hemophilia/HIV external analysis | 500/500 bootstrap replicates | `NEUTRAL` | Replicate-level JSON, summaries, figures, configuration, report, and decision |

Gate 3 trial-level JSON files are not duplicated in this public release; its
locked aggregate report, decision object, resolved configuration, and detailed
provenance manifest are included. The source and exact historical two-stage
replay instructions are included. The external analyses include all
replicate-level results.

## Deliberate exclusions

- The unfinished faithful DR-COSARC/IPCW/AIPCW comparison and its installation
  log. It did not generate admissible scientific results.
- Raw RunPod environment logs and temporary repair files.
- The official DR-COSARC source tree. The pinned upstream repository had no
  license file, so Gate 3 downloads and hash-verifies it rather than
  redistributing it.
- Any analysis applying ordinary right-censoring DR-COSARC or AIPCW directly to
  the raw interval-censored external cohorts.

## Verification record

The release was checked in a clean repository layout using
`bash verify_repository.sh`:

- 1,015 JSON files parsed successfully;
- final gate decisions and external completion markers matched expectations;
- exactly 500 replicate records were present for each external cohort;
- Gate 3 base: 18 tests passed;
- Gate 3 hotfix: 21 offline-safe tests passed, 1 live-data test deselected;
- mastitis: 5 tests passed;
- hemophilia/HIV: 5 tests passed.

The deselected hotfix test calls the live `lifelines` GBSG2 loader. The full
launcher performs this public-data preflight and prohibits fallback. The final
run manifest records that required-public fallback was false.

## Terminology audit

- **Published DR-COSARC** means the unmodified upstream method of Sesia and
  Svetnik at the pinned commit.
- **Midpoint repair** and **conditional interval repair** are the two
  observed-data interfaces introduced and evaluated here.
- Neither repair is labeled as DR-COSARC itself.
- No earlier surrogate is represented as the published method.

## Release status

The package is ready for a public GitHub/Zenodo software release after the
author confirms creator metadata and adds an ORCID if desired.

