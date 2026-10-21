# Предварительный REST API

Контракт описывает направление реализации, а не существующие эндпоинты. Сейчас реализован только `GET /health` без version prefix.

## Общие правила

- бизнес API размещается под `/api/v1`;
- JSON использует `snake_case`, даты — `YYYY-MM-DD`, timestamps — ISO 8601 UTC;
- списки имеют cursor pagination и стабильную сортировку;
- ошибки: `{"error":{"code":"...","message":"...","details":{}}}`;
- создание возвращает `201`, удаление/архивация — `204`, optimistic conflict — `409`;
- изменяемые сущности получают `updated_at`; клиент передаёт ожидаемую версию/ETag для защиты от тихой перезаписи;
- OpenAPI генерируется FastAPI, но является результатом типизированных схем, а не заменой согласованного поведения.

## System и auth

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | liveness, реализован |
| POST | `/api/v1/auth/login` | создать серверную сессию |
| POST | `/api/v1/auth/logout` | отозвать текущую сессию |
| GET | `/api/v1/auth/me` | текущий пользователь и capabilities |
| POST | `/api/v1/auth/change-password` | обязательная/обычная смена пароля |

Endpoint readiness с проверкой БД следует добавить отдельно (`/ready`), чтобы liveness не зависел от временной ошибки БД.

## Users, groups, students

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/api/v1/users` | список/ручное создание аккаунта (owner или согласованное право) |
| POST | `/api/v1/users/{id}/temporary-password` | сброс и одноразовая выдача временного пароля |
| GET/POST | `/api/v1/groups` | видимые группы / создать и назначить создателя |
| GET/PATCH | `/api/v1/groups/{id}` | карточка / изменение с object ACL |
| PUT | `/api/v1/groups/{id}/curator` | переназначить единственного куратора (предлагается owner-only) |
| GET/POST | `/api/v1/groups/{id}/students` | состав / создать ученика в этой группе |
| GET/PATCH | `/api/v1/students/{id}` | профиль; student видит только себя |
| GET/POST | `/api/v1/students/{id}/meetings` | существующая история встреч |

## Strategies и homeworks

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/v1/students/{id}/strategy` | единственная стратегия ученика |
| POST | `/api/v1/students/{id}/strategy` | создать стратегию ученика |
| POST/PATCH | `/api/v1/strategies/{id}/sections` | добавить / изменить порядок разделов |
| POST | `/api/v1/strategies/{id}/tasks` | создать задачу |
| GET/PATCH | `/api/v1/tasks/{id}` | читать / редактировать задачу |
| POST | `/api/v1/tasks/{id}/status-transitions` | валидируемый переход статуса |
| PUT | `/api/v1/tasks/{id}/anya-approval` | изменить отдельный цикл согласования |
| GET/POST | `/api/v1/strategies/{id}/homeworks` | история / черновик из выбранных задач |
| GET/PATCH | `/api/v1/homeworks/{id}` | карточка / допустимые поля текущего состояния |
| POST | `/api/v1/homeworks/{id}/transitions` | issue, submit, return, accept |

Переходы оформляются командами, а не произвольным PATCH статуса: сервис должен атомарно обновить Homework, связанные задачи, историю и progress. Ответ включает обновлённые ресурсы либо их версии.

## Импорт, экспорт и файлы

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/v1/imports/legacy/validate` | проверить JSON без записи, вернуть counts/conflicts |
| POST | `/api/v1/imports/legacy` | идемпотентный подтверждённый импорт |
| GET | `/api/v1/exports/backup` | полный переносимый JSON-бэкап |
| POST | `/api/v1/files` | будущая загрузка с лимитами MIME/размера |
| GET | `/api/v1/files/{id}` | авторизованная выдача файла |

Загрузку файлов и submission API проектируем, но не реализуем в текущем этапе. Исходные PDF должны импортироваться административным job/CLI с отчётом, а не публичным пользовательским endpoint.

