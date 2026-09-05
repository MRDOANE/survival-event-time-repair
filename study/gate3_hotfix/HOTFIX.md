# Gate 3 GBSG2 resume hotfix

Hotfix ID: `gate3-gbsg2-reference-coding-v1`

This package repairs the single execution defect found in the first Gate 3
run.  The archived run completed 960 of 1,200 trials.  All 240 trials in the
GBSG2 semi-synthetic mixture world stopped before producing metrics with
`conditional interval imputation returned invalid event times`.  The other
four data worlds completed, and both scientific branches passed every
evaluable core and support rule.

## Root cause

The GBSG2 loader originally retained every level of each categorical variable.
With the survival-model intercept, its 13-column design matrix had rank 10:
the two hormone-therapy indicators, two menopausal-status indicators, and
three tumor-grade indicators introduced three exact aliases.  The
interval-censored `survreg` fit consequently produced invalid linear
predictions during conditional-median imputation.

## Permitted repair

GBSG2 now uses deterministic reference-level dummy coding
(`pandas.get_dummies(..., drop_first=True)`).  The repaired matrix has ten
intercept-augmented columns and rank ten.  Reference coding spans the same
categorical linear-predictor space while removing the redundant columns.

No changes are made to:

- outcome or censoring generation;
- recording-error mechanisms;
- midpoint or conditional-interval correction definitions;
- official DR-COSARC source or source pin;
- seeds, splits, sample sizes, regimes, conditions, bootstrap count, or gates;
- any of the 960 completed trial records.

The scientific compatibility hash remains the frozen Gate 3 hash because the
scientific specification is unchanged.  The package separately records the
new execution implementation hash and hotfix ID.  Resume logic refuses to
execute a missing non-GBSG2 trial, and final aggregation verifies that exactly
the GBSG2 block was completed by this hotfix.

## Prior evidence lock

- Prior result archive SHA-256:
  `cece54bbc9024188adfd3e1018d4c5c16bc55e57a6727e9d035dcbd7790d0083`
- Frozen scientific configuration hash:
  `c995696c82ead376c690aeca35b4480d`
- Frozen base implementation SHA-256:
  `9b1497562f0d210e71f59862e43c1f543c460dea7a76265952684491d8ee2718`

The final result is inferential only if all 1,200 trials are complete, all
integrity checks pass, the public-data fallback remains unused, and the
original preregistered decision rules produce a non-inconclusive decision.
