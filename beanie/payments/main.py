"""Payments: a pretend card processor. It never talks to a bank.

The card token decides the outcome, so exercises are repeatable:
  tok_visa      approved
  tok_declined  declined (HTTP 402)
  tok_slow      approved after 1.5 seconds
Charging the same order twice returns the first result (idempotent), like a real processor.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import HTTPException
from prometheus_client import Counter
from pydantic import BaseModel, Field

from beanie.common.app import Service
from beanie.common.config import Settings

log = logging.getLogger("beanie.payments")


class ChargeRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0, le=1_000_000)
    card_token: str = Field(min_length=1, max_length=64)


def create_app(settings: Settings | None = None, tracer_provider=None):
    settings = settings or Settings.from_env()
    service = Service("payments", settings, tracer_provider=tracer_provider)
    app = service.app
    charges: dict[str, dict] = {}
    revenue = Counter("beanie_payments_total", "Charges by result", ["result"], registry=service.registry)
    cents = Counter("beanie_payments_approved_cents_total", "Money approved, in cents", registry=service.registry)

    @app.post("/charge", tags=["payments"])
    async def charge(req: ChargeRequest):
        if req.order_id in charges:
            return charges[req.order_id]
        if req.card_token == "tok_slow":  # noqa: S105
            await asyncio.sleep(1.5)
        if req.card_token == "tok_declined":  # noqa: S105
            revenue.labels("declined").inc()
            log.warning("card declined", extra={"order_id": req.order_id})
            raise HTTPException(402, "card declined")
        result = {
            "payment_id": "pay_" + uuid.uuid4().hex[:10],
            "order_id": req.order_id,
            "amount_cents": req.amount_cents,
            "status": "approved",
        }
        charges[req.order_id] = result
        revenue.labels("approved").inc()
        cents.inc(req.amount_cents)
        log.info("charge approved", extra={"order_id": req.order_id, "amount_cents": req.amount_cents})
        return result

    app.state.service = service
    return app
