---
name: crm-pr-readiness
description: Assess whether crm-mentoring changes are ready for a Pull Request by reviewing the diff and running the repository's required quality gates. Use only when a functional block is complete or PR readiness is requested; do not commit, push, create, or merge a PR.
---

# CRM PR Readiness

Read `AGENTS.md` and [quality standards](../../../docs/architecture/quality-standards.md). Work from the actual branch diff against the intended base.

1. Inspect Git status, changed files, staged diff if any, and the complete branch diff. Flag accidental files, generated artifacts, secrets, unrelated formatting, data changes, and migration rewrites.
2. Perform Double QA:
   - pass one validates the requested behavior, domain invariants, regressions, and user-data safety
   - pass two rereads the diff independently for edge cases, error handling, consistency, and missing tests
3. Run the complete backend gates when backend or shared behavior changed: Ruff lint, Ruff format check, full pytest with configured branch coverage, Alembic upgrade/current/check.
4. Run frontend lint, build, and workflow verification when frontend or shared contracts changed. Perform relevant desktop/mobile visual checks when UI changed, or state why they were not possible.
5. Invoke `crm-security-review` separately for trust-boundary changes; do not replace it with the general QA passes.
6. Run `git diff --check` and report CI-equivalent commands exactly as executed.

Return a concise release report: scope, checks and results, coverage evidence, migration impact, security review status, visual-check status, blockers, and residual risk. Never commit, push, create a PR, or merge without a separate explicit request.
