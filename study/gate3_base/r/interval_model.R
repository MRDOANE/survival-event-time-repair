# Experimental interval-censored log-normal survival wrapper used by Gate 3.
# The official DR-COSARC functions remain unmodified and consume this wrapper
# through the same SurvivalModelWrapper interface used by SurvregModelWrapper.

IntervalSurvregModelWrapper <- R6::R6Class(
  "IntervalSurvregModelWrapper",
  inherit = SurvivalModelWrapper,
  public = list(
    dist = NULL,
    covariate_names = NULL,

    initialize = function(dist = "lognormal") {
      self$dist <- dist
    },

    fit_interval = function(data) {
      self$covariate_names <- grep("^X[0-9]+$", names(data), value = TRUE)
      if (length(self$covariate_names) == 0) {
        stop("interval model found no X-prefixed covariates")
      }
      rhs <- paste(sprintf("`%s`", self$covariate_names), collapse = " + ")
      formula <- stats::as.formula(
        paste0(
          "survival::Surv(time_lower, time_upper, type='interval2') ~ ",
          rhs
        )
      )
      self$formula <- formula
      self$model <- survival::survreg(
        formula,
        data = data,
        dist = self$dist,
        control = survival::survreg.control(maxiter = 1000)
      )
      finite_times <- c(
        data$time_lower[is.finite(data$time_lower)],
        data$time_upper[is.finite(data$time_upper)]
      )
      self$time.points <- seq(
        min(finite_times),
        max(finite_times),
        length.out = 100
      )
      invisible(self)
    },

    predict_quantiles = function(new_data, probs = c(0.25, 0.5, 0.75)) {
      prediction_data <- new_data[, self$covariate_names, drop = FALSE]
      quantiles <- sapply(probs, function(p) {
        stats::predict(
          self$model,
          newdata = prediction_data,
          type = "quantile",
          p = p
        )
      })
      if (is.null(dim(quantiles))) {
        quantiles <- matrix(
          quantiles,
          nrow = nrow(prediction_data),
          ncol = length(probs)
        )
      }
      colnames(quantiles) <- paste0("Q", probs * 100, "%")
      rownames(quantiles) <- paste0("Individual_", seq_len(nrow(quantiles)))
      as.data.frame(quantiles)
    },

    conditional_median_times = function(interval_data) {
      if (is.null(self$model) || is.null(self$covariate_names)) {
        stop("interval model must be fitted before conditional imputation")
      }
      required <- c("time_lower", "time_upper", "status", self$covariate_names)
      if (!all(required %in% names(interval_data))) {
        stop("conditional imputation received an incomplete interval frame")
      }
      out <- as.numeric(interval_data$time_lower)
      event <- as.integer(interval_data$status) == 1L
      if (any(event)) {
        prediction_data <- interval_data[event, self$covariate_names, drop = FALSE]
        location <- as.numeric(stats::predict(
          self$model,
          newdata = prediction_data,
          type = "lp"
        ))
        scale <- as.numeric(self$model$scale)
        lower <- as.numeric(interval_data$time_lower[event])
        upper <- as.numeric(interval_data$time_upper[event])
        p.lower <- stats::plnorm(lower, meanlog = location, sdlog = scale)
        p.upper <- stats::plnorm(upper, meanlog = location, sdlog = scale)
        probability <- 0.5 * (p.lower + p.upper)
        probability <- pmin(pmax(probability, 1e-12), 1 - 1e-12)
        imputed <- stats::qlnorm(
          probability,
          meanlog = location,
          sdlog = scale
        )
        out[event] <- pmin(pmax(imputed, lower), upper)
      }
      if (
        any(!is.finite(out)) ||
          any(out < interval_data$time_lower - 1e-10) ||
          any(event & out > interval_data$time_upper + 1e-10)
      ) {
        stop("conditional interval imputation returned invalid event times")
      }
      out
    }
  )
)
