"""Service authentication runs before parsing candidate-controlled request bodies."""
import hashlib
import hmac
import os
import re
from starlette.responses import JSONResponse

MAX_BODY_BYTES = 100_000


def service_token() -> str:
    token = os.environ.get("ML_SERVICE_TOKEN", "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise RuntimeError("ML_SERVICE_TOKEN must be a random 32-byte hex token")
    return token


class ServiceBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["path"] != "/health":
            try:
                expected = "Bearer " + service_token()
            except RuntimeError:
                return await JSONResponse({"error": "Service unavailable"}, status_code=503)(scope, receive, send)
            supplied = headers.get(b"authorization", b"")
            if not hmac.compare_digest(hashlib.sha256(supplied).digest(), hashlib.sha256(expected.encode()).digest()):
                return await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
        # Bound streamed bodies, including chunked requests without Content-Length.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY_BYTES:
                return await JSONResponse({"error": "Request too large"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]
            await send(message)
        await self.app(scope, bounded_receive, private_send)
