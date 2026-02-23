# Harmonia Risk API

Real-time fraud detection engine for instant payout disbursements. Every request is evaluated in **< 200 ms** across six fraud signals and returns a composite risk score with a recommended action.

**Stack:** Python 3.11+ · FastAPI 0.115 · Uvicorn · SQLite (`aiosqlite`) · Pydantic v2

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

## API Reference

### Health

```
GET /health
→ { "status": "ok", "service": "harmonia-risk-api", "version": "1.0.0" }
```

---

### Risk Scoring

#### `POST /api/v1/risk/score`

Evaluate a payout and return a risk assessment.

**Request body** (`PayoutRequest`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `transaction_id` | string | ✓ | Unique identifier for this payout |
| `merchant_id` | string | ✓ | |
| `user_id` | string | ✓ | The sender |
| `recipient_account` | string | ✓ | Destination bank account |
| `amount` | float > 0 | ✓ | |
| `currency` | string | — | ISO 4217, default `USD` |
| `recipient_email` | string | — | Used by allowlist check |
| `recipient_phone` | string | — | |
| `user_ip` | string | — | Used by blocklist and geo_mismatch |
| `device_id` | string | — | Used by blocklist |
| `user_country` | string | — | ISO 3166-1 alpha-3; used by geo_mismatch |
| `ip_country` | string | — | ISO 3166-1 alpha-3; used by geo_mismatch |
| `account_created_at` | datetime | — | Used by new_account signal |
| `timestamp` | datetime | — | Defaults to `utcnow()` |
| `metadata` | object | — | Arbitrary key/value data, stored but not scored |

**Response** (`RiskAssessment`):

```json
{
  "transaction_id": "TXN-2024-001",
  "merchant_id": "MER001",
  "risk_score": 72.0,
  "risk_level": "HIGH",
  "action": "BLOCK",
  "signals": [
    {
      "signal": "velocity",
      "triggered": true,
      "score_contribution": 30,
      "description": "High velocity: 6 transactions in last 10 min (limit: 3)",
      "details": { "transaction_count": 6, "window_minutes": 10, "limit": 3 }
    },
    {
      "signal": "amount_anomaly",
      "triggered": true,
      "score_contribution": 22,
      "description": "Amount is 4.6x above user's average ($48.20)",
      "details": { "current_amount": 222.0, "user_avg": 48.2, "multiplier": 4.6 }
    }
  ],
  "processing_time_ms": 12.4,
  "evaluated_at": "2024-06-15T14:30:01Z"
}
```

---

### Risk Rules

#### `GET /api/v1/rules/{merchant_id}`

Returns current rules for the merchant. If no custom rules exist, returns the system defaults.

#### `PUT /api/v1/rules/{merchant_id}`

Create or replace the full `MerchantRules` object. **Invalidates the rules cache immediately.**

`merchant_id` in the URL must match `merchant_id` in the request body.

Full configurable fields:

```json
{
  "merchant_id": "MER001",
  "velocity":       { "enabled": true, "max_transactions": 5, "time_window_minutes": 10, "max_score": 30 },
  "amount_anomaly": { "enabled": true, "threshold_multiplier": 3.0, "min_history_count": 3, "no_history_large_amount": 500.0, "max_score": 25 },
  "geo_mismatch":   { "enabled": true, "max_score": 20 },
  "new_account":    { "enabled": true, "new_account_days": 7, "suspicious_amount": 200.0, "max_score": 15 },
  "money_mule":     { "enabled": true, "min_merchant_count": 3, "max_score": 20 },
  "time_of_day":    { "enabled": true, "suspicious_hours": [0,1,2,3,4,5], "max_score": 10 },
  "max_payout":     { "enabled": true, "max_amount": 10000.0 },
  "score_thresholds": { "low_max": 30, "medium_max": 60 },
  "allowlist_auto_approve": true
}
```

---

### Blocklist & Allowlist

**Blocklist** — auto-BLOCKs a transaction when a matching identifier is found.

Valid `entry_type` values: `ip`, `email`, `account`, `device`, `user`.

Set `merchant_id: null` for a **global** entry (applies across all merchants).

```
GET    /api/v1/blocklist/                        Query params: entry_type, merchant_id
POST   /api/v1/blocklist/                        Body: { entry_type, value, reason?, merchant_id? }  → 201
DELETE /api/v1/blocklist/{entry_id}              → 204
```

**Allowlist** — auto-APPROVEs a transaction (skips all signal evaluation).

Valid `entry_type` values: `recipient_account`, `recipient_email`.

Allowlist entries are always merchant-scoped (`merchant_id` is required).

```
GET    /api/v1/blocklist/allowlist/              Query param: merchant_id
POST   /api/v1/blocklist/allowlist/              Body: { entry_type, value, merchant_id, reason? }  → 201
DELETE /api/v1/blocklist/allowlist/{entry_id}    → 204
```

Both lists use a **1-minute in-memory cache**, invalidated immediately on any write or delete.

---

### Batch Re-scoring

#### `POST /api/v1/batch/rescore`

Re-evaluates historical transactions against the **current** rules. Useful after rule changes to see what decisions would have looked different.

Select transactions by explicit list or by date range — `merchant_id` is always required.

```json
{
  "merchant_id": "MER001",
  "transaction_ids": ["TXN-001", "TXN-002"],
  "start_date": null,
  "end_date": null,
  "update_scores": false
}
```

Set `update_scores: true` to persist the new scores back to the `transactions` table. The original audit log record is never modified.

---

### Audit Trail

Every scored transaction writes an immutable record containing the full request payload, all signal results, the rules snapshot active at evaluation time, and processing duration.

```
GET /api/v1/audit/                   Query params: merchant_id, action (APPROVE|REVIEW|BLOCK), limit (max 500), offset
GET /api/v1/audit/{transaction_id}   Full detail: request, signals, rules_snapshot, processing_time_ms
```

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
