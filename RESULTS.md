# Results summary

## Frozen Gate 3 evidence

Status: **supportive — `ADVANCE_BOTH`**.

The final locked grid contains 1,200/1,200 completed trials, zero execution
errors, five data worlds, five regimes, eight recording conditions, and six
seeds. The nominal anchor target is 90% coverage.

In the anchor cell, clean-record coverage was 0.9059 and naive upper-endpoint
coverage fell to 0.8554. Midpoint repair increased coverage to 0.9070 and the
conditional interval repair to 0.8996. The paired repair effects were 0.0516
and 0.0442, respectively.

Across the pooled expansion, mean repairs were 0.0373 for midpoint and 0.0319
for the conditional interval method. Their seed-clustered lower 95% confidence
bounds were 0.0357 and 0.0303. Midpoint and interval repairs improved absolute
target accuracy in 91.43% and 94.29% of eligible comparisons. Clean-regime
geometric lower-prediction-bound ratios were 0.990 and 1.027 relative to the
clean reference, indicating little loss of informativeness on that scale.

The complete prespecified cell table and branch decisions are in
`results/gate3/gate_report.md`; machine-readable criteria and outcomes are in
`results/gate3/gate_decision.json`.

## External interval-censored cohorts

Both external analyses are **formally neutral**. The intervals containing the
true event times are observed; the exact event times are not. Consequently,
coverage is only partially identified, and held-out interval negative log
likelihood (NLL) is the primary proper predictive score.

| Cohort | Replicates | Naive certain miss | Midpoint | Conditional interval | Naive NLL | Midpoint | Conditional interval | Formal gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Dairy-cow mastitis | 500/500 | 0.1165 | 0.0302 | 0.0356 | 2.0737 | 2.0125 | 2.0134 | NEUTRAL |
| Hemophilia/HIV | 500/500 | 0.1113 | 0.0865 | 0.0877 | 0.9637 | 0.9075 | 0.9066 | NEUTRAL |

For mastitis, mean NLL improvements were positive but their lower uncertainty
bounds crossed zero. For hemophilia/HIV, the midpoint NLL improvement had a
positive lower bound, but the prespecified certain-miss noninferiority rule was
not met. Target-compatible replicate rates increased from 0.486 to 0.904 in
mastitis and from 0.350 to 0.966/0.968 in hemophilia/HIV.

These data are directionally supportive of the repair rationale but do not
constitute confirmation of latent-time coverage or positive external gates.

## Evidence not claimed

A later package intended to compare faithful published DR-COSARC, IPCW, and
AIPCW baselines did not reach a completed experiment. It is deliberately absent
from this release and supplies no manuscript evidence. The existing Gate 3
method is the official published DR-COSARC implementation preceded by the two
study-specific observed-data interfaces; neither interface is itself called
DR-COSARC.

