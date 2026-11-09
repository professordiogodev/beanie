"""Notifications: tells the customer what happened. Here it only keeps the last messages in memory."""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

from prometheus_client import Counter
from pydantic import BaseModel, Field

from beanie.common.app import Service
from beanie.common.config import Settings

log = logging.getLogger("beanie.notifications")
KEEP = 200


class Notification(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern="^(order_confirmed|payment_failed)$")
    customer: str = Field(min_length=1, max_length=80)


def create_app(settings: Settings | None = None, tracer_provider=None):
    settings = settings or Settings.from_env()
    service = Service("notifications", settings, tracer_provider=tracer_provider)
    app = service.app
    sent: deque[dict] = deque(maxlen=KEEP)
    counter = Counter("beanie_notifications_total", "Notifications sent", ["kind"], registry=service.registry)

    @app.post("/notify", status_code=202, tags=["notifications"])
    async def notify(n: Notification):
        message = {"at": datetime.now(UTC).isoformat(timespec="seconds"), **n.model_dump()}
        sent.appendleft(message)
        counter.labels(n.kind).inc()
        log.info("notification sent", extra={"order_id": n.order_id, "kind": n.kind})
        return {"queued": True}

    @app.get("/notifications", tags=["notifications"])
    async def recent(limit: int = 20):
        return list(sent)[: max(1, min(limit, KEEP))]

    app.state.service = service
    return app
