"""Test wiring. `Cafe` runs all five services in one process, talking over in-memory ASGI transports."""

from __future__ import annotations

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from beanie.common.config import Settings
from beanie.common.downstream import Downstream
from beanie.gateway.main import create_app as gateway_app
from beanie.menu.main import create_app as menu_app
from beanie.notifications.main import create_app as notifications_app
from beanie.orders.main import create_app as orders_app
from beanie.payments.main import create_app as payments_app


def make_settings(**overrides) -> Settings:
    base = dict(
        app_version="test",
        log_level="warn",
        log_format="text",
        menu_url="http://menu",
        orders_url="http://orders",
        payments_url="http://payments",
        notifications_url="http://notifications",
        database_url="",
        downstream_timeout=2.0,
        otlp_endpoint="",
        trace_console=False,
        chaos_enabled=False,
        max_items_per_order=20,
    )
    base.update(overrides)
    return Settings(**base)


def link(name: str, app, provider) -> Downstream:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{name}")
    return Downstream(name, f"http://{name}", 2.0, client=client, tracer_provider=provider)


class Cafe:
    def __init__(self, **overrides) -> None:
        self.spans = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.spans))
        s = make_settings(**overrides)
        p = self.provider
        self.menu = menu_app(s, tracer_provider=p)
        self.payments = payments_app(s, tracer_provider=p)
        self.notifications = notifications_app(s, tracer_provider=p)
        self.orders = orders_app(
            s,
            menu=link("menu", self.menu, p),
            payments=link("payments", self.payments, p),
            notifications=link("notifications", self.notifications, p),
            tracer_provider=p,
        )
        self.gateway = gateway_app(s, menu=link("menu", self.menu, p), orders=link("orders", self.orders, p), tracer_provider=p)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.gateway), base_url="http://gateway")

    def direct(self, app) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://svc")


@pytest.fixture
def cafe():
    return Cafe()


@pytest.fixture
def chaos_cafe():
    return Cafe(chaos_enabled=True)
