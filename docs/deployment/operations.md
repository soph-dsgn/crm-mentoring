# Operations runbook

## Upgrade

1. Зафиксировать текущий image tag, Alembic revision, health и backup checksum.
2. Собрать новый immutable image tag из проверенного commit.
3. Создать operational backup и проверить `pg_restore --list`.
4. Прочитать новые migration upgrade/downgrade; определить совместимость старого image с новой
   schema. Не считать downgrade безопасным автоматически.
5. Выполнить `alembic upgrade head` одноразовым контейнером.
6. Создать новый application container с временным именем/loopback-портом и проверить readiness.
7. После подтверждения переключить только CRM upstream в reverse proxy.
8. Сохранить старый image/container до окончания acceptance window.

Если migration несовместима со старым image, application rollback требует согласованного restore
в новую database из pre-migration backup. Не выполняйте schema downgrade или restore поверх
production автоматически.

## Operational backup

Backup-каталог находится вне Git и image, имеет ограниченные права, шифрование at rest, retention
и off-host copy. Команда не перезаписывает существующий archive:

```bash
docker run --rm \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --env-file /srv/kuratorskaya/config/backend.env \
  --mount type=bind,src=/srv/kuratorskaya/backups,dst=/backups \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}" \
  python -m app.cli.postgres_backup backup \
  --output "/backups/kuratorskaya-<UTC_TIMESTAMP>.dump" \
  --confirm-database '<CRM_DB_NAME>'
```

Сохраните `.dump` и `.metadata.json` вместе. Success означает checksum и readability check, но не
заменяет restore rehearsal. Не удаляйте последний проверенный backup при создании нового.

## Isolated restore verification

DBA создаёт отдельную пустую database с суффиксом `_restore`, не production database. Создайте
отдельный restricted env-файл с `KURATORSKAYA_ENVIRONMENT=test` и
`KURATORSKAYA_RESTORE_DATABASE_URL`; не помещайте credentials в CLI arguments.

```bash
docker run --rm \
  --network kuratorskaya-net \
  --add-host host.docker.internal:host-gateway \
  --env-file /srv/kuratorskaya/config/restore.env \
  --mount type=bind,src=/srv/kuratorskaya/backups,dst=/backups,readonly \
  "kuratorskaya-backend:${CRM_IMAGE_TAG}" \
  python -m app.cli.postgres_backup restore \
  --archive "/backups/<BACKUP>.dump" \
  --confirm-target-database '<CRM_DB_NAME_restore>' \
  --confirm-destructive-restore
```

Restore использует одну transaction, требует пустой target и сверяет Alembic revision. Удаление
disposable database — отдельное подтверждённое действие DBA после проверки.

## Incident diagnosis

Сначала собирайте минимальные несекретные факты:

```bash
docker inspect --format '{{.State.Status}} {{.State.Health.Status}} {{.State.ExitCode}}' kuratorskaya-backend
docker logs --tail 200 kuratorskaya-backend
curl --fail --silent --show-error "http://127.0.0.1:${CRM_API_PORT}/health/live"
curl --fail --silent --show-error "http://127.0.0.1:${CRM_API_PORT}/health/ready"
pg_isready
```

Не публикуйте env, database URL, cookies, request bodies или полный `docker inspect` в тикеты.
Liveness failure указывает на process/container. Liveness `200` и readiness `503` указывают на
database connectivity/pool/migration path; health endpoint сам migrations не запускает.

## Application rollback

- Неизменная schema: вернуть previous image tag, запустить на временном порту, проверить readiness,
  затем переключить только CRM proxy upstream.
- Изменённая совместимая schema: тот же порядок после подтверждения совместимости.
- Несовместимая schema/data corruption: остановить writes, сохранить evidence, создать новую
  database и восстановить подтверждённый backup. Production target не перезаписывать.

Никогда не применять `docker compose down -v`, broad `docker system prune`, uncontrolled Alembic
downgrade или delete PostgreSQL volume/database.

## Disaster recovery prerequisites

- документированные RPO/RTO и ответственный оператор;
- encrypted off-host backup и проверенные checksums;
- регулярный isolated restore rehearsal;
- сохранённые image tags/digests и deployment env key inventory без secret values;
- процедура DNS/proxy switch и возврата;
- доступ к PostgreSQL 18 client того же major;
- отдельная процедура миграции browser-local frontend/IndexedDB данных.
