"""OpenTelemetry tracing.

Every service creates spans for incoming requests and outgoing HTTP calls and passes the trace context on
(W3C `traceparent` header), so one order shows up as one trace across all five services. Spans are exported
only if `OTEL_EXPORTER_OTLP_ENDPOINT` is set (to a collector, Jaeger, Tempo ...). Trace and span ids are
always added to the logs, so logs and traces can be joined even without a collector.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

_provider_installed = False


class TraceLogFilter(logging.Filter):
    """Add trace_id and span_id of the active span to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        return True


def setup_tracing(service: str, version: str, otlp_endpoint: str = "", console: bool = False) -> TracerProvider:
    """Install the process-wide tracer provider once; return it."""
    global _provider_installed
    provider = TracerProvider(resource=Resource.create({"service.name": service, "service.version": version}))
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint.rstrip("/") + "/v1/traces")))
    if console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    if not _provider_installed:
        trace.set_tracer_provider(provider)
        _provider_installed = True
    for handler in logging.getLogger().handlers:
        handler.addFilter(TraceLogFilter())
    return provider
