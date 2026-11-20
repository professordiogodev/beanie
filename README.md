# Beanie

[![CI](https://github.com/professordiogodev/beanie/actions/workflows/ci.yml/badge.svg)](https://github.com/professordiogodev/beanie/actions/workflows/ci.yml)

A small cafe ordering system made of **five services that call each other**. It is the application you run on Kubernetes, observe and operate in weeks 7 to 9 of the Ironhack DevOps & Cloud Engineering bootcamp.

It is built to be **observed**: every service exposes metrics, writes structured logs and produces OpenTelemetry traces, and every service can be made slow or flaky on purpose so you can practise finding the problem.

```text
                         ┌──> menu :8001           (what we sell, prices)
customer ──> gateway :8000
                         └──> orders :8002 ──┬──> menu          (price every item)
                                 │           ├──> payments :8003  (charge the card)
                                 ▼           └──> notifications :8004  (tell the customer)
                            PostgreSQL (optional)
```

| Service | What it does | Port | Depends on |
|---------|--------------|------|------------|
| `gateway` | The only public door. `/api/menu`, `/api/orders`. Turns failures behind it into 502, 503 or 504. | 8000 | menu, orders |
| `menu` | The items and prices. Read only. | 8001 | nothing |
| `orders` | Prices an order, charges it, saves it (memory or PostgreSQL), notifies. | 8002 | menu, payments, notifications, PostgreSQL (optional) |
| `payments` | A pretend card processor. `tok_visa` approves, `tok_declined` declines, `tok_slow` approves after 1.5 s. | 8003 | nothing |
| `notifications` | Keeps the last 200 messages sent to customers. | 8004 | nothing |

What it does **not** have: a Dockerfile, a compose file, Kubernetes manifests, Helm charts, dashboards or alert rules. Those are your job.

## Requirements

| You need | Why | Check it |
|----------|-----|----------|
| **Python 3.11 or newer** (tested on 3.12, 3.13, 3.14 and 3.15; Ubuntu 24.04 ships 3.12) | the application and its tests | `python3 --version` |
| **`make`** | short commands for install, run and test (macOS: `xcode-select --install`; Ubuntu: `sudo apt install make`) | `make --version` |
| **`git`** | to clone the repository | `git --version` |

PostgreSQL is **optional**: without `DATABASE_URL`, orders are kept in memory. The `venv` folder keeps the dependencies inside the project, so nothing is installed on your whole system.

> **If `make install-dev` fails** with `Could not find a version that satisfies the requirement ...`, or with a long build error: first make sure the virtual environment is active (your prompt starts with `(venv)`), and run `python --version` inside it. The dependencies are version ranges that have ready-made packages for Python 3.11 to 3.15; a much older or much newer Python may not have them. Pick a Python in that range explicitly (for example `python3.13 -m venv venv` after `brew install python@3.13`, or `sudo apt install python3.12-venv`), delete the old `venv` folder (`rm -rf venv`) and start again from the quick start. Do not use `sudo pip`.

## Quick start (development)

```bash
git clone https://github.com/professordiogodev/beanie.git
cd beanie
python3 -m venv venv && source venv/bin/activate
make install-dev
make run                       # all five services: gateway on http://localhost:8000
```

In another terminal:

```bash
curl -s localhost:8000/api/menu
curl -s -X POST localhost:8000/api/orders -H 'Content-Type: application/json' \
  -d '{"customer": "Ana", "items": [{"item_id": "flat-white", "quantity": 2}]}'
curl -s localhost:8004/notifications           # the customer was told
make load                                      # steady stream of orders, for dashboards and traces
```

Interactive docs of each service: `http://localhost:PORT/docs`.

## The public API (gateway)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/menu` | The menu. |
| `POST` | `/api/orders` | Place an order: `customer`, `items` (`item_id`, `quantity`), optional `card_token` (default `tok_visa`). **201** paid, **402** card declined, **409** item sold out, **422** invalid, **503** menu or payments unreachable, **504** too slow. |
| `GET` | `/api/orders/{id}` | One order and its status: `pending`, `paid`, `payment_failed`, `payment_error`. |
| `GET` | `/api/orders` | Latest orders. |

Every service also has `GET /healthz` (liveness), `GET /readyz` (readiness), `GET /metrics` (Prometheus) and `GET`/`PUT /chaos` (failure injection, see below).

## Observability (what is built in)

| Signal | How |
|--------|-----|
| **Metrics** | `/metrics` on every service. `beanie_http_requests_total{service,method,route,status}`, `beanie_http_request_duration_seconds` (histogram), `beanie_http_requests_in_flight`, `beanie_build_info`, plus business metrics: `beanie_orders_total{status}`, `beanie_payments_total{result}`, `beanie_payments_approved_cents_total`, `beanie_notifications_total{kind}`. |
| **Logs** | One JSON object per line on stdout: `ts`, `level`, `service`, `msg`, `request_id`, `trace_id`, `span_id` and fields such as `order_id`. |
| **Traces** | OpenTelemetry. One order is one trace across all five services (W3C `traceparent`). Set `OTEL_EXPORTER_OTLP_ENDPOINT` to send spans to a collector, Jaeger or Tempo; `OTEL_TRACES_CONSOLE=true` prints them. |
| **Correlation** | The same `request_id` and `trace_id` appear in the logs of every service an order touched, so you can follow one order across services. |

### Failure injection

Start a service with `CHAOS_ENABLED=true`, then make it misbehave:

```bash
curl -X PUT localhost:8003/chaos -H 'Content-Type: application/json' -d '{"latency_ms": 3000}'     # slow payments
curl -X PUT localhost:8001/chaos -H 'Content-Type: application/json' -d '{"error_rate": 0.5}'       # menu fails half the time
curl -X PUT localhost:8001/chaos -H 'Content-Type: application/json' -d '{"latency_ms": 0, "error_rate": 0}'   # back to normal
```

Never enable it in production. `/healthz`, `/readyz` and `/metrics` are never affected.

## Configuration

Environment variables only. `.env.example` lists all of them with comments. `.env` is ignored by git: never commit it.

| Variable | Default | Used by | Description |
|----------|---------|---------|-------------|
| `MENU_URL`, `ORDERS_URL`, `PAYMENTS_URL`, `NOTIFICATIONS_URL` | `http://localhost:8001` ... `8004` | gateway, orders | Where the other services are. In Docker or Kubernetes: the service names. |
| `DOWNSTREAM_TIMEOUT` | `2` | gateway, orders | Seconds to wait for another service. |
| `DATABASE_URL` | empty (memory) | orders | `postgresql://USER:PASSWORD@HOST:5432/DATABASE`. The table is created on startup. |
| `PORT`, `HOST` | per service, `0.0.0.0` | all | Listen address for `python -m beanie <service>`. |
| `APP_VERSION` | package version | all | Reported by `/healthz`, `/metrics`, logs. Set it to the image tag in your pipeline. |
| `LOG_LEVEL`, `LOG_FORMAT` | `info`, `json` | all | `debug\|info\|warn\|error`, `json\|text` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | all | OTLP/HTTP endpoint, e.g. `http://collector:4318`. |
| `OTEL_TRACES_CONSOLE` | `false` | all | Also print spans to stdout. |
| `CHAOS_ENABLED` | `false` | all | Allow `PUT /chaos`. |
| `MAX_ITEMS_PER_ORDER` | `20` | orders | Input limit. |

## Things worth knowing as a DevOps engineer

- **One codebase, one image, five commands.** `python -m beanie gateway|menu|orders|payments|notifications` (or `uvicorn beanie.menu.main:create_app --factory`). You can build one image or five.
- **Liveness never looks at other services; readiness does.** If `menu` is down the gateway stays alive (`/healthz` 200) but is not ready (`/readyz` 503). Restarting it would not help, and that is the point of the two probes.
- **Without `DATABASE_URL`, orders live in the process.** Two replicas of `orders` then show different orders. That is the lesson that sends you to a database.
- **A slow service is worse than a dead one.** Payments waits up to 5 s, so a slow payment makes the whole order slow. Traces show exactly where the time went.
- **Notifications are best effort.** If it is down, orders still succeed and a warning is logged.
- **Payments is idempotent** per order id, like a real processor.

## Development

```bash
make help
make test                # unit tests + coverage (no services needed; all five services run in one process)
make test-integration    # real PostgreSQL (DATABASE_URL set)
make lint                # ruff
make check               # lint + tests: what CI runs
```

```text
beanie/
  common/                configuration, logging, tracing, the shared service skeleton, failure injection, the client for calling other services
  gateway/ menu/ orders/ payments/ notifications/    one folder per service (main.py)
scripts/                 run_all.py (start everything), loadgen.py (traffic)
tests/                   unit and cross-service tests; tests/integration uses a real PostgreSQL
docs/                    architecture and operations runbook
```

## Documentation

- [Architecture](docs/architecture.md)
- [Operations runbook](docs/operations.md): ports, health, metrics, logs, traces, failure modes
- [Contributing](CONTRIBUTING.md), [Changelog](CHANGELOG.md), [Security policy](SECURITY.md)

## License

MIT, see [LICENSE](LICENSE).
