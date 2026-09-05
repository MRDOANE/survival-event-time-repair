suppressPackageStartupMessages({
  library(jsonlite)
  library(R6)
  library(survival)
  library(tidyverse)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript official_trial.R BUNDLE_DIR OUTPUT_JSON")
}

bundle_dir <- normalizePath(args[[1]], mustWork = TRUE)
output_json <- args[[2]]
upstream_root <- Sys.getenv("DRCOSARC_UPSTREAM_DIR", unset = "")
if (upstream_root == "") stop("DRCOSARC_UPSTREAM_DIR is not set")
upstream_root <- normalizePath(upstream_root, mustWork = TRUE)
official_dir <- file.path(upstream_root, "code", "conf_surv")
file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(file_arg) != 1) stop("cannot resolve official_trial.R path")
driver_path <- sub("^--file=", "", file_arg[[1]])
driver_dir <- dirname(normalizePath(driver_path, mustWork = TRUE))

source(file.path(official_dir, "utils_survival.R"), local = .GlobalEnv)
source(file.path(official_dir, "utils_censoring.R"), local = .GlobalEnv)
source(file.path(official_dir, "utils_conformal.R"), local = .GlobalEnv)
source(file.path(driver_dir, "interval_model.R"), local = .GlobalEnv)

manifest <- jsonlite::fromJSON(
  file.path(bundle_dir, "manifest.json"),
  simplifyVector = FALSE
)

read_frame <- function(record) {
  path <- file.path(bundle_dir, record$file)
  frame <- read.csv(path, check.names = FALSE)
  frame$status <- as.integer(frame$status)
  frame$time <- as.numeric(frame$time)
  if (!all(frame$status %in% c(0L, 1L))) {
    stop(sprintf("non-binary status in %s", path))
  }
  if (any(!is.finite(as.matrix(frame)))) {
    stop(sprintf("non-finite value in %s", path))
  }
  if (nrow(frame) != as.integer(record$rows)) {
    stop(sprintf("row-count mismatch in %s", path))
  }
  frame
}

read_interval_frame <- function(record) {
  path <- file.path(bundle_dir, record$file)
  frame <- read.csv(path, check.names = FALSE, na.strings = c("", "NA"))
  frame$status <- as.integer(frame$status)
  frame$time_lower <- as.numeric(frame$time_lower)
  frame$time_upper <- as.numeric(frame$time_upper)
  if (!all(frame$status %in% c(0L, 1L))) {
    stop(sprintf("non-binary interval status in %s", path))
  }
  if (any(!is.finite(frame$time_lower)) || any(frame$time_lower <= 0)) {
    stop(sprintf("invalid interval lower endpoint in %s", path))
  }
  event <- frame$status == 1L
  censored <- !event
  if (any(!is.finite(frame$time_upper[event]))) {
    stop(sprintf("non-finite event upper endpoint in %s", path))
  }
  if (any(!is.na(frame$time_upper[censored]))) {
    stop(sprintf("closed right-censored upper endpoint in %s", path))
  }
  if (any(frame$time_lower[event] > frame$time_upper[event])) {
    stop(sprintf("reversed event interval in %s", path))
  }
  covariates <- grep("^X[0-9]+$", names(frame), value = TRUE)
  if (length(covariates) == 0 || any(!is.finite(as.matrix(frame[covariates])))) {
    stop(sprintf("invalid interval covariates in %s", path))
  }
  if (nrow(frame) != as.integer(record$rows)) {
    stop(sprintf("row-count mismatch in %s", path))
  }
  frame
}

make_survival_model <- function(name) {
  if (name == "survreg_lognormal") {
    return(SurvregModelWrapper$new(dist = "lognormal"))
  }
  stop(sprintf("unsupported official survival model: %s", name))
}

make_censoring_model <- function(name) {
  if (name == "survreg_lognormal") {
    base <- SurvregModelWrapper$new(dist = "lognormal")
  } else {
    stop(sprintf("unsupported official censoring model: %s", name))
  }
  CensoringModel$new(model = base)
}

predict_adaptive <- function(surv_model, cens_model, cal, test, seed) {
  set.seed(as.integer(seed))
  as.numeric(predict_drcosarc(
    data.test = test,
    surv_model = surv_model,
    cens_imputator = cens_model,
    data.cal = cal,
    alpha = as.numeric(manifest$alpha),
    cutoffs = "adaptive",
    finite_sample_correction = isTRUE(manifest$finite_sample_correction),
    doubly_robust = TRUE
  ))
}

fit_proxy <- function(records, test, seed) {
  train <- read_frame(records$train)
  cal <- read_frame(records$cal)
  surv_model <- make_survival_model(manifest$survival_model)
  cens_model <- make_censoring_model(manifest$censoring_model)
  surv_model$fit(Surv(time, status) ~ ., data = train)
  cens_model$fit(data = train)
  nominal <- as.numeric(
    surv_model$predict_quantiles(test, probs = as.numeric(manifest$alpha))[[1]]
  )
  list(
    nominal = pmax(nominal, 0),
    adaptive = pmax(predict_adaptive(surv_model, cens_model, cal, test, seed), 0)
  )
}

interval_to_proxy <- function(interval_frame, event_times) {
  covariates <- grep("^X[0-9]+$", names(interval_frame), value = TRUE)
  proxy <- data.frame(
    time = as.numeric(event_times),
    status = as.integer(interval_frame$status)
  )
  cbind(proxy, interval_frame[, covariates, drop = FALSE])
}

fit_interval_suite <- function(records, test, seed) {
  interval_train <- read_interval_frame(records$interval_train)
  interval_cal <- read_interval_frame(records$interval_cal)
  lower_train <- read_frame(records$lower_proxy_train)
  lower_cal <- read_frame(records$lower_proxy_cal)
  midpoint_train <- read_frame(records$midpoint_proxy_train)
  midpoint_cal <- read_frame(records$midpoint_proxy_cal)
  surv_model <- IntervalSurvregModelWrapper$new(dist = "lognormal")
  surv_model$fit_interval(interval_train)
  nominal <- as.numeric(
    surv_model$predict_quantiles(test, probs = as.numeric(manifest$alpha))[[1]]
  )

  conditional_train <- interval_to_proxy(
    interval_train,
    surv_model$conditional_median_times(interval_train)
  )
  conditional_cal <- interval_to_proxy(
    interval_cal,
    surv_model$conditional_median_times(interval_cal)
  )

  adaptive_with_proxy <- function(proxy_train, proxy_cal) {
    cens_model <- make_censoring_model(manifest$censoring_model)
    cens_model$fit(data = proxy_train)
    pmax(predict_adaptive(surv_model, cens_model, proxy_cal, test, seed), 0)
  }

  list(
    nominal = pmax(nominal, 0),
    lower_adaptive = adaptive_with_proxy(lower_train, lower_cal),
    midpoint_adaptive = adaptive_with_proxy(midpoint_train, midpoint_cal),
    conditional_adaptive = adaptive_with_proxy(
      conditional_train,
      conditional_cal
    ),
    conditional_diagnostics = list(
      train_event_count = sum(conditional_train$status == 1L),
      cal_event_count = sum(conditional_cal$status == 1L),
      train_mean_imputed_event_time = mean(
        conditional_train$time[conditional_train$status == 1L]
      ),
      cal_mean_imputed_event_time = mean(
        conditional_cal$time[conditional_cal$status == 1L]
      )
    )
  )
}

run_main <- function() {
  test <- read_frame(manifest$files$test)
  method_seed <- as.integer(manifest$seed) + 26000L
  clean <- fit_proxy(manifest$files$clean, test, method_seed)
  corrupt <- fit_proxy(manifest$files$corrupt, test, method_seed)
  lower <- fit_proxy(manifest$files$lower_edge, test, method_seed)
  midpoint <- fit_proxy(manifest$files$midpoint, test, method_seed)
  midpoint_under <- fit_proxy(
    manifest$files$midpoint_under75,
    test,
    method_seed
  )
  midpoint_over <- fit_proxy(
    manifest$files$midpoint_over125,
    test,
    method_seed
  )
  wrong <- fit_proxy(manifest$files$wrong_direction, test, method_seed)
  interval <- fit_interval_suite(
    manifest$files$interval_primary,
    test,
    method_seed
  )

  bounds <- list(
    clean_reference_drcosarc_adaptive = clean$adaptive,
    naive_corrupt_drcosarc_adaptive = corrupt$adaptive,
    lower_edge_proxy_drcosarc_adaptive = lower$adaptive,
    midpoint_proxy_drcosarc_adaptive = midpoint$adaptive,
    midpoint_under75_drcosarc_adaptive = midpoint_under$adaptive,
    midpoint_over125_drcosarc_adaptive = midpoint_over$adaptive,
    interval_conditional_cal_drcosarc_adaptive = interval$conditional_adaptive,
    interval_midpoint_cal_drcosarc_adaptive = interval$midpoint_adaptive,
    stopped_interval_lower_cal_drcosarc_adaptive = interval$lower_adaptive,
    wrong_upper_shift_drcosarc_adaptive = wrong$adaptive,
    uncalibrated_corrupt_official_model = corrupt$nominal,
    uncalibrated_midpoint_model = midpoint$nominal,
    uncalibrated_interval_model = interval$nominal,
    trivial_zero_bound = rep(0, nrow(test))
  )
  for (name in names(bounds)) {
    values <- as.numeric(bounds[[name]])
    if (length(values) != nrow(test)) {
      stop(sprintf(
        "%s returned %d values for %d test rows",
        name,
        length(values),
        nrow(test)
      ))
    }
    if (any(!is.finite(values)) || any(values < 0)) {
      stop(sprintf("%s returned invalid bounds", name))
    }
    bounds[[name]] <- values
  }
  list(
    schema_version = "3.0",
    status = "complete",
    official_source_commit = manifest$official_source$commit,
    input_fingerprint = manifest$input_fingerprint,
    algorithm = "adaptive",
    survival_model = manifest$survival_model,
    censoring_model = manifest$censoring_model,
    experimental_survival_model = "interval_lognormal_survreg",
    calibration_proxy = "gate3_midpoint_and_conditional_interval_expansion",
    bounds = bounds,
    diagnostics = list(
      common_random_seed = method_seed,
      correction_protocol = manifest$correction_protocol,
      view_diagnostics = manifest$view_diagnostics,
      conditional_imputation = interval$conditional_diagnostics
    )
  )
}

dir.create(dirname(output_json), recursive = TRUE, showWarnings = FALSE)
result <- tryCatch(
  run_main(),
  error = function(e) list(
    schema_version = "3.0",
    status = "error",
    error = conditionMessage(e),
    traceback = paste(capture.output(traceback()), collapse = "\n")
  )
)
jsonlite::write_json(
  result,
  output_json,
  auto_unbox = TRUE,
  pretty = TRUE,
  digits = 16
)
if (!identical(result$status, "complete")) {
  message(result$error)
  quit(save = "no", status = 1)
}
