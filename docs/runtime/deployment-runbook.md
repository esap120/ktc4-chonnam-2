# Runtime Deployment Runbook

**Status:** Working — deployment execution checklist  
**Owner:** common/runtime — 김준영  
**Ops policy:** [Runtime Ops Spec](./ops-spec.md)

> 이 문서는 배포 담당자의 기억에 의존하지 않고 같은 절차를 반복·검증·복구할 수 있도록 하는 실행 체크리스트다. 현재 deployment stack의 exact command가 아직 구현되지 않은 항목은 임의로 채우지 않으며, 실제 Docker/Compose/OIDC/SSM 구현 PR에서 명령을 확정한다.

## 1. 배포 완료의 정의

배포는 원격 명령이나 `docker compose up`이 성공한 시점에 끝나지 않는다.

다음이 모두 확인되어야 배포 완료로 본다.

- 배포 revision을 commit SHA로 식별할 수 있음
- Registry 기반이면 image tag/digest를 재현할 수 있음
- 필요한 container/process가 실행 중임
- `/health/live`가 정상
- `/health/ready`가 정상
- 외부 공개 endpoint가 있으면 최소 smoke test가 정상
- 직전 known-good revision을 식별할 수 있음
- 실패 시 rollback 절차를 실행할 수 있음

## 2. 배포 전

### Revision / 변경 확인

- [ ] 배포 대상 commit SHA 확인
- [ ] CI quality gate 통과 확인
- [ ] 배포 artifact/image가 필요한 경우 식별 가능한 tag/digest 확인
- [ ] 직전 known-good revision 기록
- [ ] DB migration 포함 여부 확인
- [ ] migration이 포함되면 backward compatibility / restore 필요 여부 확인

### Configuration / Secret

- [ ] build-time 값과 runtime 값을 구분했는가
- [ ] secret이 image/repository/log에 bake되지 않는가
- [ ] 필요한 runtime configuration key가 준비됐는가
- [ ] `.env.example`과 실제 secret source의 역할을 혼동하지 않는가
- [ ] secret이 Parameter Store `SecureString`에 있고, EC2 instance role이 그 경로를 읽을 수 있는가 (불가하면 Session Manager 수동 배치 fallback — [Ops Spec](./ops-spec.md) §4-1)
- [ ] host의 보호된 config 파일이 container UID 소유 · 최소 권한이고, 값이 배포 log · stdout에 남지 않는가
- [ ] 값 변경을 `docker compose up -d --force-recreate api worker`로 반영하는가 (`restart`로 보장하지 않음)

### Public endpoint가 있는 경우

- [ ] DNS가 의도한 endpoint를 가리키는가
- [ ] 필요한 80/443 접근 조건이 준비됐는가
- [ ] HTTPS 인증서/reverse proxy 상태를 확인할 수 있는가
- [ ] OAuth를 사용한다면 callback URI가 실제 HTTPS endpoint와 일치하는가

## 3. 배포

현재 목표 경로:

```text
GitHub Actions
→ GitHub OIDC
→ AWS STS AssumeRole
→ SSM Run Command
→ EC2
→ Docker Compose
```

구현 시 이 절에 다음 exact command를 기록한다.

- artifact/image 전달 방식
- SSM Run Command
- Docker Compose pull/build/update command
- migration command가 있다면 실행 순서 — api · worker 시작 전 단일 단계이며 app startup에서 돌리지 않는다([Tech Spec](./runtime-tech-spec.md) §4.4)
- old container 정리 방식

### 원칙

- GitHub Actions용 장기 AWS Access Key를 만들지 않는다.
- GitHub Actions 배포를 위해 SSH private key를 저장하거나 22번 port를 인터넷에 열지 않는다.
- Registry 기반이면 `latest`만으로 배포 revision을 식별하지 않는다.
- runtime secret은 build artifact에 포함하지 않는다.

## 4. 배포 직후 검증

### Process / Container

- [ ] api process/container 정상
- [ ] worker process/container 정상
- [ ] mysql dependency 정상
- [ ] 반복 restart/crash loop 없음

### Runtime Health

- [ ] `GET /health/live`
- [ ] `GET /health/ready` — 호출 쪽 timeout은 ready budget([Provisional Baseline v0.1](./provisional-baseline-v0.1.md) B-H3)보다 길게 둔다

외부 AI provider 하나의 장애만으로 API liveness가 실패하도록 설계하지 않는다.

### External Smoke Test

외부 공개 endpoint가 있다면 실제 사용자 경로에서 최소 1회 검증한다.

- [ ] DNS resolve
- [ ] HTTPS handshake / 응답
- [ ] 대표 API endpoint 응답
- [ ] 필요 시 Web → API 연결
- [ ] 새 revision 반영 확인

exact smoke endpoint는 API composition root가 구현될 때 고정한다.

### Log / Correlation

- [ ] 새 요청에 `trace_id`가 남는가
- [ ] 가능하면 `case_id → job_id → execution_id`가 같은 흐름에서 연결되는가
- [ ] secret / 번호판 / 상세 위치 / raw provider payload가 일반 운영 로그에 노출되지 않는가

## 5. 실패 시 Rollback

배포 직후 health/readiness/smoke test가 실패하고 즉시 수정하는 것보다 서비스 복구가 우선이면 rollback한다.

```text
새 revision 검증 실패
→ 직전 known-good revision 선택
→ 동일 deployment path로 재배포
→ /health/live
→ /health/ready
→ external smoke test
→ 복구 확인
```

### Rollback 전 확인

- [ ] 직전 known-good commit/image 확인
- [ ] DB migration이 새 revision과 함께 적용됐는가
- [ ] 이전 code가 현재 DB schema와 호환되는가
- [ ] managed asset/storage 변경이 rollback을 막지 않는가

### 주의

DB schema/data migration처럼 단순 code rollback으로 되돌릴 수 없는 변경은 자동 rollback 대상으로 가정하지 않는다. 해당 배포는 사전에 backward-compatible migration 또는 별도 restore 절차가 있어야 한다.

exact rollback command는 deployment workflow 구현 시 이 문서에 추가한다.

## 6. 장애 원인 축소 순서

서비스 이상 시 무작정 전체 로그부터 읽지 않고 바깥에서 안쪽으로 범위를 좁힌다.

```text
1. 외부 endpoint / DNS / HTTPS
2. reverse proxy
3. api container/process
4. /health/live
5. /health/ready / DB
6. worker heartbeat / lease / queue
7. domain capability
8. provider invocation
9. storage / disk working set
```

비동기 작업 문제는 `trace_id`, `case_id`, `job_id`, `execution_id`를 함께 사용해 추적한다.

## 7. 배포 후 기록

최소 다음을 남긴다.

```text
deployed_at
commit_sha
image_tag_or_digest (해당 시)
deployment_result
health_result
smoke_test_result
rollback 여부
known_good_revision
```

저장 위치와 자동화 방식은 deployment workflow 구현 시 결정한다.

## 8. 아직 닫지 않은 항목

- [ ] exact Dockerfile / Compose command
- [ ] artifact 전달 방식(S3/ECR 등)
- [ ] immutable image tag/digest convention
- [ ] SSM Run Command
- [x] runtime secret source / injection — 경로는 [Ops Spec](./ops-spec.md) §4-1(RD-07)로 닫힘. exact fetch · render 명령은 SSM Run Command 구현 때 이 문서에 기록
- [ ] public endpoint / Caddy 구성
- [ ] external smoke endpoint
- [ ] known-good revision 기록 방식
- [ ] exact rollback command
- [ ] DB migration/restore 운영 절차

## References

- [Runtime Ops Spec](./ops-spec.md)
- [Runtime Tech Spec](./runtime-tech-spec.md)
- [Pre-deploy security review](../management/pre-deploy-security-review.md)
