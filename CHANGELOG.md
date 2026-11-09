# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com/), versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-09

### Added
- Five services: gateway, menu, orders, payments (fake), notifications.
- Orders kept in memory or in PostgreSQL (`DATABASE_URL`).
- `/healthz`, `/readyz` and `/metrics` on every service; JSON logs with `request_id`, `trace_id` and `span_id`.
- OpenTelemetry traces across all services, exported over OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- Failure injection (`PUT /chaos`, off unless `CHAOS_ENABLED=true`).
- `scripts/run_all.py` and `scripts/loadgen.py`.
- Tests (all services in one process, resilience, observability), integration tests against PostgreSQL, CI, `.env.example`, architecture and operations docs.
