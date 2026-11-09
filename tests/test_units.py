import json
import logging

import pytest

from beanie.common.config import Settings
from beanie.common.logging_config import JsonFormatter, configure_logging
from beanie.common.telemetry import TraceLogFilter, setup_tracing
from beanie.orders.store import MemoryStore


def test_settings_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    monkeypatch.delenv("MENU_URL", raising=False)
    s = Settings.from_env()
    assert s.menu_url == "http://localhost:8001" and s.database_url == "" and s.chaos_enabled is False
    monkeypatch.setenv("MENU_URL", "http://menu:8001/")
    monkeypatch.setenv("CHAOS_ENABLED", "true")
    monkeypatch.setenv("DOWNSTREAM_TIMEOUT", "0.5")
    s = Settings.from_env()
    assert s.menu_url == "http://menu:8001" and s.chaos_enabled and s.downstream_timeout == 0.5


@pytest.mark.parametrize(
    ("name", "value"), [("MAX_ITEMS_PER_ORDER", "many"), ("DOWNSTREAM_TIMEOUT", "fast"), ("LOG_FORMAT", "xml")]
)
def test_bad_settings_fail_loudly(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        Settings.from_env()


def test_json_logs_carry_extra_fields_and_trace_ids(capsys):
    configure_logging("orders", "info", "json")
    provider = setup_tracing("orders", "t")
    with provider.get_tracer("t").start_as_current_span("x"):
        logging.getLogger("t").info("hello", extra={"order_id": "o1"})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["service"] == "orders" and line["order_id"] == "o1" and line["msg"] == "hello"
    assert len(line["trace_id"]) == 32 and len(line["span_id"]) == 16


def test_text_logs_and_filter_without_span(capsys):
    configure_logging("menu", "debug", "text")
    logging.getLogger("t").info("plain")
    assert "menu plain" in capsys.readouterr().out
    record = logging.LogRecord("n", logging.INFO, "f", 1, "m", (), None)
    assert TraceLogFilter().filter(record) and not hasattr(record, "trace_id")
    assert JsonFormatter("x").format(record)


async def test_memory_store_roundtrip():
    s = MemoryStore()
    await s.create({"id": "a", "created_at": "2026-01-01", "status": "pending"})
    await s.create({"id": "b", "created_at": "2026-01-02", "status": "pending"})
    await s.set_status("a", "paid")
    assert (await s.get("a"))["status"] == "paid" and await s.get("zzz") is None
    assert [o["id"] for o in await s.recent(10)] == ["b", "a"]
    assert await s.ping() and await s.close() is None
