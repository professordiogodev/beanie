"""Configuration from environment variables only (twelve-factor). One class serves all five services."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_version: str
    log_level: str
    log_format: str
    # where the other services live (DNS names in Docker or Kubernetes, localhost in development)
    menu_url: str
    orders_url: str
    payments_url: str
    notifications_url: str
    # orders keeps its data here; empty means in memory (lost on restart)
    database_url: str
    # how long one service waits for another before giving up
    downstream_timeout: float
    # telemetry: empty endpoint means traces stay in the process
    otlp_endpoint: str
    trace_console: bool
    # failure injection for monitoring exercises (off unless asked for)
    chaos_enabled: bool
    max_items_per_order: int

    @classmethod
    def from_env(cls) -> Settings:
        from beanie import __version__

        log_format = os.environ.get("LOG_FORMAT", "json").strip().lower()
        if log_format not in {"json", "text"}:
            raise ValueError("LOG_FORMAT must be 'json' or 'text'")
        return cls(
            app_version=os.environ.get("APP_VERSION", __version__).strip() or __version__,
            log_level=os.environ.get("LOG_LEVEL", "info").strip().lower(),
            log_format=log_format,
            menu_url=os.environ.get("MENU_URL", "http://localhost:8001").rstrip("/"),
            orders_url=os.environ.get("ORDERS_URL", "http://localhost:8002").rstrip("/"),
            payments_url=os.environ.get("PAYMENTS_URL", "http://localhost:8003").rstrip("/"),
            notifications_url=os.environ.get("NOTIFICATIONS_URL", "http://localhost:8004").rstrip("/"),
            database_url=os.environ.get("DATABASE_URL", "").strip(),
            downstream_timeout=_float("DOWNSTREAM_TIMEOUT", 2.0),
            otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip(),
            trace_console=_bool("OTEL_TRACES_CONSOLE"),
            chaos_enabled=_bool("CHAOS_ENABLED"),
            max_items_per_order=_int("MAX_ITEMS_PER_ORDER", 20),
        )
