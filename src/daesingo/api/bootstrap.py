"""API configuration composition bootstrap; HTTP app/routes are RT-08."""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from daesingo.common.bootstrap import ModuleFactory, Startup, bootstrap_service


def bootstrap(*, revision: str, stream: TextIO | None = None,
              module_factories: Sequence[ModuleFactory] = ()) -> Startup:
    """Validate all registered module configurations before accepting work.

    No API module currently consumes file-based configuration. RT-08 registers
    factories for dependencies as it assembles the HTTP app.
    """
    path = os.environ.get("DAESINGO_ENV_FILE", str(Path.cwd() / ".env"))
    return bootstrap_service("api", env_file=path, revision=revision,
                             stream=stream, module_factories=module_factories)
