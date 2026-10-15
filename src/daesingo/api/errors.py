"""HTTP Contract §3.3 envelope and §3.4 status mapping, without exception detail."""
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from daesingo.common.db.errors import BeforeCommitFailure, CommitOutcomeUnknown

_HTTP_CODES = {
    400: "http.malformed_request", 404: "http.not_found", 405: "http.method_not_allowed",
    413: "http.payload_too_large", 415: "http.unsupported_media_type",
    500: "http.internal_error", 503: "http.dependency_unavailable",
}


def error_response(status: int, *, headers=None) -> JSONResponse:
    code = _HTTP_CODES[status]
    return JSONResponse({"ok": False, "error": {"code": code, "message_key": code},
                         "case_view": None}, status_code=status, headers=headers)


def install_error_handlers(app, events):
    def failure(status, *, headers=None):
        events.emit("api.request.failed", status=str(status))
        return error_response(status, headers=headers)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        status = error.status_code if error.status_code in _HTTP_CODES else 500
        # Framework-generated Allow is protocol metadata; arbitrary exception
        # headers can contain internal details and are deliberately not echoed.
        headers = None
        if status == 405:
            route = request.scope.get("route")
            methods = getattr(route, "methods", None)
            if methods:
                headers = {"Allow": ", ".join(sorted(methods))}
        return failure(status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Transport conversion failures, never domain invalid_payload. Command
        # handlers in (c) pass opaque JSON through to Case's own validation.
        return failure(400)

    @app.exception_handler(BeforeCommitFailure)
    async def before_commit(request, error):
        return failure(503)

    @app.exception_handler(CommitOutcomeUnknown)
    async def unknown_commit(request, error):
        return failure(500)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return failure(500)
