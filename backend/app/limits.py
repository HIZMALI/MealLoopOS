from starlette.responses import JSONResponse

from .parsing import MAX_BYTES


class UploadSizeLimitMiddleware:
    """Bound every upload before multipart parsing, including chunked bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/dataset/import":
            return await self.app(scope, receive, send)
        limit = MAX_BYTES + 65_536  # bounded allowance for multipart headers
        length = dict(scope.get("headers", [])).get(b"content-length")
        error = JSONResponse(status_code=413, content={"detail": {"message": "Upload exceeds the 10 MiB file limit."}})
        if length and (not length.isdigit() or int(length) > limit):
            return await error(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                return await error(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(messages)

        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        return await self.app(scope, replay, send)
