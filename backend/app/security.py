"""Small bounded ASGI gate: authorization precedes body parsing and route execution."""
import ipaddress
import asyncio
import json
import re
import threading
import time
from collections import deque
from urllib.parse import parse_qs, urlsplit

from starlette.responses import JSONResponse
from fastapi.routing import iter_route_contexts

from .public_policy import PUBLIC_ROUTES

MAX_BODY = 65_536
MAX_URL = 4096


class PublicLimiter:
    """Single-worker limits. Forwarded headers are deliberately never trusted."""
    def __init__(self):
        self.clients = {}
        self.global_hits = deque()
        self.lock = threading.Lock()

    def allow(self, client, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            for key in list(self.clients):
                hits = self.clients[key]
                while hits and hits[0] <= now - 60:
                    hits.popleft()
                if not hits:
                    del self.clients[key]
            while self.global_hits and self.global_hits[0] <= now - 60:
                self.global_hits.popleft()
            if len(self.global_hits) >= 120 or (client not in self.clients and len(self.clients) >= 1024):
                return False
            hits = self.clients.setdefault(client, deque())
            if len(hits) >= 60:
                return False
            hits.append(now)
            self.global_hits.append(now)
            return True


class SecurityMiddleware:
    def __init__(self, app, settings, routes):
        self.app, self.settings, self.routes = app, settings, routes
        self.limiter = PublicLimiter()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        public = self.settings.public
        response_started = False
        async def secure_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                headers += [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                            (b"referrer-policy", b"no-referrer"), (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                            (b"cache-control", b"no-store")]
                if public:
                    headers.append((b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"))
                message = {**message, "headers": headers}
            await send(message)
        async def reject(code, message):
            response = JSONResponse({"detail": {"message": message}}, code,
                                    headers={"Retry-After": "60"} if code == 429 else None)
            await response(scope, receive, secure_send)
        if not public:
            peer = (scope.get("client") or ("",))[0]
            try:
                local = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                local = peer == "testclient"  # in-process tests only; not a network address
            if not local:
                return await reject(403, "LOCAL mode accepts loopback clients only.")
            # CORS alone does not stop a foreign page's simple multipart POST.
            # Keep CLI requests working, but require trusted browser origins for
            # local writes as well as the separate public-demo calculation gate.
            headers = dict(scope["headers"])
            origin = headers.get(b"origin", b"").decode("latin1")
            same_origin = f"{scope['scheme']}://{headers.get(b'host', b'').decode('latin1')}"
            development_origins = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (15173, 4173)}
            if scope["method"] == "POST" and origin and origin not in development_origins | {same_origin}:
                return await reject(403, "LOCAL writes require a trusted local browser origin.")
            return await self.app(scope, receive, secure_send)
        path, method = scope["path"], scope["method"]
        if len(scope.get("query_string", b"")) + len(path) > MAX_URL:
            return await reject(414, "Request URL exceeds the demo limit.")
        # Match the actual registered route first. A new overlapping route cannot
        # inherit permission from a reviewed wildcard template.
        from starlette.routing import Match
        matched = next((r for r in iter_route_contexts(self.routes) if r.matches(scope)[0] == Match.FULL), None)
        key = (method, getattr(matched, "path", None))
        if path.startswith("/api"):
            if key not in PUBLIC_ROUTES:
                return await reject(403, "This action is unavailable in PUBLIC_DEMO. Use a local workspace to import, save or export.")
        elif method not in ("GET", "HEAD") or (path not in ("/", "/index.html", "/favicon.svg") and not path.startswith("/assets/")):
            return await reject(404, "Resource not available.")
        query = parse_qs(scope.get("query_string", b"").decode("utf-8", errors="replace"), keep_blank_values=True)
        if any(v != "1" for v in query.get("batch_id", [])) or any(v != "synthetic" for v in query.get("source_category", [])):
            return await reject(403, "Only the official demo batch and synthetic operational cohort are public.")
        if key[1] and "{plan_id}" in key[1] and not re.fullmatch(r"/api/decisions/plans/1", path):
            return await reject(404, "Demo plan not found.")
        if key[1] and "{service_id}" in key[1] and not re.match(r"^/api/impact/records/[12](?:/|$)", path):
            return await reject(404, "Demo record not found.")
        if method == "POST":
            headers = dict(scope["headers"])
            # Single-origin calculations: direct HTTP clients may omit Origin.
            origin = headers.get(b"origin")
            host = headers.get(b"host", b"").decode("latin1").lower()
            if origin:
                try:
                    parsed = urlsplit(origin.decode("latin1").lower())
                except ValueError:
                    return await reject(403, "Invalid browser origin.")
                # TLS may terminate at the hosting edge; no forwarded header is
                # needed to compare its browser origin with the validated Host.
                if parsed.scheme not in ("http", "https") or parsed.netloc != host or parsed.path or parsed.query or parsed.fragment:
                    return await reject(403, "Cross-origin demo calculations are unavailable.")
            if not headers.get(b"content-type", b"").lower().startswith(b"application/json"):
                return await reject(415, "Use application/json for demo previews.")
            try:
                size = int(headers.get(b"content-length", b"0"))
                if size < 0 or size > MAX_BODY:
                    return await reject(413, "Demo request exceeds 64 KiB.")
            except ValueError:
                return await reject(400, "Invalid request length.")
            if not self.limiter.allow((scope.get("client") or ("unknown",))[0]):
                return await reject(429, "Demo calculation limit reached. Wait one minute and retry.")
            body = bytearray()
            deadline = time.monotonic() + 10
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - time.monotonic()))
                except TimeoutError:
                    return await reject(408, "Demo request body timed out.")
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY:
                    return await reject(413, "Demo request exceeds 64 KiB.")
                if not message.get("more_body", False):
                    break
            try:
                data = json.loads(body)
            except (ValueError, RecursionError):
                return await reject(422, "Invalid JSON request.")
            if isinstance(data, dict):
                if data.get("batch_id", 1) != 1 or data.get("context_batch_id") not in (None, 1) or data.get("decision_plan_id") not in (None, 1):
                    return await reject(403, "Only public demo references are available.")
                if path.startswith("/api/impact/") and data.get("source_category") != "synthetic":
                    return await reject(403, "Impact previews must be explicitly synthetic in PUBLIC_DEMO.")
                if path == "/api/decisions/preview":
                    # Tighten the local engine's larger bounds for public CPU use.
                    scenarios = data.get("demand_scenarios", [])
                    capacity, step = data.get("maximum_capacity"), data.get("batch_increment")
                    if isinstance(scenarios, list) and len(scenarios) > 10:
                        return await reject(422, "Public previews allow at most 10 demand scenarios.")
                    if isinstance(capacity, int) and isinstance(step, int) and step > 0 and capacity // step >= 201:
                        return await reject(422, "Public previews allow at most 201 batch candidates. Increase the batch increment or reduce capacity.")
            async def replay():
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            receive = replay
        try:
            await self.app(scope, receive, secure_send)
        except Exception as exc:
            import logging
            logging.getLogger("mealloop").error("Public request failed (%s)", type(exc).__name__)
            if response_started:
                raise
            return await reject(500, "The service could not complete this request. Please retry.")
