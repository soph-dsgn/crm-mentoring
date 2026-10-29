# First deployment runbook

Команды ниже — шаблон. Перед выполнением Юрий подтверждает значения переменных и каждый шаг,
меняющий host. Production deployment в рамках разработки не выполняется.

## 1. Сборка образов

На доверенной build-машине из проверенного commit:

```bash
export CRM_IMAGE_TAG='<GIT_COMMIT_SHA>'
docker build --pull --file backend/Dockerfile --tag "kuratorskaya-backend:${CRM_IMAGE_TAG}" backend
docker build --pull --file frontend/Dockerfile --tag "kuratorskaya-frontend:${CRM_IMAGE_TAG}" frontend
docker image inspect "kuratorskaya-backend:${CRM_IMAGE_TAG}" "kuratorskaya-frontend:${CRM_IMAGE_TAG}"
```

Backend использует Python `3.13.17`, exact Python dependencies из `requirements.lock`, PostgreSQL
client 18 и non-root UID/GID `10001`. Frontend собирается через `npm ci` из `package-lock.json` и
работает под non-root Nginx. Не используйте mutable `latest` для rollout или rollback.

## 2. PostgreSQL

DBA создаёт отдельную role/database без superuser, role creation и public network access. Пароль
задаётся интерактивно либо через действующий secret manager, не в shell history. Application role
получает права только на свою database/schema. Существующие databases и роли не изменяются.

Контейнер подключается к host PostgreSQL через заранее проверенный private address. Для Docker
можно использовать `--add-host host.docker.internal:host-gateway`, но PostgreSQL должен слушать
только согласованный private interface, а `pg_hba.conf` — разрешать только application role и
необходимый Docker subnet. PostgreSQL нельзя публиковать в Internet.

Версия `pg_dump` не должна быть старше server major; образ содержит client 18 для PostgreSQL 18.4.

## 3. Environment

```bash
install -d -m 0700 /srv/kuratorskaya/config
install -m 0600 deploy/backend.env.example /srv/kuratorskaya/config/backend.env
```

Замените все placeholders. Env-файл не хранится в Git, backup или логах. Docker administrators
могут видеть container environment и относятся к доверенной операционной границе.

Рекомендуемые значения для сервера с 2 CPU и ограниченной памятью: pool `3`, overflow `1`, один
Uvicorn worker. Не увеличивайте worker/pool без измерений общей нагрузки PostgreSQL.

## 4. Миграции и bootstrap

После отдельного подтверждения создайте изолированную Docker network, если подходящей сети ещё нет:

```bash
docker network create kuratorskaya-net
```

Проверка и применение миграций выполняются отдельно от startup:

```bash
docker run --rm \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --env-file /srv/kuratorskaya/config/backend.env \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}" alembic current

docker run --rm \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --env-file /srv/kuratorskaya/config/backend.env \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}" alembic upgrade head

docker run --rm \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --env-file /srv/kuratorskaya/config/backend.env \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}" alembic current
```

Первого owner создают один раз в интерактивном TTY. Login и database name не подставляйте из
непроверенного ввода:

```bash
docker run --rm -it \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --env-file /srv/kuratorskaya/config/backend.env \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}" \
  python -m app.cli.bootstrap_owner \
  --login '<OWNER_LOGIN>' \
  --confirm-database '<CRM_DB_NAME>' \
  --confirm-first-owner
```

Temporary password показывается один раз. Не перенаправляйте вывод и не запускайте bootstrap через
CI/deployment log.

## 5. Запуск

Выберите подтверждённые свободные loopback-порты:

```bash
export CRM_API_PORT='<LOOPBACK_API_PORT>'
export CRM_WEB_PORT='<LOOPBACK_WEB_PORT>'

docker run --detach \
  --name kuratorskaya-backend \
  --restart unless-stopped \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --publish "127.0.0.1:${CRM_API_PORT}:8000" \
  --env-file /srv/kuratorskaya/config/backend.env \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 384m --cpus 1 \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}"

docker run --detach \
  --name kuratorskaya-frontend \
  --restart unless-stopped \
  --publish "127.0.0.1:${CRM_WEB_PORT}:8080" \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 96m --cpus 0.25 \
  "kuratorskaya-frontend:${CRM_IMAGE_TAG}"
```

Проверьте `docker inspect`, non-root UID, health status, `/health/live` и `/health/ready` через
loopback. Readiness должен стать `200`; при недоступной БД он возвращает безопасный `503`.

## 6. Reverse proxy и HTTPS

Baseline intentionally запускает Uvicorn с `--no-proxy-headers`. Existing proxy должен:

- завершать TLS и перенаправлять HTTP на HTTPS;
- проксировать выбранный API hostname на `127.0.0.1:${CRM_API_PORT}`;
- проксировать frontend hostname на `127.0.0.1:${CRM_WEB_PORT}`;
- передавать исходный `Host`, но очищать `Forwarded` и `X-Forwarded-*` в baseline;
- ограничивать request body/timeouts и добавлять HSTS только после проверки HTTPS;
- сохранять `Origin`, cookies и `X-CSRF-Token`;
- не публиковать container ports на `0.0.0.0`.

`KURATORSKAYA_PERMITTED_HOSTS` содержит API hostname, а `KURATORSKAYA_FRONTEND_ORIGINS` — точный
HTTPS origin frontend. Wildcards запрещены. `KURATORSKAYA_TRUSTED_PROXY_IPS=[]` остаётся безопасным
baseline. Режим с forwarded headers не включайте без отдельной acceptance-проверки прямого peer IP
и согласованной конфигурации Uvicorn/application.

Если browser frontend позднее подключается к API на другом hostname, оба HTTPS hostname должны
оставаться в одном schemeful site (например, соседние поддомены одного registrable domain), иначе
session cookie с `SameSite=Lax` не будет работать для browser API-запросов. Альтернатива — единый
origin с маршрутизацией `/api`; не ослабляйте `SameSite` ради несогласованной DNS-схемы.

Перед изменением live proxy: сохранить текущий конфиг, выполнить syntax test, подготовить rollback,
получить подтверждение Юрия, применить reload без остановки других виртуальных хостов.

## 7. Приёмка

После TLS-публикации проверить:

1. `/health/live` и `/health/ready` через публичный API hostname.
2. Неизвестный Host отклоняется, `/docs` и `/openapi.json` возвращают `404`.
3. Login первого owner через защищённый API client с корректным frontend Origin.
4. Ответ требует сменить temporary password; смена выполняется с session cookie и CSRF header.
5. Старые session cookies после смены пароля недействительны.
6. Static frontend открывается, но явно остаётся browser-local и не считается backend acceptance.
7. Operational backup и isolated restore rehearsal проходят по operations runbook.
