# Deployment handoff

Этот пакет предназначен для интеграции «Кураторской» в существующий Ubuntu-сервер. Он не
разворачивает production автоматически и не изменяет PostgreSQL, firewall, reverse proxy или
другие сервисы без отдельного подтверждения оператора.

## Архитектура

- `kuratorskaya-backend` — один non-root Uvicorn worker в отдельном контейнере.
- `kuratorskaya-frontend` — статический Vite build в non-root Nginx на порту `8080`.
- PostgreSQL 18 остаётся существующим host service. Новый database container не создаётся.
- Оба HTTP-порта публикуются только на `127.0.0.1`; внешний доступ даёт существующий HTTPS
  reverse proxy.
- Миграции, bootstrap и backup запускаются явными одноразовыми командами. Startup приложения не
  изменяет schema.

Контейнеры не требуют Docker Compose. Имена сети, контейнеров, портов, hostname и пути в runbook —
переменные, которые оператор выбирает после read-only inventory.

## Критическое ограничение frontend

Текущий React frontend продолжает хранить CRM-данные в `localStorage` и знания в IndexedDB. Он не
подключён к защищённым backend API. Публикация статического образа не превращает его в
многопользовательскую серверную CRM и не переносит браузерные данные. До отдельной интеграции UI
нельзя обещать серверную синхронизацию, RBAC или централизованный backup пользовательских данных.

## Порядок документов

1. [Read-only preflight](preflight.md)
2. [Первое развёртывание и reverse proxy](runbook.md)
3. [Обновления, backup, rollback и incident response](operations.md)
4. [Application production contract](../architecture/production-readiness.md)

Каждая мутация production требует отдельного подтверждения Юрия с точным target и планом
проверки/rollback.
