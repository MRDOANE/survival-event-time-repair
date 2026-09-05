# Data provenance

The frozen `hiv.csv` file is a lossless tabular conversion of `hiv.rda` from
CRAN package **icensBKL 1.5** (package date 2023-12-19; CRAN manual published
2026-05-08). The original R data file, documentation, and package DESCRIPTION
are included beside the CSV for direct audit.

- CRAN source: `https://cran.r-project.org/src/contrib/icensBKL_1.5.tar.gz`
- Source archive SHA-256: `0adcb57b18a5a46981e5fb1a9cea87f83b57f6b6580cce12ff2523185bd2d5c9`
- Dataset: 368 patients from a 16-center prospective hemophilia cohort
- Endpoint: HIV-1 infection
- Observation: `(low, upp]` in quarters from 1978-01-01; a missing `upp` is right censoring
- Covariate: no versus low-dose factor VIII concentrate
- Primary source cited by the package: Sun J. (2006), Table A.2 and Section 3.4
- Clinical references cited by the package: Goedert et al. (1989); Kroner et al. (1994)

The package is GPL (>=2). This analysis bundle is distributed under GPL-3.0;
see `LICENSE`.
