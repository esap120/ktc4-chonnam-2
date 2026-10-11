# `/update-readme` 사용 안내

루트 `README.md`의 **사실 절**(레포 구성 · 실행 · 기술 스택)을 레포 실제 상태와 맞추는 Claude Code skill이다. 멘토 리뷰(PR #66)의 「루트 README 갱신 — 푸시 전 혹은 PR 전에 갱신하는 규칙」을 운영하려고 만들었다. Claude가 읽는 지시문은 `SKILL.md`이고, 이 파일은 사람용 안내다(Claude Code는 이 파일을 자동으로 읽지 않는다).

## 언제 쓰나

PR에 아래 변경이 **있을 때만** 쓴다. 대부분의 PR은 해당이 없다 — 그때는 쓰지 않고 PR 템플릿 체크박스도 그냥 둔다.

- 최상위 폴더를 새로 만들거나 지우거나 옮겼다
- 루트 `package.json`(Node 버전 · npm script) · `pyproject.toml`(Python 버전 · 의존성) · `.github/workflows/`를 고쳤다
- `src/daesingo/<모듈>`이 README만 있던 골격에서 실제 코드가 들어간 상태가 됐다

## 어떻게 쓰나

1. Claude Code에서 `/update-readme`를 입력한다. Claude에게 PR을 올려 달라고 할 때 위 변경이 있으면 Claude가 먼저 불러올 수도 있다(보장은 아니다).
2. 결과 요약을 본다 — 「고친 줄 / 확인 필요 / 그대로 둔 절」 세 묶음으로 나온다.
3. **실제로 어긋난 줄이 있을 때만** README 변경을 PR에 포함한다. 「어긋남 없음」이면 아무것도 바뀌지 않는다.
4. 「확인 필요」 문장(예: 구현 현황 표현의 정도)은 skill이 고치지 않는다. 필요하면 직접 판단해 고친다.

Cursor · Copilot 사용자는 PR 템플릿 체크박스를 보고 위 「언제 쓰나」 해당 여부만 직접 확인하면 된다.

## 무엇을 고치지 않나

사실 절 밖(제품 약속 · 문서 읽는 순서 · 미결 문장)과 각 모듈 폴더의 README는 고치지 않는다. 그 내용의 원본은 다른 문서에 있고 README는 가리키기만 한다(`docs/README.md` 「다른 모듈의 규칙을 복제하지 않는다」).

## 왜 공개 skill이 아니라 이 레포 전용인가 (2026-10-06 조사)

| 찾아본 것 | 하는 일 | 고르지 않은 이유 |
| --- | --- | --- |
| 공개 README skill — [yamz8/readme-skill](https://github.com/yamz8/readme-skill) · [Update README](https://mcpmarket.com/tools/skills/update-readme) · [Update Docs](https://mcpmarket.com/tools/skills/update-docs) | 코드베이스를 읽고 README 전체를 새로 쓰거나 다듬는다. 어떤 것은 에이전트 3개를 병렬로 돌려 git 이력까지 훑는다 | 범위가 README **전체**라 다른 문서를 가리키는 절까지 고쳐 쓴다 — 레포의 「한 결정은 한 곳」 원칙과 충돌한다. 매번 넓게 읽어 토큰도 크다. 외부 지시문을 팀 Claude Code에 들이는 것이라 검토 부담도 생긴다 |
| CI drift 검사 도구 — [fiberplane/drift](https://github.com/fiberplane/drift) · [driftcheck](https://github.com/Ymax27/driftcheck) · [docs-drift](https://github.com/georg-nikola/docs-drift) | 문서와 코드 · 버전 파일의 불일치를 CI에서 기계적으로 막는다 | Claude 밖 경로(직접 push · 웹 PR · Cursor)까지 보장하는 장점이 있다. 다만 「구현 현황」 같은 판단 문장은 못 본다. 지금은 PR 템플릿 체크로 충분한지 먼저 보고, 기계적 어긋남이 반복되면 이쪽(PR #285의 「B안」)을 더한다 |

그래서 **대조할 절과 원천을 고정한 좁은 skill**을 직접 두었다. 필요한 판단 기준(원천 · 하지 말 것)이 이 레포의 문서 규칙이라 공개 skill을 고쳐 쓰는 것보다 짧게 쓰는 편이 낫다.
