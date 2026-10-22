# Backend «кураторской»

Основа модульного монолита на FastAPI и SQLAlchemy. Реализованы конфигурация приложения,
подключение БД, Alembic, `GET /health` и первые доменные модели `User`, `Group`, `Student`.
Auth API, CRUD и импорт данных намеренно не реализованы.

Первая миграция создаёт пользователей, группы и профили учеников. Роли ограничены значениями
`admin|student`; полномочия владельца задаются отдельным флагом `is_owner`. Составные внешние
ключи не позволяют назначить student-пользователя куратором или связать admin-пользователя с
профилем ученика. Связанные пользователи и группы защищены `ON DELETE RESTRICT`; для завершения
жизненного цикла предусмотрены деактивация пользователя, архивный статус группы и архивирование
профиля ученика.

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
alembic check
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
alembic check
```

SQLite-файл по умолчанию создаётся как `backend/kuratorskaya.db` и игнорируется Git. Для PostgreSQL достаточно заменить `KURATORSKAYA_DATABASE_URL`; драйвер PostgreSQL будет добавлен на этапе развёртывания, когда будет выбран способ хостинга.

