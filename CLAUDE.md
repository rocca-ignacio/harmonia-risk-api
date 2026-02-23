# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API server
uvicorn app.main:app --reload

# Seed the database with sample data (merchants, transactions, blocklist/allowlist)
python -m data.seed_data

# Run tests
pytest

# Run a single test file
pytest tests/test_file.py

# Run a specific test
pytest tests/test_file.py::test_function_name
```

API docs are available at `/docs` (Swagger) and `/redoc` (ReDoc) once the server is running.

## Architecture

This is a FastAPI-based fraud detection and risk scoring service for payout transactions. The core flow in `app/services/risk_engine.py`:

1. **Allowlist check** → auto-APPROVE (early exit)
2. **Blocklist check** → auto-BLOCK (early exit)
3. **Max payout cap** → hard block if exceeded
4. **Six fraud signals** evaluated (each returns a score contribution):
   - `velocity.py` – too many transactions in rolling window (max 30 pts)
   - `amount_anomaly.py` – payout far above user's historical average (max 25 pts)
   - `geo_mismatch.py` – IP country ≠ account country (max 20 pts)
   - `new_account.py` – new account requesting large payout (max 15 pts)
   - `money_mule.py` – recipient receiving from many merchants (max 20 pts)
   - `time_of_day.py` – transactions at unusual UTC hours (max 10 pts)
5. **Composite score** (sum of contributions, capped at 100) → APPROVE / REVIEW / BLOCK

All signals extend `BaseSignal` in `app/services/signals/base.py` and are async.

## Key Design Decisions

**Per-merchant configurable rules**: All signal thresholds (velocity window, anomaly multiplier, suspicious hours, etc.) are stored in SQLite as JSON per merchant. Default rules apply when no merchant-specific rules exist. Rules are loaded via `rules_service.py` with a 5-minute in-memory TTL cache that is invalidated on `PUT /rules/{merchant_id}`.

**Blocklist/allowlist caching**: 1-minute TTL cache keyed by `(entry_type, value, merchant_id)`, cleared on any mutation.

**Database**: SQLite via `aiosqlite` (fully async). Five tables: `transactions`, `merchant_rules`, `blocklist`, `allowlist`, `risk_audit`. Schema is created on startup in `app/database/db.py`.

**Audit trail**: Every scored transaction writes a full snapshot of the request, all signal results, the active rules, and processing time to `risk_audit`.

## Configuration

Settings are loaded via `pydantic-settings` in `app/config.py` with the `HARMONIA_` prefix:

| Variable | Default | Purpose |
|----------|---------|---------|
| `HARMONIA_DATABASE_PATH` | `harmonia.db` | SQLite file path |
| `HARMONIA_RULES_CACHE_TTL_SECONDS` | `300` | Rule cache TTL |
| `HARMONIA_BLOCKLIST_CACHE_TTL_SECONDS` | `60` | Blocklist cache TTL |
| `HARMONIA_MAX_RESPONSE_TIME_MS` | `200` | SLA target (logged, not enforced) |

## Adding a New Fraud Signal

1. Create `app/services/signals/my_signal.py` extending `BaseSignal`
2. Implement the async `evaluate(transaction, rules, db) -> SignalResult` method
3. Add corresponding rule fields to `MerchantRules` in `app/models/rules.py`
4. Register the signal in `risk_engine.py`
