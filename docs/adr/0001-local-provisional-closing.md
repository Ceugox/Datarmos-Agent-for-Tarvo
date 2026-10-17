# Local deterministic closing driven by a versioned rules policy

Status: accepted 2026-10-16; updated 2026-10-17 after the finance team answered on Slack.

The delivery is a Python command with Decimal arithmetic, original source adapters, CSV exports and a standalone HTML review. It runs without an external model, a hosted service or a database.

Business rules live in `config/closing-policy.json` (schema 2): checkout and remittance bases, EC overrides, commercial conditions, unbilled merchants and bank rules, each with evidence, approver and date. Changing a rule changes the policy, not the code, and produces a different run fingerprint.

Every output row carries signed contributions back to source rows. Existing output directories cannot be overwritten by a different execution. Invoices, contests and postings are proposals for human review; the engine never executes fiscal, banking or messaging actions.
