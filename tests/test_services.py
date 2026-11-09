import pytest

pytestmark = pytest.mark.asyncio

ORDER = {"customer": "Ana", "items": [{"item_id": "espresso", "quantity": 2}, {"item_id": "croissant", "quantity": 1}]}


async def test_menu_lists_and_gets_items(cafe):
    async with cafe.direct(cafe.menu) as c:
        items = (await c.get("/items")).json()
        assert {"espresso", "croissant"} <= {i["id"] for i in items}
        assert (await c.get("/items/espresso")).json()["price_cents"] == 220
        assert (await c.get("/items/nope")).status_code == 404


async def test_payments_approves_declines_and_is_idempotent(cafe):
    async with cafe.direct(cafe.payments) as c:
        body = {"order_id": "o1", "amount_cents": 500, "card_token": "tok_visa"}
        first = (await c.post("/charge", json=body)).json()
        again = (await c.post("/charge", json=body)).json()
        assert first["status"] == "approved" and first == again
        declined = await c.post("/charge", json={**body, "order_id": "o2", "card_token": "tok_declined"})
        assert declined.status_code == 402
        assert (await c.post("/charge", json={**body, "amount_cents": 0})).status_code == 422


async def test_notifications_validates_and_keeps_recent(cafe):
    async with cafe.direct(cafe.notifications) as c:
        assert (await c.post("/notify", json={"order_id": "o1", "kind": "order_confirmed", "customer": "Ana"})).status_code == 202
        assert (await c.post("/notify", json={"order_id": "o1", "kind": "spam", "customer": "Ana"})).status_code == 422
        recent = (await c.get("/notifications")).json()
        assert len(recent) == 1 and recent[0]["kind"] == "order_confirmed"


async def test_order_end_to_end_through_the_gateway(cafe):
    r = await cafe.client.post("/api/orders", json=ORDER)
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "paid" and order["total_cents"] == 2 * 220 + 280
    assert (await cafe.client.get(f"/api/orders/{order['id']}")).json()["status"] == "paid"
    async with cafe.direct(cafe.notifications) as c:
        assert (await c.get("/notifications")).json()[0]["order_id"] == order["id"]


async def test_order_validation_and_menu_rules(cafe):
    assert (await cafe.client.post("/api/orders", json={"customer": "A", "items": []})).status_code == 422
    unknown = await cafe.client.post("/api/orders", json={"customer": "A", "items": [{"item_id": "pizza", "quantity": 1}]})
    assert unknown.status_code == 422
    soldout = await cafe.client.post("/api/orders", json={"customer": "A", "items": [{"item_id": "banana-bread", "quantity": 1}]})
    assert soldout.status_code == 409


async def test_declined_card_gives_402_and_a_failed_order(cafe):
    r = await cafe.client.post("/api/orders", json={**ORDER, "card_token": "tok_declined"})
    assert r.status_code == 402 and r.json()["status"] == "payment_failed"
    assert (await cafe.client.get(f"/api/orders/{r.json()['id']}")).json()["status"] == "payment_failed"


async def test_unknown_order_is_404_and_listing_works(cafe):
    assert (await cafe.client.get("/api/orders/ord_missing")).status_code == 404
    await cafe.client.post("/api/orders", json=ORDER)
    assert len((await cafe.client.get("/api/orders")).json()) == 1


async def test_gateway_menu_passthrough(cafe):
    assert len((await cafe.client.get("/api/menu")).json()) >= 5
