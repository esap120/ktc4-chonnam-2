"""Opt-in local diagnostic CLI; not a product Search command or eval-mode branch."""

import argparse
import hashlib
import json
import math
import subprocess
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from daesingo.common import load_env_file

from .config import GeminiSearchConfig, api_key_from_env
from .diagnostic import DiagnosticDependencies, run_case
from .diagnostic_artifacts import (
    ArtifactLocationError,
    DiagnosticFixture,
    FixtureInvoker,
    safe_summary,
    prepare_artifact_directory,
    store_result,
)
from .diagnostic_models import (
    DiagnosticContext,
    DiagnosticManifest,
    DiagnosticProfile,
    DiagnosticRunResult,
)
from .errors import UnsafeGeminiBaseUrlError
from .execution import DeadlineExceededError, RunDeadline
from .media import (
    ByteSizeMismatchError,
    FfmpegError,
    FfprobeError,
    MediaPreparer,
    MediaTooLargeError,
    MissingFfmpegError,
    SourceTooLargeError,
    _probe,
)
from .provider import GeminiProvider


class DiagnosticPreconditionError(Exception):
    """No provider call is allowed when local input prerequisites fail."""


def _manifest(path: Path, config: GeminiSearchConfig) -> DiagnosticManifest:
    parsed = DiagnosticManifest.model_validate_json(path.read_text(encoding="utf-8"))
    cases = tuple(
        case.model_copy(update={"source": (path.parent / case.source).resolve()})
        for case in parsed.cases
    )
    for case in cases:
        if (
            not case.source.is_file()
            or case.source.stat().st_size > config.max_materialized_source_bytes
        ):
            raise DiagnosticPreconditionError("source prerequisite failed")
        probe = _probe(case.source, RunDeadline(time.monotonic, 30000))
        if (
            not (0 < probe.duration_sec <= 60)
            or abs(probe.duration_sec - case.duration_sec) > 0.25
        ):
            raise DiagnosticPreconditionError("duration prerequisite failed")
    return parsed.model_copy(update={"cases": cases})


def _implementation_fingerprint() -> str:
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted((*root.glob("*.py"), *root.glob("prompt_resources/*.txt"))):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m daesingo.search.diagnostic_cli")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=[item.value for item in DiagnosticProfile],
        default="diagnostic-v1",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--provider-fixture", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=180)
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout_sec) or not 0 < args.timeout_sec <= 3600:
            raise DiagnosticPreconditionError("timeout prerequisite failed")
        env = load_env_file(str(args.env_file))
        config = replace(GeminiSearchConfig.from_dotenv(env), max_retries=0)
        manifest = _manifest(args.manifest.resolve(), config)
        prepare_artifact_directory(Path.cwd())
        provider = None
        mode = "LIVE"
        if args.provider_fixture is not None:
            fixture = DiagnosticFixture.model_validate_json(
                args.provider_fixture.read_text(encoding="utf-8")
            )
            provider = FixtureInvoker(fixture)
            mode = "FIXTURE"
        else:
            key = api_key_from_env(env)
            if not key:
                raise DiagnosticPreconditionError("api key prerequisite failed")
            provider = GeminiProvider(key, config)
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        context = DiagnosticContext.model_validate(
            {
                "run_id": "trace_" + uuid4().hex,
                "created_at": datetime.now(UTC).isoformat(),
                "mode": mode,
                "profile": args.profile,
                "git_sha": sha,
                "implementation_fingerprint": _implementation_fingerprint(),
                "model": config.model,
                "config_fingerprint": config.fingerprint,
                "coarse_fps": config.coarse_fps,
                "fine_fps": config.fine_fps,
                "fine_padding_sec": config.fine_padding_sec,
                "reasoning_effort": config.reasoning_effort,
                "timeout_sec": args.timeout_sec,
                "input_usd_per_million": config.input_usd_per_million,
                "output_usd_per_million": config.output_usd_per_million,
            }
        )
        dependencies = DiagnosticDependencies(
            provider,
            MediaPreparer(config),
            config,
            DiagnosticProfile(args.profile),
            args.timeout_sec,
        )
    except (
        OSError,
        UnicodeError,
        ValidationError,
        UnsafeGeminiBaseUrlError,
        ValueError,
        DiagnosticPreconditionError,
        ArtifactLocationError,
        subprocess.CalledProcessError,
        DeadlineExceededError,
        FfprobeError,
        FfmpegError,
        MissingFfmpegError,
        ByteSizeMismatchError,
        SourceTooLargeError,
        MediaTooLargeError,
    ):
        print(
            json.dumps(
                {
                    "schema_version": "search-decision-trace/v1",
                    "status": "NOT_EXECUTED",
                    "issue_code": "INVALID_INPUT",
                }
            )
        )
        return 2
    result = DiagnosticRunResult(
        context=context,
        cases=tuple(run_case(case, dependencies) for case in manifest.cases),
    )
    try:
        paths = store_result(result, Path.cwd())
    except (OSError, ArtifactLocationError):
        print(
            json.dumps(
                {
                    "schema_version": "search-decision-trace/v1",
                    "status": "FAILED",
                    "issue_code": "OUTPUT_WRITE_FAILED",
                }
            )
        )
        return 1
    summary = safe_summary(result, paths)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["failures"] or summary["diagnostic_issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
