# 모듈 결과의 위치 · case가 읽는 길 — 결과 저장소 · `StoredObservationAdapter` · 관찰 반영 (8-6 2단계)

> **상태: case 쪽 결정 · RT-10 Implementer 확인 대기 · §4-5 구현(2026-10-13 — 저장소와 무관한 정산 · gate만)** · 결정일 2026-10-12 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-6 2단계(`../design-refinement-w7-baseline.md`), 6.6순위 조건 2, #245 D-1 · #246 S-4, Runtime Tech Spec §12.2(T1 · T2), RT-10 Gate, REC-1(#302)
> CaseView를 무엇으로 조립하는지와 T2에서 관찰 결과로 무엇을 하는지는 case 결정 범위다. 8-6 2단계는 Runtime Plan §7이 「case 주도 설계, 새 RD 아님」으로 둔 RT-10 Gate다. 다만 **결과 저장소와 T1에서의 쓰기는 Runtime 구현**이라 RT-10 Implementer(정철원)와 먼저 맞춘다(Plan §12.2 Consult, §8). 그것이 Contract · Tech Spec 의미 변경인지는 Plan §12.3대로 Implementer가 판단해 Runtime/Ops Owner(김준영)에게 올린다. 객체의 뜻 · 모양은 각 모듈 계약 몫이고, recording 저장은 REC-1 몫이다.

## 1. 목표 · 범위

`get_view`와 Worker T2가 프로세스 메모리(case별 `AdapterRegistry`)에 기대지 않는다. 서버가 다시 떠도, API와 Worker가 다른 프로세스여도 같은 CaseView가 나온다. 1단계(`case-store-mysql.md`)가 case 상태를 옮겼고, 이 문서는 남은 「모듈 결과」를 다룬다.

**범위 밖:** `EvidenceNeeds` 자동 재발주(`jobs.issue_needed_jobs` — 사용자 행동 없이 비용 드는 job을 내는 일이라 따로 정한다) · 어느 job handler가 IncidentClip을 만드는가(RT-10 handler 설계) · 결과 저장소 테이블 구현(Runtime) · recording 영속화(REC-1) · 동기 real 경로 제거.

## 2. 지금

| 무엇 | 어디에 있나 |
| --- | --- |
| case 상태 · JobRecord · AnalysisScope | MySQL(8-6 1단계) |
| 실행 기록 · `produced` 참조 | MySQL `job_execution`(Runtime) |
| search · readout 결과 | 프로세스 메모리뿐 — 저장하는 곳이 없다 |
| recording(time source · AssetFact) | `InMemoryRecordingRepository` — REC-1(#302)이 MySQL로 옮긴다 |
| evidence · RequirementReport · ReportPackage | 순수 함수(`real_e2e.assemble_evidence_bundle`)로 그때 계산 |
| CaseView 입력 | case마다 `AdapterRegistry`의 adapter. `RealAdapter` · `RealVideoAdapter`는 view 때 Fine · OCR · IncidentClip을 동기로 돌린다 |

## 3. 흐름

```
[Worker T1] handler 실행 → 같은 tx: terminal 행 + produced + 결과 저장소 append(kind, ref, case_id, execution_id, payload)
[Worker T2] reflect_execution(outcome)
   ├─ HINT_EXTRACT · COARSE_SEARCH → 지금처럼(result-reflection.md) — 내용은 ProducedReader
   └─ PLATE_READ · OVERLAY_TIME_READ · FINE_VERIFY → 정산(REFLECTED) · processed_executions
        └─ stage=EVIDENCE_REVIEW면 mark_ready_if_package_ready(case, store.adapter_for(case))

[API] get_view(case_id)
   └─ store.adapter_for(case) → StoredObservationAdapter(case, conn)
        ├─ read port: 관찰 kind의 execution(produced)
        ├─ ProducedReader: produced → 결과 객체
        ├─ 현재 후보 목록 세대 · 선택 후보의 객체만 남김(§4-4)
        ├─ recording 공개 함수: time source · AssetFact
        └─ assemble_evidence_bundle(…) → evidence · requirements · package (매번 계산)
```

## 4. 결정

1. **search · readout 결과는 common/runtime 결과 저장소에 둔다(RT-10 Implementer 확인 필요).** 모양 예시는 `produced_objects(kind, ref, case_id, execution_id, payload JSON)`이다. Worker가 T1에서 terminal 행 · `produced`와 **같은 transaction**에서 쓴다 — 실행은 끝났는데 내용이 없는 상태가 생기지 않는다. 저장소는 내용을 해석하지 않는 append-only 상자이고, 뜻과 모양은 각 모듈 계약이 정한다. recording은 REC-1의 자기 저장소를 공개 함수로 읽는다(같은 사실을 두 곳에 두지 않는다).
2. **evidence · RequirementReport · ReportPackage는 저장하지 않고 `get_view`마다 다시 계산한다.** 재료(관찰 객체 · recording 사실 · case 상태와 정정)가 모두 저장되어 있고 조립은 순수 함수라, 저장하면 정정 · 재선택 때 무효화할 사본만 늘어난다. `get_view`는 실행 · 관찰을 돌리지 않는다 — 모든 관찰은 job 결과이거나 recording 영속 조회다.
3. **`ModuleAdapter` Protocol은 남기고, 요청마다 만드는 무상태 구현 `StoredObservationAdapter`를 더한다.** `CaseStore`는 case별 registry 대신 composition root가 꽂는 **`adapter_factory(case, conn)`**를 받고, `store.adapter_for(case)`가 그것을 부른다. API · Worker는 stored factory를, 테스트 · 데모는 지금 registry에서 꺼내는 factory를 쓴다. 「adapter 제거」는 「프로세스 메모리에 case별 상태를 들지 않는다」는 뜻이다. `view.py` · `service.py` · `command.py`의 조립 코드와 동기 real 경로 · 테스트는 그대로 돈다.
4. **선택 후보의 관찰은 결과 객체 안의 `candidate_id`와 job 순서로 고른다.** JobRecord 계약(v1.8)은 바꾸지 않는다(6.6순위 「관찰 결과는 후보에 묶인다」).
   - **현재 후보 목록 세대의 job만** 본다: 현재 후보 목록을 들여온 `COARSE_SEARCH`(가장 나중의 `REFLECTED` 탐색 job)보다 뒤에 append된 관찰 JobRecord. `job_records`가 append-only라 새 state 없이 계산된다. 재탐색 뒤 같은 `candidate_id`가 다시 나와도 이전 세대의 관찰을 쓰지 않는다(`reselect-observation-reuse.md` 「같은 후보와 같은 입력은 다르다」).
   - 그 안에서 객체의 `candidate_id`가 현재 선택 후보와 같은 것만, kind마다 가장 나중 job의 것 하나를 쓴다(A§10-7 대표 job). 같은 세대 안 A→B→A면 A의 관찰을 다시 쓴다(`reselect-observation-reuse.md` (b)).
   - 6.6순위 조건 2(늦게 온 이전 후보 결과 버리기)는 따로 guard 없이 이 필터로 성립한다 — 저장소에 있어도 투영되지 않는다.
5. **T2에서 관찰 job(`PLATE_READ` · `OVERLAY_TIME_READ` · `FINE_VERIFY`) 결과는 정산만 한다.** applier는 그 job을 `REFLECTED`로 정산하고(기다리는 job만 받는 guard, `stop-analysis.md` §3-7), stage가 `EVIDENCE_REVIEW`면 `mark_ready_if_package_ready`를 다시 본다 — command 뒤와 같은 gate이고 adapter는 factory로 받는다. *(2026-10-13 구현 `reflection._apply_observation`: factory(§4-3) 전이라 command와 같이 `store.get_adapter()`를 쓴다 — 선택 후보가 있는데 adapter가 없으면 `AdapterNotAttached`로 T2가 실패한다. 결과를 읽지 않으므로 §4-1 저장소 확인과 무관하다.)* 내용은 case state에 복사하지 않는다(§4-2와 같은 이유). `FAILED` terminal도 정산만 하고, 실패 notice는 view가 read port의 실행 상태로 계산한다(`jobexecution-read-port.md`). 이전 후보의 결과도 기다리던 job이면 정산하고, 투영은 §4-4가, `READY`는 gate의 현재 선택 확인(#191)이 막는다.
6. **새 port는 없다.** 내용 읽기는 8-8의 `ProducedReader(conn, kind, produced)`를 그대로 쓰고, Runtime 쪽 구현이 결과 저장소를 읽는다. 계약 문서 · id가 없는 객체(`IntentHintResult` 등)는 저장소가 붙인 `ref`로 가리킨다.

## 5. 알려진 한계

- REC-1 전에는 recording이 in-memory라, API와 Worker가 다른 프로세스면 time source · AssetFact를 못 읽는다. stored 경로의 첫 비동기 E2E는 REC-1 머지를 기다리거나 같은 프로세스에서 돈다.
- `get_view`마다 관찰 객체를 읽고 evidence를 조립한다. case당 객체가 몇 개 수준이라 지금은 문제 삼지 않는다 — 측정해서 느리면 그때 캐시를 정한다.

## 6. 미결 (채우지 않는다)

- 결과 저장소 이름 · 컬럼 · 인덱스, `ref` 부여 규칙 — RT-10 Implementer(정철원)가 정한다(Plan §12.3 implementation detail, §8).
- IncidentClip을 만드는 job handler와 그 결과의 위치 — RT-10 handler 설계.

## 7. 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| 모듈마다 자기 저장소(search · readout 테이블) | 지금 영속하는 모듈이 없어 각자 새로 만들어야 하고, T1 같은 tx에 여러 모듈 저장을 엮게 된다. 해석 없는 상자 하나면 계약은 그대로 각 모듈에 남는다 |
| evidence · package를 저장 | 재료가 저장되어 있어 사본이다. 정정 · 재선택마다 무효화 경로가 생긴다 |
| Protocol을 없애고 CaseView 입력을 새로 짠다 | 구조는 깔끔하지만 테스트 약 40개 파일 · 데모 · 스크립트를 함께 고쳐야 해 이번 범위로 크다 |
| JobRecord에 `candidate_ref` | JobRecord ↔ CaseView 계약이 바뀌고 6.6순위 결정(「JobRecord 계약 변경 불필요」)을 뒤집는다 |
| `candidate_id`만으로 거른다 | 재탐색 뒤 같은 id에 이전 세대 관찰을 잘못 쓴다(`reselect-observation-reuse.md` (c)) |
| T2에서 관찰 내용을 case state에 복사 | 저장소가 원본이라 같은 사실이 두 곳에 생긴다 |

## 8. 맞출 것 (Consult #346 — RT-10 Implementer @cheol1203, Contract 판단은 @flosure23, search · readout 사실 확인)

1. 결과 저장소 신설 — common/runtime, 해석 없는 append-only.
2. T1 범위 확장 — terminal 행 · `produced`와 같은 transaction에서 저장소 append.
3. id 없는 객체의 `ref` 부여 규칙.
4. 관찰 객체(readout `ReadRequest` 계열 · Fine `VisualEvidence`)가 `candidate_id`를 싣는다는 확인 — search · readout Owner.

## 9. case 쪽 구현 (RT-10 Implementer 확인 뒤, TDD)

- `CaseStore(adapter_factory=…)` — 기본은 지금 registry factory.
- `StoredObservationAdapter` — Runtime 저장소 전에는 가짜 `ProducedReader` · 가짜 recording으로 테스트한다.
- `reflection._APPLIERS`에 관찰 kind 3개.
- 테스트: 세대 · 선택 필터(재탐색 뒤 같은 id, A→B→A), 이전 후보의 늦은 결과, 관찰 반영 뒤 `READY`, `FAILED` 정산.
