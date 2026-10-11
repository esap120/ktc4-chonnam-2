"""Shared startup mechanics; path selection belongs to composition roots."""

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TextIO

from daesingo.common.config import ConfigError, RuntimeConfig, runtime_keys
from daesingo.common.env import load_env_file
from daesingo.common.logging import configure_logging, log_event


@dataclass(frozen=True, slots=True)
class ModuleFactory:
    """The composition root declares relevant keys; factory owns their meaning.

    Factories receive the same read-only mapping, create/validate configuration
    without network calls, and return the object later used by the service.
    All key declarations are validated before any factory runs. Generic
    exceptions are reported with validated keys, never exception text.
    """

    name: str
    keys: tuple[str, ...]
    factory: Callable[[Mapping[str, str]], object] = field(repr=False)


@dataclass(frozen=True, slots=True)
class Startup:
    config: RuntimeConfig
    modules: Mapping[str, object] = field(repr=False)
    logger: logging.Logger = field(repr=False)


def bootstrap_service(service: str, *, env_file: str, revision: str,
                      module_factories: Sequence[ModuleFactory] = (),
                      stream: TextIO | None = None) -> Startup:
    logger = configure_logging(service, stream=stream)
    module_factories = tuple(module_factories)
    for registration in module_factories:
        if not isinstance(registration.keys, tuple) or not all(
            isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
            for key in registration.keys
        ):
            # Unvalidated declaration text is neither a safe key nor a diagnostic.
            log_event(logger, "runtime.config.invalid", level=logging.ERROR,
                      keys=(), status="INVALID_MODULE_FACTORY_KEYS")
            raise SystemExit(1)
    invalid = None
    try:
        # Always explicit, including cwd/.env; never merge os.environ values.
        values = MappingProxyType(load_env_file(env_file))
        unknown = sorted(key for key in values
                         if key.startswith("DAESINGO_RUNTIME_") and key not in runtime_keys())
        if unknown:
            # Malformed names cannot inject newlines or arbitrary text into logs.
            safe_keys = [key for key in unknown if re.fullmatch(r"[A-Z][A-Z0-9_]*", key)]
            log_event(logger, "runtime.config.unknown", level=logging.WARNING, keys=safe_keys)
        config = RuntimeConfig.from_mapping(service, values)
        modules = {}
        for registration in module_factories:
            if registration.name in modules:
                raise ValueError("duplicate module registration")
            try:
                modules[registration.name] = registration.factory(values)
            except Exception:
                # Even custom/provider exceptions may contain input and secrets.
                raise ConfigError(registration.keys) from None
        log_event(logger, "process.started", revision=revision)
        logger.setLevel(config.log_level)
        return Startup(config, MappingProxyType(modules), logger)
    except ConfigError as error:
        invalid = error.keys
    except (OSError, UnicodeError, ValueError):
        invalid = ("DAESINGO_ENV_FILE",)
    # Outside the except block: no input-bearing exception/traceback chain.
    log_event(logger, "runtime.config.invalid", level=logging.ERROR, keys=invalid)
    raise SystemExit(1)


__all__ = ["ModuleFactory", "Startup", "bootstrap_service"]
