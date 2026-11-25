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

## Единый HTTPS origin

Один hostname обслуживает React на `/`, FastAPI на `/api/` и отдельные health endpoints. Сессия и токен CSRF принадлежат этому hostname. Готовый шаблон location-блоков находится в [настройках Nginx](../../deploy/nginx-crm.locations.conf.example). Hostname, порты и PostgreSQL target подтверждаются в preflight.

Установите образы на Ubuntu 26.04 LTS с существующей PostgreSQL 18.4. Порядок работ: inventory, полный backup с изолированным restore rehearsal, миграция Alembic отдельной командой, запуск контейнеров, проверка HTTPS и сессии, при необходимости bootstrap. Для отката сохраните предыдущее приложение и pre-migration backup.

## Порядок документов

1. [Read-only preflight](preflight.md)
2. [Первое развёртывание и reverse proxy](runbook.md)
3. [Обновления, backup, rollback и incident response](operations.md)
4. [Application production contract](../architecture/production-readiness.md)

Каждая мутация production требует отдельного подтверждения Юрия с точным target и планом
проверки/rollback.
