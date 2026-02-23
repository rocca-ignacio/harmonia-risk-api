# API Reference — Harmonia Risk API

Base URL: `http://localhost:8000`

Interactive docs (auto-generated from code):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Table of Contents

1. [Health Check](#health-check)
2. [Risk Scoring](#risk-scoring)
3. [Merchant Rules](#merchant-rules)
4. [Blocklist](#blocklist)
5. [Allowlist](#allowlist)
6. [Batch Re-scoring](#batch-re-scoring)
7. [Audit Log](#audit-log)
8. [Data Models](#data-models)
9. [Error Responses](#error-responses)

---

## Health Check

### `GET /health`

Verify the service is running.

**Response `200 OK`:**
```json
{ "status": "ok" }
```

---

## Risk Scoring

### `POST /api/v1/risk/score`

Score a payout transaction in real time. Returns a risk assessment in under 200ms.

**Pipeline (per request):**
1. Check allowlist → auto-APPROVE (score 0) if recipient is trusted
2. Check blocklist → auto-BLOCK (score 100) if any identifier is blocked
3. Max payout cap → auto-BLOCK (score 100) if amount > merchant limit
4. Evaluate 6 fraud signals → each contributes 0–N points
5. Sum contributions (capped at 100)
6. Classify: score → risk level → action
7. Persist transaction + audit log

**Request body:** [`PayoutRequest`](#payoutrequest)

```json
{
  "transaction_id": "TXN-2024-001",
  "merchant_id": "MER001",
  "user_id": "USR_RF_001",
  "recipient_account": "PH-ACC-7812345678",
  "recipient_email": "driver@example.com",
  "recipient_phone": null,
  "amount": 52.50,
  "currency": "PHP",
  "user_ip": "203.177.12.45",
  "device_id": "DEV-ABC123",
  "user_country": "PHL",
  "ip_country": "PHL",
  "account_created_at": "2023-01-15T00:00:00",
  "timestamp": "2024-06-15T14:30:00",
  "metadata": null
}
```

**Response `200 OK`:** [`RiskAssessment`](#riskassessment)

```json
{
  "transaction_id": "TXN-2024-001",
  "merchant_id": "MER001",
  "risk_score": 0.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": [
    {
      "signal": "velocity",
      "triggered": false,
      "score_contribution": 0,
      "description": "Velocity OK: 1 transaction in last 10 min (limit: 3)",
      "details": { "transaction_count": 1, "window_minutes": 10, "limit": 3 }
    },
    {
      "signal": "amount_anomaly",
      "triggered": false,
      "score_contribution": 0,
      "description": "Amount $52.50 is 1.0x user average $52.10 — within 3.0x threshold",
      "details": { "current_amount": 52.5, "user_avg": 52.1, "multiplier": 1.0 }
    },
    {
      "signal": "geo_mismatch",
      "triggered": false,
      "score_contribution": 0,
      "description": "IP country PHL matches account country PHL",
      "details": {}
    },
    {
      "signal": "new_account",
      "triggered": false,
      "score_contribution": 0,
      "description": "Account is 530 days old — not a new account",
      "details": { "account_age_days": 530 }
    },
    {
      "signal": "money_mule",
      "triggered": false,
      "score_contribution": 0,
      "description": "Recipient seen at 1 merchant — below threshold of 3",
      "details": { "merchant_count": 1 }
    },
    {
      "signal": "time_of_day",
      "triggered": false,
      "score_contribution": 0,
      "description": "Transaction hour 14 is not in suspicious hours",
      "details": { "hour": 14 }
    }
  ],
  "processing_time_ms": 8.3,
  "evaluated_at": "2024-06-15T14:30:00.123456"
}
```

**Blocked example (blocklist hit):**
```json
{
  "transaction_id": "TXN-BLOCKED-001",
  "merchant_id": "MER001",
  "risk_score": 100.0,
  "risk_level": "HIGH",
  "action": "BLOCK",
  "signals": [],
  "processing_time_ms": 2.1,
  "evaluated_at": "2024-06-15T14:30:00.456789"
}
```

**Errors:**

| Status | Condition |
|---|---|
| `422 Unprocessable Entity` | Missing required fields or `amount <= 0` |
| `500 Internal Server Error` | Unexpected engine error |

---

## Merchant Rules

### `GET /api/v1/rules/{merchant_id}`

Retrieve the current risk rules for a merchant. Returns defaults for unknown merchants.

**Path parameter:** `merchant_id` — e.g., `MER001`

**Response `200 OK`:** [`MerchantRules`](#merchantrules)

```json
{
  "merchant_id": "MER001",
  "velocity": {
    "enabled": true,
    "max_transactions": 3,
    "time_window_minutes": 10,
    "max_score": 30
  },
  "amount_anomaly": {
    "enabled": true,
    "threshold_multiplier": 3.0,
    "min_history_count": 3,
    "no_history_large_amount": 300.0,
    "max_score": 25
  },
  "geo_mismatch": {
    "enabled": true,
    "max_score": 20
  },
  "new_account": {
    "enabled": true,
    "new_account_days": 14,
    "suspicious_amount": 200.0,
    "max_score": 15
  },
  "money_mule": {
    "enabled": true,
    "min_merchant_count": 3,
    "max_score": 20
  },
  "time_of_day": {
    "enabled": true,
    "suspicious_hours": [0, 1, 2, 3, 4, 5],
    "max_score": 10
  },
  "max_payout": {
    "enabled": true,
    "max_amount": 2000.0
  },
  "score_thresholds": {
    "low_max": 30,
    "medium_max": 60
  },
  "allowlist_auto_approve": true
}
```

---

### `PUT /api/v1/rules/{merchant_id}`

Update risk rules for a merchant. Invalidates the in-memory cache immediately — all subsequent scoring requests use the new rules.

**Path parameter:** `merchant_id`

**Request body:** [`MerchantRules`](#merchantrules) (full object required)

**Response `200 OK`:** Updated [`MerchantRules`](#merchantrules)

**Example:**
```bash
curl -X PUT http://localhost:8000/api/v1/rules/MER001 \
  -H "Content-Type: application/json" \
  -d '{
    "merchant_id": "MER001",
    "velocity": { "enabled": true, "max_transactions": 2, "time_window_minutes": 10, "max_score": 30 },
    "amount_anomaly": { "enabled": true, "threshold_multiplier": 2.5, "min_history_count": 3, "no_history_large_amount": 200.0, "max_score": 25 },
    "geo_mismatch": { "enabled": true, "max_score": 20 },
    "new_account": { "enabled": true, "new_account_days": 14, "suspicious_amount": 150.0, "max_score": 15 },
    "money_mule": { "enabled": true, "min_merchant_count": 2, "max_score": 20 },
    "time_of_day": { "enabled": true, "suspicious_hours": [0,1,2,3,4,5], "max_score": 10 },
    "max_payout": { "enabled": true, "max_amount": 1000.0 },
    "score_thresholds": { "low_max": 25, "medium_max": 55 },
    "allowlist_auto_approve": true
  }'
```

---

## Blocklist

Blocked identifiers receive an automatic score of 100 / BLOCK without signal evaluation. Entries can be global (applies to all merchants) or merchant-specific.

**Valid `entry_type` values:** `ip`, `email`, `account`, `device`, `user`

---

### `GET /api/v1/blocklist/`

List blocklist entries.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `entry_type` | string (optional) | Filter by type: `ip`, `email`, `account`, `device`, `user` |
| `merchant_id` | string (optional) | Filter by merchant. Use empty string for global entries. |

**Response `200 OK`:**
```json
[
  {
    "id": 1,
    "entry_type": "ip",
    "value": "45.67.89.10",
    "reason": "Known fraud proxy — ASN AS209605",
    "merchant_id": "",
    "created_at": "2024-06-01T00:00:00"
  }
]
```

---

### `POST /api/v1/blocklist/`

Add a blocklist entry. Invalidates the cache immediately.

**Request body:**
```json
{
  "entry_type": "ip",
  "value": "198.51.100.99",
  "reason": "Flagged by threat intel feed",
  "merchant_id": ""
}
```

| Field | Required | Description |
|---|---|---|
| `entry_type` | Yes | `ip`, `email`, `account`, `device`, or `user` |
| `value` | Yes | The value to block |
| `reason` | No | Human-readable reason for the audit log |
| `merchant_id` | No | Leave empty or omit for a global entry; set to a merchant ID for a merchant-specific entry |

**Response `201 Created`:** The created [`BlocklistRecord`](#blocklistrecord)

**Errors:**

| Status | Condition |
|---|---|
| `409 Conflict` | Entry already exists |
| `422 Unprocessable Entity` | Invalid `entry_type` |

---

### `DELETE /api/v1/blocklist/{entry_id}`

Remove a blocklist entry by its numeric ID. Invalidates the cache immediately.

**Path parameter:** `entry_id` (integer)

**Response `204 No Content`**

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | Entry ID does not exist |

---

## Allowlist

Allowlisted recipients are auto-approved (score 0) before any signal evaluation. Allowlists are always merchant-specific.

**Valid `entry_type` values:** `recipient_account`, `recipient_email`

---

### `GET /api/v1/blocklist/allowlist/`

List allowlist entries.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `merchant_id` | string (optional) | Filter by merchant |

**Response `200 OK`:**
```json
[
  {
    "id": 1,
    "entry_type": "recipient_account",
    "value": "PH-ACC-TRUSTED-DRIVER01",
    "merchant_id": "MER001",
    "reason": "Verified driver — 3 years, 0 chargebacks",
    "created_at": "2024-06-01T00:00:00"
  }
]
```

---

### `POST /api/v1/blocklist/allowlist/`

Add a trusted recipient to a merchant's allowlist. Invalidates the cache immediately.

**Request body:**
```json
{
  "entry_type": "recipient_account",
  "value": "PH-ACC-NEW-TRUSTED-999",
  "merchant_id": "MER001",
  "reason": "Background-checked, approved by ops team"
}
```

| Field | Required | Description |
|---|---|---|
| `entry_type` | Yes | `recipient_account` or `recipient_email` |
| `value` | Yes | The account number or email to allowlist |
| `merchant_id` | Yes | Merchant this allowlist entry applies to |
| `reason` | No | Human-readable justification |

**Response `201 Created`:** The created [`AllowlistRecord`](#allowlistrecord)

**Errors:**

| Status | Condition |
|---|---|
| `409 Conflict` | Entry already exists |
| `422 Unprocessable Entity` | Invalid `entry_type` |

---

### `DELETE /api/v1/blocklist/allowlist/{entry_id}`

Remove an allowlist entry by its numeric ID. Invalidates the cache immediately.

**Path parameter:** `entry_id` (integer)

**Response `204 No Content`**

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | Entry ID does not exist |

---

## Batch Re-scoring

### `POST /api/v1/batch/rescore`

Re-evaluate historical transactions against the **current** risk rules. Useful after a rule update to measure its retrospective impact.

**Selection modes (at least one required):**
- Provide `transaction_ids` for a specific list, **or**
- Provide `start_date` / `end_date` for a date range

**Request body:**
```json
{
  "merchant_id": "MER001",
  "transaction_ids": [],
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "update_scores": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | Yes | Merchant whose transactions to re-score |
| `transaction_ids` | string[] | No | Specific transaction IDs to re-score |
| `start_date` | string (ISO date) | No | Start of date range (inclusive) |
| `end_date` | string (ISO date) | No | End of date range (inclusive) |
| `update_scores` | boolean | No | If `true`, overwrite stored `risk_score` and `action` in the DB. Default: `false` |

**Response `200 OK`:**
```json
{
  "rescored_count": 42,
  "updated_in_db": false,
  "summary": {
    "total": 42,
    "approve": 38,
    "review": 3,
    "block": 1,
    "changed": 4
  },
  "results": [
    {
      "transaction_id": "HIST-0001",
      "old_score": 10.0,
      "old_action": "APPROVE",
      "new_score": 30.0,
      "new_action": "BLOCK",
      "score_delta": 20.0
    }
  ]
}
```

| Field | Description |
|---|---|
| `rescored_count` | Total number of transactions processed |
| `updated_in_db` | Whether scores were written back to the DB |
| `summary.changed` | Transactions whose `action` changed under the new rules |
| `results[].score_delta` | `new_score - old_score` (null if transaction had no prior score) |

**Errors:**

| Status | Condition |
|---|---|
| `422 Unprocessable Entity` | Neither `transaction_ids` nor `start_date`/`end_date` provided |

---

## Audit Log

### `GET /api/v1/audit/`

List recent audit records. The audit log is append-only — each scoring call creates a permanent record including the full request, signal breakdown, and a snapshot of the rules that were active at evaluation time.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `merchant_id` | string | — | Filter by merchant |
| `action` | string | — | Filter by action: `APPROVE`, `REVIEW`, `BLOCK` |
| `limit` | integer | 50 | Max records to return (1–500) |
| `offset` | integer | 0 | Pagination offset |

**Response `200 OK`:**
```json
[
  {
    "id": 101,
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
        "description": "High velocity: 4 transactions in last 10 min (limit: 3)",
        "details": { "transaction_count": 4, "window_minutes": 10, "limit": 3 }
      }
    ],
    "processing_time_ms": 12.4,
    "evaluated_at": "2024-06-15T14:30:01"
  }
]
```

---

### `GET /api/v1/audit/{transaction_id}`

Get the full audit detail for a single transaction. Includes the original request payload and the merchant rules snapshot at the time of scoring.

**Path parameter:** `transaction_id`

**Response `200 OK`:**
```json
{
  "id": 101,
  "transaction_id": "TXN-2024-001",
  "merchant_id": "MER001",
  "risk_score": 72.0,
  "risk_level": "HIGH",
  "action": "BLOCK",
  "signals": [ ... ],
  "processing_time_ms": 12.4,
  "evaluated_at": "2024-06-15T14:30:01",
  "request": {
    "transaction_id": "TXN-2024-001",
    "merchant_id": "MER001",
    "user_id": "USR_RF_ATCK01",
    "recipient_account": "PH-ACC-2267890123",
    "amount": 48.0,
    "currency": "PHP",
    "user_ip": "203.177.12.45",
    "user_country": "PHL",
    "ip_country": "PHL",
    "timestamp": "2024-06-15T14:30:00"
  },
  "rules_snapshot": {
    "merchant_id": "MER001",
    "velocity": { "enabled": true, "max_transactions": 3, "time_window_minutes": 10, "max_score": 30 },
    "score_thresholds": { "low_max": 30, "medium_max": 60 }
  }
}
```

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No audit record for the given `transaction_id` |

---

## Data Models

### PayoutRequest

| Field | Type | Required | Description |
|---|---|---|---|
| `transaction_id` | string | Yes | Unique transaction identifier |
| `merchant_id` | string | Yes | Merchant submitting the payout |
| `user_id` | string | Yes | User/sender initiating the payout |
| `recipient_account` | string | Yes | Destination bank account number |
| `recipient_email` | string | No | Recipient email (checked against blocklist/allowlist) |
| `recipient_phone` | string | No | Recipient phone (stored, not scored) |
| `amount` | float | Yes | Payout amount — must be > 0 |
| `currency` | string | No | ISO 4217 currency code. Default: `USD` |
| `user_ip` | string | No | IP address of the request (checked against blocklist; used for geo mismatch) |
| `device_id` | string | No | Device fingerprint (checked against blocklist) |
| `user_country` | string | No | ISO 3166-1 alpha-3 country of the user's registered account (e.g., `PHL`) |
| `ip_country` | string | No | ISO 3166-1 alpha-3 country resolved from the IP (e.g., `NGA`) |
| `account_created_at` | datetime | No | When the user's account was created (used by `new_account` signal) |
| `timestamp` | datetime | No | Transaction timestamp. Defaults to `now()` |
| `metadata` | object | No | Arbitrary pass-through metadata (stored, not scored) |

---

### RiskAssessment

| Field | Type | Description |
|---|---|---|
| `transaction_id` | string | Echoed from the request |
| `merchant_id` | string | Echoed from the request |
| `risk_score` | float (0–100) | Composite risk score |
| `risk_level` | `LOW` \| `MEDIUM` \| `HIGH` | Derived from score vs. merchant thresholds |
| `action` | `APPROVE` \| `REVIEW` \| `BLOCK` | Recommended action |
| `signals` | `SignalResult[]` | One entry per evaluated signal (empty on blocklist/allowlist hits) |
| `processing_time_ms` | float | Total evaluation time in milliseconds |
| `evaluated_at` | datetime | UTC timestamp of when scoring completed |

---

### SignalResult

| Field | Type | Description |
|---|---|---|
| `signal` | string | Signal name: `velocity`, `amount_anomaly`, `geo_mismatch`, `new_account`, `money_mule`, `time_of_day` |
| `triggered` | boolean | Whether the signal fired |
| `score_contribution` | float | Points added to the total risk score |
| `description` | string | Human-readable explanation of the result |
| `details` | object | Signal-specific key-value diagnostic data |

---

### MerchantRules

| Field | Type | Default | Description |
|---|---|---|---|
| `merchant_id` | string | — | Merchant identifier |
| `velocity.enabled` | boolean | `true` | Enable velocity signal |
| `velocity.max_transactions` | integer | `5` | Max allowed transactions in the window |
| `velocity.time_window_minutes` | integer | `10` | Rolling window size in minutes |
| `velocity.max_score` | integer | `30` | Max score contribution for this signal |
| `amount_anomaly.enabled` | boolean | `true` | Enable amount anomaly signal |
| `amount_anomaly.threshold_multiplier` | float | `3.0` | Flag if amount > X × user's historical average |
| `amount_anomaly.min_history_count` | integer | `3` | Minimum past transactions needed for a baseline |
| `amount_anomaly.no_history_large_amount` | float | `500.0` | Flag if user has no history and amount exceeds this |
| `amount_anomaly.max_score` | integer | `25` | Max score contribution |
| `geo_mismatch.enabled` | boolean | `true` | Enable geo mismatch signal |
| `geo_mismatch.max_score` | integer | `20` | Max score contribution |
| `new_account.enabled` | boolean | `true` | Enable new account signal |
| `new_account.new_account_days` | integer | `7` | Account younger than X days is considered new |
| `new_account.suspicious_amount` | float | `200.0` | Trigger if new account AND amount exceeds this |
| `new_account.max_score` | integer | `15` | Max score contribution |
| `money_mule.enabled` | boolean | `true` | Enable money mule signal |
| `money_mule.min_merchant_count` | integer | `3` | Flag if recipient received from ≥ X distinct merchants |
| `money_mule.max_score` | integer | `20` | Max score contribution |
| `time_of_day.enabled` | boolean | `true` | Enable time-of-day signal |
| `time_of_day.suspicious_hours` | integer[] | `[0,1,2,3,4,5]` | UTC hours considered suspicious |
| `time_of_day.max_score` | integer | `10` | Max score contribution |
| `max_payout.enabled` | boolean | `true` | Enable max payout hard cap |
| `max_payout.max_amount` | float | `10000.0` | Auto-block if amount exceeds this |
| `score_thresholds.low_max` | integer | `30` | Scores 0–`low_max` → LOW → APPROVE |
| `score_thresholds.medium_max` | integer | `60` | Scores `low_max+1`–`medium_max` → MEDIUM → REVIEW; above → HIGH → BLOCK |
| `allowlist_auto_approve` | boolean | `true` | Auto-approve if recipient is on the merchant's allowlist |

---

### BlocklistRecord

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-assigned numeric ID |
| `entry_type` | string | `ip`, `email`, `account`, `device`, or `user` |
| `value` | string | The blocked value |
| `reason` | string | Optional explanation |
| `merchant_id` | string | Empty string = global; otherwise merchant-specific |
| `created_at` | string (ISO datetime) | When the entry was created |

---

### AllowlistRecord

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-assigned numeric ID |
| `entry_type` | string | `recipient_account` or `recipient_email` |
| `value` | string | The trusted value |
| `merchant_id` | string | Merchant this entry applies to |
| `reason` | string | Optional justification |
| `created_at` | string (ISO datetime) | When the entry was created |

---

## Error Responses

All errors follow FastAPI's standard error format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status Code | Meaning |
|---|---|
| `404 Not Found` | Resource does not exist (audit record, blocklist entry) |
| `409 Conflict` | Duplicate blocklist or allowlist entry |
| `422 Unprocessable Entity` | Validation error — invalid field value or missing required field |
| `500 Internal Server Error` | Unexpected internal error |

**422 example (missing required field):**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "merchant_id"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

---

## Risk Level Bands

| Score Range | Level | Action |
|---|---|---|
| 0 – `low_max` (default 30) | LOW | APPROVE |
| `low_max+1` – `medium_max` (default 60) | MEDIUM | REVIEW |
| `medium_max+1` – 100 | HIGH | BLOCK |

Thresholds are configurable per merchant via `score_thresholds` in [`MerchantRules`](#merchantrules).

## Fraud Signals

| Signal | Max pts | Trigger condition |
|---|---|---|
| `velocity` | 30 | User exceeds `max_transactions` in rolling `time_window_minutes` |
| `amount_anomaly` | 25 | Amount > `threshold_multiplier` × user's historical average, or no history and amount > `no_history_large_amount` |
| `geo_mismatch` | 20 | `ip_country` ≠ `user_country` |
| `new_account` | 15 | Account age < `new_account_days` AND amount > `suspicious_amount` |
| `money_mule` | 20 | Recipient received payouts from ≥ `min_merchant_count` distinct merchants |
| `time_of_day` | 10 | Transaction `timestamp` hour (UTC) is in `suspicious_hours` |

Scores are summed and capped at 100.
