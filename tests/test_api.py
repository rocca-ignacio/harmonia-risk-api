"""
Integration tests for the Harmonia Risk API.

Fixtures (setup_db, client) are provided by tests/conftest.py.

Run with:
    pytest tests/ -v
"""
from datetime import datetime, timedelta, timezone


def ts(delta_minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)).isoformat()


# ── Health ─────────────────────────────────────────────────────────────────────

async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Normal transaction: LOW risk ───────────────────────────────────────────────

async def test_normal_transaction(client):
    payload = {
        "transaction_id": "T-NORM-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 52.00,
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "device_id": "DEV-USR_RF_001",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "APPROVE"
    assert data["risk_level"] == "LOW"
    assert data["risk_score"] <= 30
    assert data["processing_time_ms"] < 500
    assert len(data["signals"]) > 0


# ── Blocklisted IP → BLOCK, score 100 ─────────────────────────────────────────

async def test_blocklisted_ip(client):
    payload = {
        "transaction_id": "T-BLOCK-IP-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 50.00,
        "currency": "PHP",
        "user_ip": "45.67.89.10",  # on global blocklist
        "device_id": "DEV-USR_RF_001",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "BLOCK"
    assert data["risk_score"] == 100.0
    signal_names = [s["signal"] for s in data["signals"]]
    assert "blocklist" in signal_names


# ── Allowlisted recipient → APPROVE, score 0 ──────────────────────────────────

async def test_allowlisted_recipient(client):
    payload = {
        "transaction_id": "T-ALLOW-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-TRUSTED-DRIVER01",
        "amount": 9999.00,  # huge amount — but allowlisted
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "device_id": "DEV-USR_RF_001",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "APPROVE"
    assert data["risk_score"] == 0.0
    signal_names = [s["signal"] for s in data["signals"]]
    assert "allowlist" in signal_names


# ── Amount anomaly → HIGH risk ─────────────────────────────────────────────────

async def test_amount_anomaly(client):
    payload = {
        "transaction_id": "T-AMT-ANOM-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_ATCK02",  # historical avg ~$48
        "recipient_account": "PH-ACC-3378901234",
        "amount": 380.00,  # ~8x average
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "device_id": "DEV-USR_RF_ATCK02",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-03-15T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["risk_score"] > 30
    triggered = [s for s in data["signals"] if s["signal"] == "amount_anomaly" and s["triggered"]]
    assert len(triggered) == 1
    assert triggered[0]["details"]["multiplier"] > 3.0


# ── Geographic anomaly ─────────────────────────────────────────────────────────

async def test_geo_anomaly(client):
    payload = {
        "transaction_id": "T-GEO-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_ATCK03",  # all history from PHL
        "recipient_account": "PH-ACC-4489012345",
        "amount": 55.00,
        "currency": "PHP",
        "user_ip": "197.210.10.123",
        "device_id": "DEV-UNKNOWN",
        "user_country": "PHL",
        "ip_country": "NGA",  # Nigeria
        "account_created_at": "2022-08-20T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    triggered = [s for s in data["signals"] if s["signal"] == "geo_mismatch" and s["triggered"]]
    assert len(triggered) == 1
    assert triggered[0]["score_contribution"] > 0


# ── New account + large amount ─────────────────────────────────────────────────

async def test_new_account_large_payout(client):
    payload = {
        "transaction_id": "T-NEWACCT-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_BRANDNEW_99",
        "recipient_account": "PH-ACC-FRESH-12345",
        "amount": 600.00,
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "device_id": "DEV-NEW-99",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    triggered = [s for s in data["signals"] if s["signal"] == "new_account" and s["triggered"]]
    assert len(triggered) == 1


# ── Max payout exceeded → BLOCK ────────────────────────────────────────────────

async def test_max_payout_exceeded(client):
    payload = {
        "transaction_id": "T-MAXPAY-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 2500.00,  # MER001 limit is $2000
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "device_id": "DEV-USR_RF_001",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "BLOCK"
    assert data["risk_score"] == 100.0
    signal_names = [s["signal"] for s in data["signals"]]
    assert "max_payout" in signal_names


# ── Money mule detection ────────────────────────────────────────────────────────

async def test_money_mule(client):
    """Recipient PH-ACC-MULE-99999 has received from all 3 merchants in seed data."""
    payload = {
        "transaction_id": "T-MULE-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-MULE-99999",
        "amount": 60.00,
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "device_id": "DEV-USR_RF_001",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    triggered = [s for s in data["signals"] if s["signal"] == "money_mule" and s["triggered"]]
    assert len(triggered) == 1
    assert triggered[0]["details"]["merchant_count"] >= 3


# ── Time of day signal ─────────────────────────────────────────────────────────

async def test_time_of_day_suspicious(client):
    """Transaction at 2am UTC should trigger time_of_day signal."""
    suspicious_ts = datetime.now(timezone.utc).replace(hour=2, minute=30, second=0)
    payload = {
        "transaction_id": "T-TOD-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 50.00,
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": suspicious_ts.isoformat(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    triggered = [s for s in data["signals"] if s["signal"] == "time_of_day" and s["triggered"]]
    assert len(triggered) == 1


# ── Score response structure ───────────────────────────────────────────────────

async def test_response_has_all_required_fields(client):
    payload = {
        "transaction_id": "T-STRUCT-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 50.00,
        "timestamp": ts(),
    }
    r = await client.post("/api/v1/risk/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "transaction_id" in data
    assert "merchant_id" in data
    assert "risk_score" in data
    assert "risk_level" in data
    assert "action" in data
    assert "signals" in data
    assert "processing_time_ms" in data
    assert "evaluated_at" in data
    assert data["risk_score"] >= 0
    assert data["risk_score"] <= 100
    assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert data["action"] in ("APPROVE", "REVIEW", "BLOCK")


# ── Rules API ─────────────────────────────────────────────────────────────────

async def test_get_rules_default(client):
    """Unknown merchant returns default rules."""
    r = await client.get("/api/v1/rules/UNKNOWN_MERCHANT")
    assert r.status_code == 200
    data = r.json()
    assert data["merchant_id"] == "UNKNOWN_MERCHANT"
    assert "velocity" in data
    assert "amount_anomaly" in data
    assert "geo_mismatch" in data
    assert "new_account" in data
    assert "money_mule" in data
    assert "time_of_day" in data
    assert "score_thresholds" in data


async def test_get_rules_seeded_merchant(client):
    """Seeded merchant rules should have custom values."""
    r = await client.get("/api/v1/rules/MER001")
    assert r.status_code == 200
    data = r.json()
    assert data["merchant_id"] == "MER001"
    assert data["velocity"]["max_transactions"] == 3  # seeded value


async def test_update_rules(client):
    """PUT rules should persist and be retrievable."""
    r = await client.get("/api/v1/rules/MER002")
    rules = r.json()
    original_max = rules["velocity"]["max_transactions"]
    rules["velocity"]["max_transactions"] = 2  # tighten

    r2 = await client.put("/api/v1/rules/MER002", json=rules)
    assert r2.status_code == 200
    assert r2.json()["velocity"]["max_transactions"] == 2

    # Restore original
    rules["velocity"]["max_transactions"] = original_max
    await client.put("/api/v1/rules/MER002", json=rules)


async def test_update_rules_mismatched_id(client):
    """merchant_id in body must match path param."""
    r = await client.get("/api/v1/rules/MER001")
    rules = r.json()
    rules["merchant_id"] = "DIFFERENT_ID"
    r2 = await client.put("/api/v1/rules/MER001", json=rules)
    assert r2.status_code == 422


# ── Blocklist API ─────────────────────────────────────────────────────────────

async def test_blocklist_crud(client):
    """Add an IP, verify it blocks transactions, then remove it."""
    # Add
    entry = {"entry_type": "ip", "value": "10.99.99.99", "reason": "test entry"}
    r = await client.post("/api/v1/blocklist/", json=entry)
    assert r.status_code == 201
    entry_id = r.json()["id"]

    # Verify it blocks
    payload = {
        "transaction_id": "T-DYNBLOCK-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 50.00,
        "currency": "PHP",
        "user_ip": "10.99.99.99",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    r2 = await client.post("/api/v1/risk/score", json=payload)
    assert r2.json()["action"] == "BLOCK"

    # Remove
    r3 = await client.delete(f"/api/v1/blocklist/{entry_id}")
    assert r3.status_code == 204


async def test_blocklist_list(client):
    r = await client.get("/api/v1/blocklist/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_blocklist_invalid_type(client):
    entry = {"entry_type": "invalid_type", "value": "test"}
    r = await client.post("/api/v1/blocklist/", json=entry)
    assert r.status_code == 422


async def test_allowlist_crud(client):
    """Add an allowlist entry, verify auto-approve, then remove it."""
    entry = {
        "entry_type": "recipient_account",
        "value": "PH-ACC-TEST-ALLOW-999",
        "merchant_id": "MER001",
        "reason": "test allowlist",
    }
    r = await client.post("/api/v1/blocklist/allowlist/", json=entry)
    assert r.status_code == 201
    entry_id = r.json()["id"]

    payload = {
        "transaction_id": "T-ALLOW-TEST-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-TEST-ALLOW-999",
        "amount": 9999.00,
        "timestamp": ts(),
    }
    r2 = await client.post("/api/v1/risk/score", json=payload)
    assert r2.json()["action"] == "APPROVE"
    assert r2.json()["risk_score"] == 0.0

    r3 = await client.delete(f"/api/v1/blocklist/allowlist/{entry_id}")
    assert r3.status_code == 204


# ── Audit trail ───────────────────────────────────────────────────────────────

async def test_audit_trail(client):
    """Scoring a transaction should produce an audit record."""
    payload = {
        "transaction_id": "T-AUDIT-001",
        "merchant_id": "MER001",
        "user_id": "USR_RF_001",
        "recipient_account": "PH-ACC-7812345678",
        "amount": 50.00,
        "currency": "PHP",
        "user_ip": "203.177.12.45",
        "user_country": "PHL",
        "ip_country": "PHL",
        "account_created_at": "2022-06-01T00:00:00",
        "timestamp": ts(),
    }
    await client.post("/api/v1/risk/score", json=payload)

    r = await client.get("/api/v1/audit/T-AUDIT-001")
    assert r.status_code == 200
    data = r.json()
    assert data["transaction_id"] == "T-AUDIT-001"
    assert "signals" in data
    assert "rules_snapshot" in data
    assert "request" in data
    assert "processing_time_ms" in data


async def test_audit_list(client):
    r = await client.get("/api/v1/audit/?limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_audit_list_filter_by_action(client):
    r = await client.get("/api/v1/audit/?action=BLOCK&limit=5")
    assert r.status_code == 200
    records = r.json()
    for rec in records:
        assert rec["action"] == "BLOCK"


async def test_audit_not_found(client):
    r = await client.get("/api/v1/audit/DOES-NOT-EXIST-999")
    assert r.status_code == 404


# ── Batch re-scoring ──────────────────────────────────────────────────────────

async def test_batch_rescore_by_ids(client):
    """Batch rescore specific known transaction IDs."""
    r = await client.post("/api/v1/batch/rescore", json={
        "merchant_id": "MER001",
        "transaction_ids": ["HIST-0001", "HIST-0002", "HIST-0003"],
        "update_scores": False,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["rescored_count"] == 3
    assert "results" in data
    assert "summary" in data
    assert data["updated_in_db"] is False


async def test_batch_rescore_by_date_range(client):
    r = await client.post("/api/v1/batch/rescore", json={
        "merchant_id": "MER001",
        "start_date": "2024-01-01",
        "end_date": "2030-12-31",
        "update_scores": False,
    })
    assert r.status_code == 200
    data = r.json()
    assert "rescored_count" in data
    assert "summary" in data


async def test_batch_rescore_requires_selection(client):
    """Must provide transaction_ids or date range."""
    r = await client.post("/api/v1/batch/rescore", json={
        "merchant_id": "MER001",
        "update_scores": False,
    })
    assert r.status_code == 422
