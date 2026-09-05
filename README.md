# Guardian Ledger

**Track 04 — AI Finance Controller (RazorpayAI Buildathon 2026)**

Guardian Ledger is a reconciliation engine that matches payments across three sources that were never designed to agree with each other — a payment gateway, a bank settlement report, and an internal ledger — and does so in a way that lets an AI model help with messy evidence without ever letting that AI directly change financial state.

**Core principle:** No AI-generated conclusion can directly change financial state. The AI proposes; a deterministic verifier authorizes; a bounded executor acts.

---

## 1. What This Solves

Reconciliation is the process of confirming that a payment recorded in one system matches what actually happened in another. In practice, three sources almost never agree cleanly:

- Timing lag — the bank settles days after the gateway shows a payment captured.
- Fee mismatch — the amount that lands in the account is less than the gateway's reported amount, after fees.
- Duplicates, orphaned records, and partial refunds that show up in one source but not the others.

Most businesses catch these by hand today, cross-checking spreadsheets. This is slow and error-prone at any real volume.

Guardian Ledger automates the clean matches, automatically classifies what's left into known mismatch categories, and — where free-text evidence like a refund note needs interpreting — uses an LLM strictly as a proposal generator. The AI's output is never trusted directly. Every proposal, whether from deterministic matching or from the AI, passes through a trust boundary before anything is marked resolved. Even if that boundary's pattern-matching layer is fooled, there is no code path in the system capable of moving money or altering ledger state outside four fixed, logged outcomes. That structural guarantee — not the pattern scan — is the actual security property being demonstrated.

---

## 2. Architecture — The Modular Build Plan (M0–M6)

The system is built as seven submodules, each with its own milestone check, built in strict order since each depends on the last.

| Module | Responsibility | Status |
|---|---|---|
| **M0** — Synthetic Data Generator | Produces gateway/bank/ledger CSVs plus a poisoned fixture, with a hidden answer key for scoring | ✅ Built, milestone passed |
| **M1** — Deterministic Matching Engine | Exact `txn_ref` join across all three sources, pure code, no LLM | ✅ Built, milestone passed |
| **M2** — Exception Classifier | Rule-based categorization into timing lag / fee mismatch / duplicate / orphan / amount drift / unexplained | ✅ Built, milestone passed |
| **M3** — Evidence Extraction Layer (AI) | LLM parses messy free-text evidence (refund notes) into a structured proposal only; never writes state | ✅ Built and wired into the live `refund.processed` webhook path |
| **M4** — Trust Boundary / Deterministic Verifier | Every proposal passes four checks (source agreement, schema validity, instruction-pattern scan, privileged-action allowlist) before anything is marked resolved | ✅ Built, both milestone directions (catch attack / don't cry wolf on clean data) passed in isolated testing |
| **M5** — Action Router | Routes M4's verdict to exactly one of MATCH / REVIEW / EXCEPTION / QUARANTINE, no other path exists | ✅ Built, all four outcomes confirmed reachable |
| **M6** — Reporting & Audit Log | Match rate, exception breakdown, throughput, quarantine count, false-quarantine rate, full audit trail | ✅ Built, JSON + Markdown output confirmed |

The batch-pipeline version of M0–M6 (`matcher.py`, `classifier.py`, `run.py` against static CSVs) runs independently of the live web app and was used to validate each module's logic before wiring it into production code.

---

## 3. What's Actually Built — The Live Application

Beyond the M0–M6 pipeline, a full multi-tenant web application exists:

### Backend (FastAPI)
- **Auth** — signup/login with JWT (`user_id`, `merchant_id`, `role`), bcrypt password hashing.
- **Multi-tenancy** — every table is scoped by `merchant_id`; every endpoint filters by the logged-in user's merchant, never a client-supplied parameter.
- **Rate limiting** — sliding-window limiter on `/api/login` (5 attempts per 60s, then 429), confirmed working correctly.
- **Per-merchant Razorpay integration** — each merchant stores their own encrypted Razorpay key ID, key secret, and webhook secret (Fernet encryption at rest), entered through the Settings page. Live Checkout creates real Razorpay orders; a signed webhook receives `payment.captured`, `payment.failed`, `refund.processed`, and `settlement.processed` events.
- **Webhook security** — signature verification against the merchant's own webhook secret, a 5-minute timestamp-skew check against replay attacks, and event-ID deduplication.
- **AI-in-the-loop refund handling** — the `refund.processed` webhook branch extracts the refund's free-text `notes` field via the M3 extractor, attaches the AI's proposal, and runs the full evidence through the M4 trust boundary (`verify_proposal()`) before logging any action. This was a real gap identified and closed during development: this path previously could have let poisoned refund notes reach the LLM without a check downstream.
- **Bank statement upload** — CSV upload endpoint feeding an incremental "unmatched pile" model, separate from the batch pipeline.
- **Reporting** — `/api/dashboard` computes match rate, exception breakdown, quarantine count, false-quarantine rate (based on actual human review decisions, not hardcoded), throughput, and human-agreement rate.

### Frontend (React + Vite)
A working multi-page app exists, not scaffolding:
- **Auth** — signup/login screen.
- **Dashboard** — headline metrics (match rate, exceptions, quarantined count, human agreement rate), unmatched pile counts, exception breakdown chart.
- **Review Queue** — lists items flagged REVIEW/EXCEPTION/QUARANTINE, with approve/reject actions. Expandable rows show the AI's proposal (field, extracted value, confidence, source span) alongside the raw evidence it was extracted from.
- **Transactions** — full audit log with search, pagination, and expandable rows showing gateway/bank/ledger records per transaction.
- **Live Checkout** — triggers a real Razorpay test payment end to end.
- **Settings** — per-merchant Razorpay key entry (encrypted), bank statement CSV upload, manual reconciliation sweep trigger.

---

## 4. Fixes Made During This Build Cycle

- **Pydantic validation gap in `extractor.py`** — a malformed or schema-mismatched AI response previously crashed the extraction call instead of falling back to human review, violating the module's own stated invariant. Fixed: any schema mismatch now raises `ExtractionTimeoutError`, which the caller already treats as a fallback trigger.
- **Refund webhook trust-boundary gap** — confirmed the `refund.processed` path routes through `verify_proposal()` before logging, closing a path where AI-extracted refund evidence could previously have been treated as safe without a check.
- **Review Queue AI visibility gap** — the AI's proposal and the raw evidence behind it were being computed and stored correctly on the backend, but were never surfaced in the Review Queue UI. Added an expandable row showing both, so a reviewer can actually see what the AI found before approving or rejecting.
- **`human_agreement_stats()` test gap** — a missing test fixture (matching `transactions` rows for the decisions being tested) was identified and corrected.
- **Rate limiter, git/Render deploy sync, encryption at rest, and multi-tenant isolation** — all independently confirmed working as designed.

---

## 5. What's Left / Known Gaps

### Blocking for a complete live demo
- **Live UI walkthrough of the AI + trust boundary path is not fully polished.** The backend logic — AI extraction, trust boundary verification, quarantine routing — all works and has been exercised. Getting a clean, reliable, end-to-end demonstration of this specifically inside the live UI (trigger a refund with poisoned notes, watch it land in the Review Queue as QUARANTINE, click in and see why) was not completed to a fully rehearsed, presentation-ready state before the deadline. This is the honest gap in the submission: the engineering is done and tested, the live visual walkthrough needed more time than was available.
- A minor UI display bug: the "Exceptions" metric card on the Dashboard was pulling from a field the backend never returns, silently falling back to total transaction count instead of actual exception count. Identified; a one-line fix was written but final deployment/verification is pending.

### Explicitly deprioritized (not blockers, flagged for post-demo hardening)
- Bank CSV ingestion has a few real edge cases: a dedup check that isn't wrapped in a database constraint (a double-submit could error instead of gracefully skipping), missing-`external_id` rows falling back to random IDs (defeating dedup on re-upload), and malformed CSV headers parsing silently as zero-amount rows instead of raising an error.
- Fuzzy/near-match reconciliation (typo'd references, split settlements) is not implemented; exact `txn_ref` matching only, which is an accepted and stated limitation for this stage.
- `EXTRACTION_TIMEOUT_SECONDS` is currently set to 8 seconds; one cold-start real API call approached this limit. Not yet clear if this recurs — worth monitoring, with 15–20 seconds as a safe fallback if it does.

### Not started — out of scope for MVP, part of the roadmap
- **Observability** — no alerting exists yet for stuck jobs, repeated AI failures, or quarantine spikes.
- **Legal/compliance scaffolding** — no Privacy Policy, Terms of Service, or documented data-deletion process yet.
- A dedicated human-review UI beyond the current Review Queue table, a general-purpose (rather than single-scenario) AI evidence parser, an expanded library of adversarial test cases, live data connectors replacing static/manual CSV ingestion, and streaming (rather than batch/webhook-triggered) reconciliation are all deliberately scoped as V2/V3 work, not required for this stage.

---

## 6. Honest Summary

Every core safety and reconciliation guarantee this project claims to make — deterministic matching, honest exception classification, AI-as-proposal-only, a trust boundary that verifies before acting, and a hard allowlist with no privileged action for an attack to reach — is implemented and has been tested at the code level, including both the "catches the attack" and "doesn't cry wolf on clean data" directions the trust boundary is specifically required to prove.

What remains incomplete is turning that verified backend behavior into a fully rehearsed, click-through live demonstration inside the UI. The system works; showing it working smoothly on screen, under time pressure, did not get finished to the standard intended.
