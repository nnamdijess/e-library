"""Bound actual incoming bytes before multipart parsing, including chunked bodies."""

from starlette.middleware.body_limit import RequestBodyLimitMiddleware


class BodyLimits:
    def __init__(self, app, max_upload_bytes: int):
        self.upload = RequestBodyLimitMiddleware(app, max_body_size=max_upload_bytes + 64 * 1024)
        self.normal = RequestBodyLimitMiddleware(app, max_body_size=64 * 1024)

    async def __call__(self, scope, receive, send):
        is_upload = scope.get("method") == "POST" and scope.get("path") == "/api/v1/books"
        await (self.upload if is_upload else self.normal)(scope, receive, send)
