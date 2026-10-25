---
name: crm-security-review
description: Perform an independent security review of crm-mentoring changes that affect authentication, authorization, object access, sessions, writes, concurrency, migrations, audit records, or sensitive data. Use for trust-boundary changes and final acceptance, not routine cosmetic edits.
---

# CRM Security Review

Review independently from the implementation narrative. Start from the actual diff and follow each changed trust boundary through route, validation, authorization, persistence, and response serialization.

Check as applicable:

- authentication and RBAC deny-by-default behavior
- IDOR/BOLA through object ownership and group/student relationships
- mass assignment and over-posting in Pydantic input models
- CSRF and session/cookie security for the real authentication mechanism
- optimistic concurrency, stale writes, idempotency, and duplicate submissions
- transaction boundaries, rollback behavior, and partial failure
- Alembic upgrade safety, constraints, defaults, and data preservation
- sensitive data exposure in responses, errors, logs, exports, and audit records
- audit integrity, actor attribution, ordering, and tamper-resistant invariants

Use targeted negative tests where evidence is missing. Do not report hypothetical framework issues that the changed path cannot reach. Classify each finding by severity, cite file and line evidence, describe exploit or failure conditions, and propose the smallest robust fix. If there are no actionable findings, say so and list the reviewed boundaries and remaining test limitations.
