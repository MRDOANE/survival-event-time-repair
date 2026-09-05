suppressPackageStartupMessages({
  library(jsonlite)
  library(R6)
  library(survival)
  library(tidyverse)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript preflight_official.R UPSTREAM_ROOT OUTPUT_JSON")
}
upstream_root <- normalizePath(args[[1]], mustWork = TRUE)
output_json <- args[[2]]
official_dir <- file.path(upstream_root, "code", "conf_surv")
file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(file_arg) != 1) stop("cannot resolve preflight_official.R path")
driver_path <- sub("^--file=", "", file_arg[[1]])
driver_dir <- dirname(normalizePath(driver_path, mustWork = TRUE))
source(file.path(official_dir, "utils_survival.R"), local = .GlobalEnv)
source(file.path(official_dir, "utils_censoring.R"), local = .GlobalEnv)
source(file.path(official_dir, "utils_conformal.R"), local = .GlobalEnv)
source(file.path(driver_dir, "interval_model.R"), local = .GlobalEnv)

run_check <- function() {
  set.seed(20260831)
  make_frame <- function(n) {
    x <- rnorm(n)
    event_time <- exp(1.4 + 0.35 * x + rnorm(n, sd = 0.45))
    censor_time <- exp(1.55 + rnorm(n, sd = 0.70))
    data.frame(
      time = pmin(event_time, censor_time),
      status = as.integer(event_time <= censor_time),
      X1 = x
    )
  }
  train <- make_frame(180)
  cal <- make_frame(180)
  test <- make_frame(24)
  surv_model <- SurvregModelWrapper$new(dist = "lognormal")
  cens_base <- SurvregModelWrapper$new(dist = "lognormal")
  cens_model <- CensoringModel$new(model = cens_base)
  surv_model$fit(Surv(time, status) ~ ., data = train)
  cens_model$fit(train)

  set.seed(191)
  adaptive <- predict_drcosarc(
    test, surv_model, cens_model, cal, alpha = 0.1,
    cutoffs = "adaptive", finite_sample_correction = FALSE,
    doubly_robust = TRUE
  )
  set.seed(193)
  fixed <- predict_drcosarc(
    test, surv_model, cens_model, cal, alpha = 0.1,
    cutoffs = "candes-fixed", finite_sample_correction = FALSE,
    doubly_robust = TRUE
  )
  if (length(adaptive) != nrow(test) || length(fixed) != nrow(test)) {
    stop("official algorithms returned the wrong number of bounds")
  }
  if (any(!is.finite(adaptive)) || any(!is.finite(fixed))) {
    stop("official algorithms returned non-finite bounds")
  }

  width <- 0.8
  interval_train <- train
  event <- interval_train$status == 1L
  interval_train$time_upper <- NA_real_
  interval_train$time_lower <- interval_train$time
  interval_train$time_upper[event] <-
    width * ceiling(interval_train$time[event] / width)
  interval_train$time_lower[event] <- pmax(
    interval_train$time_upper[event] - width,
    1e-6
  )
  interval_train <- interval_train[, c(
    "time_lower", "time_upper", "status", "X1"
  )]
  proxy_train <- train
  proxy_train$time[event] <- interval_train$time_lower[event]
  proxy_cal <- cal
  cal_event <- proxy_cal$status == 1L
  cal_upper <- width * ceiling(proxy_cal$time[cal_event] / width)
  proxy_cal$time[cal_event] <- pmax(cal_upper - width, 1e-6)
  interval_cal <- cal
  interval_cal$time_upper <- NA_real_
  interval_cal$time_lower <- interval_cal$time
  interval_cal$time_upper[cal_event] <- cal_upper
  interval_cal$time_lower[cal_event] <- pmax(cal_upper - width, 1e-6)
  interval_cal <- interval_cal[, c(
    "time_lower", "time_upper", "status", "X1"
  )]

  interval_surv <- IntervalSurvregModelWrapper$new(dist = "lognormal")
  interval_cens <- CensoringModel$new(
    model = SurvregModelWrapper$new(dist = "lognormal")
  )
  interval_surv$fit_interval(interval_train)
  interval_cens$fit(proxy_train)
  set.seed(197)
  interval_adaptive <- predict_drcosarc(
    test, interval_surv, interval_cens, proxy_cal, alpha = 0.1,
    cutoffs = "adaptive", finite_sample_correction = FALSE,
    doubly_robust = TRUE
  )
  conditional_train <- data.frame(
    time = interval_surv$conditional_median_times(interval_train),
    status = interval_train$status,
    X1 = interval_train$X1
  )
  conditional_cal <- data.frame(
    time = interval_surv$conditional_median_times(interval_cal),
    status = interval_cal$status,
    X1 = interval_cal$X1
  )
  conditional_cens <- CensoringModel$new(
    model = SurvregModelWrapper$new(dist = "lognormal")
  )
  conditional_cens$fit(conditional_train)
  set.seed(199)
  conditional_adaptive <- predict_drcosarc(
    test, interval_surv, conditional_cens, conditional_cal, alpha = 0.1,
    cutoffs = "adaptive", finite_sample_correction = FALSE,
    doubly_robust = TRUE
  )
  if (
    length(interval_adaptive) != nrow(test) ||
      any(!is.finite(interval_adaptive)) ||
      any(interval_adaptive < 0)
  ) {
    stop("experimental interval wrapper failed the official adaptive path")
  }
  if (
    length(conditional_adaptive) != nrow(test) ||
      any(!is.finite(conditional_adaptive)) ||
      any(conditional_adaptive < 0) ||
      any(conditional_train$time < interval_train$time_lower - 1e-10) ||
      any(
        conditional_train$status == 1L &
          conditional_train$time > interval_train$time_upper + 1e-10
      )
  ) {
    stop("conditional interval calibration failed the official adaptive path")
  }
  list(
    status = "pass",
    r_version = R.version.string,
    package_versions = list(
      jsonlite = as.character(packageVersion("jsonlite")),
      R6 = as.character(packageVersion("R6")),
      survival = as.character(packageVersion("survival")),
      tidyverse = as.character(packageVersion("tidyverse"))
    ),
    adaptive_bounds_n = length(adaptive),
    fixed_bounds_n = length(fixed),
    interval_adaptive_bounds_n = length(interval_adaptive),
    interval_conditional_bounds_n = length(conditional_adaptive),
    adaptive_finite = all(is.finite(adaptive)),
    fixed_finite = all(is.finite(fixed)),
    interval_adaptive_finite = all(is.finite(interval_adaptive)),
    interval_conditional_finite = all(is.finite(conditional_adaptive)),
    conditional_times_inside_intervals = TRUE
  )
}

result <- tryCatch(
  run_check(),
  error = function(e) list(status = "fail", error = conditionMessage(e))
)
dir.create(dirname(output_json), recursive = TRUE, showWarnings = FALSE)
jsonlite::write_json(result, output_json, auto_unbox = TRUE, pretty = TRUE)
if (!identical(result$status, "pass")) {
  message(result$error)
  quit(save = "no", status = 1)
}
