"""The Worker composition root owns one immutable kind registration snapshot.

RD-09a: register invocations, not process-global mutable RecordingService state.
RT-10 invocations create a service per execution and close it in finally; durable
repositories may be shared. No service lifecycle implementation belongs here.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from daesingo.common.jobs.execution import ExecutionContext, HandlerResult, runtime_failure

Handler = Callable[[ExecutionContext], HandlerResult]


class KindRegistry:
    def __init__(self, handlers: Mapping[str, Handler]):
        self._handlers = MappingProxyType(dict(handlers))

    def dispatch(self, context: ExecutionContext) -> HandlerResult:
        handler = self._handlers.get(context.kind)
        if handler is None:
            return runtime_failure("RUNTIME_UNREGISTERED_KIND")
        try:
            result = handler(context)
            if not isinstance(result, HandlerResult):
                return runtime_failure("RUNTIME_INVALID_RESULT")
            # Revalidate even a model constructed/copied without validation.
            return HandlerResult.model_validate(result.model_dump())
        except Exception:
            return runtime_failure("RUNTIME_HANDLER_ERROR")
