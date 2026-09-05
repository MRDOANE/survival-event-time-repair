# External interval-censored validation: Multicenter Hemophilia HIV Cohort

Decision: **NEUTRAL**

External interval-censored evidence is evaluated with held-out interval log score and partially identified lower-bound coverage. No latent event time is treated as observed.

## Cohort and execution

- Rows: 368
- Independent resampling units: 368
- Finite event intervals: 103
- Bootstrap replicates completed: 500/500
- Primary target coverage: 0.900

## Method summaries

| Method | Identified coverage lower | Identified coverage upper | Certain miss | Interval NLL | Geometric mean LPB | Target-compatible reps |
|---|---:|---:|---:|---:|---:|---:|
| naive_upper | 0.4845 | 0.8887 | 0.1113 | 0.9637 | 36.1749 | 0.350 |
| midpoint | 0.3655 | 0.9135 | 0.0865 | 0.9075 | 34.5595 | 0.966 |
| interval_aware | 0.2740 | 0.9123 | 0.0877 | 0.9066 | 37.5191 | 0.968 |

## Paired comparisons against naive upper-endpoint coding

Positive interval-NLL improvement and positive certain-miss reduction favor the correction.

| Branch | Classification | NLL improvement (mean; 95% bootstrap interval) | Certain-miss reduction (mean; 95% bootstrap interval) | Geometric LPB ratio |
|---|---|---:|---:|---:|
| midpoint | **neutral** | 0.0562 [0.0010, 0.1425] | 0.0248 [-0.0108, 0.0753] | 0.959 |
| interval_aware | **neutral** | 0.0570 [-0.0039, 0.1538] | 0.0236 [-0.0108, 0.0753] | 1.043 |

## Interpretation guardrail

The exact event times remain unknown. The held-out interval log score is the primary proper predictive score. Coverage is reported as a partially identified interval: a bound at or below the observed lower endpoint is certainly covering, a bound above a finite upper endpoint is certainly missing, and all other cases are ambiguous. These data can externally support the direction of the Gate 3 result, but they cannot recreate clean-event-time coverage.
