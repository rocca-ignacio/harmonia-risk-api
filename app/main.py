from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.db import init_db
from app.routers import risk, rules, blocklist, batch, audit


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Harmonia Bank — Real-Time Risk Scoring API",
    description="""
## Overview

Real-time fraud detection engine for instant payout disbursements.

Every payout request is evaluated in **< 200 ms** across six fraud signals:

| Signal | What it detects |
|---|---|
| **Velocity** | Too many transactions in a short window (scripted attacks) |
| **Amount anomaly** | Payout far above the user's historical average |
| **Geo mismatch** | IP country ≠ account country |
| **New account** | Recently created accounts requesting large payouts |
| **Money mule** | Recipient receiving from many unrelated merchants |
| **Time of day** | Transactions at unusual hours |

Plus **blocklist** (auto-BLOCK) and **allowlist** (auto-APPROVE) overrides.

All risk rules are **configurable per merchant** — no code changes required.

## Risk levels

| Score | Level | Action |
|---|---|---|
| 0 – 30 | LOW | APPROVE |
| 31 – 60 | MEDIUM | REVIEW |
| 61 – 100 | HIGH | BLOCK |
""",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router,      prefix="/api/v1/risk",      tags=["Risk Scoring"])
app.include_router(rules.router,     prefix="/api/v1/rules",     tags=["Risk Rules"])
app.include_router(blocklist.router, prefix="/api/v1/blocklist", tags=["Blocklist & Allowlist"])
app.include_router(batch.router,     prefix="/api/v1/batch",     tags=["Batch Operations"])
app.include_router(audit.router,     prefix="/api/v1/audit",     tags=["Audit Trail"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "harmonia-risk-api", "version": "1.0.0"}
