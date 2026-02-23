import json
from typing import Optional
import aiosqlite
from cachetools import TTLCache
from app.config import settings
from app.models.rules import MerchantRules

# Bounded TTL cache: evicts LRU entries beyond maxsize, auto-expires after TTL
_rules_cache: TTLCache = TTLCache(maxsize=1000, ttl=settings.RULES_CACHE_TTL_SECONDS)


async def get_merchant_rules(merchant_id: str, db: aiosqlite.Connection) -> MerchantRules:
    """Return rules for a merchant, from cache or DB. Falls back to safe defaults."""
    rules = _rules_cache.get(merchant_id)
    if rules is not None:
        return rules

    async with db.execute(
        "SELECT rules_json FROM merchant_rules WHERE merchant_id = ?",
        (merchant_id,),
    ) as cursor:
        row = await cursor.fetchone()

    rules = MerchantRules(**json.loads(row[0])) if row else MerchantRules(merchant_id=merchant_id)
    _rules_cache[merchant_id] = rules
    return rules


async def upsert_merchant_rules(merchant_id: str, rules: MerchantRules, db: aiosqlite.Connection) -> None:
    """Persist merchant rules to DB and invalidate cache."""
    await db.execute(
        """
        INSERT INTO merchant_rules (merchant_id, rules_json, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(merchant_id) DO UPDATE SET
            rules_json = excluded.rules_json,
            updated_at = datetime('now')
        """,
        (merchant_id, rules.model_dump_json()),
    )
    await db.commit()
    _rules_cache.pop(merchant_id, None)


def invalidate_cache(merchant_id: Optional[str] = None) -> None:
    """Invalidate one or all cached rule sets."""
    if merchant_id:
        _rules_cache.pop(merchant_id, None)
    else:
        _rules_cache.clear()
