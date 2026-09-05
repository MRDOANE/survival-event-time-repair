# External interval-censored validation: Clustered Dairy-Cow Mastitis Cohort

Decision: **NEUTRAL**

External interval-censored evidence is evaluated with held-out interval log score and partially identified lower-bound coverage. No latent event time is treated as observed.

## Cohort and execution

- Rows: 400
- Independent resampling units: 100
- Finite event intervals: 317
- Bootstrap replicates completed: 500/500
- Primary target coverage: 0.900

## Method summaries

| Method | Identified coverage lower | Identified coverage upper | Certain miss | Interval NLL | Geometric mean LPB | Target-compatible reps |
|---|---:|---:|---:|---:|---:|---:|
| naive_upper | 0.6320 | 0.8835 | 0.1165 | 2.0737 | 53.2014 | 0.486 |
| midpoint | 0.7423 | 0.9698 | 0.0302 | 2.0125 | 36.9690 | 0.904 |
| interval_aware | 0.7275 | 0.9644 | 0.0356 | 2.0134 | 38.5799 | 0.904 |

## Paired comparisons against naive upper-endpoint coding

Positive interval-NLL improvement and positive certain-miss reduction favor the correction.

| Branch | Classification | NLL improvement (mean; 95% bootstrap interval) | Certain-miss reduction (mean; 95% bootstrap interval) | Geometric LPB ratio |
|---|---|---:|---:|---:|
| midpoint | **neutral** | 0.0612 [-0.0345, 0.1882] | 0.0864 [0.0000, 0.2024] | 0.692 |
| interval_aware | **neutral** | 0.0602 [-0.0400, 0.1882] | 0.0810 [0.0000, 0.1905] | 0.724 |

## Interpretation guardrail

The exact event times remain unknown. The held-out interval log score is the primary proper predictive score. Coverage is reported as a partially identified interval: a bound at or below the observed lower endpoint is certainly covering, a bound above a finite upper endpoint is certainly missing, and all other cases are ambiguous. These data can externally support the direction of the Gate 3 result, but they cannot recreate clean-event-time coverage.
