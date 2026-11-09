"""Where orders live: memory (default) or PostgreSQL. Plain SQL so every query can be read."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Protocol

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          text PRIMARY KEY,
    customer    text NOT NULL,
    items       jsonb NOT NULL,
    total_cents integer NOT NULL,
    status      text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS orders_created_idx ON orders (created_at DESC);
"""


class OrderStore(Protocol):
    async def create(self, order: dict[str, Any]) -> None: ...
    async def set_status(self, order_id: str, status: str) -> None: ...
    async def get(self, order_id: str) -> dict[str, Any] | None: ...
    async def recent(self, limit: int) -> list[dict[str, Any]]: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._orders: dict[str, dict[str, Any]] = {}

    async def create(self, order: dict[str, Any]) -> None:
        self._orders[order["id"]] = dict(order)

    async def set_status(self, order_id: str, status: str) -> None:
        self._orders[order_id]["status"] = status

    async def get(self, order_id: str) -> dict[str, Any] | None:
        order = self._orders.get(order_id)
        return dict(order) if order else None

    async def recent(self, limit: int) -> list[dict[str, Any]]:
        return [dict(o) for o in sorted(self._orders.values(), key=lambda o: o["created_at"], reverse=True)[:limit]]

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(dsn, min_size=1, max_size=5, open=True, timeout=5)
        with self._pool.connection() as conn:
            conn.execute(SCHEMA)

    @staticmethod
    def _row(r) -> dict[str, Any]:
        return {"id": r[0], "customer": r[1], "items": r[2], "total_cents": r[3], "status": r[4], "created_at": r[5].isoformat()}

    async def create(self, order: dict[str, Any]) -> None:
        def run() -> None:
            with self._pool.connection() as conn:
                conn.execute(
                    "INSERT INTO orders (id, customer, items, total_cents, status, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        order["id"],
                        order["customer"],
                        json.dumps(order["items"]),
                        order["total_cents"],
                        order["status"],
                        datetime.fromisoformat(order["created_at"]),
                    ),
                )

        await asyncio.to_thread(run)

    async def set_status(self, order_id: str, status: str) -> None:
        def run() -> None:
            with self._pool.connection() as conn:
                conn.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))

        await asyncio.to_thread(run)

    async def get(self, order_id: str) -> dict[str, Any] | None:
        def run():
            with self._pool.connection() as conn:
                return conn.execute(
                    "SELECT id, customer, items, total_cents, status, created_at FROM orders WHERE id = %s", (order_id,)
                ).fetchone()

        row = await asyncio.to_thread(run)
        return self._row(row) if row else None

    async def recent(self, limit: int) -> list[dict[str, Any]]:
        def run():
            with self._pool.connection() as conn:
                return conn.execute(
                    "SELECT id, customer, items, total_cents, status, created_at FROM orders ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                ).fetchall()

        return [self._row(r) for r in await asyncio.to_thread(run)]

    async def ping(self) -> bool:
        def run() -> bool:
            try:
                with self._pool.connection(timeout=2) as conn:
                    conn.execute("SELECT 1")
                return True
            except Exception:
                return False

        return await asyncio.to_thread(run)

    async def close(self) -> None:
        await asyncio.to_thread(self._pool.close)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
