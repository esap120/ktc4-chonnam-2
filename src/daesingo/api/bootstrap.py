"""API configuration bootstrap; app.py owns HTTP resource composition."""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from daesingo.common.bootstrap import ModuleFactory, Startup, bootstrap_service


def bootstrap(*, revision: str, stream: TextIO | None = None,
              module_factories: Sequence[ModuleFactory] = ()) -> Startup:
    """Validate all registered module configurations before accepting work.

    RT-08(a) consumes RuntimeConfig for engines and health. Later composition
    registers configuration factories for any domain dependencies it uses.
    """
    path = os.environ.get("DAESINGO_ENV_FILE", str(Path.cwd() / ".env"))
    return bootstrap_service("api", env_file=path, revision=revision,
                             stream=stream, module_factories=module_factories)
