"""Public validation must share existing transition semantics."""

from importlib import import_module
import pytest


@pytest.mark.parametrize("current,target", [
    ("QUEUED", "RUNNING"), ("QUEUED", "FAILED"), ("QUEUED", "CANCELLED"),
    ("RUNNING", "SUCCEEDED"), ("RUNNING", "FAILED"), ("RUNNING", "STALE"), ("RUNNING", "CANCELLED"),
])
def test_public_validator_accepts_existing_edges(current, target):
    import_module("daesingo.common.job_execution").validate_transition(current, target)


@pytest.mark.parametrize("current,target", [("SUCCEEDED", "RUNNING"), ("QUEUED", "SUCCEEDED"),
                                           ("RUNNING", "QUEUED"), ("UNKNOWN", "RUNNING")])
def test_public_validator_rejects_invalid_edges(current, target):
    module = import_module("daesingo.common.job_execution")
    with pytest.raises(module.JobExecutionError) as error:
        module.validate_transition(current, target)
    assert error.value.code == "INVALID_STATUS_TRANSITION"
