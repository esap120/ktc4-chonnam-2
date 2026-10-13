# real E2E 시나리오 확장 · 관련 asset 선택 (4 · 5순위)

> **상태: 결정** · 결정일 2026-10-12 · 담당 유소연(`case`) · 근거 W7 고도화 4순위 · 5순위(`../design-refinement-w7-baseline.md`), `real_e2e.py` 모듈 docstring 「시나리오 고정」, readout 계약 §3 `source_profile`, `reselect-observation-reuse.md`
> fixture를 real 공개 함수로 어디까지 돌리는지와 case가 어떤 asset을 「이 case 것」으로 넘기는지는 case 결정 범위다. 어떤 역할의 asset이 신고 요건에 쓰이는지는 evidence 규칙이고(여기서 다시 정하지 않는다), `data/mock/{recording,search,readout,evidence}` fixture는 각 모듈 소유라 고치지 않는다.

## 1. 목표 · 범위

real 경로(`real_e2e.py` · `RealAdapter`)가 `scenario_happy_001` 하나에 고정돼 있다. Mock 경로가 다루는 시나리오를 real 공개 함수로도 돌려, 같은 시나리오에서 Mock과 같은 결론을 내는지 확인한다. 함께 `asset_refs = fixture의 asset_facts 전부`를 case 규칙으로 바꾼다.

**범위 밖:** 실영상 경로(`RealVideoAdapter`) · `observation_facts`(I4, #280) · GPS · Mock 경로 변경 · 다른 모듈 fixture 추가.

## 2. 시나리오 — 5/7을 real로, 2개는 다른 경로

| 시나리오 | real 경로 | 이유 |
| --- | --- | --- |
| happy_001 | ✅(기존) | — |
| unknown_abstain_partial_001 | ✅ | 지금은 `UNCERTAIN`을 monkeypatch로 흉내 낸다 — fixture Fine 결과로 바꾼다 |
| correction_rerun_001 | ✅ | 사건 시각 정정 뒤 조립만 다시(이슈 #73) |
| plate_reread_001 | ✅ | `PLATE_REREAD` 재판독까지(§4-3) |
| empty_001 | ✅ | 후보 0개 — 관찰 단계에 들어가지 않는다 |
| infra_failure_001 | ✗ 비동기 E2E(RT-09 · RT-10) 몫 | Runtime 실행 실패(STALE → FAILED, 재판독 취소)를 검증한다. 동기 real 경로에는 job 실행이 없다. search fixture · recording 구간도 없다 |
| relative_rebase_001 | ✗ 범위 밖 | 선택 전 timeline rebase다. real 경로는 선택 뒤부터 관찰하고, recording에 rebase 공개 함수가 없다. rev1 구간 · readout fixture도 없다 |

## 3. fixture가 real 함수에 들어가는 길 (확인한 사실)

시나리오 이름으로 찾는 곳은 recording fixture 로드 하나뿐이다. 나머지는 값으로 찾는다.

- search — `search_candidates`는 `scope.scope_id`, `verify_visual`은 `input_ref`(AnalysisSource ref)로 찾는다.
- readout — `FixtureOcrProvider`는 `(incident_clip_ref, source_profile)`로 찾는다.
- recording — `RecordingService.from_fixture`가 시나리오 fixture를 등록하고, `resolve_span`은 등록된 구간으로 찾는다.

그래서 시나리오를 넓히는 일은 「`SCENARIO_ID` 상수와 `[0]` 가정을 걷어내는 것」이다.

## 4. 결정

1. **happy 고정을 걷어낸다.** `observe_happy_001_candidate` · `build_happy_001_evidence_bundle`을 `observe_fixture_candidate` · `build_fixture_evidence_bundle(scenario_id=…)`로 바꾸고 `RealAdapter(scenario_id=…)`를 받는다(기본 happy — 기존 호출 그대로). fixture의 AnalysisSource가 하나일 때만 그 profile을 쓰고, 아니면 오류다(조용히 `[0]`을 쓰지 않는다 — 5개 시나리오는 모두 하나다). `time_source_candidates` 직접 읽기(알려진 단순화 1)는 그대로 두고 시나리오 파일만 바뀐다.
2. **관련 asset은 lineage로 고른다(5순위).** 순수 함수 `select_case_assets(incident_clip_ref, asset_facts)` — 선택 후보의 IncidentClip 자신과, `lineage`에 그 clip ref가 있는 asset만 남긴다(clip 자신의 AssetFacts는 lineage에 자기가 없다). **역할(`derived_role`)로는 거르지 않는다** — 어느 역할이 패키지에 쓰이는지는 evidence가 정한다(`_package_assets`). 후보 목록은 인자로 받는다: fixture 경로는 `fixture.asset_facts`, 8-6 2단계 `StoredObservationAdapter`는 recording 공개 조회 결과(`observation-storage.md`). 다른 clip · 다른 후보의 asset이 섞이면 지금은 막는 곳이 없고, 같은 역할이 둘이면 evidence가 오류를 낸다 — 이 규칙이 둘 다 막는다.
3. **재판독은 `readout-native-hires`로 한다.** `RealAdapter`는 `PLATE_REREAD`로 발주된 `PLATE_READ` job(`force_rerun`)을 보면 같은 IncidentClip을 `readout-native-hires`로 다시 읽고 조립을 다시 한다. 프로파일은 readout 계약 §3 「abstain 뒤 재판독할 때 쓴다」를 따른다 — case가 새로 정하는 값이 아니다. 관찰 캐시 키에 「그 후보의 재판독 수」를 더한다 — JobRecord에 후보가 없어(6.6순위) 지난 조립 뒤 새로 발주된 재판독을 그때 선택된 후보에 붙인다. 세대가 바뀌면 재판독 수도 버린다. A→B→A 재사용 규칙(`reselect-observation-reuse.md`)은 그대로다. **한계:** 발주와 다음 조립 사이에 선택을 바꾸면 재판독이 바뀐 후보에 붙는다 — 동기 adapter 한정이고, 8-6 2단계는 결과 객체의 `candidate_id`로 고른다(`observation-storage.md` §4-4).
4. **판정은 case fixture의 마지막 CaseView와 핵심 사실을 대조한다.** 대조 원본은 `data/mock/case/<scenario>.json`의 `case_views` 마지막 항목(case 소유 fixture)이다. `data/mock/expected/*.expected.json`은 eval 채점 목표(`metric_targets`)라 CaseView 결론을 담지 않는다. real 경로는 id · 시각을 새로 만들어 통째로 같아질 수 없으므로 아래만 본다 — 값은 테스트에 다시 적지 않고 fixture에서 읽는다.
   - `stage` · notice `code` 집합 · `package` 유무 · `evidence.plate_display` · `evidence.event_time_display` · 후보 수
5. **어긋나면 가른다.** case 버그는 고친다. fixture와 다른 모듈 real 함수가 서로 맞지 않는 것은 고치지 않고 §6 「발견 사항」에 남기고, 그 시나리오는 맞는 지점까지만 검증한다.

## 5. 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| 다른 모듈에 fixture를 요청해 7/7 | fixture가 생겨도 infra는 동기 경로에 job 실행이 없어 기대 결론(4 revision · STALE/FAILED)에 못 간다. 다른 사람을 기다린다 |
| 기대값을 테스트에 직접 적기 | fixture와 테스트에 같은 값이 두 번 생긴다 |
| asset을 lineage + 역할로 거르기 | 「어느 역할이 패키지에 필요한가」(evidence 규칙)가 case에 한 벌 더 생긴다 |
| 재판독 프로파일을 case가 고른다 | readout 계약 §3이 이미 정했다 |

## 6. 발견 사항

구현하며 찾은 것. case가 고칠 것이 아니라 고치지 않았고, `tests/case/test_real_e2e_scenarios.py`의 `UNDERIVED_NOTICES` · `KNOWN_GAPS`에 이름만 두었다 — 원인이 풀리면 테스트가 「차이가 사라졌다」로 실패한다.

1. **Mock fixture에만 있는 notice 3종** — `evidence.time_post_stamp_required` · `evidence.time_conflict_needs_notice` · `evidence.visual_event_unconfirmed`. `data/mock/case/`의 CaseView에는 있지만 이 code를 만드는 코드가 어디에도 없다. 어느 모듈이 어떤 근거로 붙일지는 notice 규칙을 새로 정하는 일이라 이번 범위 밖이다. *(처음 4종이던 `case.report_video_not_generated`는 #351로 발동 조건을 정해 case가 붙인다 — `report-video-export.md`.)*
2. **unknown_abstain_partial_001은 real에서 `READY`가 되지 않는다.** 「잘 모르겠어요」 응답 뒤에도 FINAL `package.time.post_stamp_applied`가 `UNKNOWN`(`time.post_stamp.not_observed`)이다 — `observation_facts`가 없다(I4, #280, `real_e2e.py` 알려진 단순화 2). 번호판 · 시각 · 상황 응답 · notice는 fixture와 같다.
3. **판정 시각이 실제 현재 시각이다.** real 조립의 `evaluated_at`이 `datetime.now()`라 deadline check가 시나리오 날짜(2026-08) 기준 `EXCEEDED`(WARN)다. 5개 시나리오의 readiness는 바뀌지 않지만, 날짜에 따라 결과가 달라질 수 있는 입력이다.
4. **domain `reselect_candidate()`만 부르면 `RealAdapter`가 다시 조립하지 않는다.** adapter 캐시는 `case_rev`로 판단하는데 재선택은 `correction.reselect_candidate()`(CorrectionRecord · `case_rev` +1)를 거쳐야 오른다. command 경로는 늘 그쪽이라 문제는 아니고, 테스트는 correction 경로를 쓴다.

## 7. 테스트

- `tests/case/test_real_e2e_scenarios.py` — 5개 시나리오 parametrize, 마지막 CaseView 대조(§4-4).
- `tests/case/test_case_asset_selection.py` — 다른 clip의 `REPORT_VIDEO`가 섞인 목록 · clip 자신 · lineage 없는 asset · 빈 목록 · recording `AssetFacts` 모델.
- `tests/case/test_real_plate_reread.py` — hires 재판독으로 번호판 · Need 해소, 재판독은 발주한 후보에만(A→B→A), 세대가 바뀌면 재판독 수를 버림.
- 기존 `test_real_e2e.py` · `test_correction_partial_rerun.py` · `test_await_situation_response.py`는 새 이름으로 그대로 통과.
