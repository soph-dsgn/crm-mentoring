---
name: crm-context-handoff
description: Create or refresh a compact, secret-free handoff for unfinished crm-mentoring work when changing chats, models, agents, or context windows. Do not use for routine completed tasks that need no continuation.
---

# CRM Context Handoff

Write `.codex/handoff.md` as current state, not a transcript. Replace superseded content rather than appending history.

Include only:

- branch and clean/dirty status
- current objective and acceptance criteria
- confirmed decisions and relevant invariants
- changed files with one-line purpose
- tests and checks actually run, including failures
- unresolved risks or blockers
- the next evidence-producing action

Keep it short enough to load in one read. Exclude secrets, tokens, credentials, personal data, raw user records, large logs, speculative theories, and information already available in `AGENTS.md` or stable architecture docs. Verify paths and Git state before writing. The file is local and ignored by Git by default.
