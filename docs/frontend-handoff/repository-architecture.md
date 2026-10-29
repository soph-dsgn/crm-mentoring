# Архитектура репозитория

## Структура

| Область | Технологии | Ответственность |
|---|---|---|
| `frontend/` | React 19, TypeScript, Vite | Текущий browser-local интерфейс и UX |
| `backend/app/` | FastAPI, Pydantic 2, SQLAlchemy 2 | API, auth, RBAC, доменные сервисы |
| `backend/migrations/` | Alembic | Версионирование PostgreSQL/SQLite schema |
| `docs/architecture/` | Markdown | Доменные и API-контракты |
| `docs/deployment/` | Docker/runbooks | Безопасная передача развёртывания оператору |
| `.github/workflows/` | GitHub Actions | Backend/frontend quality gates |

Frontend и backend находятся в одном репозитории, но сейчас не соединены: React сохраняет бизнес-
данные локально, а FastAPI уже предоставляет серверные endpoints. Наличие backend не означает, что
данные текущего браузера автоматически синхронизируются.

## Backend

- `backend/app/api/routes/` объявляет HTTP-контракт и dependencies
- `backend/app/modules/*/schemas.py` содержит wire schemas; изменяющие schemas используют
  `extra="forbid"`
- `backend/app/modules/*/service.py` содержит транзакционные бизнес-операции
- `backend/app/modules/auth/authorization.py` и API contexts обеспечивают role/object checks
- server-side session хранится в БД; browser получает HttpOnly session cookie и отдельный CSRF
  cookie
- mutations требуют session, same-origin и `X-CSRF-Token`
- версии ресурсов и атомарные updates защищают от silent lost update
- migrations содержат FK, unique/check constraints и database safeguards для PostgreSQL 18 и
  SQLite development/tests

Приложение не создаёт schema и не запускает migrations при старте. Production OpenAPI UI отключён.

## Frontend

- `frontend/src/App.tsx` — navigation shell и владелец текущего `AppData` state
- `frontend/src/data.ts` — начальные данные, normalizer v1-v3 и localStorage persistence
- domain types расположены рядом с экранами и в `types.ts`
- `workflow.ts` и helpers реализуют локальные переходы задач, ДЗ и согласований
- `KnowledgePage`/knowledge helpers используют отдельный IndexedDB store
- общий `Dialog`, `Select`, motion tokens и FlowBackground формируют существующую design system

До интеграции frontend не должен одновременно считать localStorage и API двумя равноправными
источниками истины. Cutover выполняется отдельным этапом после validate/import и сверки результата.

## Development и production

Локальная разработка допускает SQLite и Vite dev server. Production требует PostgreSQL,
явных host/origin allowlists, secure cookies и запуск собранных артефактов согласно
[`docs/deployment/`](../deployment/README.md). Docker packaging не означает готовую React↔API
интеграцию.

Основные команды:

```text
cd backend
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .

cd frontend
npm ci
npm run lint
npm run build
npm run verify:workflow
```

Полный актуальный набор проверок описан в
[`quality-standards.md`](../architecture/quality-standards.md) и `.github/workflows/ci.yml`.

