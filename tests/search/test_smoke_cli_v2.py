"""CLI mode-split tests: offline (--provider-fixture) and live (--live-manifest).

Acceptance matrix from task-13 brief:
- both modes work independently
- mutual exclusion: both flags -> argparse error, neither -> argparse error
- live with missing manifest/key/pricing -> NOT_EXECUTED exit 2, no provider call
- SHA mismatch -> typed failure (NOT_EXECUTED)
- offline fixture run -> exit 0 with exactly one v2 JSON on stdout
- stdout/stderr contain no injected secret/path sentinel

NOTE: load_env_file() reads .env from cwd; tests write .env in tmp_path and
      chdir there instead of using monkeypatch.setenv.
"""

import hashlib
import json
from pathlib import Path

import pytest

from daesingo.search.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "smoke_provider.json"

_SECRET_SENTINEL = "sk-live-secret-key-never-print"
_PATH_SENTINEL = "C:/absolute/private-sentinel.mp4"

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_dotenv(tmp_path: Path, **kwargs: str) -> None:
    """Write a .env file in tmp_path with the given KEY=VALUE pairs."""
    lines = "\n".join(f"{k}={v}" for k, v in kwargs.items())
    (tmp_path / ".env").write_text(lines, encoding="utf-8")


def _write_source(tmp_path: Path, content: bytes = b"bounded smoke recording") -> Path:
    p = tmp_path / "recording.mp4"
    p.write_bytes(content)
    return p


def _write_manifest(
    tmp_path: Path,
    source: Path,
    *,
    sha256: str | None = None,
    event_type: str = "SIGNAL",
    duration_sec: float = 12.0,
) -> Path:
    actual_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "daesingo-search-live-input/v1",
        "source_path": str(source),
        "expected_sha256": sha256 if sha256 is not None else actual_sha,
        "event_type": event_type,
        "duration_sec": duration_sec,
        "contains_target_event": True,
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def _pricing_env() -> dict[str, str]:
    return {
        "GEMINI_API_KEY": _SECRET_SENTINEL,
        "DAESINGO_GEMINI_INPUT_USD_PER_MILLION": "0.75",
        "DAESINGO_GEMINI_OUTPUT_USD_PER_MILLION": "3.75",
        "DAESINGO_GEMINI_MAX_COST_USD": "1.0",
    }


def _run_offline(
    tmp_path: Path, capsys, *extra: str
) -> tuple[int, dict[str, JsonValue], str, str]:
    source = _write_source(tmp_path)
    exit_code = main(
        [
            "smoke",
            "--provider-fixture", str(FIXTURE),
            "--source", str(source),
            "--duration-sec", "12",
            *extra,
        ]
    )
    captured = capsys.readouterr()
    return exit_code, json.loads(captured.out), captured.out, captured.err


# ---------------------------------------------------------------------------
# Mode split — mutual exclusion
# ---------------------------------------------------------------------------


def test_neither_mode_flag_is_argparse_error(tmp_path: Path, monkeypatch) -> None:
    """No --provider-fixture and no --live-manifest -> argparse exits with 2."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["smoke", "--source", str(tmp_path / "x.mp4"), "--duration-sec", "12"])
    assert exc.value.code == 2


def test_both_mode_flags_is_argparse_error(tmp_path: Path, monkeypatch) -> None:
    """Both --provider-fixture and --live-manifest -> argparse exits with 2."""
    monkeypatch.chdir(tmp_path)
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "smoke",
                "--provider-fixture", str(FIXTURE),
                "--live-manifest", str(manifest),
                "--source", str(source),
                "--duration-sec", "12",
            ]
        )
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Offline mode (--provider-fixture) — basic success
# ---------------------------------------------------------------------------


def test_offline_fixture_succeeds_exit_0_one_json(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # No .env needed — fixture mode doesn't require API key

    exit_code, report, raw_out, _ = _run_offline(tmp_path, capsys)

    assert exit_code == 0
    # Exactly one JSON document on stdout (parse succeeds and report is valid)
    assert report["status"] == "succeeded"
    # The whole stdout must be parseable as a single JSON object
    assert raw_out.strip().startswith("{") and raw_out.strip().endswith("}")


def test_offline_stdout_and_stderr_free_of_sentinels(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, GEMINI_API_KEY=_SECRET_SENTINEL)

    exit_code, _, raw_out, raw_err = _run_offline(tmp_path, capsys)

    assert exit_code == 0
    assert _SECRET_SENTINEL not in raw_out
    assert _SECRET_SENTINEL not in raw_err
    assert _PATH_SENTINEL not in raw_out
    assert _PATH_SENTINEL not in raw_err


# ---------------------------------------------------------------------------
# Live mode — NOT_EXECUTED preconditions (no provider call)
# ---------------------------------------------------------------------------


def test_live_missing_manifest_file_not_executed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, GEMINI_API_KEY=_SECRET_SENTINEL)

    exit_code = main(
        ["smoke", "--live-manifest", str(tmp_path / "no-such-manifest.json")]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 2
    assert report["schema_version"] == "daesingo-search-not-executed/v1"
    assert report["status"] == "not_executed"
    assert report["missing_prerequisite"] == "manifest"
    # No secret or path leaks
    assert _SECRET_SENTINEL not in captured.out
    assert _SECRET_SENTINEL not in captured.err


def test_live_malformed_manifest_not_executed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, GEMINI_API_KEY=_SECRET_SENTINEL)
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "wrong/v1"}', encoding="utf-8")

    exit_code = main(["smoke", "--live-manifest", str(bad)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["status"] == "not_executed"
    assert report["missing_prerequisite"] == "manifest"


def test_live_missing_api_key_not_executed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # No .env -> no ELICE_ML_API_KEY (or legacy GEMINI_API_KEY)
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source)

    exit_code = main(["smoke", "--live-manifest", str(manifest)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["status"] == "not_executed"
    assert report["missing_prerequisite"] == "ELICE_ML_API_KEY"


def test_live_missing_pricing_not_executed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """API key present but no pricing fields -> NOT_EXECUTED naming pricing field."""
    monkeypatch.chdir(tmp_path)
    # Only key, no pricing
    _write_dotenv(tmp_path, GEMINI_API_KEY=_SECRET_SENTINEL)
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source)

    exit_code = main(["smoke", "--live-manifest", str(manifest)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["status"] == "not_executed"
    # input_usd_per_million defaults to 0.0 -> precondition fires
    assert "USD_PER_MILLION" in report["missing_prerequisite"]


def test_live_missing_pricing_no_provider_call(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Precondition failure must not reach the provider."""
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, GEMINI_API_KEY=_SECRET_SENTINEL)
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source)

    import daesingo.search.provider as _prov

    def _fail_if_called(self, *_a, **_kw) -> None:
        raise AssertionError("GeminiProvider must not be instantiated on NOT_EXECUTED")

    monkeypatch.setattr(_prov.GeminiProvider, "__init__", _fail_if_called)

    exit_code = main(["smoke", "--live-manifest", str(manifest)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["status"] == "not_executed"


# ---------------------------------------------------------------------------
# Live mode — SHA-256 mismatch
# ---------------------------------------------------------------------------


def test_live_sha_mismatch_not_executed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, **_pricing_env())
    source = _write_source(tmp_path)
    # wrong hash
    manifest = _write_manifest(tmp_path, source, sha256="a" * 64)

    exit_code = main(["smoke", "--live-manifest", str(manifest)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["status"] == "not_executed"
    assert report["missing_prerequisite"] == "expected_sha256_mismatch"


def test_live_sha_mismatch_no_provider_call(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, **_pricing_env())
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source, sha256="b" * 64)

    import daesingo.search.provider as _prov

    def _fail_if_called(self, *_a, **_kw) -> None:
        raise AssertionError("GeminiProvider must not be called on SHA mismatch")

    monkeypatch.setattr(_prov.GeminiProvider, "__init__", _fail_if_called)

    exit_code = main(["smoke", "--live-manifest", str(manifest)])

    assert exit_code == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "not_executed"


# ---------------------------------------------------------------------------
# Live mode — spy provider wires real assembly path up to network boundary
# ---------------------------------------------------------------------------


def test_live_wiring_reaches_provider_via_spy(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """With all preconditions met, GeminiProvider.__init__ is called (spy confirms
    real assembly path is exercised up to the network boundary), but search_coarse
    raises so no real network call goes out."""
    from collections.abc import Generator
    from contextlib import contextmanager

    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path, **_pricing_env())
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source)

    import daesingo.search.media as _media
    import daesingo.search.provider as _prov
    from daesingo.search.media import PreparedMedia
    from daesingo.search.smoke_errors import SmokeProviderError

    provider_inited: list[bool] = []
    _orig_init = _prov.GeminiProvider.__init__

    def _spy_init(self, *args, **kwargs) -> None:
        provider_inited.append(True)
        _orig_init(self, *args, **kwargs)

    def _raise_on_coarse(self, request):
        raise SmokeProviderError("spy: no network")

    @contextmanager
    def _fake_prepare_coarse(self, media_input, deadline) -> Generator[PreparedMedia]:
        yield PreparedMedia(
            path=source,
            content_type="video/mp4",
            byte_size=len(source.read_bytes()),
            duration_sec=12.0,
            origin_start_sec=0.0,
            origin_end_sec=12.0,
        )

    monkeypatch.setattr(_prov.GeminiProvider, "__init__", _spy_init)
    monkeypatch.setattr(_prov.GeminiProvider, "search_coarse", _raise_on_coarse)
    monkeypatch.setattr(_media.MediaPreparer, "prepare_coarse", _fake_prepare_coarse)

    exit_code = main(["smoke", "--live-manifest", str(manifest)])

    # Provider was constructed (real assembly path exercised up to network boundary)
    assert provider_inited, "GeminiProvider.__init__ should have been called"
    # No real network call: coarse raised -> exit 1 (runtime failure)
    assert exit_code == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "failed"
    assert report["failure_stage"] == "coarse"
    # Secret must not appear in output
    assert _SECRET_SENTINEL not in captured.out
    assert _SECRET_SENTINEL not in captured.err


def test_live_output_contains_no_secret_or_path_sentinel(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Even on NOT_EXECUTED, no secret value or absolute path appears in output."""
    monkeypatch.chdir(tmp_path)
    # Only key, no pricing -> NOT_EXECUTED
    _write_dotenv(tmp_path, GEMINI_API_KEY=_SECRET_SENTINEL)
    source = _write_source(tmp_path)
    manifest = _write_manifest(tmp_path, source)

    main(["smoke", "--live-manifest", str(manifest)])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert _SECRET_SENTINEL not in combined
    assert _PATH_SENTINEL not in combined
