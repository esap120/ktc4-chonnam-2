# `case` — Workflow / Orchestration — 유일한 지휘자

**Owner:** 유소연 (`docs/management/ownership.md`) · **경계:** `docs/architecture/module-architecture.md` §4-모듈5 · **문서 작업공간:** `docs/modules/case/`

## 이 폴더가 하는 일 (요약 — 원문은 §4-모듈5)

자연어 단서 구조화·상태 기계·Candidate selection·**`JobIntent` 생성**·rerun_policy·`EvidenceNeeds` → JobIntent·stale 결과 적용 여부·`CaseView` projection·`USER_REVIEWED`·correction 로그 export

## 이 폴더가 알면 안 되는 것 (§4-모듈5 「알면 안 되는 것」)

130MB 등 규정 숫자 / OCR threshold / prompt 내용 / Overlay가 왜 우선인지 같은 evidence 정책 / codec·ffmpeg / Worker lifecycle 구현(그건 `common/`)

## 공개 함수

§4-모듈5 「Public Capability」의 함수 이름은 설계 시점 placeholder였다. 1차 구현 실제 코드 기준
확정본과 각 함수의 근거·검증 현황은 **`docs/modules/case/tech-spec.md`**(Tech Spec)에 정리했다 —
이 README는 요약만 남긴다.

- `domain.CaseAggregate` — 상태 기계 + selection_rev를 갖는 Case 애그리게잇(`intake`/`start_search`/`receive_candidates`/`select_candidate`/`mark_ready`/`next_job_id`)
- `jobs` — JobRecord 발주 7종(`issue_coarse_search`/`issue_plate_read`/`issue_overlay_time_read`/`issue_fine_verify`/`issue_report_video_export`/`issue_resume_search`/`issue_plate_reread`)
- `correction.apply_correction` — CorrectionRecord 생성(case가 Producer)
- `view.build_case_view` — CaseView projection(web의 유일한 read 경로, `case-view/v1.3`)
- `reflection.reflect_execution` — Worker T2가 terminal execution을 넘기는 반영 진입점(`execution_id` 중복 제거 · 기다리는 job만 반영, `docs/modules/case/decisions/result-reflection.md`)
- `adapters.MockFixtureAdapter` — 1차 구현 한정 내부 stand-in, **공개 API 아님**(Tech Spec §7 참고)

다른 모듈은 위 공개 함수들만 호출한다 — `MockFixtureAdapter`는 예외.

## 상태

1차 구현 완료(happy path, `scenario_happy_001`). 상태 기계·JobRecord 발주·CorrectionRecord·CaseView
projection이 코드로 존재하고, `tests/test_scenario_happy_smoke.py`가 그 재현을 검증하며
`scripts/check_boundaries.py` 경계 검사도 통과했다 — 근거·제외 범위는
`docs/modules/case/checklists/phase1-completion-checklist.md` 참고. FastAPI 엔드포인트 배선·
영속성(DB)·역행 전이·나머지 6개 시나리오는 §11(1차 완료 제외 범위)로 다음 라운드에 다룬다.
