"""Orders: the heart of the system. Prices an order with Menu, charges it with Payments, tells Notifications.

Order of events for POST /orders:
  1. ask Menu for every item (existence, availability, price)      -> 503 if Menu is down
  2. save the order as `pending`
  3. ask Payments to charge it                                      -> declined: `payment_failed` (402)
                                                                       Payments down or slow: `payment_error` (503)
  4. save `paid`, then tell Notifications (best effort: a failure is logged, never fails the order)
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter
from pydantic import BaseModel, Field

from beanie.common.app import Service
from beanie.common.config import Settings
from beanie.common.downstream import Downstream, DownstreamError
from beanie.orders.store import MemoryStore, OrderStore, PostgresStore, now_iso

log = logging.getLogger("beanie.orders")


class Line(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=20)


class NewOrder(BaseModel):
    customer: str = Field(min_length=1, max_length=80)
    items: list[Line] = Field(min_length=1)
    card_token: str = Field(default="tok_visa", min_length=1, max_length=64)


def create_app(
    settings: Settings | None = None,
    store: OrderStore | None = None,
    menu: Downstream | None = None,
    payments: Downstream | None = None,
    notifications: Downstream | None = None,
    tracer_provider=None,
):
    settings = settings or Settings.from_env()
    store = store or (PostgresStore(settings.database_url) if settings.database_url else MemoryStore())
    t = settings.downstream_timeout
    menu = menu or Downstream("menu", settings.menu_url, t, tracer_provider=tracer_provider)
    payments = payments or Downstream("payments", settings.payments_url, max(t, 5.0), tracer_provider=tracer_provider)
    notifications = notifications or Downstream("notifications", settings.notifications_url, t, tracer_provider=tracer_provider)

    async def close() -> None:
        for d in (menu, payments, notifications):
            await d.aclose()
        await store.close()

    service = Service(
        "orders",
        settings,
        checks={"store": store.ping, "menu": menu.ping, "payments": payments.ping},
        tracer_provider=tracer_provider,
        on_close=close,
    )
    app = service.app
    orders_total = Counter("beanie_orders_total", "Orders by final status", ["status"], registry=service.registry)

    async def price(lines: list[Line]) -> tuple[list[dict], int]:
        wanted = sorted({line.item_id for line in lines})
        if len(lines) > settings.max_items_per_order:
            raise HTTPException(422, f"at most {settings.max_items_per_order} lines per order")
        try:
            responses = await asyncio.gather(*(menu.request("GET", f"/items/{i}") for i in wanted))
        except DownstreamError as exc:
            raise HTTPException(503, f"menu is {exc.kind}") from exc
        found: dict[str, dict] = {}
        for item_id, r in zip(wanted, responses, strict=True):
            if r.status_code == 404:
                raise HTTPException(422, f"unknown item {item_id!r}")
            if r.status_code != 200:
                raise HTTPException(503, "menu is failing")
            found[item_id] = r.json()
        priced = []
        for line in lines:
            item = found[line.item_id]
            if not item["available"]:
                raise HTTPException(409, f"{item['name']} is sold out")
            priced.append(
                {
                    "item_id": line.item_id,
                    "name": item["name"],
                    "quantity": line.quantity,
                    "unit_cents": item["price_cents"],
                }
            )
        return priced, sum(p["quantity"] * p["unit_cents"] for p in priced)

    async def notify(order: dict, kind: str) -> None:
        try:
            await notifications.json(
                "POST",
                "/notify",
                expect=(202,),
                json={"order_id": order["id"], "kind": kind, "customer": order["customer"]},
            )
        except DownstreamError as exc:
            log.warning("could not notify", extra={"order_id": order["id"], "reason": str(exc)})

    @app.post("/orders", status_code=201, tags=["orders"])
    async def create_order(body: NewOrder):
        lines, total = await price(body.items)
        order = {
            "id": "ord_" + uuid.uuid4().hex[:10],
            "customer": body.customer,
            "items": lines,
            "total_cents": total,
            "status": "pending",
            "created_at": now_iso(),
        }
        await store.create(order)
        log.info("order created", extra={"order_id": order["id"], "total_cents": total})
        try:
            response = await payments.request(
                "POST", "/charge", json={"order_id": order["id"], "amount_cents": total, "card_token": body.card_token}
            )
        except DownstreamError as exc:
            await store.set_status(order["id"], "payment_error")
            orders_total.labels("payment_error").inc()
            log.error("payment failed", extra={"order_id": order["id"], "reason": str(exc)})
            return JSONResponse({"detail": f"payments is {exc.kind}", "order_id": order["id"]}, status_code=503)
        if response.status_code == 402:
            order["status"] = "payment_failed"
            await store.set_status(order["id"], "payment_failed")
            orders_total.labels("payment_failed").inc()
            await notify(order, "payment_failed")
            return JSONResponse(order, status_code=402)
        if response.status_code != 200:
            await store.set_status(order["id"], "payment_error")
            orders_total.labels("payment_error").inc()
            return JSONResponse({"detail": "payments is failing", "order_id": order["id"]}, status_code=503)
        order["status"] = "paid"
        await store.set_status(order["id"], "paid")
        orders_total.labels("paid").inc()
        await notify(order, "order_confirmed")
        return order

    @app.get("/orders/{order_id}", tags=["orders"])
    async def get_order(order_id: str):
        order = await store.get(order_id)
        if not order:
            raise HTTPException(404, "no such order")
        return order

    @app.get("/orders", tags=["orders"])
    async def recent_orders(limit: int = 20):
        return await store.recent(max(1, min(limit, 100)))

    app.state.service = service
    return app
