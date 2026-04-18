# Fazle WBOM Platform — Complete Diagnostic Audit Report

**Date:** 2026-04-18  
**Scope:** Database, API, Frontend, Social Engine, Owner Control, Relationships, Search, AI/Brain  
**Method:** Live VPS queries + full codebase read  

---

## System Health Score: 52 / 100

| Category | Score | Items |
|----------|-------|-------|
| 🟢 GREEN (Working) | 8 items | Core CRUD, auth, dedup, search, brain routing, webhook flow, legacy migration, indexes |
| 🟡 YELLOW (Degraded) | 9 items | Phone formats, response inconsistency, empty tables, no FK enforcement, owner commands, mixed auth |
| 🔴 RED (Broken/Critical) | 7 items | Contact relations all "unknown", no employee bank data, 0 contact roles, phone normalization split, no WBOM auth, envelope mismatch, leads no auth |

---

## 🟢 GREEN — Working Correctly

| # | Area | Finding |
|---|------|---------|
| G1 | **DB Migration** | All 5 legacy tables migrated. No code references `_legacy_*` tables. Social engine has explicit migration notes. |
| G2 | **Core CRUD (employees/programs/transactions)** | Frontend ↔ Backend field names match. Raw arrays returned. Dashboard loads correctly. |
| G3 | **Auth (API gateway)** | JWT + API key dual auth. bcrypt hashing. Timing-safe comparison. Admin routes protected. |
| G4 | **Message Dedup** | Redis-backed with `SET NX` (300s TTL) on Meta message ID. Sender-level 2s cooldown. |
| G5 | **Search** | Trigram fuzzy search (`pg_trgm` installed), ILIKE, cross-table (employees + contacts + vessels + transactions). |
| G6 | **Brain Architecture** | No direct DB access. Calls WBOM/Memory via HTTP. No legacy table names in code. Clean separation. |
| G7 | **Webhook Flow** | WA signature verification → dedup → owner detection → brain routing → safety classifier → auto/draft send. Complete pipeline. |
| G8 | **Indexes** | Good coverage: `wbom_employees` has 6 indexes (incl. trigram on name). `wbom_cash_transactions` has 8 indexes. `wbom_contacts` has 7 indexes. |

---

## 🟡 YELLOW — Degraded / Needs Attention

| # | Area | Finding | Impact |
|---|------|---------|--------|
| Y1 | **Phone Format Inconsistency** | `wbom_contacts`: 507 as `01X` (11-digit), 24 as `880XXXXXXXXXX` (13-digit), 511 "other" (international, concatenated, malformed). `wbom_employees`: 167 clean `01X`, 2 malformed (10-digit, 12-digit). `wbom_cash_transactions`: 1206 `01X`, 2 `880` format, 10 NULL. | Contact lookups can fail when format differs between sender and stored number. |
| Y2 | **Response Format Inconsistency** | 4 of 19 route files use `api_response()` envelope (`clients`, `job_applications`, `audit`, partial `payment`). 15 return raw dicts/arrays. `schema.py` defines field names matching envelope format, not raw format. | Frontend must handle both formats. Currently works only because the 3 main tabs (employees/programs/transactions) use raw format. |
| Y3 | **Legacy Tables Still Exist** | 5 `_legacy_*` tables total ~1.4 MB. No code references them. | Dead weight. Safe to drop but no urgency. |
| Y4 | **Duplicate Transactions** | 4 duplicate combos (same employee_id + amount + date). Employee 54 has 3 duplicates with 150.00 across different dates. | May cause double-counting in salary reports. |
| Y5 | **Employee-Contact Overlap** | 27 employees share mobile numbers with contacts. No cross-table foreign key linking them. | Employee messages may be treated as unknown contacts by social engine. |
| Y6 | **`fazle_relationship_graph` stores phone in JSON** | 64 rows. Phone numbers stored as `attributes->>'contact_number'` (JSON), not in a dedicated column. Mixed Bangla/English names. | Cannot be efficiently queried/joined for phone-based lookups. |
| Y7 | **Owner Phone Format** | Env: `SOCIAL_OWNER_PHONE=+8801880446111`. `fazle_access_rules`: `+8801848144841`, `+8801772274173`. These are in `+880` format. Employees/contacts stored as `01X`. | Owner detection works (uses `_normalize_phone`), but if access rules are ever used for contact lookup, format mismatch. |
| Y8 | **`fazle_user_rules`** | Only 2 test rules for `test_user_phase2`. | Feature built but not used in production. |
| Y9 | **Brain Bangla Command Regex** | Greedy capture: `(.+?)কে` captures everything before `কে`. "আমার ভাই করিমকে ১০০০ টাকা পাঠাও" → name = "আমার ভাই করিম" not "করিম". No Bangla↔English transliteration. | Owner financial commands may match wrong employee or fail to match at all. |

---

## 🔴 RED — Broken / Critical

| # | Area | Finding | Impact |
|---|------|---------|--------|
| R1 | **ALL 1042 contacts have `relation = 'unknown'`** | `wbom_contacts.relation` is never set to meaningful values (client/employee/vendor). The social engine `_classify_reply_safety()` checks `relation == 'employee'` to restrict auto-replies, but NO contact ever has this relation set. | Safety classifier cannot distinguish employees from strangers. All contacts treated the same. Owner contact commands ("01X is client") may set relation, but current data shows 0 clients/employees/vendors. |
| R2 | **ZERO employee bank accounts** | 169 employees, ALL have `bank_account = NULL or ''`. | Payment execution via bKash/bank transfer cannot work. `idx_wbom_employees_bkash` index exists but indexes nothing. |
| R3 | **`fazle_contact_roles` is EMPTY** | Table has proper schema (phone, name, role, sub_role, language_pref, platform) but 0 rows. | Contact-role-based routing/personalization is dead code. |
| R4 | **Phone normalization split** | `webhooks.py::_normalize_phone()` adds `88` prefix for `01X` numbers (used ONLY for owner detection). `main.py::upsert_contact()` / `get_contact()` only does `lstrip("+")`. These produce DIFFERENT values: `01848123456` vs `8801848123456`. | A contact stored as `8801848XXXX` from Meta webhook will NOT match a lookup for `01848XXXX` from WBOM. Duplicate contacts can be created for the same person. |
| R5 | **ZERO auth on ALL 19 WBOM routes** | None of the 19 route files in `fazle-system/wbom/routes/` import or use any auth dependency. Security relies entirely on: (1) API gateway `require_admin` on the proxy, and (2) `X-INTERNAL-KEY` header check. If WBOM port 9900 is exposed, ALL data is public. | Single point of failure. If nginx misconfiguration exposes port 9900, no defense in depth. |
| R6 | **`GET /leads` and `POST /leads/capture` have NO AUTH** | In `lead_routes.py`, both endpoints are fully public. Anyone can list all leads or inject fake leads. | Data leak + spam injection vector. |
| R7 | **Envelope routes break frontend** | `clients.py`, `job_applications.py`, `audit.py` return `{success, data, meta, schema, version}` envelope. Frontend `handleResponse()` does NOT unwrap — it returns `res.json()` directly. Frontend types expect raw arrays. | If dashboard ever adds Clients/Applications/Audit tabs, they will show empty or crash. Currently unexposed in main WBOM page so not visibly broken. |

---

## Side-by-Side: What Frontend Expects vs What Backend Returns

| Tab / Feature | Frontend Expects | Backend Returns | Match? |
|---------------|-----------------|-----------------|--------|
| **Employees list** | `WbomEmployee[]` (employee_id, employee_name, employee_mobile, ...) | Raw array of DB rows | ✅ Match |
| **Programs list** | `WbomProgram[]` (program_id, mother_vessel, lighter_vessel, ...) | Raw array of DB rows | ✅ Match |
| **Transactions list** | `WbomTransaction[]` (transaction_id, employee_id, amount, ...) | Raw array of DB rows | ✅ Match |
| **Salary summary** | `SalarySummary[]` (employee_name, basic_salary, net_salary, ...) | Raw array from service | ✅ Match |
| **Attendance report** | `AttendanceRecord[]` (employee_name, status, location, ...) | Raw array from service | ✅ Match |
| **Admin command** | `{action, details, ...}` | `AdminCommandResponse` model | ✅ Match |
| **Clients list** | Would expect raw array | Returns `{success, data: [{id, name, phone, ...}], meta}` envelope with RENAMED fields | ❌ **Broken** |
| **Job applications** | Would expect raw array | Returns `{success, data: [...], meta}` envelope | ❌ **Broken** |
| **Audit log** | Would expect raw array | Returns `{success, data: [...], meta}` envelope | ❌ **Broken** |
| **Pending payments** | Would expect raw array | Returns `{success, data: [...]}` envelope | ❌ **Broken** |
| **Contact relation** | Not displayed | ALL `'unknown'` — never populated | ⚠️ **Dead** |
| **Employee bank_account** | Form field exists | ALL NULL | ⚠️ **Empty** |
| **Search /fuzzy** | Raw results | Raw results | ✅ Match |

---

## Database Schema Summary

| Table | Rows | Key Issue |
|-------|------|-----------|
| `wbom_employees` | 169 | 2 malformed phones, 0 bank accounts |
| `wbom_contacts` | 1042 | ALL relation='unknown', 535 non-standard phone formats |
| `wbom_cash_transactions` | 1218 | 4 duplicate combos, 10 NULL mobiles, 2 in 880 format |
| `wbom_escort_programs` | 3175 | Clean |
| `wbom_whatsapp_messages` | 52 | Low volume (36 in, 16 out) |
| `wbom_staging_payments` | 0 | Empty — payment pipeline never used |
| `wbom_employee_requests` | 0 | Empty — self-service never used |
| `wbom_billing_records` | 0 | Empty — billing never used |
| `wbom_clients` | 0 | Empty — client management never used |
| `wbom_job_applications` | 0 | Empty — recruitment never used |
| `wbom_audit_logs` | 0 | Empty — audit logging not generating entries |
| `fazle_users` | 4 | Azim (admin), admin@al-aqsa (admin), Sarah (wife), Aisha (daughter). NO phone column! |
| `fazle_relationship_graph` | 64 | Phone in JSON attributes, not queryable |
| `fazle_contact_roles` | 0 | Completely empty |
| `fazle_access_rules` | 2 | +8801848144841, +8801772274173 |
| `fazle_leads` | unknown | No auth on list endpoint |
| `_legacy_*` (5 tables) | ~1.4MB | Dead. No code references. |

---

## Foreign Key Analysis

- **21 foreign keys** exist across `wbom_*` tables
- **wbom_contacts ↔ wbom_employees**: NO foreign key. 27 overlapping mobiles but no enforced relationship.
- **wbom_cash_transactions.employee_id → wbom_employees.employee_id**: EXISTS (via FK). 0 orphans confirmed.
- **wbom_escort_programs.escort_employee_id → wbom_employees.employee_id**: EXISTS.

---

## Top 10 Critical Fixes (Priority Order)

| Rank | Fix | Severity | Effort | Risk |
|------|-----|----------|--------|------|
| **1** | **Normalize ALL phone numbers** in `wbom_contacts` to consistent `01XXXXXXXXX` format. Fix `upsert_contact()` in social-engine to use `_normalize_phone()` for ALL operations, not just owner detection. | 🔴 Critical | Medium | Low — data migration + code fix |
| **2** | **Add auth to lead routes** (`lead_routes.py`): wrap both endpoints with `require_admin` or at minimum `get_current_user`. | 🔴 Critical | Trivial | Zero — additive change |
| **3** | **Remove `api_response`/`api_single` from remaining 4 route files** (`clients.py`, `job_applications.py`, `audit.py`, `payment.py::list_pending`) to match the raw format all other routes use. | 🔴 Critical | Low | Low — same pattern as previous employees/transactions fix |
| **4** | **Populate `wbom_contacts.relation`** for the 27 contacts that match employees — set to `'employee'`. This enables the safety classifier to work. | 🔴 Critical | Low | Low — UPDATE query |
| **5** | **Add WBOM-level auth middleware** checking `X-INTERNAL-KEY` header on all routes (defense in depth). Currently WBOM trusts the network. | 🟡 High | Medium | Low — middleware addition |
| **6** | **Fix 2 malformed employee phones**: Mohiuddin (0161542189 → should be 01615421890?), Mohsin Mea (017411150726 → should be 01741115072?). Verify with actual numbers. | 🟡 High | Trivial | Low — manual verification needed |
| **7** | **Populate employee bank accounts** — all 169 are NULL. Salary payment pipeline cannot work without this. | 🟡 High | Manual | Zero — data entry task |
| **8** | **Fix Bangla command regex** in `control_layer.py` — trim name capture, add English alias lookup, consider substring matching. | 🟡 Medium | Medium | Medium — regex changes need testing |
| **9** | **Drop 5 legacy tables** to reduce DB overhead (1.4MB, negligible but creates confusion). | 🟡 Low | Trivial | Zero — no code references them |
| **10** | **Remove or populate `fazle_contact_roles`** — 0 rows, dead feature. Either drop table or implement the role assignment flow. | 🟡 Low | Trivial | Zero |

---

## Safe Fix Order (Dependency-Aware)

```
Phase A — Zero Risk (no behavioral change):
  A1. Add auth to lead_routes.py                    [Fix #2]
  A2. Drop 5 legacy tables                          [Fix #9]
  A3. Fix 2 malformed employee phones               [Fix #6]

Phase B — Low Risk (format alignment):
  B1. Remove api_response/api_single from 4 routes  [Fix #3]
  B2. Add WBOM-level X-INTERNAL-KEY middleware       [Fix #5]

Phase C — Data Normalization (requires migration script):
  C1. Normalize all phone numbers to 01X format     [Fix #1]
  C2. Fix upsert_contact() normalization            [Fix #1 continued]
  C3. Set relation='employee' for 27 matching contacts [Fix #4]

Phase D — Feature Completion (requires manual input):
  D1. Collect and populate employee bank accounts   [Fix #7]
  D2. Fix Bangla command regex                      [Fix #8]
  D3. Decide: populate or drop fazle_contact_roles  [Fix #10]
```

---

## Service Architecture (Verified)

```
Browser → Nginx(443)
  ├── /api/fazle/* → API Gateway (8100)
  │     ├── /fazle/wbom/* → WBOM Service (9900) [X-INTERNAL-KEY injected]
  │     ├── /fazle/social/* → Social Engine (9800)
  │     ├── /fazle/admin/* → admin_routes, watchdog_routes
  │     ├── /fazle/users/* → user_routes
  │     ├── /fazle/gdpr/* → gdpr_routes
  │     ├── /auth/* → inline auth in main.py
  │     ├── /leads/* → lead_routes (⚠️ NO AUTH)
  │     ├── /knowledge/* → knowledge_routes
  │     ├── /governance/* → governance_routes
  │     └── /owner/* → owner_query_routes
  ├── / → Frontend (3020)
  └── WBOM direct blocks → DISABLED ✅

Social Engine (9800)
  ├── WhatsApp webhook → message processing → Brain (8200)
  ├── Contact CRUD → wbom_contacts table
  └── WBOM forward → WBOM (9900) /api/subagent/wbom/process-message

Brain (8200)
  ├── /chat → social user routing via control layer
  ├── /chat/owner → owner conversational control
  ├── /chat/multimodal → image/audio processing
  └── WBOM agent → WBOM (9900) search/reports

WBOM (9900) — 19 route modules
  ├── employees, programs, transactions, contacts, salary, attendance
  ├── billing, messages, templates, search, subagent, reports
  ├── admin, self_service, payment, job_applications, clients
  ├── audit, schema
  └── ⚠️ ZERO auth on all routes (relies on network isolation)
```

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Total DB tables | 71 |
| Active WBOM tables | ~20 |
| Empty WBOM tables | 6 (staging_payments, employee_requests, billing, clients, job_applications, audit_logs) |
| Legacy tables (dead) | 5 |
| Total employees | 169 |
| Total contacts | 1042 (ALL relation='unknown') |
| Total transactions | 1218 |
| Total programs | 3175 |
| Total WA messages | 52 (36 in, 16 out) |
| API route files (API gateway) | 13 |
| WBOM route files | 19 |
| Foreign keys (WBOM) | 21 |
| Indexes (employees) | 6 |
| Indexes (transactions) | 8 |
| Indexes (contacts) | 7 |
| Dashboard pages | 24 subdirectories |
| Brain endpoints | 10 |
| Auth-protected API routes | ~90% |
| Auth-protected WBOM routes | 0% |

---

*Report complete. No code changes have been made. Awaiting instructions before proceeding with fixes.*
