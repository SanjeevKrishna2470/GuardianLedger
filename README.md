# Guardian Ledger

Guardian Ledger closes the reconciliation loop across sources that don't agree with each other — and its answer to 'what if one of those sources is compromised' isn't a prompt asking the AI to be careful, it's a system with no capability for the AI to act on anything but a verified conclusion.

## Architecture

The system is composed of several modules:
- **M0 — Synthetic Data Generator**: Generates base "clean" transactions and injects mismatch types.
- **M1 — Deterministic Matching Engine**: Exact-match pass on `txn_ref`/UTR.
- **M2 — Exception Classifier**: Categorizes non-clean-match transactions.
- **M3 — Evidence Extraction Layer (AI)**: Parses semi-structured or messy evidence.
- **M4 — Trust Boundary / Deterministic Verifier**: Core invariant gate before marking anything "resolved".
- **M5 — Action Router**: Routes M4's verdict to final outcomes.
- **M6 — Reporting & Audit Log**: Traceable logging and human-readable reporting.

## Setup Instructions

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the end-to-end pipeline:
   ```bash
   python run.py
   ```
