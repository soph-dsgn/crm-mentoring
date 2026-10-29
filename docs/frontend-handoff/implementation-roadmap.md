# Инкрементальная дорожная карта

Каждый пункт — отдельный небольшой PR. Следующий этап начинается после merge и проверки предыдущего.

## 1. Typed API client и auth/session foundation

- **Scope:** `api/http`, wire types, AuthProvider, login/logout, `/auth/me`, forced-password gate
- **Files:** new `src/api/*`, `src/auth/*`; narrow updates to `App.tsx`/navigation
- **APIs:** `/api/v1/auth/*`
- **UX/security:** credentialed requests, CSRF, 401/429, no token/localStorage, safe errors
- **Tests:** client error mapping, auth bootstrap, expired session, password gate, CSRF header
- **DoD:** reload восстанавливает session; business UI недоступен до password change
- **Out:** domain data integration и account administration

## 2. Owner и curator account administration

- **Scope:** curator list/create/details/deactivate/offboard/ownership transfer; student account and
  reset actions where profile context already exists
- **Files:** `src/api/users.ts`, new account-admin views/dialogs, navigation
- **APIs:** `/api/v1/admin/*`
- **UX/security:** one-time credential modal, copy-only explicit action, confirmations, owner-only nav
- **Tests:** owner/admin/student visibility, password disappears after close, errors do not leak it
- **DoD:** owner безопасно управляет accounts; обычный admin не получает owner actions
- **Depends:** milestone 1
- **Out:** group/student domain persistence, automated credential delivery

## 3. Groups и Students

- **Scope:** заменить local reads/mutations для Overview, Groups и Student profile
- **Files:** `src/api/groups.ts`, `students.ts`, `App.tsx`, group/profile/forms/Overview
- **APIs:** groups/students + account actions
- **UX/security:** cursor lists, archive/restore вместо delete, versions/409, student-safe profile
- **Tests:** assigned/unassigned writes, student own read, refresh/cross-device consistency
- **DoD:** server — единственный источник этих entities
- **Depends:** milestones 1–2
- **Out:** transfer student между группами до backend/product decision

## 4. Strategies, Tasks и AnyaApproval

- **Scope:** strategy sections/tasks, status, reorder, history, archive, approval queue
- **Files:** `src/api/strategies.ts`, Strategy/Task/Anya components и workflow adapters
- **APIs:** strategy/section/task/approval routes
- **UX/security:** independent study/review/approval states; atomic reorder; review lock errors
- **Tests:** no duplicates, approval sync, 409 reconciliation, archived history, role scope
- **DoD:** Strategy и Anya views отображают одну server task
- **Depends:** milestones 1 and 3
- **Out:** section delete и cross-section move до появления контракта

## 5. Meetings и Homeworks

- **Scope:** meeting history; homework draft/issue/submit/revision/accept/archive
- **Files:** `src/api/meetings.ts`, `homeworks.ts`, meeting/Homework components
- **APIs:** meeting/homework routes and transitions
- **UX/security:** immutable snapshots, student-safe fields, lifecycle-specific actions
- **Tests:** issue does not complete task; submit/revision/accept statuses; repeated actions; reload
- **DoD:** progress берётся из server result, история сохраняется
- **Depends:** milestone 4

## 6. Student-facing workflow

- **Scope:** отдельная доступная navigation shell для own profile/strategy/meetings/homeworks
- **Files:** auth-aware navigation, student routes/views; reuse shared read components
- **APIs:** self-safe Student/Strategy/Meeting/Homework reads and homework transitions
- **UX/security:** отсутствие roster/private notes/admin controls; submit/resubmit only
- **Tests:** direct URL IDOR responses, keyboard/mobile, session expiry, completed/archived access
- **DoD:** student проходит login → own strategy → homework submission без curator UI
- **Depends:** 1, 3–5
- **Out:** student profile mutations и curator-only fields

## 7. Browser-data migration и cutover

- **Scope:** owner validation preview, conflict report, confirmed import, logical export; отключение
  business dual-write
- **Files:** `src/api/legacy.ts`, backup/import dialogs, `App.tsx` persistence boundary
- **APIs:** legacy validate/import and logical export
- **UX/security:** 5 MiB boundary, checksum confirmation, no personal-record dump in errors
- **Tests:** v1-v3 synthetic backups, duplicate request, mismatch/conflict, counts/relationship review
- **DoD:** импорт проверен, server source-of-truth включён, local backup сохранён
- **Depends:** integrated domain milestones 1–6
- **Out:** IndexedDB KnowledgeData и operational PostgreSQL backup UI

## 8. Knowledge Base resolution

- **Scope:** реализовать выбранный product option: явно browser-local либо отдельный backend project
- **Files:** `knowledge.ts`, `KnowledgePage.tsx` и, только для Option B, отдельный будущий API scope
- **APIs:** отсутствуют до product/backend решения
- **UX/security:** явно обозначить local-only границу; не обещать RBAC/sync/backup которых нет
- **Tests:** persistence/export/import для Option A либо отдельная TDD matrix для Option B
- **DoD:** выбранная граница отражена в UI, acceptance и product documentation
- **Depends:** явное product decision из `open-decisions-and-gaps.md`
- **Out:** не создавать Knowledge backend внутри frontend PR
- **Out:** не добавлять Knowledge entities в Strategy/Homework tables

## 9. Full frontend QA и E2E acceptance

- **Scope:** role-based journeys, responsive/a11y, conflicts, cross-device, production-like preview
- **Files:** workflow/browser tests и только подтверждённые fixes в затронутых features
- **APIs:** весь выбранный MVP contract
- **UX/security:** desktop/mobile/keyboard, console/privacy, role/IDOR/conflict journeys
- **Tests:** сценарии из `testing-and-acceptance.md`; console/network/privacy review
- **DoD:** gates green, no hidden local business writes, operator cutover/rollback approved
- **Depends:** все выбранные MVP milestones
- **Out:** unrelated redesign, infrastructure deployment и новые product features

