"""pytest 루트 설정 — `src/`를 import 경로에 올린다.

레포에 아직 패키지 설치 설정(`pyproject.toml`)이 없어서 `daesingo`가 설치된 패키지로
잡히지 않는다. 그동안은 테스트 파일마다 `sys.path.insert`를 적어 뒀는데, 러너를 pytest로
통일하면서 그 3줄을 여기 한 곳으로 모은다. pytest가 수집 전에 루트 conftest를 먼저 읽으므로
테스트 파일은 `from daesingo... import ...`만 쓰면 된다.

**이 파일은 한시적이다.** 통합에서 root `pyproject.toml`이 하나로 정해지고 `pythonpath`
(또는 editable 설치)가 그 안에 들어오면 이 파일은 지운다. 자세한 사정은 `tests/README.md`.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Load before collection, including Case importorskip and opt-in fixtures.
TEST_SUPPORT = Path(__file__).resolve().parent / "tests"
if str(TEST_SUPPORT) not in sys.path:
    sys.path.insert(0, str(TEST_SUPPORT))
pytest_plugins = ["mysql_harness"]
