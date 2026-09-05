required <- c("jsonlite", "R6", "survival", "tidyverse")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing) > 0) {
  repos <- c(CRAN = Sys.getenv("CRAN_REPO", unset = "https://cloud.r-project.org"))
  install.packages(missing, repos = repos, Ncpus = max(1, min(4, parallel::detectCores())))
}
still_missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]
if (length(still_missing) > 0) {
  stop(sprintf("missing required R packages: %s", paste(still_missing, collapse = ", ")))
}
versions <- vapply(required, function(name) as.character(packageVersion(name)), character(1))
print(versions)
