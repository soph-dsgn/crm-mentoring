# Read-only preflight

Preflight ничего не создаёт и не перезапускает. Сохраните только несекретные результаты.

```bash
uname -a
cat /etc/os-release
docker version
docker info --format '{{json .ServerVersion}}'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
docker network ls
ss -lnt
free -h
df -h
psql --version
pg_isready
systemctl --no-pager --full status postgresql
```

Для существующего reverse proxy определите продукт и конфигурацию только read-only командами,
например `systemctl status nginx`, `nginx -T`, `caddy version` или просмотром уже известного
конфига. Не меняйте правила и не перезагружайте сервис на preflight.

До deployment оператор должен явно выбрать:

- два свободных loopback-порта для API и static frontend;
- два DNS hostname либо согласованную routing-схему;
- существующий reverse proxy и точный proxy peer;
- отдельные PostgreSQL database/role и допустимый private путь от Docker bridge к host PostgreSQL;
- каталог env-файла с правами `0600`;
- каталог backup вне Git checkout с шифрованием, retention и off-host copy;
- image tags, равные проверяемому Git commit SHA;
- окно миграции, критерии rollback и ответственного оператора.

Остановитесь, если порт, сеть, database name, proxy ownership или backup target неоднозначны. Не
используйте broad Docker cleanup, `docker compose down -v`, автоматический Alembic downgrade или
существующую database без подтверждённого владельца.
