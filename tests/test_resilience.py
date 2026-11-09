"""What happens when a service behind another one is slow, broken or gone."""

import httpx
import pytest

from tests.conftest import link

pytestmark = pytest.mark.asyncio

ORDER = {"customer": "Ana", "items": [{"item_id": "espresso", "quantity": 1}]}


def broken(status=None, exc=None):
    def handler(request):
        if exc:
            raise exc
        return httpx.Response(status, json={"detail": "x"})

    return httpx.MockTransport(handler)


def dead_downstream(name, exc=None, status=None):
    from beanie.common.downstream import Downstream

    client = httpx.AsyncClient(transport=broken(status, exc), base_url=f"http://{name}")
    return Downstream(name, f"http://{name}", 1.0, client=client)


async def test_payments_down_gives_503_and_an_order_marked_payment_error(cafe):
    from beanie.orders.main import create_app
    from tests.conftest import make_settings

    app = create_app(
        make_settings(),
        menu=link("menu", cafe.menu, cafe.provider),
        payments=dead_downstream("payments", exc=httpx.ConnectError("refused")),
        notifications=link("notifications", cafe.notifications, cafe.provider),
        tracer_provider=cafe.provider,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://o") as c:
        r = await c.post("/orders", json=ORDER)
        assert r.status_code == 503 and "unreachable" in r.json()["detail"]
        order = (await c.get(f"/orders/{r.json()['order_id']}")).json()
        assert order["status"] == "payment_error"


async def test_menu_timeout_is_503_and_nothing_is_saved(cafe):
    from beanie.orders.main import create_app
    from tests.conftest import make_settings

    app = create_app(
        make_settings(),
        menu=dead_downstream("menu", exc=httpx.ReadTimeout("slow")),
        payments=link("payments", cafe.payments, cafe.provider),
        notifications=link("notifications", cafe.notifications, cafe.provider),
        tracer_provider=cafe.provider,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://o") as c:
        assert (await c.post("/orders", json=ORDER)).status_code == 503
        assert (await c.get("/orders")).json() == []


async def test_notifications_down_does_not_fail_the_order(cafe):
    from beanie.orders.main import create_app
    from tests.conftest import make_settings

    app = create_app(
        make_settings(),
        menu=link("menu", cafe.menu, cafe.provider),
        payments=link("payments", cafe.payments, cafe.provider),
        notifications=dead_downstream("notifications", status=500),
        tracer_provider=cafe.provider,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://o") as c:
        r = await c.post("/orders", json=ORDER)
        assert r.status_code == 201 and r.json()["status"] == "paid"


@pytest.mark.parametrize(("exc", "status"), [(httpx.ReadTimeout("slow"), 504), (httpx.ConnectError("refused"), 503)])
async def test_gateway_maps_failures_to_clear_statuses(cafe, exc, status):
    from beanie.gateway.main import create_app
    from tests.conftest import make_settings

    app = create_app(
        make_settings(),
        menu=dead_downstream("menu", exc=exc),
        orders=dead_downstream("orders", exc=exc),
        tracer_provider=cafe.provider,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://g") as c:
        assert (await c.get("/api/menu")).status_code == status


async def test_gateway_maps_bad_upstream_answers_through(cafe):
    from beanie.gateway.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(), menu=dead_downstream("menu", status=500), orders=link("orders", cafe.orders, cafe.provider))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://g") as c:
        assert (await c.get("/api/menu")).status_code == 500


async def test_chaos_is_refused_unless_enabled(cafe):
    async with cafe.direct(cafe.menu) as c:
        assert (await c.put("/chaos", json={"latency_ms": 100})).status_code == 403


async def test_chaos_makes_a_service_fail_and_ops_endpoints_stay_clean(chaos_cafe):
    async with chaos_cafe.direct(chaos_cafe.menu) as c:
        assert (await c.put("/chaos", json={"error_rate": 1.0})).status_code == 200
        assert (await c.get("/items")).status_code == 500
        assert (await c.get("/healthz")).status_code == 200
        assert (await c.put("/chaos", json={"error_rate": 0})).status_code == 200
        assert (await c.get("/items")).status_code == 200
    # through the whole chain: menu broken -> orders says 503 -> gateway passes it on
    async with chaos_cafe.direct(chaos_cafe.menu) as c:
        await c.put("/chaos", json={"error_rate": 1.0})
    r = await chaos_cafe.client.post("/api/orders", json=ORDER)
    assert r.status_code == 503


async def test_chaos_latency_is_applied(chaos_cafe):
    import time

    async with chaos_cafe.direct(chaos_cafe.menu) as c:
        await c.put("/chaos", json={"latency_ms": 150})
        t0 = time.perf_counter()
        await c.get("/items")
        assert time.perf_counter() - t0 >= 0.14
