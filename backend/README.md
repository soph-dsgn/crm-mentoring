# Backend «кураторской»

Минимальная основа модульного монолита на FastAPI и SQLAlchemy. На этом этапе реализованы только конфигурация приложения, подключение БД, Alembic и `GET /health`. Авторизация, доменные модели, CRUD и импорт данных намеренно отложены до согласования архитектуры из `docs/architecture`.

## Требования

- Python 3.13+
- SQLite 3 (входит в стандартную поставку CPython)

Заявленная совместимость основных зависимостей с Python 3.13 проверена по метаданным PyPI и отдельным разрешением бинарных пакетов для CPython 3.13 на Windows.

## Локальный запуск

Все команды выполняются из каталога `backend`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Для bash/zsh активация окружения выполняется командой `source .venv/bin/activate`, а файл окружения можно создать через `cp .env.example .env`.

После запуска:

- health check: `http://127.0.0.1:8000/health`
- OpenAPI: `http://127.0.0.1:8000/docs`

## Проверки

```powershell
ruff check .
ruff format --check .
pytest
alembic current
```

SQLite-файл по умолчанию создаётся как `backend/kuratorskaya.db` и игнорируется Git. Для PostgreSQL достаточно заменить `KURATORSKAYA_DATABASE_URL`; драйвер PostgreSQL будет добавлен на этапе развёртывания, когда будет выбран способ хостинга.

