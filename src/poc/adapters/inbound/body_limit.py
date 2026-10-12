"""Bound request bytes before JSON/multipart parsing, including chunked uploads."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 65 * 1024 * 1024  # 64 MiB file plus bounded multipart overhead.


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        seen = 0
        oversized = False
        overflow_sent = False

        async def limited_receive():
            nonlocal seen, oversized
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > MAX_REQUEST_BYTES:
                    oversized = True
                    raise HTTPException(413, "REQUEST_TOO_LARGE")
            return message

        async def limited_send(message):
            nonlocal overflow_sent
            if oversized:
                # Body parsers may wrap the receive exception as a generic 400.
                # Preserve 413 at the outer transport boundary without reading more bytes.
                if not overflow_sent:
                    overflow_sent = True
                    await JSONResponse({"error": "REQUEST_TOO_LARGE"}, status_code=413)(
                        scope, receive, send
                    )
                return
            await send(message)

        return await self.app(scope, limited_receive, limited_send)
