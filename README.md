# Harmonia Risk API

Real-time fraud detection engine for instant payout disbursements. Every request is evaluated in **< 200 ms** across six fraud signals and returns a composite risk score with a recommended action.

**Stack:** Python 3.11+ · FastAPI 0.115 · Uvicorn · SQLite (`aiosqlite`) · Pydantic v2

---

## Documentation

| Document | Description |
|---|---|
| [docs/API.md](docs/API.md) | Full API reference — all endpoints, request/response models, error codes |
| [docs/DEMO.md](docs/DEMO.md) | Step-by-step walkthrough of all 14 fraud detection scenarios with curl examples |

Interactive docs are also auto-generated from code at `/docs` (Swagger) and `/redoc` (ReDoc) once the server is running.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Seed the database with sample merchants, transactions, blocklist, and allowlist entries
python -m data.seed_data

# 3. Start the server
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Configuration

Settings are loaded from environment variables with the `HARMONIA_` prefix (via `pydantic-settings`).

| Variable | Default | Description |
|---|---|---|
| `HARMONIA_DATABASE_PATH` | `harmonia.db` | SQLite file path |
| `HARMONIA_RULES_CACHE_TTL_SECONDS` | `300` | In-memory TTL for merchant rules cache |
| `HARMONIA_BLOCKLIST_CACHE_TTL_SECONDS` | `60` | In-memory TTL for blocklist/allowlist cache |
| `HARMONIA_MAX_RESPONSE_TIME_MS` | `200` | SLA target (logged on each request, not enforced) |

---

## Scoring Pipeline

Each `POST /api/v1/risk/score` call runs these steps in order:

```
1. Allowlist check    → auto-APPROVE  if recipient is on the merchant's allowlist
2. Blocklist check    → auto-BLOCK    if any identifier (ip, email, account, device, user) is blocked
3. Max payout cap     → auto-BLOCK    if amount > merchant's max_payout.max_amount
4. Six fraud signals  → each returns a score contribution (0 – max_score)
5. Sum contributions  → capped at 100
6. Classify score     → LOW / MEDIUM / HIGH → APPROVE / REVIEW / BLOCK
7. Persist result     → writes to transactions + risk_audit tables
```

### Fraud Signals

| Signal | Max pts | Default trigger condition |
|---|---|---|
| `velocity` | 30 | User exceeds 5 transactions in a 10-minute rolling window |
| `amount_anomaly` | 25 | Amount > 3× user's historical average, or > $500 with no prior history |
| `geo_mismatch` | 20 | `ip_country` ≠ `user_country` |
| `new_account` | 15 | Account age < 7 days **and** amount > $200 |
| `money_mule` | 20 | Recipient received payouts from ≥ 3 distinct merchants |
| `time_of_day` | 10 | Transaction hour falls in UTC 00:00–05:59 |

### Risk Levels

| Score | Level | Action |
|---|---|---|
| 0 – 30 | LOW | APPROVE |
| 31 – 60 | MEDIUM | REVIEW |
| 61 – 100 | HIGH | BLOCK |

All thresholds are **configurable per merchant** without code changes.

---

## API Overview

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service health check |
| `/api/v1/risk/score` | POST | Score a payout transaction |
| `/api/v1/rules/{merchant_id}` | GET | Get merchant risk rules |
| `/api/v1/rules/{merchant_id}` | PUT | Update merchant risk rules (invalidates cache) |
| `/api/v1/blocklist/` | GET / POST / DELETE | Manage blocked identifiers |
| `/api/v1/blocklist/allowlist/` | GET / POST / DELETE | Manage trusted recipients |
| `/api/v1/batch/rescore` | POST | Re-score historical transactions against current rules |
| `/api/v1/audit/` | GET | List audit records |
| `/api/v1/audit/{transaction_id}` | GET | Full audit detail for one transaction |

See [docs/API.md](docs/API.md) for complete request/response schemas and examples.

---

## Database Schema

SQLite, created automatically on startup. Five tables:

| Table | Primary key | Purpose |
|---|---|---|
| `transactions` | `id` (TEXT) | Every scored payout request |
| `merchant_rules` | `merchant_id` | Per-merchant rule configuration (JSON blob) |
| `blocklist` | `id` (AUTOINCREMENT) | Blocked identifiers; unique on `(entry_type, value, merchant_id)` |
| `allowlist` | `id` (AUTOINCREMENT) | Trusted recipients; unique on `(entry_type, value, merchant_id)` |
| `risk_audit` | `id` (AUTOINCREMENT) | Append-only audit log |

---

## Running Tests

```bash
pytest
pytest tests/test_file.py::test_function_name   # single test
```
