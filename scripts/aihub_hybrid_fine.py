#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["openai>=1.40,<3", "pydantic>=2,<3", "typer", "numpy<2", "pycocotools"]
# ///
# How to run: uv run --extra eval-gemini --with typer --with pycocotools python -m scripts.aihub_hybrid_fine CANDIDATES_JSON VIDEO_DIR ENV_FILE OUTPUT_JSONL
"""Checkpoint real sol Fine calls; never read event truth during inference."""

from __future__ import annotations

import base64
import hashlib
import tempfile
import time
from pathlib import Path
from typing import ClassVar

import typer
from openai import APIError, OpenAI
from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam
from pydantic import BaseModel, ConfigDict

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env
from daesingo.search.prompts import fine_prompt_for
from daesingo.search.schemas import FineResponse
from daesingo.search.scope import VisualEventType
from scripts.aihub_hybrid_candidates import Candidate, CandidateSet
from scripts.aihub_lrcn_prompt import classification_prompt
from scripts.gemini_fine_image_accuracy import _extract


class FineResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    candidate_index: int
    candidate: Candidate
    candidates_sha256: str
    window: tuple[float, float]
    target_hint: str
    frames: int
    frame_sha256: tuple[str, ...]
    prompt_sha256: str
    model: str | None
    response: FineResponse | None
    input_tokens: int | None
    output_tokens: int | None
    latency_sec: float
    failure: str | None


def run(
    candidates_json: Path,
    video_dir: Path,
    env_file: Path,
    output_jsonl: Path,
    limit: int = 1000,
) -> None:
    candidates = CandidateSet.model_validate_json(
        candidates_json.read_text(encoding="utf-8")
    )
    candidate_hash = hashlib.sha256(candidates_json.read_bytes()).hexdigest()
    durations = {v.file: v.duration_sec for v in candidates.clips}
    env = load_env_file(str(env_file))
    config = GeminiSearchConfig.from_dotenv(env)
    assert config.model == "gpt-5.6-sol"
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    done: set[int] = set()
    if output_jsonl.exists():
        for line in output_jsonl.read_text(encoding="utf-8").splitlines():
            row = FineResult.model_validate_json(line)
            assert row.candidates_sha256 == candidate_hash
            done.add(row.candidate_index)
    count = 0
    with OpenAI(
        base_url=config.base_url,
        api_key=api_key_from_env(env),
        max_retries=0,
        timeout=120,
    ) as client:
        for index, candidate in enumerate(candidates.candidates):
            if index in done or count >= limit:
                continue
            start = max(0.0, candidate.start_sec - 4)
            end = min(durations[candidate.file], candidate.end_sec + 4)
            box = candidate.bbox_xyxy
            if box is None:
                hint = f"LRCN predicts {candidate.event}, score={candidate.score:.6f}; no vehicle hint."
                prompt = classification_prompt(candidate, start, end)
            else:
                assert candidate.image_wh is not None
                w, h = candidate.image_wh
                hint = (
                    f"원본 {candidate.peak_sec:.2f}초(제공 구간 시작 후 {candidate.peak_sec - start:.2f}초)에 "
                    f"화면 x={100 * box[0] / w:.1f}~{100 * box[2] / w:.1f}%, y={100 * box[1] / h:.1f}~{100 * box[3] / h:.1f}%에 있는 차량. "
                    "이 위치는 자동 탐지한 대상 후보이며 위반 여부는 미확정이다. 같은 차량을 전후 프레임에서 확인하라."
                )
                event = VisualEventType(candidate.event)
                template = fine_prompt_for(event)
                prompt = template.render(
                    event_type=event.value,
                    target_hint=hint,
                    start_sec=start,
                    end_sec=end,
                )
            prompt += "\n제공 이미지는 원본 시간 순서로 초당 4장이다. 첫 이미지부터의 상대 시각으로 답하라. 자동 후보와 선 종류는 틀릴 수 있으니 원본 픽셀로 독립 확인하라."
            response: FineResponse | None = None
            returned_model: str | None = None
            input_tokens: int | None = None
            output_tokens: int | None = None
            failure: str | None = None
            with tempfile.TemporaryDirectory(prefix="aihub_fine_") as directory:
                frames = _extract(
                    video_dir / candidate.file, start, end, 4, Path(directory), 720
                )
                content: list[ChatCompletionContentPartParam] = [
                    {"type": "text", "text": prompt}
                ]
                hashes: list[str] = []
                for frame in frames:
                    data = frame.read_bytes()
                    hashes.append(hashlib.sha256(data).hexdigest())
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,"
                                + base64.b64encode(data).decode()
                            },
                        }
                    )
                messages: list[ChatCompletionMessageParam] = [
                    {"role": "user", "content": content}
                ]
                began = time.monotonic()
                try:
                    completion = client.chat.completions.parse(
                        model=config.model,
                        messages=messages,
                        response_format=FineResponse,
                        reasoning_effort="low",
                    )
                    returned_model = completion.model
                    response = completion.choices[0].message.parsed
                    if completion.usage:
                        input_tokens = completion.usage.prompt_tokens
                        output_tokens = completion.usage.completion_tokens
                    if returned_model != config.model:
                        failure = "MODEL_ROUTING_MISMATCH"
                    elif response is None:
                        failure = "NO_PARSE"
                    elif any(
                        f.at_offset_ms is not None
                        and f.at_offset_ms > round((end - start) * 1000 + 250)
                        for f in response.temporal_facts
                    ):
                        failure = "RESPONSE_TIME_OUT_OF_BOUNDS"
                except APIError as error:
                    failure = (
                        f"{type(error).__name__}:{getattr(error, 'status_code', None)}"
                    )
                result = FineResult(
                    candidate_index=index,
                    candidate=candidate,
                    candidates_sha256=candidate_hash,
                    window=(start, end),
                    target_hint=hint,
                    frames=len(frames),
                    frame_sha256=tuple(hashes),
                    prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    model=returned_model,
                    response=response,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_sec=round(time.monotonic() - began, 3),
                    failure=failure,
                )
            with output_jsonl.open("a", encoding="utf-8") as stream:
                _ = stream.write(result.model_dump_json() + "\n")
                stream.flush()
            count += 1
            label = response.verification.value if response else "FAILED"
            print(
                f"{index + 1}/{len(candidates.candidates)} {candidate.file} {candidate.event} {start:.1f}-{end:.1f} {label} failure={failure} {result.latency_sec}s tokens={input_tokens}",
                flush=True,
            )


if __name__ == "__main__":
    typer.run(run)
