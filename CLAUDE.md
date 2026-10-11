# 대신고 (Daesingo) — 레포 읽기 라우터

블랙박스 영상에서 교통위반 신고 자료를 준비해 주는 제품. 6명 팀, 10주 MVP. `apps/`에 실행 코드, `docs/`에 living document, `src/`·`eval/`에 코드 골격.

**이 파일은 규칙을 담지 않는다. 어느 문서를 읽을지만 알려준다.** 규칙 원문은 아래 포인터의 문서에 있고, 여기에는 복제하지 않는다.

## 이런 작업이면 이 문서만

| 하려는 일 | 읽을 것 |
| --- | --- |
| 제품이 무엇을 약속하고 안 하는지 | `docs/product/product-spec.md` §5 · §7 |
| 화면 흐름 · 실패 UX | `docs/product/core-user-flow.md` |
| 모듈 경계 · 계약 · 금지사항 | `docs/architecture/module-architecture.md` — §1 → §2 → **§4 내 모듈** → §5 → §11 내 항목. 1,900줄이므로 전체를 읽지 않는다 |
| 내 모듈의 조사·실험·결정 | `docs/modules/<module>/` |
| Runtime 구현 (RT-xx) | `docs/runtime/runtime-implementation-plan.md` — §6 해당 Task → §12(PR 순서는 §12.8). 900줄이므로 전체를 읽지 않는다 |
| 누가 무엇을 맡는지 | `docs/management/ownership.md` |
| 운영 결정(승인 경로·리뷰 담당) | `docs/management/cross-cutting-decisions.md` |
| 문서 폴더 사용 규칙 · 충돌 시 우선순위 | `docs/README.md` |
| 폴더 구조 · 실행 방법 · 의존성을 바꾼 PR의 루트 README 사실 확인 | `/update-readme` (`.claude/skills/update-readme/`) |

## 하지 말 것

1. `docs/archive/`를 현재 문서로 읽지 않는다. 분량이 가장 크고 제목이 그럴듯하지만 과거 snapshot이다.
2. `docs/management/secret/`·`docs/management/submissions/`·`doc/`을 커밋하지 않는다. gitignore 대상이며 `git add -f` 금지.
3. 문서 간 규칙을 복제하지 않는다. 한 결정은 한 곳에만 있고 나머지는 가리킨다.
4. 미결(`[미결 유지]`·`확인 필요`·`미정`)을 완성도를 위해 채우지 않는다. 미결은 미결로 남긴다.
5. 다른 모듈의 문서·폴더를 고치지 않는다. 각 모듈은 Owner가 관리한다.
6. `.github/`의 **파일 4개**를 건드리지 않는다 — `workflows/{assign-mentor,notify-discord,convention-check}.yml`·`CODEOWNERS`. 운영진(카테캠) 소유이고 리뷰 자동화가 여기서 돈다. 그 밖의 `.github/` 추가·수정은 허용된다(운영진 CODEOWNERS 개정).

## 규칙 원문은 여기 없다

- 제품 수준 불변 경계 → `docs/product/product-spec.md` §7
- 구조가 강제하는 정책 → `docs/architecture/module-architecture.md` §3 · 부록 B
- 모듈별 「알면 안 되는 것」 → 같은 문서 §4 각 모듈 ⑦/⑧
