"""Run against a real database:  DATABASE_URL=postgresql://... make test-integration"""

import os
import uuid

import httpx
import pytest

from beanie.orders.main import create_app
from beanie.orders.store import PostgresStore, now_iso
from tests.conftest import Cafe, link, make_settings

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is not set")]


async def test_store_roundtrip_in_postgres():
    store = PostgresStore(DATABASE_URL)
    oid = "ord_" + uuid.uuid4().hex[:8]
    await store.create(
        {
            "id": oid,
            "customer": "Ana",
            "items": [{"item_id": "espresso", "quantity": 1}],
            "total_cents": 220,
            "status": "pending",
            "created_at": now_iso(),
        }
    )
    await store.set_status(oid, "paid")
    got = await store.get(oid)
    assert got["status"] == "paid" and got["items"][0]["item_id"] == "espresso"
    assert oid in [o["id"] for o in await store.recent(50)]
    assert await store.ping() is True
    await store.close()


async def test_orders_service_persists_in_postgres_and_reports_ready():
    cafe = Cafe()
    store = PostgresStore(DATABASE_URL)
    app = create_app(
        make_settings(),
        store=store,
        menu=link("menu", cafe.menu, cafe.provider),
        payments=link("payments", cafe.payments, cafe.provider),
        notifications=link("notifications", cafe.notifications, cafe.provider),
        tracer_provider=cafe.provider,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://o") as c:
        r = await c.post("/orders", json={"customer": "Ana", "items": [{"item_id": "espresso", "quantity": 3}]})
        assert r.status_code == 201
        assert (await c.get(f"/orders/{r.json()['id']}")).json()["total_cents"] == 660
        assert (await c.get("/readyz")).status_code == 200
    await store.close()
