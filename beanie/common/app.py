"""What every Beanie service shares: request ids, access log, metrics, health, readiness, tracing, chaos."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
    generate_latest,
)

from beanie.common.chaos import Chaos, ChaosConfig
from beanie.common.config import Settings
from beanie.common.downstream import request_id_var
from beanie.common.logging_config import configure_logging
from beanie.common.telemetry import setup_tracing

disable_created_metrics()
Check = Callable[[], Awaitable[bool]]
UNTOUCHED = {"/healthz", "/readyz", "/metrics", "/chaos"}
log = logging.getLogger("beanie.http")


class Service:
    """A FastAPI app plus its own metrics registry, so five of them can live in one test process."""

    def __init__(
        self, name: str, settings: Settings, checks: dict[str, Check] | None = None, tracer_provider=None, on_close=None
    ):
        self.name, self.settings, self.checks = name, settings, checks or {}
        self.chaos = Chaos(enabled=settings.chaos_enabled)
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "beanie_http_requests_total",
            "HTTP requests handled",
            ["service", "method", "route", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "beanie_http_request_duration_seconds",
            "HTTP request duration",
            ["service", "method", "route"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.inflight = Gauge("beanie_http_requests_in_flight", "Requests being handled", ["service"], registry=self.registry)
        self.info = Gauge("beanie_build_info", "Version of this service", ["service", "version"], registry=self.registry)
        self.info.labels(name, settings.app_version).set(1)
        self.on_close = on_close
        configure_logging(name, settings.log_level, settings.log_format)
        self.provider = tracer_provider or setup_tracing(
            name, settings.app_version, settings.otlp_endpoint, settings.trace_console
        )

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            yield
            if self.on_close:
                await self.on_close()

        self.app = FastAPI(title=f"Beanie {name}", version=settings.app_version, lifespan=lifespan)
        self.app.middleware("http")(self._middleware)
        # added last on purpose: the newest middleware is the outermost, so the span is active while we log
        FastAPIInstrumentor.instrument_app(
            self.app, tracer_provider=self.provider, excluded_urls="healthz,readyz,metrics", exclude_spans=["receive", "send"]
        )
        self._routes()

    async def _middleware(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        path = request.url.path
        self.inflight.labels(self.name).inc()
        started = time.perf_counter()
        try:
            if path not in UNTOUCHED and await self.chaos.apply():
                response: Response = JSONResponse({"detail": "injected failure"}, status_code=500)
            else:
                response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"request_id": rid, "path": path})
            response = JSONResponse({"detail": "internal error"}, status_code=500)
        finally:
            self.inflight.labels(self.name).dec()
        elapsed = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        if path not in UNTOUCHED:
            self.requests.labels(self.name, request.method, route, str(response.status_code)).inc()
            self.duration.labels(self.name, request.method, route).observe(elapsed)
            log.info(
                "request",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": path,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 1),
                },
            )
        response.headers["X-Request-ID"] = rid
        request_id_var.reset(token)
        return response

    def _routes(self) -> None:
        app, s = self.app, self.settings

        @app.get("/healthz", tags=["ops"])
        async def healthz():
            """Liveness: the process is up. Never checks other services."""
            return {"status": "ok", "service": self.name, "version": s.app_version}

        @app.get("/readyz", tags=["ops"])
        async def readyz():
            """Readiness: the things this service cannot work without answer."""
            results = {name: await check() for name, check in self.checks.items()}
            ok = all(results.values())
            return JSONResponse({"status": "ready" if ok else "not ready", "checks": results}, status_code=200 if ok else 503)

        @app.get("/metrics", tags=["ops"])
        async def metrics():
            return Response(generate_latest(self.registry), media_type=CONTENT_TYPE_LATEST)

        @app.get("/chaos", tags=["ops"])
        async def chaos_get():
            return self.chaos.view()

        @app.put("/chaos", tags=["ops"])
        async def chaos_put(cfg: ChaosConfig):
            if not self.chaos.enabled:
                raise HTTPException(403, "failure injection is off; start the service with CHAOS_ENABLED=true")
            self.chaos.set(cfg)
            log.warning("chaos changed", extra=cfg.model_dump())
            return self.chaos.view()
