# Production readiness

Документ описывает application contract. Интеграция с существующим сервером, reverse proxy,
firewall, секретами и backup описана в [`docs/deployment/`](../deployment/README.md).

## Первый запуск

1. Создать отдельные PostgreSQL database и role с правами только на application database/schema.
2. Передать настройки через защищённое окружение, не через Git или командную строку:

   ```text
   KURATORSKAYA_ENVIRONMENT=production
   KURATORSKAYA_DEBUG=false
   KURATORSKAYA_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
   KURATORSKAYA_PERMITTED_HOSTS=["api.example.com"]
   KURATORSKAYA_FRONTEND_ORIGINS=["https://app.example.com"]
   KURATORSKAYA_TRUSTED_PROXY_IPS=[]
   ```

3. Выполнить `alembic upgrade head`, `alembic current` и `alembic check`.
4. В интерактивном терминале создать первого owner. URL берётся только из
   `KURATORSKAYA_DATABASE_URL`, а имя БД подтверждается отдельно:

   ```bash
   python -m app.cli.bootstrap_owner \
     --login OWNER_LOGIN \
     --confirm-database DATABASE \
     --confirm-first-owner
   ```

   Временный пароль показывается один раз после успешного commit. Его нельзя перенаправлять в файл,
   CI log или deployment log.
5. Запустить FastAPI. Безопасный container baseline использует `--no-proxy-headers`, а reverse
   proxy очищает `Forwarded`/`X-Forwarded-*`. Не включать proxy-header processing без отдельной
   проверки прямого peer IP и согласованного application/Uvicorn trust contract.
6. Проверить `/health/live` и `/health/ready`.
7. Войти первым owner и немедленно сменить временный пароль. До смены бизнес-операции запрещены.

Production startup отклоняет SQLite, debug, пустые или wildcard hosts/origins и HTTP frontend
origins. `/docs`, `/redoc` и `/openapi.json` в production отключены.

## Health probes

- `/health/live` проверяет только способность процесса отвечать. Его используют для restart policy.
- `/health/ready` выполняет один `SELECT 1` через ограниченный pool. При недоступной БД возвращает
  безопасный `503` без URL, credentials и текста исключения. Его используют для допуска трафика.
- `/health` сохранён как совместимый alias liveness.

Health endpoints не создают schema, не запускают Alembic и не выполняют business queries.

## Operational PostgreSQL backup

Operational backup включает всю application database: пользователей, password hashes, audit,
legacy mappings, schema и business data. Это чувствительный архив; шифрование at rest и off-host
copy обязательны на уровне эксплуатации. Рекомендуется хранить несколько поколений и регулярно
проверять restore, не удаляя предыдущий подтверждённый backup до проверки нового.

На хосте должны быть PostgreSQL 18 `pg_dump` и `pg_restore`. Credentials читаются из
`KURATORSKAYA_DATABASE_URL` и передаются subprocess только через `PG*` environment:

```bash
python -m app.cli.postgres_backup backup \
  --output /secure/backups/kuratorskaya-YYYYMMDD.dump \
  --confirm-database DATABASE
```

Команда отказывается перезаписывать файлы, создаёт custom archive и metadata JSON, ограничивает
права файла где это поддерживается, проверяет `pg_restore --list` и записывает SHA-256,
application version, Alembic revision и версию `pg_dump`. Backup считается успешным только после
атомарной установки archive и metadata. Каталог backup не должен находиться в Git checkout.

## Restore verification

Прямой restore в production запрещён. Проверка выполняется только в заранее созданную пустую
disposable БД с суффиксом `_restore` или `_test`. В отдельном operator shell задаются:

```text
KURATORSKAYA_ENVIRONMENT=test
KURATORSKAYA_RESTORE_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE_restore
```

После этого:

```bash
python -m app.cli.postgres_backup restore \
  --archive /secure/backups/kuratorskaya-YYYYMMDD.dump \
  --confirm-target-database DATABASE_restore \
  --confirm-destructive-restore
```

Перед restore проверяются metadata, checksum, читаемость архива и пустота target. `pg_restore`
выполняется с `--single-transaction`; ошибка не должна оставлять частичную схему. После операции
Alembic revision сверяется с metadata. Переключение production на восстановленную БД, RPO/RTO,
удаление старых архивов и аварийный rollback входят в отдельный Deployment Handoff.

## Ограничения

- Application-level backup не шифрует архив самостоятельно; нужен защищённый filesystem или
  внешний encryption/backup layer.
- App не мигрирует schema автоматически при startup и не создаёт базу или role.
- Per-request timeout задаётся reverse proxy/ASGI deployment contract; database connect и pool
  wait ограничены application settings.
- SQLite поддерживается для разработки и тестов, но запрещён для production.
