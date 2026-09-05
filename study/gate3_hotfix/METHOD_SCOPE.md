# Method scope and claim boundaries

## Published method boundary

Sesia and Svetnik introduced DR-COSARC for lower prediction bounds under right
censoring. Gate 3 retrieves their repository at commit
`5b2cd20354e42105c980eabb4650240ae76dc866`, verifies the registered source
hashes, and sources the official survival, censoring, and conformal R files
without modification.

The adaptive `predict_drcosarc` call, censoring-time imputation, weighted
calibration, and doubly robust minimum remain the authors' implementation.

## Experimental contribution

Gate 3 evaluates two observed-data interfaces for event times represented by
upper-endpoint recording intervals:

- a midpoint proxy interface;
- a log-normal interval-censored survival wrapper with fitted conditional
  medians for censoring and calibration.

The expansion adds subject-level regular, irregular, and informative visit
brackets; estimation of grid width and origin from a disjoint protocol split;
multiple outcome distributions, censoring regimes, sample sizes, and coverage
targets; and two public-covariate data worlds.

Neither correction is part of the published DR-COSARC method. No finite-sample
or asymptotic coverage theorem is claimed under event-time record error. The
conditional interval method remains model-dependent.

## Information boundary

Known-grid methods receive corrupted training and calibration records plus
declared width, direction, and origin. The estimated-grid method receives only
observed event endpoints from the disjoint protocol-estimation split. Visit
conditions receive recorded lower and upper visit endpoints for each event.

Latent event times score untouched test coverage only. Clean records are used
only by the matched reference. Simulated corruption flags are unavailable to
the corrections.

## Permissible interpretation

Advancement supports an empirical claim that the qualifying interface restores
latent event-time lower-bound coverage across the preregistered simulated and
semi-synthetic recording conditions while preserving useful lower prediction
bounds.

The study does not establish validity for status misclassification, completely
unknown observation intervals, arbitrary informative examination processes,
unmeasured-dependent censoring, real clinical outcomes with unavailable latent
event times, or general interval-censored conformal prediction. Rossi and
GBSG2 supply public covariate geometry; their Gate 3 outcomes are
semi-synthetic.

## Upstream redistribution

The pinned upstream repository did not contain a license file. Its source is
not redistributed. The launcher fetches and verifies it on the execution
machine.
