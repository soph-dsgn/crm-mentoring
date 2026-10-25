---
name: crm-backend-tdd
description: Implement or fix FastAPI, SQLAlchemy, Pydantic, Alembic, or backend API behavior in crm-mentoring through focused RED-GREEN-REFACTOR development. Use for backend business logic and bug fixes; do not use for documentation-only or frontend-only changes.
---

# CRM Backend TDD

Read the repository `AGENTS.md` and [quality standards](../../../docs/architecture/quality-standards.md). Preserve existing architecture, domain invariants, user data, API contracts, and migrations.

1. Trace the smallest relevant path: route, schema, service, repository/model, migration, and existing tests. Search symbols before opening broad files.
2. RED: add the narrowest test that expresses the agreed behavior and fails for the intended reason. Include negative cases, authorization boundaries, validation, and transaction invariants when relevant. Use only synthetic data and an isolated test database.
3. GREEN: make the minimum reliable implementation using existing FastAPI, Pydantic, SQLAlchemy 2, and dependency-injection conventions. Preserve error handling and type safety.
4. REFACTOR only when it removes real duplication or clarifies the changed path. Avoid unrelated cleanup and new abstractions without a second concrete use.
5. Run the focused test first, then the affected module suite. After a functional block, run relevant integration/API regression tests. Do not repeatedly run the full suite during a small edit.
6. Inspect migration impact whenever models or constraints change. Never rewrite an existing migration or touch production/user data without an explicit request and backup plan.

Return the failing-test evidence, implementation summary, targeted checks, migration impact, and unresolved risk. Never commit, push, or open a PR unless the user separately asks.
