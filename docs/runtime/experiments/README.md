# Runtime Experiments

Runtime의 cross-cutting 실행 질문을 실제 환경에서 검증하기 위한 experiment plan/result 라우터다.

> 이 폴더의 실험 문서는 **결정의 근거(evidence)** 이며 Final Contract, Runtime Tech Spec, Ops Spec을 대체하지 않는다. 반복 가능한 결과가 실제 구현·운영 결정을 만들 때만 상위 문서로 승격한다.

## 이 폴더가 다루는 것

```text
recording
→ media/profile/ffmpeg/storage 사실

search
→ provider compatibility / recall / token / cost / latency 사실

runtime experiments
→ 위 경로가 실제 실행 환경에서 합쳐졌을 때
   CPU / RAM / disk / queue / concurrency / recovery에 미치는 영향
```

대표 질문:

- api + worker + mysql이 같은 baseline host에서 함께 동작할 때 자원 경합이 있는가
- ffmpeg materialization과 provider request construction의 peak working set은 얼마인가
- Worker concurrency를 늘릴 여유가 실제로 있는가
- process-local reuse가 restart/다중 Worker에서도 충분한가
- failure/crash 후 temp asset과 실행 상태가 회수되는가
- long-duration Real E2E가 현재 storage/capacity 가정을 깨는가

Search/Recording 자체의 품질·profile·provider 내부 알고리즘 실험은 각 module Owner 문서가 소유한다.

## 문서 lifecycle

```text
상위 이슈 / module 실험 결과
→ Runtime에 남은 질문 정의
→ experiments/* plan
→ 실제 환경에서 측정
→ result 기록
→ 반복 가능한 사실만 runtime-tech-spec / ops-spec에 승격
→ 여러 구현에 장기 영향을 주는 구조 결정이면 decisions/ ADR
```

### Plan

아직 검증하지 않은 질문, 입력 후보, 관측 항목, 실험 순서를 적는다.

Plan 단계에서는 다음을 하지 않는다.

- 근거 없는 PASS threshold 발명
- module canonical profile 확정
- EC2/Worker/Object Storage 확장 선결
- provider-specific 계약을 Runtime 문서에 복제

### Result

실제 실행 환경, revision, 입력, 측정 방식, raw observation과 해석을 구분해 남긴다.

한 호스트·한 입력의 단회 수치를 일반적인 운영 상수로 승격하지 않는다.

### Decision / ADR 승격

실험 결과가 다음 조건을 만족할 때 Tech/Ops 문서에 반영한다.

1. 어떤 질문을 닫는 결과인지 명확하다.
2. 실행 환경과 revision이 식별 가능하다.
3. module Owner의 품질/계약 의미를 Runtime이 재정의하지 않는다.
4. 결과가 구현·운영 선택을 실제로 바꾼다.

다음처럼 여러 구현과 향후 migration에 장기 영향을 주면 `docs/runtime/decisions/` ADR 후보로 올린다.

- Worker concurrency/scaling model 변경
- persistent/shared media storage 도입
- DB Queue에서 전용 Queue로 전환
- baseline deployment topology 변경
- 공용 versioned pricing/FX artifact 도입 같은 cross-module 구조 변경

단순 tuning 값이나 단회 benchmark마다 ADR을 만들지는 않는다.

## 현재 계획

| 문서 | 상태 | 닫으려는 질문 |
| --- | --- | --- |
| [Elice Runtime Capacity Smoke Plan](./elice-runtime-capacity-smoke-plan.md) | Planned | #95 P0/P1 경로를 baseline EC2에서 실행할 때 CPU/RAM/disk/queue/reuse가 안전한가 |
| [Pre-implementation Spike 2026-10-03](./pre-implementation-spike-2026-10-03.md) | Result | workflow §5 A Decision의 기술 semantics — claim lock(RR/RC) · conditional UPDATE 경합 · Compose secret file · shared volume rename. capacity 실험이 아니다 |

P2 결과가 현재 가정을 크게 바꾸면 그 결과를 바탕으로 P3 30분~1시간 Runtime E2E plan을 별도로 만든다. P3 문서를 선작성해 가정을 고정하지 않는다.

## Routing

- 실행 lifecycle / queue / UsageRecord persistence → [Runtime Tech Spec](../runtime-tech-spec.md)
- deployment / capacity / storage / monitoring → [Runtime Ops Spec](../ops-spec.md)
- 배포 실행 체크 → [Deployment Runbook](../deployment-runbook.md)
- 장기 구조 결정 → `../decisions/`
- Search/usage/pricing/provider config 경계 조사·합의 → [Issue #153](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153) (Runtime 반영: Tech Spec §11.3 · §15.1)

## References

- [Issue #95 — Elice ML API migration tracker](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/95)
- [Issue #153 — provider usage · pricing · runtime config boundary review](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153)
- [Runtime README](../README.md)
