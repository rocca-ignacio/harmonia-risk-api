from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.database.db import get_db
from app.services.blocklist_service import invalidate_caches

router = APIRouter()

VALID_BLOCKLIST_TYPES = {"ip", "email", "account", "device", "user"}
VALID_ALLOWLIST_TYPES = {"recipient_account", "recipient_email"}


class BlocklistEntry(BaseModel):
    entry_type: str
    value: str
    reason: Optional[str] = None
    merchant_id: Optional[str] = None  # None/empty = global blocklist


class AllowlistEntry(BaseModel):
    entry_type: str
    value: str
    merchant_id: str
    reason: Optional[str] = None


class BlocklistRecord(BaseModel):
    id: int
    entry_type: str
    value: str
    reason: Optional[str]
    merchant_id: Optional[str]
    created_at: str


class AllowlistRecord(BaseModel):
    id: int
    entry_type: str
    value: str
    merchant_id: str
    reason: Optional[str]
    created_at: str


# ── Blocklist ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[BlocklistRecord], summary="List blocklist entries")
async def list_blocklist(
    entry_type: Optional[str] = Query(None),
    merchant_id: Optional[str] = Query(None),
):
    db = await get_db()
    try:
        query = "SELECT id, entry_type, value, reason, merchant_id, created_at FROM blocklist WHERE 1=1"
        params: list = []
        if entry_type:
            query += " AND entry_type = ?"
            params.append(entry_type)
        if merchant_id:
            query += " AND merchant_id = ?"
            params.append(merchant_id)
        query += " ORDER BY created_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


@router.post("/", response_model=BlocklistRecord, status_code=201, summary="Add a blocklist entry")
async def add_to_blocklist(entry: BlocklistEntry):
    if entry.entry_type not in VALID_BLOCKLIST_TYPES:
        raise HTTPException(status_code=422, detail=f"entry_type must be one of {VALID_BLOCKLIST_TYPES}")
    db = await get_db()
    try:
        async with db.execute(
            """
            INSERT INTO blocklist (entry_type, value, reason, merchant_id)
            VALUES (?, ?, ?, ?)
            """,
            (entry.entry_type, entry.value, entry.reason, entry.merchant_id or ""),
        ) as cursor:
            row_id = cursor.lastrowid
        await db.commit()
        invalidate_caches()

        async with db.execute("SELECT * FROM blocklist WHERE id = ?", (row_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row)
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="Entry already exists in blocklist")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await db.close()


@router.delete("/{entry_id}", status_code=204, summary="Remove a blocklist entry")
async def remove_from_blocklist(entry_id: int):
    db = await get_db()
    try:
        async with db.execute("DELETE FROM blocklist WHERE id = ?", (entry_id,)) as cursor:
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Entry not found")
        await db.commit()
        invalidate_caches()
    finally:
        await db.close()


# ── Allowlist ─────────────────────────────────────────────────────────────────

@router.get("/allowlist/", response_model=List[AllowlistRecord], summary="List allowlist entries")
async def list_allowlist(merchant_id: Optional[str] = Query(None)):
    db = await get_db()
    try:
        query = "SELECT id, entry_type, value, merchant_id, reason, created_at FROM allowlist WHERE 1=1"
        params: list = []
        if merchant_id:
            query += " AND merchant_id = ?"
            params.append(merchant_id)
        query += " ORDER BY created_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


@router.post("/allowlist/", response_model=AllowlistRecord, status_code=201, summary="Add an allowlist entry")
async def add_to_allowlist(entry: AllowlistEntry):
    if entry.entry_type not in VALID_ALLOWLIST_TYPES:
        raise HTTPException(status_code=422, detail=f"entry_type must be one of {VALID_ALLOWLIST_TYPES}")
    db = await get_db()
    try:
        async with db.execute(
            """
            INSERT INTO allowlist (entry_type, value, merchant_id, reason)
            VALUES (?, ?, ?, ?)
            """,
            (entry.entry_type, entry.value, entry.merchant_id, entry.reason),
        ) as cursor:
            row_id = cursor.lastrowid
        await db.commit()
        invalidate_caches()

        async with db.execute("SELECT * FROM allowlist WHERE id = ?", (row_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row)
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="Entry already exists in allowlist")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await db.close()


@router.delete("/allowlist/{entry_id}", status_code=204, summary="Remove an allowlist entry")
async def remove_from_allowlist(entry_id: int):
    db = await get_db()
    try:
        async with db.execute("DELETE FROM allowlist WHERE id = ?", (entry_id,)) as cursor:
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Entry not found")
        await db.commit()
        invalidate_caches()
    finally:
        await db.close()
