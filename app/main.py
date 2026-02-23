from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database.db import init_db
from app.routers import risk, rules, blocklist, batch, audit, analytics


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

## Error responses

All errors return a consistent JSON envelope:

```json
{ "error": "NotFound", "detail": "No audit record for transaction 'TXN-X'", "status_code": 404 }
```
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

app.include_router(risk.router,       prefix="/api/v1/risk",       tags=["Risk Scoring"])
app.include_router(rules.router,      prefix="/api/v1/rules",      tags=["Risk Rules"])
app.include_router(blocklist.router,  prefix="/api/v1/blocklist",  tags=["Blocklist & Allowlist"])
app.include_router(batch.router,      prefix="/api/v1/batch",      tags=["Batch Operations"])
app.include_router(audit.router,      prefix="/api/v1/audit",      tags=["Audit Trail"])
app.include_router(analytics.router,  prefix="/api/v1/analytics",  tags=["Analytics"])


# ── Uniform error response envelope ───────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": type(exc).__name__, "detail": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "ValidationError", "detail": exc.errors(), "status_code": 422},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "detail": str(exc), "status_code": 500},
    )


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "harmonia-risk-api", "version": "1.0.0"}
