"""The Runtime port carries immutable facts, not Case-owned intent/payload."""

from dataclasses import FrozenInstanceError
from importlib import import_module
import warnings

import pytest

from daesingo.common.jobs.execution import HandlerResult


def port():
    try:
        module = import_module("daesingo.common.jobs.reflection")
    except ModuleNotFoundError:
        module = None
    assert module is not None, "RT-04(b) reflection port is missing"
    return module


def incoming(module):
    return module.ReflectionInput("exec", "job", "case", "TEST", 1, HandlerResult())


@pytest.mark.parametrize("status,reason", [
    ("APPLIED", None), ("ALREADY_APPLIED", None),
    ("NOT_APPLIED", "STOPPED_WAITING"), ("NOT_APPLIED", "CANCELLED"), ("NOT_APPLIED", "SUPERSEDED"),
])
def test_reflection_taxonomy_is_immutable(status, reason):
    module = port()
    result = module.ReflectionResult(status, reason)
    assert result.status == status and result.reason == reason and result.jobs == ()
    with pytest.raises(FrozenInstanceError):
        result.status = "APPLIED"


@pytest.mark.parametrize("status,reason", [
    ("ALREADY_APPLIED", None), ("NOT_APPLIED", "STOPPED_WAITING"),
    ("NOT_APPLIED", "CANCELLED"), ("NOT_APPLIED", "SUPERSEDED"),
])
def test_only_applied_may_issue_followup_jobs(status, reason):
    module = port()
    job = module.RuntimeJobRecord("follow", "case", "FOLLOW")
    with pytest.raises(ValueError, match="invalid reflection"):
        module.ReflectionResult(status, reason, (job,))


@pytest.mark.parametrize("status,reason", [
    ("APPLIED", "STOPPED_WAITING"), ("ALREADY_APPLIED", "CANCELLED"),
    ("NOT_APPLIED", None), ("NOT_APPLIED", "secret /private/path"), ("secret /private/path", None),
])
def test_bad_taxonomy_errors_do_not_echo_input(status, reason):
    module = port()
    with pytest.raises(ValueError) as error:
        module.ReflectionResult(status, reason)
    assert all(s not in str(error.value) for s in ("secret", "private", "payload"))


def test_input_and_followups_are_frozen_and_snapshot_mutable_sequences():
    module = port()
    value = incoming(module)
    with pytest.raises(FrozenInstanceError):
        value.attempt = 2
    job = module.RuntimeJobRecord("follow", "case", "FOLLOW")
    with pytest.raises(FrozenInstanceError):
        job.kind = "OTHER"
    jobs = [job]
    result = module.ReflectionResult("APPLIED", jobs=jobs)
    jobs.clear()
    assert result.jobs == (job,)


@pytest.mark.parametrize("field,value", [("attempt", True), ("attempt", 0), ("job_id", "secret\uac00/private"),
                                        ("terminal", {"payload": "secret /private/path"})])
def test_invalid_input_is_sanitized(field, value):
    module = port()
    fields = dict(execution_id="exec", job_id="job", case_id="case", kind="TEST", attempt=1, terminal=HandlerResult())
    fields[field] = value
    with pytest.raises(ValueError) as error:
        module.ReflectionInput(**fields)
    assert "secret" not in str(error.value) and "private" not in str(error.value)


def test_extra_fields_are_rejected_without_payload():
    module = port()
    with pytest.raises(TypeError) as error:
        module.ReflectionResult("APPLIED", claim_token="secret /private/path")
    assert "secret" not in str(error.value)


def test_tampered_models_are_revalidated():
    module = port()
    result = module.ReflectionResult("NOT_APPLIED", "STOPPED_WAITING")
    object.__setattr__(result, "reason", "secret /private/path")
    with pytest.raises(ValueError) as error:
        module.validated_result(result)
    assert "secret" not in str(error.value)
    result = module.ReflectionResult("APPLIED")
    with pytest.raises(ValueError):
        module.validated_result({"status": "APPLIED", "claim_token": "secret"})
    job = module.RuntimeJobRecord("follow", "case", "FOLLOW")
    object.__setattr__(job, "job_id", "secret\uac00/private")
    object.__setattr__(result, "jobs", (job,))
    with pytest.raises(ValueError) as error:
        module.validated_result(result)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("model,args", [("ReflectionResult", ("APPLIED",)),
    ("RuntimeJobRecord", ("job", "case", "TEST")),
    ("ReflectionInput", ("exec", "job", "case", "TEST", 1, HandlerResult()))])
def test_unknown_field_names_cannot_disclose_secret_or_path(model, args):
    module = port()
    with pytest.raises(TypeError) as error:
        getattr(module, model)(*args, **{"secret /private/payload": "claim_token"})
    assert all(word not in str(error.value) for word in ("secret", "private", "payload", "claim_token"))


@pytest.mark.parametrize("mode", ["produced", "terminal_extra", "ref_extra", "ref_type"])
def test_tampered_terminal_is_rejected_without_serialization_warning(mode, capsys):
    module = port()
    terminal = HandlerResult(produced=[{"kind": "Candidates", "ref": "cand"}])
    if mode in ("produced", "terminal_extra"):
        terminal = terminal.model_copy(update={"produced" if mode == "produced" else "claim_token": "secret /private/payload"})
    else:
        ref = terminal.produced[0].model_copy(update={"claim_token" if mode == "ref_extra" else "kind": "secret" if mode == "ref_extra" else 123})
        terminal = terminal.model_copy(update={"produced": (ref,)})
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        with pytest.raises(ValueError) as error:
            module.ReflectionInput("exec", "job", "case", "TEST", 1, terminal)
    assert not emitted and capsys.readouterr().err == ""
    assert all(word not in str(error.value) for word in ("secret", "private", "payload", "claim_token"))
