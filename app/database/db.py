import aiosqlite
from app.config import settings

DB_PATH = settings.DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    recipient_account TEXT NOT NULL,
    recipient_email TEXT,
    recipient_phone TEXT,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    user_ip TEXT,
    device_id TEXT,
    user_country TEXT,
    ip_country TEXT,
    account_created_at TEXT,
    timestamp TEXT NOT NULL,
    risk_score REAL,
    risk_level TEXT,
    action TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tx_user_ts ON transactions(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_merchant ON transactions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_tx_recipient ON transactions(recipient_account);
CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(timestamp);

CREATE TABLE IF NOT EXISTS merchant_rules (
    merchant_id TEXT PRIMARY KEY,
    rules_json TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS blocklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL,
    value TEXT NOT NULL,
    reason TEXT,
    merchant_id TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(entry_type, value, merchant_id)
);

CREATE INDEX IF NOT EXISTS idx_blocklist_lookup ON blocklist(entry_type, value);

CREATE TABLE IF NOT EXISTS allowlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL,
    value TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(entry_type, value, merchant_id)
);

CREATE INDEX IF NOT EXISTS idx_allowlist_lookup ON allowlist(entry_type, value, merchant_id);

CREATE TABLE IF NOT EXISTS risk_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    request_json TEXT NOT NULL,
    risk_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    action TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    rules_json TEXT NOT NULL,
    processing_time_ms REAL NOT NULL,
    evaluated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_tx ON risk_audit(transaction_id);
CREATE INDEX IF NOT EXISTS idx_audit_merchant ON risk_audit(merchant_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON risk_audit(evaluated_at);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db
