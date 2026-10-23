from starlette.responses import JSONResponse


class DecisionBodyLimitMiddleware:
    """Bound JSON requests before parsing, including bodies without Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/decisions"):
            return await self.app(scope, receive, send)
        limit = 65_536
        error = JSONResponse(status_code=413, content={"detail": {"message": "Decision request exceeds the 64 KiB limit."}})
        length = dict(scope.get("headers", [])).get(b"content-length")
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
