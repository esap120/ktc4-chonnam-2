"""Contract validation errors must never retain the private DB row."""

from datetime import datetime, timezone
import logging
import re
from types import MappingProxyType

from pydantic import ValidationError
import pytest

from daesingo.common.jobs import repository


CONTRACT_FIELDS = {
    "contract", "contract_version", "execution_id", "job_id", "status", "attempt",
    "queued_at", "started_at", "ended_at", "produced", "failure_kind", "usage_refs",
}
INTERNAL_COLUMNS = (
    "claim_token", "lease_owner", "lease_expires_at", "heartbeat_at", "available_at",
    "cancel_requested_at", "case_applied_at", "trace_id", "kind", "case_id",
    "future_private_column",
)
SECRET = "synthetic-private-secret-p2"
PATH = "/synthetic/private/path-p2"


def assert_private_input_absent(error, private_values, caplog):
    representations = {
        "str": str(error), "repr": repr(error), "json": error.json(),
        "errors": repr(error.errors()),
    }
    # Log the actual error renderings, rather than relying on a masking logger.
    logger = logging.getLogger("tests.validation_privacy")
    for name, rendered in representations.items():
        assert all(value not in rendered for value in private_values), (
            "private DB value retained in " + name
        )
        assert not any(re.search(r"\b" + column + r"\b", rendered)
                       for column in INTERNAL_COLUMNS), "private DB column retained in " + name
    # Preserve the original Pydantic model-validation failure, including its input.
    details = error.errors()
    assert any(detail["loc"] == () and detail["type"] == "value_error" for detail in details)
    assert all(set(detail["input"]) == CONTRACT_FIELDS for detail in details)
    for name, rendered in representations.items():
        logger.error("validation %s: %s", name, rendered)
    assert all(value not in caplog.text for value in private_values), "private value logged"


def db_row():
    now = datetime(2026, 10, 9, 1, 2, 3)
    return {
        "execution_id": "execution", "job_id": "job", "status": "RUNNING", "attempt": 1,
        "queued_at": now, "started_at": now, "ended_at": None, "produced": [],
        "failure_kind": None,
        **{column: SECRET + PATH for column in INTERNAL_COLUMNS},
    }


@pytest.mark.parametrize("private_changes", [False, True])
def test_validation_error_retains_only_contract_input(private_changes, caplog):
    source = db_row()
    before = source.copy()
    changes = {"status": "FAILED", "ended_at": source["started_at"]}
    if private_changes:
        changes.update({column: "override-" + SECRET + PATH for column in INTERNAL_COLUMNS})
    with pytest.raises(ValidationError) as caught:
        repository._execution_model(MappingProxyType(source), **changes)
    assert_private_input_absent(caught.value, [SECRET, PATH], caplog)
    assert source == before


def test_contract_projection_keeps_valid_state_and_does_not_mutate_db_row():
    source = db_row()
    before = source.copy()
    model = repository._execution_model(MappingProxyType(source))
    assert model.status == "RUNNING" and model.failure_kind is None
    assert model.started_at == datetime(2026, 10, 9, 1, 2, 3, tzinfo=timezone.utc)
    assert set(model.model_dump()) == CONTRACT_FIELDS
    assert model.produced == model.usage_refs == []
    assert source == before
