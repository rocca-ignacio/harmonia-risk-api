import time
from typing import Optional
import aiosqlite
from app.config import settings
from app.models.transaction import PayoutRequest

# Cache: (entry_type, value, merchant_id_or_global) → (is_blocked, cached_at)
_blocklist_cache: dict[tuple, tuple[bool, float]] = {}
_allowlist_cache: dict[tuple, tuple[bool, float]] = {}
_CACHE_TTL = settings.BLOCKLIST_CACHE_TTL_SECONDS


async def is_blocklisted(tx: PayoutRequest, db: aiosqlite.Connection) -> tuple[bool, str]:
    """
    Check all transaction identifiers against global and merchant-specific blocklists.
    Returns (is_blocked, reason).
    """
    checks = []
    if tx.user_ip:
        checks.append(("ip", tx.user_ip))
    if tx.recipient_email:
        checks.append(("email", tx.recipient_email))
    if tx.recipient_account:
        checks.append(("account", tx.recipient_account))
    if tx.device_id:
        checks.append(("device", tx.device_id))
    checks.append(("user", tx.user_id))

    for entry_type, value in checks:
        # Check global blocklist
        blocked, reason = await _check_entry(entry_type, value, None, db)
        if blocked:
            return True, f"Blocklisted {entry_type}: {value} — {reason}"
        # Check merchant-specific blocklist
        blocked, reason = await _check_entry(entry_type, value, tx.merchant_id, db)
        if blocked:
            return True, f"Merchant-blocklisted {entry_type}: {value} — {reason}"

    return False, ""


async def _check_entry(
    entry_type: str, value: str, merchant_id: Optional[str], db: aiosqlite.Connection
) -> tuple[bool, str]:
    cache_key = (entry_type, value, merchant_id or "")
    cached = _blocklist_cache.get(cache_key)
    if cached:
        is_blocked, cached_at = cached
        if time.monotonic() - cached_at < _CACHE_TTL:
            return is_blocked, "cached"

    mid = merchant_id or ""
    async with db.execute(
        "SELECT reason FROM blocklist WHERE entry_type = ? AND value = ? AND merchant_id = ?",
        (entry_type, value, mid),
    ) as cursor:
        row = await cursor.fetchone()

    is_blocked = row is not None
    reason = row[0] if row else ""
    _blocklist_cache[cache_key] = (is_blocked, time.monotonic())
    return is_blocked, reason


async def is_allowlisted(tx: PayoutRequest, db: aiosqlite.Connection) -> tuple[bool, str]:
    """
    Check if recipient is on the merchant's allowlist.
    Returns (is_allowed, reason).
    """
    checks = [
        ("recipient_account", tx.recipient_account),
    ]
    if tx.recipient_email:
        checks.append(("recipient_email", tx.recipient_email))

    for entry_type, value in checks:
        cache_key = (entry_type, value, tx.merchant_id)
        cached = _allowlist_cache.get(cache_key)
        if cached:
            is_allowed, cached_at = cached
            if time.monotonic() - cached_at < _CACHE_TTL:
                if is_allowed:
                    return True, "cached"
                continue

        async with db.execute(
            "SELECT reason FROM allowlist WHERE entry_type = ? AND value = ? AND merchant_id = ?",
            (entry_type, value, tx.merchant_id),
        ) as cursor:
            row = await cursor.fetchone()

        is_allowed = row is not None
        reason = row[0] if row else ""
        _allowlist_cache[cache_key] = (is_allowed, time.monotonic())
        if is_allowed:
            return True, reason

    return False, ""


def invalidate_caches() -> None:
    _blocklist_cache.clear()
    _allowlist_cache.clear()
