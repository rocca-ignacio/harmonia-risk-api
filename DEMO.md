# Demo Guide — Harmonia Risk API

Step-by-step walkthrough of every fraud detection scenario. Each section shows the curl command, the full expected response, and an explanation of what drove the score.

**Prerequisites:** Server running with seeded data.
```bash
pip install -r requirements.txt
python -m data.seed_data
uvicorn app.main:app --reload --port 8000
```

Interactive playground: http://localhost:8000/docs

---

## Scenario Index

| # | Scenario | Trigger | Expected Action | Score |
|---|---|---|---|---|
| 1 | Normal transaction | Clean history, matching geo | APPROVE | ~0 |
| 2 | Allowlisted recipient | Recipient on merchant allowlist | APPROVE | 0 |
| 3 | Blocklisted IP | Known fraud proxy IP | BLOCK | 100 |
| 4 | Max payout exceeded | Amount > merchant cap | BLOCK | 100 |
| 5 | Velocity attack | Too many txns in window | BLOCK | 30 |
| 6 | Amount anomaly | Amount >> user average | REVIEW/BLOCK | 25 |
| 7 | Geographic anomaly | IP country ≠ account country | REVIEW | 20 |
| 8 | New account + large payout | New account, high amount | REVIEW | 40 |
| 9 | Money mule recipient | Recipient from many merchants | REVIEW | 20 |
| 10 | Combined signals | Geo + amount + night-time | REVIEW | 55 |
| 11 | Rule update (live) | Tighten velocity threshold | — | — |
| 12 | Batch re-scoring | Re-evaluate historical transactions | — | — |
| 13 | Dynamic blocklist | Add entry, verify instant effect | BLOCK | 100 |
| 14 | Audit trail | Retrieve full decision record | — | — |

---

## Scenario 1: Normal Transaction (LOW → APPROVE)

A RideFleet driver with 15 transactions on record, requesting their usual $54.50 payout. IP resolves to the Philippines, matching the account's registered country.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-NORMAL-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-NORMAL-001",
  "merchant_id": "MER001",
  "risk_score": 0.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": [
    { "signal": "velocity",       "triggered": false, "score_contribution": 0, "description": "Velocity OK: 1 transaction in last 10 min (limit: 3)" },
    { "signal": "amount_anomaly", "triggered": false, "score_contribution": 0, "description": "Amount $54.50 is 1.0x user average — within 3.0x threshold" },
    { "signal": "geo_mismatch",   "triggered": false, "score_contribution": 0, "description": "IP country PHL matches account country PHL" },
    { "signal": "new_account",    "triggered": false, "score_contribution": 0, "description": "Account is 2+ years old — not a new account" },
    { "signal": "money_mule",     "triggered": false, "score_contribution": 0, "description": "Recipient seen at 1 merchant — below threshold of 3" },
    { "signal": "time_of_day",    "triggered": false, "score_contribution": 0, "description": "Transaction hour is not in suspicious hours list" }
  ],
  "processing_time_ms": 8.3,
  "evaluated_at": "2024-06-15T14:30:01.123456"
}
```

**Why LOW:** No signals triggered. The amount is consistent with the user's ~$52 historical average, the IP resolves to PHL matching the registered country, and transaction velocity is within limits.

---

## Scenario 2: Allowlisted Recipient (AUTO-APPROVE, score 0)

`PH-ACC-TRUSTED-DRIVER01` is on MER001's allowlist. Even a $9,999 payout is auto-approved — the pipeline exits at step 1 without evaluating any signals.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-ALLOW-001",
    "merchant_id": "MER001",
    "user_id": "USR_RF_001",
    "recipient_account": "PH-ACC-TRUSTED-DRIVER01",
    "amount": 9999.00,
    "currency": "PHP",
    "user_ip": "203.177.12.45",
    "user_country": "PHL",
    "ip_country": "PHL",
    "account_created_at": "2022-06-01T00:00:00",
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-ALLOW-001",
  "merchant_id": "MER001",
  "risk_score": 0.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": []
}
```

**Why score 0:** The recipient is on MER001's allowlist (seeded as "Verified driver — 3 years, 0 chargebacks"). The engine short-circuits at allowlist check — no signals computed, no latency wasted.

---

## Scenario 3: Blocklisted IP (AUTO-BLOCK, score 100)

IP `45.67.89.10` is on the global blocklist. Any transaction from this IP is instantly blocked, regardless of the user, amount, or merchant.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-BLKLST-001",
    "merchant_id": "MER001",
    "user_id": "USR_RF_001",
    "recipient_account": "PH-ACC-7812345678",
    "amount": 50.00,
    "currency": "PHP",
    "user_ip": "45.67.89.10",
    "user_country": "PHL",
    "ip_country": "PHL",
    "account_created_at": "2022-06-01T00:00:00",
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-BLKLST-001",
  "merchant_id": "MER001",
  "risk_score": 100.0,
  "risk_level": "HIGH",
  "action": "BLOCK",
  "signals": []
}
```

**Why score 100:** `45.67.89.10` matches the global blocklist entry ("Known fraud proxy — ASN AS209605"). The engine exits at step 2 with an automatic score of 100. No signals are computed.

---

## Scenario 4: Max Payout Exceeded (AUTO-BLOCK, score 100)

`USR_RF_002` is a trusted user with a clean history, but MER001 has a $2,000 hard cap on payouts. The $2,500 request fails the cap check before any signal evaluation.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-MAXPAY-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-MAXPAY-001",
  "merchant_id": "MER001",
  "risk_score": 100.0,
  "risk_level": "HIGH",
  "action": "BLOCK",
  "signals": []
}
```

**Why score 100:** MER001's `max_payout.max_amount` is $2,000. The $2,500 request fails the hard cap at step 3, receiving an automatic score of 100. MER002 has a $1,000 cap; MER003 allows up to $10,000.

---

## Scenario 5: Velocity Attack (HIGH → BLOCK)

`USR_RF_ATCK01` submits 4 transactions within 10 minutes. MER001's limit is 3 per 10-minute window. Submit the seed transactions first, then the attack transaction.

```bash
# Step 5a: Seed 3 rapid transactions (simulates burst history)
for i in 1 2 3; do
  curl -s -X POST http://localhost:8000/api/v1/risk/score \
    -H "Content-Type: application/json" \
    -d '{
      "transaction_id": "DEMO-VEL-SEED-00'"$i"'",
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
      "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
    }' > /dev/null
  echo "Seeded transaction $i"
done

# Step 5b: Submit the 4th transaction — triggers the velocity block
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-VEL-ATTACK-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-VEL-ATTACK-001",
  "merchant_id": "MER001",
  "risk_score": 30.0,
  "risk_level": "HIGH",
  "action": "BLOCK",
  "signals": [
    {
      "signal": "velocity",
      "triggered": true,
      "score_contribution": 30,
      "description": "High velocity: 4 transactions in last 10 min (limit: 3)",
      "details": { "transaction_count": 4, "window_minutes": 10, "limit": 3 }
    }
  ]
}
```

**Why BLOCK:** MER001 allows a maximum of 3 transactions per 10-minute window. The 4th transaction triggers the velocity signal at its full max_score (30 pts), which lands exactly at the HIGH threshold.

---

## Scenario 6: Amount Anomaly (REVIEW/BLOCK)

`USR_RF_ATCK02` has a historical average of ~$48 across 10 recorded transactions. The $380 request is ~7.9× above average, far exceeding MER001's 3.0× threshold.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-AMT-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-AMT-001",
  "merchant_id": "MER001",
  "risk_score": 25.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": [
    {
      "signal": "amount_anomaly",
      "triggered": true,
      "score_contribution": 25,
      "description": "Amount $380.00 is 7.9x user average $48.20 — exceeds 3.0x threshold",
      "details": { "current_amount": 380.0, "user_avg": 48.2, "multiplier": 7.9, "threshold": 3.0 }
    }
  ]
}
```

**Why only 25:** The amount anomaly signal fires at full weight (25 pts), but no other signals trigger — the geo matches, velocity is fine, and the account is old. In isolation the score lands at LOW/APPROVE. See Scenario 10 to see this signal combine with others for a BLOCK decision.

---

## Scenario 7: Geographic Anomaly (REVIEW)

`USR_RF_ATCK03` has 9 recorded transactions all originating from PHL IPs. This request comes from a Nigerian IP (`197.210.10.123`) — a country never seen for this user.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-GEO-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-GEO-001",
  "merchant_id": "MER001",
  "risk_score": 20.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": [
    {
      "signal": "geo_mismatch",
      "triggered": true,
      "score_contribution": 20,
      "description": "IP country NGA does not match account country PHL",
      "details": { "user_country": "PHL", "ip_country": "NGA" }
    }
  ]
}
```

**Why only 20:** The geo mismatch fires at full weight (20 pts), but the amount ($55) is consistent with the user's history and no other signals trigger. Score 20 = LOW/APPROVE. See Scenario 10 to see geo mismatch in combination.

---

## Scenario 8: New Account + Large Payout (MEDIUM → REVIEW)

A brand-new account (1 day old) requesting $800. MER001 flags accounts younger than 14 days requesting more than $200. With no transaction history, the amount anomaly signal also fires via the no-history large-amount rule.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-NEW-001",
    "merchant_id": "MER001",
    "user_id": "USR_NEW_DEMO_99",
    "recipient_account": "PH-ACC-NEW-77777",
    "amount": 800.00,
    "currency": "PHP",
    "user_ip": "203.177.12.45",
    "device_id": "DEV-NEW-99",
    "user_country": "PHL",
    "ip_country": "PHL",
    "account_created_at": "'"$(date -u -v-1d +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S)"'",
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-NEW-001",
  "merchant_id": "MER001",
  "risk_score": 40.0,
  "risk_level": "MEDIUM",
  "action": "REVIEW",
  "signals": [
    {
      "signal": "amount_anomaly",
      "triggered": true,
      "score_contribution": 25,
      "description": "No transaction history — amount $800.00 exceeds no-history threshold $300.00",
      "details": { "current_amount": 800.0, "no_history_threshold": 300.0 }
    },
    {
      "signal": "new_account",
      "triggered": true,
      "score_contribution": 15,
      "description": "Account is 1 day old and amount $800.00 exceeds suspicious threshold $200.00",
      "details": { "account_age_days": 1, "new_account_threshold_days": 14, "amount": 800.0 }
    }
  ]
}
```

**Why REVIEW:** Two signals fire together — `amount_anomaly` (25 pts, via the no-history large-amount rule since the user has no prior transactions) and `new_account` (15 pts). Combined score 40 falls in the MEDIUM band (31–60).

---

## Scenario 9: Money Mule Detection

`PH-ACC-MULE-99999` has received payouts from all three seeded merchants (MER001, MER002, MER003). MER001's rule flags recipients seen across 3 or more distinct merchants.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-MULE-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "transaction_id": "DEMO-MULE-001",
  "merchant_id": "MER001",
  "risk_score": 20.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": [
    {
      "signal": "money_mule",
      "triggered": true,
      "score_contribution": 20,
      "description": "Recipient PH-ACC-MULE-99999 has received payouts from 3 distinct merchants (threshold: 3)",
      "details": { "merchant_count": 3, "min_merchant_count": 3 }
    }
  ]
}
```

**Why triggered:** The seed data includes historical payouts to `PH-ACC-MULE-99999` from MER001, MER002, and MER003 — exactly meeting the threshold of 3. The signal fires at full weight. By itself it's LOW; combined with velocity or amount anomaly it would escalate.

---

## Scenario 10: Combined Signals (MEDIUM → REVIEW)

The most realistic fraud pattern: geographic anomaly + extreme amount anomaly + late-night transaction, all firing simultaneously. `USR_QF_ATCK02` (MER002) has a ~$38 average. This request arrives from a Nigerian IP at 2:30 AM UTC for $420.

```bash
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-COMBO-001",
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
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S | sed 's/T[0-9]*/T02/')"'30:00"
  }' | python3 -m json.tool
```

> Alternatively, use a hardcoded 2:30 AM timestamp to ensure `time_of_day` fires:
> `"timestamp": "2024-06-15T02:30:00"`

**Expected response:**
```json
{
  "transaction_id": "DEMO-COMBO-001",
  "merchant_id": "MER002",
  "risk_score": 55.0,
  "risk_level": "MEDIUM",
  "action": "REVIEW",
  "signals": [
    {
      "signal": "amount_anomaly",
      "triggered": true,
      "score_contribution": 25,
      "description": "Amount $420.00 is 11.1x user average $38.00 — exceeds 3.5x threshold",
      "details": { "current_amount": 420.0, "user_avg": 38.0, "multiplier": 11.1, "threshold": 3.5 }
    },
    {
      "signal": "geo_mismatch",
      "triggered": true,
      "score_contribution": 20,
      "description": "IP country NGA does not match account country PHL",
      "details": { "user_country": "PHL", "ip_country": "NGA" }
    },
    {
      "signal": "time_of_day",
      "triggered": true,
      "score_contribution": 10,
      "description": "Transaction at hour 2 UTC falls in suspicious hours [0, 1, 2, 3, 4, 5]",
      "details": { "hour": 2, "suspicious_hours": [0, 1, 2, 3, 4, 5] }
    }
  ],
  "processing_time_ms": 14.2,
  "evaluated_at": "2024-06-15T02:30:01.456789"
}
```

**Why 55 / REVIEW:** Three signals fire: amount anomaly (25) + geo mismatch (20) + time of day (10) = 55. This sits at the top of MEDIUM (31–60). To escalate to BLOCK, lower `score_thresholds.medium_max` to 50 for MER002 — see Scenario 11.

---

## Scenario 11: Live Rule Update

Show that rule changes take effect instantly without a restart. Lower MER002's `medium_max` threshold so the combined-signals score (55) becomes HIGH.

```bash
# Step 11a: Fetch current MER002 rules
curl -s http://localhost:8000/api/v1/rules/MER002 | python3 -m json.tool

# Step 11b: Update — tighten score thresholds (medium_max 60 → 50)
curl -s -X PUT http://localhost:8000/api/v1/rules/MER002 \
  -H "Content-Type: application/json" \
  -d '{
    "merchant_id": "MER002",
    "velocity":       { "enabled": true, "max_transactions": 5, "time_window_minutes": 15, "max_score": 30 },
    "amount_anomaly": { "enabled": true, "threshold_multiplier": 3.5, "min_history_count": 3, "no_history_large_amount": 250.0, "max_score": 25 },
    "geo_mismatch":   { "enabled": true, "max_score": 20 },
    "new_account":    { "enabled": true, "new_account_days": 7, "suspicious_amount": 150.0, "max_score": 15 },
    "money_mule":     { "enabled": true, "min_merchant_count": 3, "max_score": 20 },
    "time_of_day":    { "enabled": true, "suspicious_hours": [0,1,2,3,4,5], "max_score": 10 },
    "max_payout":     { "enabled": true, "max_amount": 1000.0 },
    "score_thresholds": { "low_max": 30, "medium_max": 50 },
    "allowlist_auto_approve": true
  }' | python3 -m json.tool

# Step 11c: Re-run the combined-signals scenario — now action should be BLOCK
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-COMBO-AFTER-RULE-UPDATE",
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
    "timestamp": "2024-06-15T02:30:00"
  }' | python3 -m json.tool
```

**Expected:** Same score (55), but now `risk_level: HIGH`, `action: BLOCK` because the MEDIUM band now ends at 50.

---

## Scenario 12: Batch Re-scoring

After tightening rules, re-score all MER001 historical transactions from the past 30 days to see how many decisions would have changed (dry run — no DB update).

```bash
curl -s -X POST http://localhost:8000/api/v1/batch/rescore \
  -H "Content-Type: application/json" \
  -d '{
    "merchant_id": "MER001",
    "start_date": "'"$(date -u -v-30d +%Y-%m-%d 2>/dev/null || date -u -d '30 days ago' +%Y-%m-%d)"'",
    "end_date": "'"$(date -u +%Y-%m-%d)"'",
    "update_scores": false
  }' | python3 -m json.tool
```

**Expected response (excerpt):**
```json
{
  "rescored_count": 42,
  "updated_in_db": false,
  "summary": {
    "total": 42,
    "approve": 38,
    "review": 3,
    "block": 1,
    "changed": 4
  },
  "results": [
    {
      "transaction_id": "HIST-0001",
      "old_score": 10.0,
      "old_action": "APPROVE",
      "new_score": 10.0,
      "new_action": "APPROVE",
      "score_delta": 0.0
    }
  ]
}
```

**What to look for:** The `summary.changed` count shows how many transactions would flip (e.g., APPROVE → BLOCK) under current rules. Set `"update_scores": true` to persist the new scores.

---

## Scenario 13: Dynamic Blocklist

Add a new IP to the blocklist and verify it takes effect immediately — no restart required. The in-memory cache is invalidated on every write.

```bash
# Step 13a: Add the IP
curl -s -X POST http://localhost:8000/api/v1/blocklist/ \
  -H "Content-Type: application/json" \
  -d '{
    "entry_type": "ip",
    "value": "192.0.2.99",
    "reason": "Flagged by threat intel — RideFleet incident #2024-06"
  }' | python3 -m json.tool

# Step 13b: Verify it blocks immediately
curl -s -X POST http://localhost:8000/api/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "DEMO-DYNBLOCK-001",
    "merchant_id": "MER001",
    "user_id": "USR_RF_002",
    "recipient_account": "PH-ACC-8823456789",
    "amount": 75.00,
    "currency": "PHP",
    "user_ip": "192.0.2.99",
    "user_country": "PHL",
    "ip_country": "PHL",
    "account_created_at": "2022-01-01T00:00:00",
    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"
  }' | python3 -m json.tool
```

**Expected:** `risk_score: 100`, `action: BLOCK` — instant effect after the POST to `/blocklist/`.

---

## Scenario 14: Audit Trail

Retrieve the full compliance record for any scored transaction. The audit log is append-only — it captures the original request, every signal result with its score contribution, and a snapshot of the merchant rules that were active at the moment of scoring.

```bash
# Full audit record for a specific transaction
curl -s http://localhost:8000/api/v1/audit/DEMO-AMT-001 | python3 -m json.tool
```

**Expected response (excerpt):**
```json
{
  "transaction_id": "DEMO-AMT-001",
  "merchant_id": "MER001",
  "risk_score": 25.0,
  "risk_level": "LOW",
  "action": "APPROVE",
  "signals": [ ... ],
  "processing_time_ms": 9.1,
  "evaluated_at": "2024-06-15T14:31:00",
  "request": {
    "transaction_id": "DEMO-AMT-001",
    "merchant_id": "MER001",
    "user_id": "USR_RF_ATCK02",
    "amount": 380.0
  },
  "rules_snapshot": {
    "velocity": { "max_transactions": 3, "time_window_minutes": 10 },
    "amount_anomaly": { "threshold_multiplier": 3.0 }
  }
}
```

```bash
# List the 10 most recent BLOCK decisions across all merchants
curl -s "http://localhost:8000/api/v1/audit/?action=BLOCK&limit=10" | python3 -m json.tool

# List REVIEW decisions for MER002 only
curl -s "http://localhost:8000/api/v1/audit/?merchant_id=MER002&action=REVIEW&limit=20" | python3 -m json.tool
```

---

## Quick Reference — Seeded Test Data

### Merchants

| ID | Name | Max Payout | Velocity Limit |
|---|---|---|---|
| `MER001` | RideFleet | $2,000 | 3 txn / 10 min |
| `MER002` | QuickFood | $1,000 | 5 txn / 15 min |
| `MER003` | TaskGig | $10,000 | 5 txn / 30 min |

### Users

| User ID | Merchant | Avg Amount | Use In Scenario |
|---|---|---|---|
| `USR_RF_001` | MER001 | ~$52 | 1 (normal), 2 (allowlist), 3 (blocklist) |
| `USR_RF_002` | MER001 | ~$78 | 4 (max payout) |
| `USR_RF_ATCK01` | MER001 | ~$50 | 5 (velocity) |
| `USR_RF_ATCK02` | MER001 | ~$48 | 6 (amount anomaly) |
| `USR_RF_ATCK03` | MER001 | ~$52 | 7 (geo anomaly) |
| `USR_QF_ATCK02` | MER002 | ~$38 | 10 (combined signals) |

### Seeded Blocklist

| Value | Type | Scope |
|---|---|---|
| `45.67.89.10` | IP | Global |
| `fraud.ring@tempmail.xyz` | Email | Global |
| `PH-ACC-BLOCKED-STOLEN01` | Account | Global |
| `DEV-BANNED-1234` | Device | MER001 only |
| `USR_KNOWN_FRAUD_01` | User | Global |

### Seeded Allowlist

| Value | Type | Merchant |
|---|---|---|
| `PH-ACC-TRUSTED-DRIVER01` | recipient_account | MER001 |
| `trusted.driver@rideflt.ph` | recipient_email | MER001 |
| `PH-ACC-TRUSTED-COURIER01` | recipient_account | MER002 |
| `PH-ACC-TRUSTED-GIGER01` | recipient_account | MER003 |
