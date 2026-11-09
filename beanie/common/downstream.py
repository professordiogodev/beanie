"""Calling another service: one place for timeouts, error mapping, request id and trace propagation."""

from __future__ import annotations

import contextvars
from typing import Any

import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class DownstreamError(Exception):
    """Another service did not give a usable answer."""

    def __init__(self, target: str, kind: str, status: int | None = None) -> None:
        super().__init__(f"{target}: {kind}" + (f" ({status})" if status else ""))
        self.target, self.kind, self.status = target, kind, status


class Downstream:
    """A small HTTP client for one other service. `kind` is timeout, unreachable or bad_status."""

    def __init__(self, name: str, base_url: str, timeout: float, client: httpx.AsyncClient | None = None, tracer_provider=None):
        self.name = name
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        HTTPXClientInstrumentor.instrument_client(self._client, tracer_provider=tracer_provider)
        self.calls: dict[str, int] = {}

    def _count(self, outcome: str) -> None:
        self.calls[outcome] = self.calls.get(outcome, 0) + 1

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {**kwargs.pop("headers", {}), "X-Request-ID": request_id_var.get()}
        try:
            response = await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            self._count("timeout")
            raise DownstreamError(self.name, "timeout") from exc
        except httpx.HTTPError as exc:
            self._count("unreachable")
            raise DownstreamError(self.name, "unreachable") from exc
        self._count("ok" if response.status_code < 500 else "error")
        return response

    async def json(self, method: str, path: str, expect: tuple[int, ...] = (200,), **kwargs: Any) -> Any:
        """Call and return the JSON body; any status not in `expect` becomes a DownstreamError."""
        response = await self.request(method, path, **kwargs)
        if response.status_code not in expect:
            raise DownstreamError(self.name, "bad_status", response.status_code)
        return response.json()

    async def ping(self) -> bool:
        try:
            return (await self._client.get("/healthz")).status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
