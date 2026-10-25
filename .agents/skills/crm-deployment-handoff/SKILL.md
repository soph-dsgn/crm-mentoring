---
name: crm-deployment-handoff
description: Prepare a safe deployment handoff for crm-mentoring to an external DevOps engineer or agent by inspecting documentation and producing preflight, Docker, database, migration, backup, restore, and rollback guidance. Do not perform the deployment or destructive operations.
---

# CRM Deployment Handoff

Inspect only the deployment-relevant documentation, manifests, dependency files, environment examples, migrations, and CI configuration. Distinguish verified repository facts from missing operational decisions.

Produce a handoff that covers:

- target environment assumptions and unresolved questions
- runtime versions, entrypoints, ports, storage, and required services
- configuration keys by purpose, never secret values
- Docker image/build expectations when present or a clearly labeled proposal when absent
- database location, ownership, persistence, and SQLite-specific concurrency/backup constraints
- Alembic preflight, upgrade order, compatibility checks, and rollback limitations
- backup creation, integrity verification, restore rehearsal, retention, and recovery ownership
- health checks, smoke tests, observability, and concise failure evidence
- reversible rollout and rollback decision points

Do not invent server details, credentials, DNS, certificates, or production topology. Do not run migrations, modify infrastructure, upload artifacts, restart services, delete data, or deploy without separate explicit authorization. Highlight every destructive or irreversible step for human approval at action time.
