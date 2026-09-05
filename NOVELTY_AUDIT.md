# Novelty audit

Audit date: 2026-09-05. Target journal: *Statistics in Medicine*.

## Bottom line

The work has a defensible, publishable novelty position as an applied
methodological study of **latent-event-time lower-bound coverage under
event-time coarsening**. It should not be presented as a new general conformal
method for interval-censored survival data. That broader territory is already
occupied, most directly by Meixide et al.'s uncertainty-quantification method
for interval-valued targets.

The strongest manuscript framing is:

> We study the empirical failure of conformal lower prediction bounds for
> latent event time when event times used for model fitting and calibration are
> recorded only as upper endpoints or visit intervals. We evaluate two simple
> observed-data interfaces to an otherwise unmodified, published DR-COSARC
> pipeline and assess both latent-time coverage in controlled experiments and
> partially identified coverage plus interval predictive score in two
> naturally interval-censored cohorts.

Use “to our knowledge” only for this narrow conjunction, and describe the
search date and databases in the manuscript or supplement.

## Literature map and overlap

| Prior work | What it establishes | Relationship to this study | Claim implication |
|---|---|---|---|
| Sesia & Svetnik (2025), DR-COSARC | Adaptive lower prediction bounds under ordinary right censoring, with asymptotic double robustness | The published method used as the fixed downstream engine | DR-COSARC is prior work; distinguish it from both repairs everywhere |
| Candès, Lei & Ren (2023) | Conformalized survival analysis for right-censored data and lower predictive bounds | Foundational right-censoring conformal work | Do not claim conformal survival prediction itself as novel |
| Meixide et al. (2024/2025), “Uncertainty quantification for intervals” | Conformal uncertainty for interval-valued/interval-censored targets (“uncervals”), including biomedical applications | Closest novelty overlap, but its target and method differ from repairing latent-time coverage in a fixed right-censoring pipeline | Do not claim the first conformal interval-censored survival method |
| Farina et al. (2026) | IPCW, outcome-regression, calibrated outcome-regression, and augmented IPCW conformal procedures under ordinary right censoring | Adjacent recent baselines; not completed in this release | Acknowledge as related right-censoring work; make no comparative-superiority claim |
| Oh et al. (2021) | Regression calibration and raking for covariate and censored event-time error using validation data | Establishes survival measurement-error correction, primarily for Cox-model parameters | Do not claim first correction for event-time error generally |
| Bar et al. (2012) | Model-based adjustment for heaped retrospectively reported event times | Establishes event-time heaping as a prior statistical problem | Position this study around predictive-bound coverage, not discovery of heaping |
| Yi et al. (2025) | Two-sided prediction intervals under right censoring using weighting and quantile regression | Further adjacent prediction-interval work | Describe the focus on one-sided latent-time lower bounds and coarsening |

## What appears novel enough to claim

1. **Failure-mode characterization.** A broad, frozen evaluation of how
   upper-endpoint coding, regular and irregular visit brackets, informative
   examination patterns, grid uncertainty, and event delay affect latent-time
   lower-bound coverage in an adaptive DR-COSARC pipeline.
2. **Non-invasive repair interfaces.** Two transparent observed-data adapters
   evaluated while leaving the official downstream DR-COSARC implementation
   unchanged: midpoint substitution and a fitted interval-survival conditional
   median.
3. **Coverage–informativeness stress testing.** Joint assessment of coverage
   restoration and lower-bound magnitude across simulated and public-covariate
   worlds, including deliberately adverse diagnostics and protocol-estimated
   recording grids.
4. **Honest external evaluation without latent outcomes.** Use of held-out
   interval log score alongside identified coverage bounds, certain-miss rate,
   and target-compatibility frequency in naturally interval-censored cohorts.

Items 2 and 4 are best described as parts of the study design rather than as
standalone algorithmic inventions.

## Claims to avoid

- “the first conformal method for interval-censored survival data”;
- “distribution-free validity under interval censoring”;
- “a new doubly robust conformal algorithm”;
- “external validation of 90% latent-time coverage”;
- “superior to IPCW/AIPCW methods”;
- “real-data confirmation” or “replication” when both external gates were
  formally neutral;
- calling either repair “DR-COSARC,” rather than an interface used before the
  published DR-COSARC implementation.

## Recommended manuscript positioning for *Statistics in Medicine*

The journal emphasizes new quantitative methods tied to a substantive
biomedical motivation or comprehensive illustrative evaluation. This work is
best sold as a pragmatic measurement-process extension with extensive stress
testing and two real interval-censored examples, not as a primarily
mathematical paper.

Recommended title:

> Repairing conformal survival lower prediction bounds under event-time
> coarsening

Suggested one-sentence contribution statement:

> We show that common upper-endpoint representations of coarsened event times
> can materially undercut latent-time lower-bound coverage, and that two simple
> observed-data interfaces restore most of this loss across a preregistered
> simulation and semi-synthetic expansion while producing directionally
> favorable but formally neutral results in two interval-censored cohorts.

## Residual reviewer risks

| Risk | Assessment | Pre-emption |
|---|---|---|
| Overlap with “uncervals” | High if claims are broad; manageable if estimand and pipeline distinction is explicit | Cite and contrast in the introduction and discussion |
| Simple repairs may seem incremental | Moderate | Lead with the failure-mode map, frozen stress design, and clinical recording-process implications |
| No theorem under coarsening | Moderate | State clearly; frame as an empirical applied-methods contribution |
| No completed recent AIPCW/IPCW benchmark | Moderate to high | Do not imply one; explain that these methods address ordinary right censoring and list direct comparison as future work |
| External gates are neutral | Moderate | Report the gates, uncertainty intervals, and partial-identification limits without spin |
| Semi-synthetic public-data worlds | Low to moderate | Call them public-covariate semi-synthetic experiments, never external outcomes |

## Audit references

- Sesia, M. and Svetnik, V. (2025). [Doubly robust and efficient calibration of
  prediction sets for censored time-to-event outcomes](https://proceedings.mlr.press/v267/sesia25a.html).
- Candès, E. J., Lei, L. and Ren, Z. (2023). [Conformalized survival
  analysis](https://academic.oup.com/jrsssb/article/85/1/24/7008653).
- Meixide, C. G. et al. (2024/2025). [Uncertainty quantification for
  intervals](https://arxiv.org/abs/2408.16381).
- Farina, M. P. et al. (2026). [Conformalized survival analysis with
  censored data](https://academic.oup.com/biomet/article/113/3/asag036/8706430).
- Oh, E. J. et al. (2021). [Addressing measurement error in survival analysis
  using regression calibration and multiple imputation](https://pmc.ncbi.nlm.nih.gov/articles/PMC7874496/).
- Bar, H. Y. et al. (2012). [Statistical adjustment for heaping in
  retrospectively reported event data](https://onlinelibrary.wiley.com/doi/abs/10.1002/sim.5419).
- Yi, G. Y. et al. (2025). [Prediction intervals for survival outcomes with
  right censoring](https://onlinelibrary.wiley.com/doi/abs/10.1002/sta4.70052).

This is a targeted novelty audit, not a systematic review or legal opinion.

