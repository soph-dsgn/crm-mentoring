# «Кураторская»: handoff для Софьи и её ChatGPT

> Состояние проверено по repository commit `64b413c9f9979e328146e03b972c3c6a586b0e5a`
> (2026-10-29). Перед любой реализацией нужно повторно сверить текущую ветку с кодом.

## 1. Что это за проект

«Кураторская» — CRM для сопровождения образовательных групп. Основной сценарий:

**группа → ученица → стратегия → текущие задачи → домашнее задание → проверка → прогресс**.

Система также хранит встречи, историю изменений и независимое согласование задач с Аней. Главные
ценности: не терять учебную историю, не смешивать разные статусы и не раскрывать данные между
пользователями.

Этот документ передаёт контекст frontend-интеграции. Backend уже реализован; текущий React всё ещё
работает преимущественно с browser-local data. Наличие API не означает готовую синхронизацию.

## 2. Люди и ответственность

- **Аня** — product owner и CRM owner. В backend owner — это `role=admin` + `is_owner=true`, не
  отдельная роль и не захардкоженная identity
- **Софья** — frontend developer и curator
- **Елисей** — другой curator с теми же правилами обычного admin
- **Students** — участницы образовательных программ, каждая связана с одним Student profile
- **Юрий** — production infrastructure/deployment; изменения его сервера требуют отдельного
  операторского подтверждения

## 3. Роли и бизнес-модель

Ролей ровно две: `admin` и `student`. Owner — дополнительный флаг admin.

- **Owner:** global read/write, user/account administration, curator reassignment/offboarding,
  ownership transfer, legacy import/export
- **Admin/curator:** читает учебные данные всех групп, изменяет только назначенные группы; создаёт
  группу с назначением на себя; управляет аккаунтами students только в своих группах
- **Student:** читает только собственные profile/strategy/meetings/homeworks; может submit/resubmit
  собственное homework; административные mutations запрещены

Frontend может скрывать недоступные controls, но это только UX. Security boundary всегда backend.

## 4. Ключевые доменные инварианты

1. У группы один активный curator; один curator ведёт много групп
2. Student принадлежит ровно одной группе; обычный profile PATCH не переносит между группами
3. Group lifecycle меняется явно: даты не завершают группу или стратегии автоматически
4. У Student не более одной Strategy
5. Sections и Tasks имеют уникальный порядок; `period_text` не равен deadline
6. `study_status`, homework `review_status` и `AnyaApproval.status` независимы
7. Draft/issued homework не завершают Tasks
8. Submission ставит task review `pending`; revision — `revision`; только acceptance ставит
   `study_status=done`, `review_status=accepted`
9. Manual task status запрещён при review `pending|revision`
10. HomeworkItem хранит immutable snapshot, даже если Task позже изменена/архивирована
11. AnyaApproval использует исходную Task, а не копию
12. Archive не равен delete: history и student-read сохраняются
13. Temporary password возвращается только один раз в create/reset response
14. Version conflict не должен молча перезаписывать чужое изменение

## 5. Архитектура репозитория

- `frontend/`: React 19, TypeScript, Vite, Framer Motion, Phosphor, Radix Select
- `backend/`: FastAPI, Pydantic 2, SQLAlchemy 2, server sessions, PostgreSQL 18; SQLite для dev/tests
- `backend/migrations/`: Alembic chain и database integrity safeguards
- `docs/architecture/`: domain/API/security/quality contracts
- `docs/deployment/`: Docker package и безопасные operator runbooks
- `.github/workflows/`: обязательные frontend/backend gates

Backend организован routes → Pydantic schemas → transactional services/models. Alembic запускается
оператором, а не при startup. Production config запрещает SQLite/insecure defaults и отключает
interactive OpenAPI.

## 6. Текущее состояние frontend

### IMPLEMENTED browser-local

- curator-oriented navigation, responsive screens и design system
- Groups, Student profiles, Strategies, Tasks, Meetings, Homeworks, Anya queue
- AppData v3 в localStorage; normalization/export/import v1-v3
- KnowledgeData v1 в отдельном IndexedDB
- dialogs, Select, sanitization, URL filtering, FlowBackground и reduced-motion

### PARTIALLY IMPLEMENTED

Domain workflows существуют локально, но не используют server API. Они полезны как UX reference,
но permissions, concurrency и persistence должны перейти на backend.

### MISSING

- login/session/logout и forced password change
- typed API client, CSRF/error/pagination/version handling
- owner/curator/student account administration
- student-specific navigation/screens
- server source-of-truth и multi-user synchronization
- safe 401/409 recovery и production cutover UI

`App.tsx` сейчас владеет всем `AppData` и mutations. `data.ts` сохраняет ключ
`crm-mentoring-v1`. Business API requests в текущем frontend отсутствуют; static seed fetch не
является backend integration.

## 7. UX и security, которые нужно сохранить

- Manrope, холодная светлая палитра, белые поверхности, Phosphor, общий motion language
- keyboard/focus behavior dialogs, pending lock, loading/error/empty states
- DOMPurify для rich content; safe URL protocols и `noopener noreferrer`
- FlowBackground как presentation-only effect с CSS fallback/reduced-motion
- отсутствие horizontal overflow на desktop/tablet/mobile
- temporary passwords не попадают в persistent state, URL, logs, analytics или toast history

## 8. Authentication, CSRF и errors

- login: `POST /api/v1/auth/login`; session bootstrap: `GET /api/v1/auth/me`
- browser requests используют `credentials: "include"`
- session cookie `kuratorskaya_session` — HttpOnly
- CSRF cookie `kuratorskaya_csrf` читается перед mutation и отправляется как `X-CSRF-Token`
- mutations также проверяют same-origin
- `must_change_password=true` блокирует business APIs; доступны change-password/logout
- change-password отзывает sessions, поэтому UI возвращается к login
- error envelope: `{"error":{"code","message","details"}}`
- `401` session, `403` permission, `404` hidden/missing, `409` version/state conflict, `422` input

Нельзя хранить session/CSRF в localStorage или доверять client-side role checks.

## 9. Фактический API overview

Ниже группы routes; точные request/response contracts и UI mapping находятся в
[`docs/frontend-handoff/api-integration-contract.md`](docs/frontend-handoff/api-integration-contract.md).

### Auth и accounts

- `/api/v1/auth/login`, `/me`, `/logout`, `/change-password`
- `/api/v1/admin/curators` create/list/detail/deactivate
- student account create/read/deactivate и user reset-password
- group curator reassignment, curator offboarding, ownership transfer

### Groups и Students

- `/api/v1/groups` list/create и `/{group_id}` read/versioned patch
- group archive/restore
- `/api/v1/groups/{group_id}/students` admin roster/create
- `/api/v1/students/{student_id}` read/versioned patch и archive/restore

### Strategy и Tasks

- Student strategy read/create
- section list/create/rename/atomic reorder
- task list/create/read/update/status/archive/restore/reorder/history
- AnyaApproval read/create/transition

### Meetings и Homeworks

- meeting list/create/read/versioned update/archive/restore
- homework list/create/read/versioned update/transition/archive/restore/history
- student sees safe responses and can only submit/resubmit own work

### Migration и operations

- owner-only `/api/v1/imports/legacy/validate` и `/api/v1/imports/legacy`
- owner-only `/api/v1/exports/backup` logical business export
- `/health`, `/health/live` и `/health/ready` — infrastructure probes, не product screens

List cursors opaque. Versioned mutations отправляют `expected_version`; после `409` клиент refetch
и предлагает осознанное разрешение конфликта, но не blind retry.

## 10. Backend gaps, важные для frontend

- **BLOCKED BY BACKEND:** Student transfer между groups
- **BLOCKED BY BACKEND:** delete/archive StrategySection
- **BLOCKED BY BACKEND:** move Task между sections; доступен только reorder внутри section
- **BLOCKED BY BACKEND:** Knowledge API/synchronization
- **MISSING:** server file uploads

Локальные delete/move actions нельзя сохранять после cutover через цепочки delete/create. Нужны
отдельные контракты или удаление action из integrated UI.

## 11. Рекомендуемая frontend architecture

Добавить минимальный `src/api/` на native fetch: `http.ts`, snake_case contracts, feature modules и
явные mappers в текущие view models. Добавить AuthProvider и forced-password gate. Не вводить большой
state manager/query dependency без подтверждённой необходимости.

Server становится единственным источником business data. Локальными остаются tabs, filters, dialogs
и form drafts. Duplicate submit блокируется UI, offline mutations не ставятся в скрытую очередь.
После 409 — refetch/reconciliation. После 401 — login и fresh state.

Подробно: [`frontend-architecture-plan.md`](docs/frontend-handoff/frontend-architecture-plan.md).

## 12. Knowledge Base: решение

KnowledgeData v1 живёт в IndexedDB `crm-mentoring-knowledge` отдельно от AppData. Там есть seed,
user edits/deletes/favorites и import DOCX/HTML/Markdown/JSON + JSON export. Legacy backend import её
не переносит.

Рекомендация для первого MVP: оставить Knowledge явно browser-local и дать отдельный backup, чтобы
не блокировать основной workflow. Ограничения — нет RBAC, cross-device sync и server backup. До
обещания полностью multi-user продукта нужно принять отдельный Knowledge API project.

## 13. Deployment status

Backend production-readiness и deployment handoff существуют: PostgreSQL 18, strict production
settings, first-owner CLI, health/readiness, operational backup/restore и Docker packaging.
Frontend packaging не превращает browser-local CRM в server-integrated CRM. Production rollout
требует auth и data cutover, согласованных HTTPS host/origin cookies и operator backup/rollback.

## 14. Инкрементальная roadmap

1. Typed API client + auth/session/password gate
2. Owner/curator account administration
3. Groups/Students server integration
4. Strategies/Tasks/AnyaApproval
5. Meetings/Homeworks
6. Student-facing workflow
7. Legacy migration and server cutover
8. Knowledge Base decision
9. Full role-based E2E and production acceptance

Каждый пункт — отдельный PR с focused tests. Полный scope/DoD:
[`implementation-roadmap.md`](docs/frontend-handoff/implementation-roadmap.md).

## 15. Главные acceptance journeys

- owner first login → forced password change → fresh login
- owner creates curator; curator creates group/student/account
- student logs in and sees own data only
- curator reset-password only for assigned student
- group lifecycle and curator reassignment update permissions
- strategy/tasks/reorder/history with 409 recovery
- independent AnyaApproval workflow
- homework issue → submit → revision → resubmit → acceptance with task progress
- two sessions/cross-device see consistent server state
- 401/403/404/409/422 produce safe, understandable UI
- AppData validation/import preserves relationships/snapshots; Knowledge gap stays explicit

Полная матрица: [`testing-and-acceptance.md`](docs/frontend-handoff/testing-and-acceptance.md).

## 16. Coding и quality conventions

- новая бизнес-логика и bug fixes: RED → GREEN → REFACTOR
- не менять design/business rules ради удобства API wiring
- backend snake_case остаётся wire contract; camelCase mapping явный
- mutations не передают server-managed identity/role/owner/curator fields
- никаких реальных данных учениц в fixtures/screenshots/logs
- после frontend change: `npm run lint`, `npm run build`, `npm run verify:workflow`, targeted browser
  QA и `git diff --check`
- перед PR использовать актуальный CI contract; не утверждать о пройденных проверках без запуска
- Conventional Commits и отдельная feature branch для каждого milestone

## 17. Как Софье работать с ChatGPT и Codex

1. Выбрать один roadmap milestone и дать ChatGPT актуальный diff/report
2. ChatGPT сверяет routes/schemas/tests и формирует scoped English prompt для Codex
3. Prompt фиксирует scope, business/security invariants, TDD, gates и явный out-of-scope
4. Codex реализует в feature branch без unrelated refactor
5. Софья проверяет UI/UX и реальные user journeys; ChatGPT помогает review diff/test evidence
6. Merge только после CI; затем обновить roadmap и unresolved decisions

Private conversations не являются repository source of truth. Любое утверждение об implementation
нужно подтверждать кодом, tests или отчётом текущего PR.

## 18. Рекомендуемая первая задача

Начать с milestone 1: typed fetch client и auth/session foundation. Это минимальный dependency для
всех следующих экранов. Scope не должен включать domain migration: только login/me/logout,
change-password gate, CSRF/error handling, authorization-aware shell и tests.

## 19. Definition of production-ready frontend

- все выбранные MVP screens используют API как единственный business source-of-truth
- owner/admin/student получают разные корректные experiences
- session expiry, forced password, CSRF, permissions и one-time credentials обработаны
- versions/409 не приводят к silent overwrite
- homework/approval/task invariants сохраняются и после reload/cross-device use
- legacy cutover проверен и имеет rollback backup
- Knowledge limitation либо устранено отдельным API, либо явно принято продуктом
- responsive/accessibility/security/full-system E2E и CI green
- production host/origin, backup, verification и rollback согласованы с Юрием

## Подробная документация

Начать с [`docs/frontend-handoff/README.md`](docs/frontend-handoff/README.md). Там есть продуктовые
правила, architecture, API inventory, screen matrix, roadmap, acceptance и open decisions.

---

## START HERE — INSTRUCTIONS FOR SOFIA'S CHATGPT

Ты — технический planning/review partner Софьи по React-интеграции CRM «Кураторская».

### Правила работы

1. Считай этот документ контекстом проекта, но не доказательством того, что implementation всё ещё
   совпадает с описанием. Перед планом проверяй текущие routes, schemas, services, tests и frontend
2. Явно разделяй **verified facts**, **assumptions**, **product decisions** и **blockers**
3. Если прямого repository access нет, запрашивай у Софьи актуальный Codex report, diff и связанные
   файлы. Не выдумывай результаты tests или существующие endpoints
4. Работай как planning и code-review partner: декомпозируй roadmap на небольшие PR, проверяй
   contracts/security/UX, помогай Софье оценить результат
5. Для Codex готовь scoped prompts на английском. Каждый prompt должен содержать:
   - branch/objective и точный scope
   - verified APIs/files
   - business/RBAC/concurrency invariants
   - RED → GREEN → REFACTOR и acceptance scenarios
   - required quality gates
   - explicit out-of-scope и запрет unrelated refactor
6. Сохраняй существующий frontend design, keyboard accessibility, sanitization и domain contracts
7. Client-side role checks никогда не называй security boundary; backend остаётся authoritative
8. Не предлагай новую infrastructure, state manager или dependency без конкретной необходимости
9. Не смешивай `study_status`, homework review и AnyaApproval
10. Не превращай archive в delete и не обходи отсутствующий backend endpoint несколькими
    destructive requests
11. Отслеживай прогресс roadmap и список unresolved blockers после каждого merged PR
12. Никогда не говори «реализовано», «проверено» или «tests passed» без evidence текущей ветки/CI
13. Не предполагай доступ к private conversations, hidden context, production credentials или
    серверу Юрия

### Порядок следующей работы

Сначала повторно проверить milestone 1 prerequisites. Затем подготовить Codex prompt только для
typed API client + authentication/session/forced-password foundation. Не включать Groups/Students
или migration в первый PR. После реализации запросить diff, test report и browser QA evidence,
провести focused review и только затем переходить к account administration.

