# Gate 3 paper-scale survival correction expansion

Decision: **ADVANCE_BOTH**

Both correction branches retained their anchor effect and met the frozen paper-scale expansion rules.

Trial grid: complete; expected 1200, observed 1200; errors 0; required-public fallback False.

## Anchor cell

| Target | Clean | Naive | Midpoint | Interval-aware | Midpoint repair | Interval repair |
|---:|---:|---:|---:|---:|---:|---:|
| 0.9000 | 0.9059 | 0.8554 | 0.9070 | 0.8996 | 0.0516 | 0.0442 |

## Branch checks

| Branch | Core | Support | Advance |
|---|---:|---:|---:|
| Midpoint | 18/18 | 8/8 | yes |
| Interval-aware | 17/17 | 9/9 | yes |

## Expansion cells

| Condition | Regime | Target | Naive | Midpoint | Interval | Midpoint success | Interval success |
|---|---|---:|---:|---:|---:|---:|---:|
| ceiling_grid20_known | main | 0.900 | 0.855 | 0.907 | 0.900 | pass | pass |
| ceiling_grid20_known | high_censoring | 0.900 | 0.884 | 0.915 | 0.911 | fail | pass |
| ceiling_grid20_known | target95 | 0.950 | 0.923 | 0.961 | 0.951 | pass | pass |
| ceiling_grid20_known | small_sample | 0.900 | 0.858 | 0.908 | 0.902 | pass | pass |
| ceiling_grid20_known | dependent_censoring | 0.900 | 0.879 | 0.916 | 0.911 | pass | pass |
| ceiling_grid20_partial | main | 0.900 | 0.880 | 0.906 | 0.902 | pass | pass |
| ceiling_grid20_partial | high_censoring | 0.900 | 0.897 | 0.915 | 0.912 | fail | fail |
| ceiling_grid20_partial | target95 | 0.950 | 0.939 | 0.958 | 0.953 | fail | pass |
| ceiling_grid20_partial | small_sample | 0.900 | 0.882 | 0.908 | 0.904 | pass | pass |
| ceiling_grid20_partial | dependent_censoring | 0.900 | 0.894 | 0.916 | 0.913 | fail | fail |
| ceiling_grid20_shifted | main | 0.900 | 0.859 | 0.910 | 0.902 | pass | pass |
| ceiling_grid20_shifted | high_censoring | 0.900 | 0.885 | 0.915 | 0.912 | fail | pass |
| ceiling_grid20_shifted | target95 | 0.950 | 0.920 | 0.958 | 0.951 | pass | pass |
| ceiling_grid20_shifted | small_sample | 0.900 | 0.860 | 0.912 | 0.903 | pass | pass |
| ceiling_grid20_shifted | dependent_censoring | 0.900 | 0.880 | 0.916 | 0.912 | pass | pass |
| ceiling_grid20_estimated | main | 0.900 | 0.859 | 0.910 | 0.902 | pass | pass |
| ceiling_grid20_estimated | high_censoring | 0.900 | 0.885 | 0.915 | 0.912 | fail | pass |
| ceiling_grid20_estimated | target95 | 0.950 | 0.920 | 0.958 | 0.951 | pass | pass |
| ceiling_grid20_estimated | small_sample | 0.900 | 0.860 | 0.912 | 0.903 | pass | pass |
| ceiling_grid20_estimated | dependent_censoring | 0.900 | 0.880 | 0.916 | 0.912 | pass | pass |
| visits_regular20 | main | 0.900 | 0.859 | 0.906 | 0.901 | pass | pass |
| visits_regular20 | high_censoring | 0.900 | 0.883 | 0.913 | 0.910 | pass | pass |
| visits_regular20 | target95 | 0.950 | 0.921 | 0.960 | 0.951 | pass | pass |
| visits_regular20 | small_sample | 0.900 | 0.864 | 0.910 | 0.905 | pass | pass |
| visits_regular20 | dependent_censoring | 0.900 | 0.880 | 0.916 | 0.912 | pass | pass |
| visits_irregular20 | main | 0.900 | 0.859 | 0.907 | 0.901 | pass | pass |
| visits_irregular20 | high_censoring | 0.900 | 0.884 | 0.915 | 0.911 | fail | pass |
| visits_irregular20 | target95 | 0.950 | 0.923 | 0.957 | 0.950 | pass | pass |
| visits_irregular20 | small_sample | 0.900 | 0.860 | 0.908 | 0.901 | pass | pass |
| visits_irregular20 | dependent_censoring | 0.900 | 0.879 | 0.914 | 0.910 | pass | pass |
| visits_informative20 | main | 0.900 | 0.863 | 0.907 | 0.902 | pass | pass |
| visits_informative20 | high_censoring | 0.900 | 0.887 | 0.915 | 0.912 | fail | fail |
| visits_informative20 | target95 | 0.950 | 0.926 | 0.957 | 0.951 | pass | pass |
| visits_informative20 | small_sample | 0.900 | 0.865 | 0.909 | 0.902 | pass | pass |
| visits_informative20 | dependent_censoring | 0.900 | 0.881 | 0.914 | 0.911 | pass | pass |
| event_delay15_known | main | 0.900 | 0.876 | 0.891 | 0.891 | pass | pass |
| event_delay15_known | high_censoring | 0.900 | 0.892 | 0.904 | 0.904 | pass | pass |
| event_delay15_known | target95 | 0.950 | 0.940 | 0.948 | 0.948 | pass | pass |
| event_delay15_known | small_sample | 0.900 | 0.879 | 0.894 | 0.893 | pass | pass |
| event_delay15_known | dependent_censoring | 0.900 | 0.891 | 0.904 | 0.904 | pass | pass |
