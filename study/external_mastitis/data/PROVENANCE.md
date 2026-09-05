# Data provenance

The frozen `mastitis.csv` file is a lossless tabular conversion of
`mastitis.rda` from CRAN package **icensBKL 1.5** (package date 2023-12-19;
CRAN manual published 2026-05-08). The original R data file, documentation,
and package DESCRIPTION are included beside the CSV for direct audit.

- CRAN source: `https://cran.r-project.org/src/contrib/icensBKL_1.5.tar.gz`
- Source archive SHA-256: `0adcb57b18a5a46981e5fb1a9cea87f83b57f6b6580cce12ff2523185bd2d5c9`
- Dataset: 400 udder quarters nested within exactly 100 cows
- Endpoint: first bacterial infection of an udder quarter after parturition
- Observation: `(ll, ul]` in days; missing `ll` is left censoring and missing `ul` is right censoring
- Covariates: udder-quarter position and cow-level parity
- Primary source cited by the package: Goethals et al. (2009), JABES 14(1):1-14

The package is GPL (>=2). This analysis bundle is distributed under GPL-3.0;
see `LICENSE`.
