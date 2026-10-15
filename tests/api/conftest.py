from io import StringIO
from types import MappingProxyType

import pytest
from daesingo.common.bootstrap import Startup
from daesingo.common.config import RuntimeConfig
from daesingo.common.logging import configure_logging

@pytest.fixture
def api_startup(tmp_path):
    config = RuntimeConfig.from_mapping("api", {
        "DAESINGO_RUNTIME_DB_URL": "mysql+pymysql://test:secret@127.0.0.1:1/api_test",
        "DAESINGO_RUNTIME_MEDIA_ROOT": str(tmp_path),
        "DAESINGO_RUNTIME_API_TEMP_ROOT": str(tmp_path),
    })
    stream = StringIO()
    return Startup(config, MappingProxyType({}), configure_logging("api", stream=stream)), stream
