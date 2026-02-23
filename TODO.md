# TODO — Evaluation Rubric Coverage

Progress tracker and rubric map for the Harmonia Risk API assessment.

---

## Risk Scoring Logic (25 pts)

- [x] Six fraud signals implemented: `velocity`, `amount_anomaly`, `geo_mismatch`, `new_account`, `money_mule`, `time_of_day`
- [x] Each signal returns a graduated score contribution (0 – max_score), not just a binary flag
- [x] Composite score is the sum of all signal contributions, capped at 100
- [x] Allowlist early exit — auto-APPROVE before signal evaluation (score 0, signals array empty)
- [x] Blocklist early exit — auto-BLOCK before signal evaluation (score 100, signals array empty)
- [x] Max payout hard cap — auto-BLOCK if amount exceeds merchant limit (score 100, signals array empty)
- [x] Risk level classification: LOW (0–30) → APPROVE, MEDIUM (31–60) → REVIEW, HIGH (61–100) → BLOCK
- [x] All signal thresholds and score bands are configurable per merchant

---

## API Design (20 pts)

- [x] `POST /api/v1/risk/score` — real-time payout scoring endpoint
- [x] `GET /health` — service health check
- [x] `GET /api/v1/rules/{merchant_id}` — retrieve merchant rules
- [x] `PUT /api/v1/rules/{merchant_id}` — update merchant rules
- [x] `GET/POST/DELETE /api/v1/blocklist/` — blocklist CRUD
- [x] `GET/POST/DELETE /api/v1/blocklist/allowlist/` — allowlist CRUD
- [x] `POST /api/v1/batch/rescore` — batch re-scoring endpoint
- [x] `GET /api/v1/audit/` and `GET /api/v1/audit/{transaction_id}` — audit log retrieval
- [x] Pydantic v2 request/response models with field validation (e.g. `amount > 0`)
- [x] Proper HTTP status codes: 200, 201, 204, 404, 409, 422, 500
- [x] FastAPI auto-generated Swagger UI (`/docs`) and ReDoc (`/redoc`)
- [x] Sub-200 ms response time target (logged per request via `processing_time_ms`)

---

## Configurable Rules (15 pts)

- [x] Per-merchant rules stored as JSON in SQLite `merchant_rules` table
- [x] System-wide defaults applied when no merchant-specific rules exist
- [x] Every signal threshold is individually configurable (velocity window, anomaly multiplier, suspicious hours, etc.)
- [x] Score band thresholds (`low_max`, `medium_max`) configurable per merchant
- [x] `PUT /api/v1/rules/{merchant_id}` immediately invalidates the in-memory rules cache
- [x] 5-minute TTL in-memory cache for merchant rules (`rules_service.py`)
- [x] Rule changes take effect on the very next scoring request (no restart needed)

---

## Historical Analysis (15 pts)

- [x] All scored transactions persisted to `transactions` table
- [x] Velocity signal queries rolling window of recent transactions per user
- [x] Amount anomaly signal computes per-user historical average from `transactions`
- [x] Money mule signal counts distinct merchants paying the same recipient account
- [x] Seed data provides realistic historical transaction volume across 3 merchants and multiple users (`data/seed_data.py`)
- [x] `POST /api/v1/batch/rescore` — re-evaluate historical transactions against current rules; supports transaction ID list or date range; optional `update_scores` flag to persist new scores
- [x] Batch re-score response includes per-transaction old/new score delta and aggregate summary (total, approve, review, block, changed)

---

## Code Quality (10 pts)

- [x] All six signals extend `BaseSignal` (`app/services/signals/base.py`) — consistent interface, easy to add new signals
- [x] Fully async I/O throughout: FastAPI async routes, `aiosqlite` for DB, async signal evaluation
- [x] Pydantic v2 models for all request/response/config types with type annotations
- [x] Services separated by concern: `risk_engine`, `rules_service`, `blocklist_service`, individual signal modules
- [x] In-memory caches with TTL for both rules and blocklist (avoids per-request DB hits)
- [x] `pydantic-settings` for environment-based configuration with `HARMONIA_` prefix
- [x] Structured signal results with `triggered`, `score_contribution`, `description`, and `details`

---

## Documentation (10 pts)

- [x] `README.md` — quick start, configuration, scoring pipeline, fraud signals table, risk levels, API overview, database schema, test commands
- [x] `docs/API.md` — full endpoint reference with request/response schemas, all data models, error codes, examples
- [x] `docs/DEMO.md` — 14 scenario walkthroughs with curl commands and expected responses
- [x] Swagger UI auto-generated from Pydantic models and FastAPI route docstrings (`/docs`)
- [x] ReDoc auto-generated (`/redoc`)
- [x] `CLAUDE.md` — architecture overview and development guide for AI-assisted development

---

## Stretch Goals (5 pts)

- [x] Blocklist and allowlist CRUD with cache invalidation on every write/delete
- [x] Global vs. merchant-scoped blocklist entries (`merchant_id: ""` = global)
- [x] Batch re-scoring with dry-run mode (`update_scores: false`) and optional DB persistence
- [x] Append-only audit trail with full request snapshot, signal breakdown, and rules snapshot at evaluation time
- [x] 1-minute TTL blocklist/allowlist cache (separate from rules cache)
- [x] Audit log supports filtering by `merchant_id`, `action`, with pagination (`limit`/`offset`)
