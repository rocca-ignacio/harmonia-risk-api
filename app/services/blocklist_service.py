from typing import Optional
import aiosqlite
from cachetools import TTLCache
from app.config import settings
from app.models.transaction import PayoutRequest

# Bounded TTL caches: auto-expire entries, evict LRU beyond maxsize
_blocklist_cache: TTLCache = TTLCache(maxsize=10000, ttl=settings.BLOCKLIST_CACHE_TTL_SECONDS)
_allowlist_cache: TTLCache = TTLCache(maxsize=10000, ttl=settings.BLOCKLIST_CACHE_TTL_SECONDS)


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
    if cached is not None:
        return cached

    mid = merchant_id or ""
    async with db.execute(
        "SELECT reason FROM blocklist WHERE entry_type = ? AND value = ? AND merchant_id = ?",
        (entry_type, value, mid),
    ) as cursor:
        row = await cursor.fetchone()

    result = (row is not None, row[0] if row else "")
    _blocklist_cache[cache_key] = result
    return result


async def is_allowlisted(tx: PayoutRequest, db: aiosqlite.Connection) -> tuple[bool, str]:
    """
    Check if recipient is on the merchant's allowlist.
    Returns (is_allowed, reason).
    """
    checks = [("recipient_account", tx.recipient_account)]
    if tx.recipient_email:
        checks.append(("recipient_email", tx.recipient_email))

    for entry_type, value in checks:
        cache_key = (entry_type, value, tx.merchant_id)
        cached = _allowlist_cache.get(cache_key)
        if cached is not None:
            is_allowed, reason = cached
            if is_allowed:
                return True, reason
            continue

        async with db.execute(
            "SELECT reason FROM allowlist WHERE entry_type = ? AND value = ? AND merchant_id = ?",
            (entry_type, value, tx.merchant_id),
        ) as cursor:
            row = await cursor.fetchone()

        result = (row is not None, row[0] if row else "")
        _allowlist_cache[cache_key] = result
        if result[0]:
            return True, result[1]

    return False, ""


def invalidate_caches() -> None:
    _blocklist_cache.clear()
    _allowlist_cache.clear()
