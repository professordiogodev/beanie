"""Gateway: the only service a customer talks to. It forwards to Menu and Orders and hides the rest.

Failures of a service behind it become clear answers: 502 (it answered with garbage), 503 (unreachable) or 504 (too slow).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from beanie.common.app import Service
from beanie.common.config import Settings
from beanie.common.downstream import Downstream, DownstreamError

log = logging.getLogger("beanie.gateway")
STATUS_FOR = {"timeout": 504, "unreachable": 503, "bad_status": 502}


def create_app(
    settings: Settings | None = None, menu: Downstream | None = None, orders: Downstream | None = None, tracer_provider=None
):
    settings = settings or Settings.from_env()
    t = settings.downstream_timeout
    menu = menu or Downstream("menu", settings.menu_url, t, tracer_provider=tracer_provider)
    orders = orders or Downstream("orders", settings.orders_url, max(t, 10.0), tracer_provider=tracer_provider)

    async def close() -> None:
        await menu.aclose()
        await orders.aclose()

    service = Service(
        "gateway", settings, checks={"menu": menu.ping, "orders": orders.ping}, tracer_provider=tracer_provider, on_close=close
    )
    app = service.app

    async def forward(target: Downstream, method: str, path: str, **kwargs) -> Response:
        try:
            r = await target.request(method, path, **kwargs)
        except DownstreamError as exc:
            log.error("upstream failed", extra={"upstream": exc.target, "reason": exc.kind})
            raise HTTPException(STATUS_FOR.get(exc.kind, 502), f"{exc.target} is {exc.kind}") from exc
        return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"))

    @app.get("/api/menu", tags=["public"])
    async def menu_list():
        return await forward(menu, "GET", "/items")

    @app.post("/api/orders", tags=["public"])
    async def order_create(body: dict):
        return await forward(orders, "POST", "/orders", json=body)

    @app.get("/api/orders", tags=["public"])
    async def order_list(limit: int = 20):
        return await forward(orders, "GET", "/orders", params={"limit": limit})

    @app.get("/api/orders/{order_id}", tags=["public"])
    async def order_get(order_id: str):
        return await forward(orders, "GET", f"/orders/{order_id}")

    @app.exception_handler(HTTPException)
    async def http_error(_, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    app.state.service = service
    return app
