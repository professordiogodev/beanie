# Operations runbook

Everything an operator needs to run Beanie. It is true for the code in this repository.

## Processes

| Process | Command | Port | Needs |
|---------|---------|------|-------|
| gateway | `python -m beanie gateway` | 8000 | menu, orders |
| menu | `python -m beanie menu` | 8001 | nothing |
| orders | `python -m beanie orders` | 8002 | menu, payments; notifications (optional); PostgreSQL if `DATABASE_URL` is set |
| payments | `python -m beanie payments` | 8003 | nothing |
| notifications | `python -m beanie notifications` | 8004 | nothing |
| PostgreSQL (optional) | 13 or newer | 5432 | |

All processes: Python 3.11 to 3.13, dependencies from `requirements.txt` (runtime only), unprivileged user, no files written. Shutdown is `SIGTERM`. Start order does not matter for the services (they connect on demand); `orders` needs PostgreSQL at startup when `DATABASE_URL` is set.

## Health and readiness

| Endpoint | Meaning | When it fails |
|----------|---------|---------------|
| `/healthz` (all) | the process is alive | restart it |
| `/readyz` gateway | menu and orders answer `/healthz` | stop sending traffic, fix the dependency, do not restart the gateway |
| `/readyz` orders | its store, menu and payments answer | same |
| `/readyz` menu, payments, notifications | always ready (no dependencies) | |

## Metrics (Prometheus)

| Metric | Where | Meaning |
|--------|-------|---------|
| `beanie_http_requests_total{service,method,route,status}` | all | rate and errors by route template |
| `beanie_http_request_duration_seconds` | all | latency histogram; use `histogram_quantile` for p95 |
| `beanie_http_requests_in_flight{service}` | all | saturation |
| `beanie_orders_total{status}` | orders | `paid`, `payment_failed`, `payment_error` |
| `beanie_payments_total{result}`, `beanie_payments_approved_cents_total` | payments | approvals, declines, money |
| `beanie_notifications_total{kind}` | notifications | messages sent |
| `beanie_build_info{service,version}` | all | which version runs where |

Starting alerts: 5xx ratio above 1% on the gateway for 5 minutes; p95 latency above 1 s; `payment_error` orders above 0; `payment_failed` share above 20%; any `/readyz` failing for 2 minutes.

Scrape each service on its own port. The `service` label is added by the service itself, so it survives relabelling.

## Logs

JSON, one object per line on stdout: `ts`, `level`, `service`, `logger`, `msg`, `request_id`, `trace_id`, `span_id`, and per message fields (`order_id`, `route`, `status`, `duration_ms` ...). The access line has `msg: "request"`.

Follow one order: find its `request_id` in the gateway log, then search every service for that id (or for the `trace_id`).

## Traces

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318` (OTLP over HTTP). Spans: one server span per request and one client span per outgoing call. Resource attributes: `service.name`, `service.version`. Health, readiness and metrics requests are not traced.

## Failure modes

| Symptom | Likely cause | Look at |
|---------|--------------|---------|
| Orders return 503 `menu is unreachable` | menu down or wrong `MENU_URL` | `/readyz` of orders and gateway, menu logs |
| Orders return 503 `payments is timeout` | payments slow (above 5 s) | payments latency histogram, a trace of one order |
| Orders return 504 from the gateway | orders slower than 10 s | traces: which child span is long |
| `payment_error` orders in the database | payments failed after the order was saved | `beanie_orders_total{status="payment_error"}`, payments logs |
| Order stays `pending` | `orders` crashed between saving and charging | orders logs around the time; restarts |
| Two replicas of orders show different orders | no `DATABASE_URL` | set it |
| `PUT /chaos` returns 403 | `CHAOS_ENABLED` is not `true` | environment |
| Gateway `/readyz` 503 but `/healthz` 200 | a dependency is down; this is expected | fix the dependency, do not restart the gateway |

## Safe to know

- No secrets are needed except the PostgreSQL password inside `DATABASE_URL`. Treat it as a secret.
- Payments never talks to a bank and stores nothing durable. Do not put real card numbers anywhere.
