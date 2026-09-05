"""Gate 3 midpoint and interval-aware event-time expansion."""

__version__ = "0.6.1"

METHODS = (
    "clean_reference_drcosarc_adaptive",
    "naive_corrupt_drcosarc_adaptive",
    "lower_edge_proxy_drcosarc_adaptive",
    "midpoint_proxy_drcosarc_adaptive",
    "midpoint_under75_drcosarc_adaptive",
    "midpoint_over125_drcosarc_adaptive",
    "interval_conditional_cal_drcosarc_adaptive",
    "interval_midpoint_cal_drcosarc_adaptive",
    "stopped_interval_lower_cal_drcosarc_adaptive",
    "wrong_upper_shift_drcosarc_adaptive",
    "uncalibrated_corrupt_official_model",
    "uncalibrated_midpoint_model",
    "uncalibrated_interval_model",
    "trivial_zero_bound",
)
