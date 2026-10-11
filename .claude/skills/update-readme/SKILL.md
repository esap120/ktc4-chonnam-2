---
name: update-readme
description: PR · push 전에 이번 변경이 최상위 경로 추가 · 삭제 · 이동, 루트 `package.json`, `pyproject.toml`, `.github/workflows/`, `src/daesingo/*` 모듈의 골격→구현 전환 중 하나를 건드렸을 때만 사용한다. 이런 변경이 없는 PR(대부분)에서는 부르지 않는다. 루트 README.md의 사실 절(레포 구성 · 실행 · 기술 스택)을 레포 실제 상태와 대조해 어긋난 줄만 고친다.
---

# 루트 README 사실 절 갱신

루트 `README.md`에서 **레포 사실을 옮겨 적은 절**만 실제 상태와 대조하고, 어긋난 줄만 고친다. 멘토 리뷰(PR #66)의 「루트 README 갱신 — 푸시 전 혹은 PR 전에 갱신하는 규칙」을 이 skill로 운영한다.

## 대조 대상과 원천

| README 절 | 대조할 사실 | 원천 |
| --- | --- | --- |
| `## 레포 구성` 표 | 경로가 실제로 있는가 · 빠진 최상위 경로(git이 추적하는 것)가 있는가 · 구현 현황 문구 | `git ls-files`의 최상위 경로 · `src/daesingo/*`에 README 말고 `.py`가 있는가 · 각 경로 README 첫 문단 |
| `## 실행` | Node · Python 최소 버전, 설치 · 실행 명령, npm 스크립트 이름 | 루트 `package.json`(`engines` · `scripts`) · `pyproject.toml`(`requires-python` · `optional-dependencies`) · `.github/workflows/python-tests.yml`(설치 명령) |
| `### 기술 스택 (확정)` | 확정 스택 중 레포에 실제로 들어온 것과 어긋나는 표현 | `pyproject.toml` dependencies · `uv.lock` 유무 |

이 셋 밖의 절(「무엇을 하고, 무엇을 하지 않는가」 · 「사용자 흐름」 · 「구조」 · 「문서를 읽는 순서」 · 미결 문장)은 **읽기만 하고 고치지 않는다.** 다른 문서를 가리키는 포인터이고, 원본은 그 문서에 있다.

## 절차

0. **먼저 가볍게 판별한다.** `git diff --name-only <base>...HEAD`(base는 PR 대상, 보통 `develop`)에 아래 중 하나라도 있는지만 본다. 없으면 원천 파일을 읽지 말고 「README 사실 절과 무관한 변경」이라고 한 줄 보고하고 끝낸다.
   - 최상위 경로가 새로 생기거나 사라진 파일(`git diff --name-status`의 `A` · `D` · `R` 중 최상위 폴더가 새로운 것)
   - 루트 `package.json` · `pyproject.toml` · `.github/workflows/*`
   - `src/daesingo/<모듈>/`에 README 말고 첫 `.py`가 생긴 경우
1. 원천 파일을 먼저 읽는다. git이 추적하지 않는 폴더(`node_modules/` · 로컬 산출물)는 「레포 구성」 근거로 쓰지 않는다 — `git ls-files`로 확인한다.
2. README 사실 절을 한 줄씩 원천과 대조한다.
3. 어긋난 줄만 고친다. 표 모양 · 문체(한국어 평서문 「~다」) · 줄 순서는 그대로 둔다. 새 절을 만들지 않는다.
4. 원천으로 확인할 수 없는 문장(예: 「진행 중」 같은 현황 표현의 정도)은 고치지 않고 「확인 필요」로 보고한다.
5. 끝에 세 묶음으로 요약한다.
   - **고친 줄:** 무엇을 → 무엇으로, 근거 원천
   - **확인 필요:** 원천으로 판단할 수 없었던 문장
   - **그대로 둔 절:** 대조했지만 어긋남이 없던 절

고칠 것이 없으면 README를 건드리지 않고 「어긋남 없음」만 보고한다.

## 하지 말 것

- 대조 대상 절 밖을 고치지 않는다.
- 다른 문서의 규칙을 README로 옮겨 적지 않는다 — 한 결정은 한 곳에만 있고 README는 가리킨다.
- `docs/archive/`를 근거로 쓰지 않는다. 과거 snapshot이다.
- `미결` · `확인 필요` · `미정`을 채우지 않는다.
- 각 모듈 폴더의 README는 그 모듈 Owner 것이다 — 원천으로 읽기만 하고 고치지 않는다.
