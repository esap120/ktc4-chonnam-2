"""Independent RT-06(b) acceptance inventory; do not import from the gate."""

REDELIVERY_MODES = {
    "eligibility": ("SUCCEEDED", "FAILED", "CANCELLED", "STALE", "QUEUED", "RUNNING", "receipt"),
    "atomicity": ("success", "failed_hint", "enqueue", "marker"),
    "concurrent": ("case_first",),
    "commit_unknown": ("followup", "stopped"),
    "isolation": ("reflector", "db", "logger", "filter", "handler", "scan"),
    "unsupported": ("PLATE_READ", "UNKNOWN"),
    "metric": ("first_stopped", "retry_stopped", "third_stopped", "CANCELLED", "SUPERSEDED", "APPLIED"),
    "startup_periodic": ("startup", "periodic"),
    "process_kill": ("gap", "running"),
}
REDELIVERY_CHECKS = tuple(("redelivery", scenario) for scenario in REDELIVERY_MODES)
REDELIVERY_PARAMETERS = tuple(("redelivery", scenario, parameter)
    for scenario, modes in REDELIVERY_MODES.items() for parameter in modes)
