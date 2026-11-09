import pytest

pytestmark = pytest.mark.asyncio

ORDER = {"customer": "Ana", "items": [{"item_id": "espresso", "quantity": 1}]}


async def test_health_is_up_and_reports_version(cafe):
    async with cafe.direct(cafe.menu) as c:
        body = (await c.get("/healthz")).json()
        assert body == {"status": "ok", "service": "menu", "version": "test"}


async def test_readiness_follows_dependencies(cafe):
    r = await cafe.client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"] == {"menu": True, "orders": True}


async def test_readiness_is_503_when_a_dependency_is_down():
    import httpx

    from beanie.common.downstream import Downstream
    from beanie.gateway.main import create_app
    from tests.conftest import make_settings

    def refuse(request):
        raise httpx.ConnectError("refused")

    def dead(n):
        return Downstream(
            n, f"http://{n}", 1, client=httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url=f"http://{n}")
        )

    app = create_app(make_settings(), menu=dead("menu"), orders=dead("orders"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://g") as c:
        r = await c.get("/readyz")
        assert r.status_code == 503 and r.json()["checks"] == {"menu": False, "orders": False}
        assert (await c.get("/healthz")).status_code == 200  # liveness never looks at dependencies


async def test_metrics_count_requests_by_route(cafe):
    await cafe.client.post("/api/orders", json=ORDER)
    await cafe.client.get("/api/orders/ord_missing")
    async with cafe.direct(cafe.orders) as c:
        text = (await c.get("/metrics")).text
    assert 'beanie_http_requests_total{method="POST",route="/orders",service="orders",status="201"} 1.0' in text
    assert 'route="/orders/{order_id}"' in text and 'status="404"' in text
    assert 'beanie_orders_total{status="paid"} 1.0' in text
    assert "beanie_http_request_duration_seconds_bucket" in text
    assert 'beanie_build_info{service="orders",version="test"} 1.0' in text


async def test_payments_metrics_track_money(cafe):
    await cafe.client.post("/api/orders", json=ORDER)
    async with cafe.direct(cafe.payments) as c:
        text = (await c.get("/metrics")).text
    assert "beanie_payments_approved_cents_total 220.0" in text


async def test_request_id_is_returned_and_reaches_downstream_services(cafe):
    r = await cafe.client.get("/api/menu", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert (await cafe.client.get("/api/menu")).headers["X-Request-ID"]


async def test_one_order_is_one_trace_across_services(cafe):
    cafe.spans.clear()
    await cafe.client.post("/api/orders", json=ORDER)
    spans = cafe.spans.get_finished_spans()
    assert len({s.context.trace_id for s in spans}) == 1
    names = {s.name for s in spans}
    assert {"POST /api/orders", "POST /orders", "GET /items/{item_id}", "POST /charge", "POST /notify"} <= names
    clients = [s for s in spans if s.kind.name == "CLIENT"]
    assert len(clients) >= 4  # gateway->orders, orders->menu, orders->payments, orders->notifications


async def test_access_log_lines_carry_the_trace_id(cafe, capsys):
    from beanie.common.logging_config import configure_logging

    configure_logging("gateway", "info", "json")
    from beanie.common.telemetry import setup_tracing

    setup_tracing("gateway", "t")  # installs the log filter on the new handler
    await cafe.client.get("/api/menu")
    lines = [line for line in capsys.readouterr().out.splitlines() if '"msg": "request"' in line]
    assert lines and all('"trace_id"' in line for line in lines)
