# WebhookRelay

Reliable webhook delivery service. Retry, circuit breaker, dead letter queue, HMAC signing — the works.

Your webhook endpoint went down at 2am. Your events didn't get lost. That's the point.

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| **[🚀 QUICKSTART.md](QUICKSTART.md)** | **Start here!** Get running in 2 minutes |
| **[📘 EXAMPLES.md](EXAMPLES.md)** | API usage examples & code snippets |
| **[🔧 TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | Common issues & solutions |
| **[📁 PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** | File organization & architecture |
| **[⚙️ GIT_SETUP.md](GIT_SETUP.md)** | Git configuration after cloning |

---

## What it does

- **At-least-once delivery** — events survive process restarts, they're in PostgreSQL
- **Exponential backoff** — with jitter, per-endpoint config, respects `Retry-After`
- **Circuit breaker** — per endpoint, Redis-backed, shared across workers
- **Dead letter queue** — browse, replay single or bulk, with idempotency guards
- **HMAC-SHA256 signing** — Stripe-style `t=timestamp,v1=signature`, replay attack prevention
- **Full audit log** — every delivery attempt with status, latency, response body

## Stack

| Component | Why |
|-----------|-----|
| FastAPI | Async REST API |
| SQLAlchemy 2.0 async | PostgreSQL ORM |
| arq | Async Redis task queue (not Celery — overkill) |
| Redis | Queue backend + circuit breaker state |
| httpx | Async HTTP delivery client |
| Alembic | Database migrations |
| PostgreSQL 16 | Durable event storage |

## Quick start

**One-command setup after cloning:**

```bash
git clone <repo-url>
cd WebhookRelay

make setup
```

**PowerShell users (рекомендуется):**
```powershell
# Автоматическая установка с проверками и retry
.\setup.ps1
```

**Что произойдет:**
1. ✓ Проверка Docker daemon
2. ✓ Загрузка базовых образов (с автоматическими повторами при ошибках)
3. ✓ Сборка образов приложения
4. ✓ Запуск PostgreSQL, Redis, API и 2x Workers
5. ✓ Автоматический запуск миграций БД
6. ✓ Проверка здоровья всех сервисов

**Endpoints:**
- API: `http://localhost:8742`
- Docs: `http://localhost:8742/docs`
- DB: `localhost:54320` (postgres/postgres)
- Redis: `localhost:63790`

**Useful commands:**
```bash
make logs
make health
make down
make clean
make test
```

**Troubleshooting:**
- Если Docker выдает TLS ошибки, запустите: `docker system prune -f && make setup`
- Проверьте что Docker Desktop запущен: `docker info`
- Логи конкретного сервиса: `docker compose logs -f api`

## Architecture

```
┌─────────┐     ┌───────────┐     ┌─────────────┐
│  Client  │────▶│  FastAPI   │────▶│  PostgreSQL  │
└─────────┘     │  (API)     │     │  (events,    │
                └─────┬──────┘     │   attempts,  │
                      │            │   DLQ)       │
                      ▼            └──────────────┘
                ┌───────────┐            ▲
                │   Redis    │            │
                │  (arq +    │     ┌──────┴──────┐
                │   circuit  │────▶│  arq Worker  │──▶ POST endpoint
                │   breaker) │     │  (delivery)  │
                └───────────┘     └─────────────┘
```

## API

### Endpoints

```
POST   /api/v1/endpoints                    Register webhook endpoint
GET    /api/v1/endpoints                    List endpoints
GET    /api/v1/endpoints/{id}               Get endpoint
PATCH  /api/v1/endpoints/{id}               Update endpoint
DELETE /api/v1/endpoints/{id}               Deactivate endpoint
GET    /api/v1/endpoints/{id}/stats         Delivery stats + circuit state
POST   /api/v1/endpoints/{id}/rotate-secret Rotate signing secret
```

### Events

```
POST   /api/v1/events                      Ingest event for delivery
GET    /api/v1/events/{id}                  Event status + attempts
GET    /api/v1/events/{id}/attempts         Delivery attempt log
```

### Dead Letter Queue

```
GET    /api/v1/dlq                          Browse DLQ
GET    /api/v1/dlq/{id}                     DLQ entry details
POST   /api/v1/dlq/{id}/replay              Replay single event
POST   /api/v1/dlq/replay/bulk              Bulk replay with filters
DELETE /api/v1/dlq/{id}                     Discard entry
```

### Operations

```
GET    /api/v1/health                       Health check
GET    /api/v1/stats                        Global delivery stats
POST   /api/v1/inbound/verify              Test HMAC verification
```

## Usage example

Register an endpoint:
```bash
curl -X POST http://localhost:8742/api/v1/endpoints \
  -H "Content-Type: application/json" \
  -d '{"name": "My Service", "url": "https://httpbin.org/post"}'
```

Send an event:
```bash
curl -X POST http://localhost:8742/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "endpoint_id": "<id-from-above>",
    "event_type": "order.created",
    "payload": {"order_id": 42, "total": 99.99}
  }'
```

Check delivery:
```bash
curl http://localhost:8742/api/v1/events/<event-id>
```

## Delivery flow

1. Event created → status `pending`
2. arq worker picks it up → status `delivering`
3. HMAC-sign payload, POST to endpoint
4. **Success (2xx)** → status `delivered`, circuit breaker records success
5. **Retryable failure (5xx, timeout)** → status `failed`, exponential backoff, next attempt scheduled
6. **Permanent failure (4xx)** → straight to DLQ
7. **All retries exhausted** → DLQ
8. **410 Gone** → endpoint auto-deactivated

## Circuit breaker

Per-endpoint, Redis-backed. State shared across all workers.

```
CLOSED ──(5 failures in 60s)──▶ OPEN ──(300s timeout)──▶ HALF_OPEN
   ▲                                                         │
   └────────────(success)──────────────────────────────────────┘
                                                         │
                                                    (failure)
                                                         │
                                                    ▼ OPEN
```

## HMAC signature

Every outgoing delivery includes:
```
X-Webhook-Signature: t=1614556800,v1=abc123def456...
X-Webhook-Event-ID: <uuid>
X-Webhook-Event-Type: order.created
X-Webhook-Timestamp: 1614556800
```

Receivers verify: `HMAC-SHA256(timestamp + "." + body, signing_secret)`.
Timestamp tolerance: 5 minutes (replay attack prevention).

## Project structure

```
src/webhook_relay/
├── api/v1/          REST endpoints
├── models/          SQLAlchemy ORM
├── schemas/         Pydantic v2
├── repositories/    Data access layer
├── services/        Business logic
├── worker/          arq task queue
├── config.py        Settings via env vars
├── database.py      Async SQLAlchemy engine
├── main.py          FastAPI app factory
└── middleware.py    Request ID + timing
```

## Ports

| Service | Port |
|---------|------|
| API | 8742 |
| PostgreSQL | 54320 |
| Redis | 63790 |

Non-default ports to avoid conflicts with local services.

## License

MIT
Webhooks that actually arrive. Retry, DLQ, HMAC verification, replay — production-grade delivery in one service.
