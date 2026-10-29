# Frontend integration handoff

Этот раздел — рабочая документация для поэтапного подключения React-интерфейса «Кураторской» к
существующему FastAPI backend. Переносимая вводная для нового чата находится в
[`SOFIA_HANDOFF.md`](../../SOFIA_HANDOFF.md).

## Навигация

- [Продукт, роли и инварианты](product-and-roles.md)
- [Архитектура репозитория](repository-architecture.md)
- [Текущее состояние frontend](frontend-current-state.md)
- [Фактический API-контракт](api-integration-contract.md)
- [Матрица экранов и API](screen-api-matrix.md)
- [План frontend-архитектуры](frontend-architecture-plan.md)
- [Инкрементальная дорожная карта](implementation-roadmap.md)
- [Тестирование и приёмка](testing-and-acceptance.md)
- [Открытые решения и пробелы](open-decisions-and-gaps.md)

## Статусы

- **IMPLEMENTED** — поведение существует в текущем коде и подтверждено routes/schemas/tests
- **PARTIALLY IMPLEMENTED** — существует только часть сквозного сценария
- **MISSING** — реализации нет
- **BLOCKED BY BACKEND** — React не может корректно завершить сценарий с текущим API
- **REQUIRES PRODUCT DECISION** — сначала нужно решение о поведении или границе MVP

При расхождении документов с кодом источником истины служат routes, Pydantic schemas, services и
тесты текущей ветки. Frontend-интеграция ещё не реализована.

## Текущий milestone

Интеграция ещё не начата. Первый рекомендуемый PR — typed API client и auth/session foundation:
login, `/auth/me`, logout, CSRF/error handling и forced-password gate. Groups/Students и migration
не входят в этот первый PR.
