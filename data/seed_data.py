"""
Seed script: inserts ~200 realistic historical transactions, merchant rules,
blocklist/allowlist entries into the database so the risk engine has a rich
baseline to detect anomalies.

Usage:
    python -m data.seed_data
"""

import asyncio
import json
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import aiosqlite
from datetime import datetime, timedelta

from app.database.db import DB_PATH, init_db

random.seed(42)

# ── Helpers ────────────────────────────────────────────────────────────────────

def days_ago(n: float) -> str:
    return (datetime.utcnow() - timedelta(days=n)).isoformat()

def hours_ago(n: float) -> str:
    return (datetime.utcnow() - timedelta(hours=n)).isoformat()


def tx(
    txn_id: str,
    merchant_id: str,
    user_id: str,
    recipient_account: str,
    amount: float,
    currency: str = "PHP",
    user_ip: str = "203.177.12.45",
    device_id: str = "DEV-DEFAULT",
    user_country: str = "PHL",
    ip_country: str = "PHL",
    account_created_at: str | None = None,
    timestamp: str | None = None,
    risk_score: float | None = None,
    risk_level: str | None = None,
    action: str | None = None,
    recipient_email: str | None = None,
    recipient_phone: str | None = None,
) -> tuple:
    return (
        txn_id, merchant_id, user_id, recipient_account,
        recipient_email, recipient_phone,
        amount, currency, user_ip, device_id,
        user_country, ip_country,
        account_created_at or days_ago(365),
        timestamp or days_ago(random.uniform(1, 30)),
        risk_score, risk_level, action,
    )


# ──────────────────────────────────────────────────────────────────────────────
# MERCHANT RULES
# ──────────────────────────────────────────────────────────────────────────────

MERCHANT_RULES = {
    # RideFleet: strictest rules — instant payouts to drivers, high fraud target
    "MER001": {
        "merchant_id": "MER001",
        "velocity": {"enabled": True, "max_transactions": 3, "time_window_minutes": 10, "max_score": 65},
        "amount_anomaly": {"enabled": True, "threshold_multiplier": 3.0, "min_history_count": 3, "no_history_large_amount": 300.0, "max_score": 65},
        "geo_mismatch": {"enabled": True, "max_score": 50},
        "new_account": {"enabled": True, "new_account_days": 14, "suspicious_amount": 200.0, "max_score": 30},
        "money_mule": {"enabled": True, "min_merchant_count": 3, "max_score": 40},
        "time_of_day": {"enabled": True, "suspicious_hours": [0, 1, 2, 3, 4, 5], "max_score": 15},
        "max_payout": {"enabled": True, "max_amount": 2000.0},
        "score_thresholds": {"low_max": 30, "medium_max": 60},
        "allowlist_auto_approve": True,
    },
    # QuickFood: medium rules — food delivery couriers, lower average amounts
    "MER002": {
        "merchant_id": "MER002",
        "velocity": {"enabled": True, "max_transactions": 5, "time_window_minutes": 15, "max_score": 65},
        "amount_anomaly": {"enabled": True, "threshold_multiplier": 3.5, "min_history_count": 3, "no_history_large_amount": 250.0, "max_score": 65},
        "geo_mismatch": {"enabled": True, "max_score": 50},
        "new_account": {"enabled": True, "new_account_days": 7, "suspicious_amount": 150.0, "max_score": 30},
        "money_mule": {"enabled": True, "min_merchant_count": 3, "max_score": 40},
        "time_of_day": {"enabled": True, "suspicious_hours": [0, 1, 2, 3, 4, 5], "max_score": 15},
        "max_payout": {"enabled": True, "max_amount": 1000.0},
        "score_thresholds": {"low_max": 30, "medium_max": 60},
        "allowlist_auto_approve": True,
    },
    # TaskGig: most relaxed — freelancers can have larger, less regular payouts
    "MER003": {
        "merchant_id": "MER003",
        "velocity": {"enabled": True, "max_transactions": 5, "time_window_minutes": 30, "max_score": 65},
        "amount_anomaly": {"enabled": True, "threshold_multiplier": 4.0, "min_history_count": 5, "no_history_large_amount": 1000.0, "max_score": 65},
        "geo_mismatch": {"enabled": True, "max_score": 50},
        "new_account": {"enabled": True, "new_account_days": 7, "suspicious_amount": 500.0, "max_score": 30},
        "money_mule": {"enabled": True, "min_merchant_count": 4, "max_score": 40},
        "time_of_day": {"enabled": True, "suspicious_hours": [0, 1, 2, 3, 4, 5], "max_score": 15},
        "max_payout": {"enabled": True, "max_amount": 10000.0},
        "score_thresholds": {"low_max": 30, "medium_max": 60},
        "allowlist_auto_approve": True,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# HISTORICAL TRANSACTIONS
# ──────────────────────────────────────────────────────────────────────────────

PHL_IPS = ["203.177.12.45", "112.198.68.12", "180.191.3.22", "103.252.116.50", "122.55.88.201"]
VNM_IPS = ["103.27.238.11", "171.252.10.45", "14.232.66.78"]
IDN_IPS = ["180.252.11.23", "114.125.45.67", "103.28.16.99"]
NGA_IPS = ["197.210.10.123", "41.58.23.44"]
USA_IPS = ["104.28.16.220", "172.217.1.46"]

def make_transactions() -> list[tuple]:
    rows = []
    i = 1

    def add(merchant_id, user_id, recipient_account, amount, currency="PHP",
            user_ip=None, device_id=None, user_country="PHL", ip_country="PHL",
            account_created_at=None, timestamp=None, risk_score=10.0, risk_level="LOW", action="APPROVE",
            recipient_email=None, recipient_phone=None):
        nonlocal i
        rows.append(tx(
            txn_id=f"HIST-{i:04d}",
            merchant_id=merchant_id,
            user_id=user_id,
            recipient_account=recipient_account,
            amount=amount,
            currency=currency,
            user_ip=user_ip or random.choice(PHL_IPS),
            device_id=device_id or f"DEV-{user_id}",
            user_country=user_country,
            ip_country=ip_country,
            account_created_at=account_created_at or days_ago(365 + random.randint(0, 365)),
            timestamp=timestamp,
            risk_score=risk_score,
            risk_level=risk_level,
            action=action,
            recipient_email=recipient_email,
            recipient_phone=recipient_phone,
        ))
        i += 1

    # ── MER001: RideFleet ─────────────────────────────────────────────────────
    # USR_RF_001: Consistent driver, avg ~52 PHP
    for day_offset in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20]:
        add("MER001", "USR_RF_001", "PH-ACC-7812345678", round(random.uniform(44, 62), 2),
            timestamp=days_ago(day_offset), recipient_email="rene.d@email.ph")

    # USR_RF_002: Avg ~78
    for day_offset in [1, 2, 3, 5, 6, 7, 8, 10, 12, 14, 15, 18]:
        add("MER001", "USR_RF_002", "PH-ACC-8823456789", round(random.uniform(65, 92), 2),
            timestamp=days_ago(day_offset))

    # USR_RF_003: Avg ~45
    for day_offset in [1, 3, 4, 6, 8, 9, 11, 13, 15, 17, 19]:
        add("MER001", "USR_RF_003", "PH-ACC-9934567890", round(random.uniform(38, 55), 2),
            timestamp=days_ago(day_offset))

    # USR_RF_004: Avg ~65
    for day_offset in [2, 4, 5, 7, 9, 11, 13, 15, 17, 20, 22, 25]:
        add("MER001", "USR_RF_004", "PH-ACC-1045678901", round(random.uniform(55, 76), 2),
            timestamp=days_ago(day_offset))

    # USR_RF_005: Avg ~55
    for day_offset in [1, 2, 4, 6, 8, 10, 12, 14, 16, 18]:
        add("MER001", "USR_RF_005", "PH-ACC-1156789012", round(random.uniform(46, 66), 2),
            timestamp=days_ago(day_offset))

    # USR_RF_ATCK01: Velocity attack candidate — has a normal history
    for day_offset in [3, 5, 7, 9, 11, 13, 15]:
        add("MER001", "USR_RF_ATCK01", "PH-ACC-2267890123", round(random.uniform(40, 60), 2),
            timestamp=days_ago(day_offset))

    # USR_RF_ATCK02: Amount anomaly candidate — avg ~$48
    for day_offset in [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]:
        add("MER001", "USR_RF_ATCK02", "PH-ACC-3378901234", round(random.uniform(40, 58), 2),
            timestamp=days_ago(day_offset))

    # USR_RF_ATCK03: Geo anomaly — PHL transactions (normal)
    for day_offset in [2, 4, 6, 8, 10, 12, 14, 16, 18]:
        add("MER001", "USR_RF_ATCK03", "PH-ACC-4489012345",
            round(random.uniform(44, 62), 2),
            user_ip=random.choice(PHL_IPS), ip_country="PHL",
            timestamp=days_ago(day_offset))

    # ── MER002: QuickFood ─────────────────────────────────────────────────────
    # USR_QF_001: Avg ~42
    for day_offset in [1, 2, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
        add("MER002", "USR_QF_001", "PH-ACC-5590123456", round(random.uniform(32, 55), 2),
            timestamp=days_ago(day_offset))

    # USR_QF_002: Avg ~58
    for day_offset in [1, 3, 5, 6, 8, 10, 12, 14, 16, 18, 20]:
        add("MER002", "USR_QF_002", "PH-ACC-6601234567", round(random.uniform(48, 70), 2),
            timestamp=days_ago(day_offset))

    # USR_QF_003: Avg ~35
    for day_offset in [2, 4, 6, 8, 10, 12, 14, 16]:
        add("MER002", "USR_QF_003", "PH-ACC-7712345678", round(random.uniform(27, 45), 2),
            timestamp=days_ago(day_offset))

    # USR_QF_004: Avg ~62
    for day_offset in [1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]:
        add("MER002", "USR_QF_004", "PH-ACC-8823456780", round(random.uniform(50, 76), 2),
            timestamp=days_ago(day_offset))

    # USR_QF_ATCK01: Velocity attack candidate — normal history
    for day_offset in [3, 6, 9, 12, 15, 18]:
        add("MER002", "USR_QF_ATCK01", "PH-ACC-9934567891", round(random.uniform(30, 50), 2),
            timestamp=days_ago(day_offset))

    # USR_QF_ATCK02: Amount anomaly — avg ~$38
    for day_offset in [2, 5, 8, 11, 14, 17, 20, 23, 26, 29]:
        add("MER002", "USR_QF_ATCK02", "PH-ACC-1045678902", round(random.uniform(30, 48), 2),
            timestamp=days_ago(day_offset))

    # ── MER003: TaskGig ───────────────────────────────────────────────────────
    # USR_TG_001: Freelancer, avg ~$250
    for day_offset in [3, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57]:
        add("MER003", "USR_TG_001", "PH-ACC-2156789013", round(random.uniform(180, 320), 2),
            timestamp=days_ago(day_offset))

    # USR_TG_002: Avg ~$420
    for day_offset in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]:
        add("MER003", "USR_TG_002", "PH-ACC-3267890124", round(random.uniform(350, 500), 2),
            timestamp=days_ago(day_offset))

    # USR_TG_003: Avg ~$130
    for day_offset in [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35, 38]:
        add("MER003", "USR_TG_003", "PH-ACC-4378901235", round(random.uniform(100, 165), 2),
            timestamp=days_ago(day_offset))

    # ── Money mule: RECV_MULE_ACC receives from all 3 merchants ──────────────
    # MER001 payouts to mule
    for day_offset in [5, 10, 15]:
        add("MER001", "USR_RF_005", "PH-ACC-MULE-99999",
            round(random.uniform(40, 80), 2),
            timestamp=days_ago(day_offset))

    # MER002 payouts to mule
    for day_offset in [4, 8, 12]:
        add("MER002", "USR_QF_003", "PH-ACC-MULE-99999",
            round(random.uniform(30, 60), 2),
            timestamp=days_ago(day_offset))

    # MER003 payouts to mule
    for day_offset in [3, 7, 11]:
        add("MER003", "USR_TG_003", "PH-ACC-MULE-99999",
            round(random.uniform(100, 200), 2),
            timestamp=days_ago(day_offset))

    return rows


HISTORICAL_TRANSACTIONS = make_transactions()

# ──────────────────────────────────────────────────────────────────────────────
# BLOCKLIST / ALLOWLIST
# ──────────────────────────────────────────────────────────────────────────────

BLOCKLIST = [
    # Global blocked IP (known fraud proxy) — merchant_id='' means global
    ("ip",      "45.67.89.10",              "Known fraud proxy — ASN AS209605",  ""),
    # Global blocked email
    ("email",   "fraud.ring@tempmail.xyz",  "Associated with 12 chargeback events", ""),
    # Global blocked account
    ("account", "PH-ACC-BLOCKED-STOLEN01",  "Stolen account number — reported by victim", ""),
    # Merchant-specific blocked device
    ("device",  "DEV-BANNED-1234",          "Used in RideFleet weekend fraud incident", "MER001"),
    # Blocked user across all merchants
    ("user",    "USR_KNOWN_FRAUD_01",       "Confirmed fraudster — multiple merchant reports", ""),
]

ALLOWLIST = [
    # RideFleet trusted long-term driver
    ("recipient_account", "PH-ACC-TRUSTED-DRIVER01", "MER001", "Verified driver — 3 years, 0 chargebacks"),
    ("recipient_email",   "trusted.driver@rideflt.ph", "MER001", "Verified driver email"),
    # QuickFood trusted courier
    ("recipient_account", "PH-ACC-TRUSTED-COURIER01", "MER002", "Senior courier — background checked"),
    # TaskGig top-rated freelancer
    ("recipient_account", "PH-ACC-TRUSTED-GIGER01", "MER003", "5-star freelancer — $50k+ paid"),
]

# ──────────────────────────────────────────────────────────────────────────────
# TEST SCENARIO PAYLOADS (for demo / README)
# ──────────────────────────────────────────────────────────────────────────────

TEST_SCENARIOS = {
    "normal_transaction": {
        "description": "Regular RideFleet driver payout — LOW risk",
        "payload": {
            "transaction_id": "TEST-NORMAL-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_001",
            "recipient_account": "PH-ACC-7812345678",
            "recipient_email": "rene.d@email.ph",
            "amount": 54.50,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-USR_RF_001",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-06-01T00:00:00",
            "timestamp": (datetime.utcnow() - timedelta(seconds=5)).isoformat(),
        },
    },
    "velocity_attack": {
        "description": "Velocity attack — same user, 4 transactions in last 8 minutes — HIGH risk",
        "setup_note": "First POST the 4 seed transactions below (they'll be stored as history), then POST the final one to see BLOCK",
        "seed_transactions": [
            {
                "transaction_id": f"TEST-VEL-SEED-00{k}",
                "merchant_id": "MER001",
                "user_id": "USR_RF_ATCK01",
                "recipient_account": "PH-ACC-2267890123",
                "amount": 48.00,
                "currency": "PHP",
                "user_ip": "203.177.12.45",
                "device_id": "DEV-USR_RF_ATCK01",
                "user_country": "PHL",
                "ip_country": "PHL",
                "account_created_at": "2022-01-01T00:00:00",
                "timestamp": (datetime.utcnow() - timedelta(minutes=9 - k * 2)).isoformat(),
            }
            for k in range(1, 4)
        ],
        "final_payload": {
            "transaction_id": "TEST-VEL-FINAL-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_ATCK01",
            "recipient_account": "PH-ACC-2267890123",
            "amount": 48.00,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-USR_RF_ATCK01",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-01-01T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "amount_anomaly": {
        "description": "Amount anomaly — user avg ~$48, requesting $380 — HIGH risk",
        "payload": {
            "transaction_id": "TEST-AMT-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_ATCK02",
            "recipient_account": "PH-ACC-3378901234",
            "amount": 380.00,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-USR_RF_ATCK02",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-03-15T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "geo_anomaly": {
        "description": "Geographic anomaly — PHL account, IP from Nigeria — HIGH risk",
        "payload": {
            "transaction_id": "TEST-GEO-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_ATCK03",
            "recipient_account": "PH-ACC-4489012345",
            "amount": 55.00,
            "currency": "PHP",
            "user_ip": "197.210.10.123",
            "device_id": "DEV-UNKNOWN-456",
            "user_country": "PHL",
            "ip_country": "NGA",
            "account_created_at": "2022-08-20T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "money_mule": {
        "description": "Money mule — recipient PH-ACC-MULE-99999 has received from 3 merchants — HIGH risk",
        "payload": {
            "transaction_id": "TEST-MULE-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_003",
            "recipient_account": "PH-ACC-MULE-99999",
            "amount": 55.00,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-USR_RF_003",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-11-01T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "new_account_large": {
        "description": "New account (2 days old) requesting $800 — HIGH risk",
        "payload": {
            "transaction_id": "TEST-NEW-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_NEW01",
            "recipient_account": "PH-ACC-NEW-88888",
            "amount": 800.00,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-NEW-001",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "blocklisted_ip": {
        "description": "Blocked IP address — auto-BLOCK, score 100",
        "payload": {
            "transaction_id": "TEST-BLOCK-IP-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_001",
            "recipient_account": "PH-ACC-7812345678",
            "amount": 50.00,
            "currency": "PHP",
            "user_ip": "45.67.89.10",
            "device_id": "DEV-USR_RF_001",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-06-01T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "allowlisted_recipient": {
        "description": "Trusted recipient on MER001 allowlist — auto-APPROVE, score 0",
        "payload": {
            "transaction_id": "TEST-ALLOW-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_001",
            "recipient_account": "PH-ACC-TRUSTED-DRIVER01",
            "recipient_email": "trusted.driver@rideflt.ph",
            "amount": 9999.00,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-USR_RF_001",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-06-01T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "max_payout_exceeded": {
        "description": "Amount exceeds MER001 max payout limit ($2000) — auto-BLOCK",
        "payload": {
            "transaction_id": "TEST-MAXPAY-001",
            "merchant_id": "MER001",
            "user_id": "USR_RF_002",
            "recipient_account": "PH-ACC-8823456789",
            "amount": 2500.00,
            "currency": "PHP",
            "user_ip": "203.177.12.45",
            "device_id": "DEV-USR_RF_002",
            "user_country": "PHL",
            "ip_country": "PHL",
            "account_created_at": "2022-01-01T00:00:00",
            "timestamp": datetime.utcnow().isoformat(),
        },
    },
    "combined_signals": {
        "description": "Geo + Amount anomaly + Night-time — multiple signals firing",
        "payload": {
            "transaction_id": "TEST-COMBO-001",
            "merchant_id": "MER002",
            "user_id": "USR_QF_ATCK02",
            "recipient_account": "PH-ACC-1045678902",
            "amount": 420.00,
            "currency": "PHP",
            "user_ip": "197.210.10.123",
            "device_id": "DEV-USR_QF_ATCK02",
            "user_country": "PHL",
            "ip_country": "NGA",
            "account_created_at": "2022-05-10T00:00:00",
            "timestamp": (datetime.utcnow().replace(hour=2, minute=30)).isoformat(),
        },
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# INSERT FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

async def seed(db: aiosqlite.Connection) -> None:
    print("Seeding merchant rules...")
    for merchant_id, rules_dict in MERCHANT_RULES.items():
        await db.execute(
            """
            INSERT INTO merchant_rules (merchant_id, rules_json)
            VALUES (?, ?)
            ON CONFLICT(merchant_id) DO UPDATE SET
              rules_json = excluded.rules_json,
              updated_at = datetime('now')
            """,
            (merchant_id, json.dumps(rules_dict)),
        )

    print(f"Inserting {len(HISTORICAL_TRANSACTIONS)} historical transactions...")
    await db.executemany(
        """
        INSERT OR IGNORE INTO transactions
          (id, merchant_id, user_id, recipient_account, recipient_email,
           recipient_phone, amount, currency, user_ip, device_id,
           user_country, ip_country, account_created_at, timestamp,
           risk_score, risk_level, action)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        HISTORICAL_TRANSACTIONS,
    )

    print(f"Inserting {len(BLOCKLIST)} blocklist entries...")
    for entry in BLOCKLIST:
        await db.execute(
            """
            INSERT OR IGNORE INTO blocklist (entry_type, value, reason, merchant_id)
            VALUES (?, ?, ?, ?)
            """,
            entry,
        )

    print(f"Inserting {len(ALLOWLIST)} allowlist entries...")
    for entry in ALLOWLIST:
        await db.execute(
            """
            INSERT OR IGNORE INTO allowlist (entry_type, value, merchant_id, reason)
            VALUES (?, ?, ?, ?)
            """,
            entry,
        )

    await db.commit()
    print("✓ Seed complete.")

    # Save test scenarios to JSON for reference
    scenarios_path = os.path.join(os.path.dirname(__file__), "test_scenarios.json")
    with open(scenarios_path, "w") as f:
        json.dump(TEST_SCENARIOS, f, indent=2)
    print(f"✓ Test scenarios saved to {scenarios_path}")


async def main() -> None:
    await init_db()
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        await seed(db)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
