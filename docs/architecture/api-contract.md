# Предварительный REST API

Контракт разделяет уже реализованные системные, auth и user-management маршруты и будущий
бизнес-API. Реализованные маршруты отмечены явно.

## Общие правила

- бизнес API размещается под `/api/v1`;
- JSON использует `snake_case`, даты — `YYYY-MM-DD`, timestamps — ISO 8601 UTC;
- списки имеют cursor pagination и стабильную сортировку;
- ошибки: `{"error":{"code":"...","message":"...","details":{}}}`;
- создание возвращает `201`, удаление обычно — `204`, optimistic conflict — `409`;
- lifecycle-команды групп и профилей возвращают `200` с обновлённым ресурсом и новой `version`,
  чтобы следующий условный запрос не требовал дополнительного чтения;
- изменяемые сущности получают `updated_at`; клиент передаёт ожидаемую версию/ETag для защиты от тихой перезаписи;
- OpenAPI генерируется FastAPI, но является результатом типизированных схем, а не заменой согласованного поведения.

## System и auth

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | liveness, реализован |
| POST | `/api/v1/auth/login` | создать серверную сессию, реализован |
| POST | `/api/v1/auth/logout` | отозвать текущую сессию, реализован |
| GET | `/api/v1/auth/me` | текущий пользователь, реализован |
| POST | `/api/v1/auth/change-password` | обязательная/обычная смена пароля, реализован |

Endpoint readiness с проверкой БД следует добавить отдельно (`/ready`), чтобы liveness не зависел от временной ошибки БД.

## User Management

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/v1/admin/curators` | owner создаёт аккаунт куратора и однократно получает временный пароль |
| GET | `/api/v1/admin/curators` | admin получает безопасный список кураторов |
| GET | `/api/v1/admin/curators/{user_id}` | owner получает безопасные данные аккаунта куратора |
| POST | `/api/v1/admin/curators/{user_id}/deactivate` | owner деактивирует куратора без назначенных групп |
| POST | `/api/v1/admin/curators/{user_id}/offboard` | owner атомарно переносит группы и деактивирует куратора |
| POST | `/api/v1/admin/curators/{user_id}/transfer-ownership` | owner передаёт полномочия активному admin |
| POST | `/api/v1/admin/students/{student_id}/account` | owner или назначенный куратор привязывает student-аккаунт |
| GET | `/api/v1/admin/students/{student_id}/account` | owner или назначенный куратор читает безопасные данные аккаунта |
| POST | `/api/v1/admin/students/{student_id}/deactivate-account` | деактивировать аккаунт без удаления профиля ученицы |
| POST | `/api/v1/admin/users/{user_id}/reset-password` | разрешённый admin сбрасывает пароль и отзывает сессии |
| POST | `/api/v1/admin/groups/{group_id}/reassign-curator` | owner назначает активного admin куратором группы |

Все изменяющие маршруты требуют authentication, same-origin и CSRF checks. Временный пароль
возвращается только после успешного commit. Обычные GET-ответы не содержат password hash,
session/CSRF tokens и временные пароли. Чужой `student_id`/`user_id` маскируется через `404`;
недостаток полномочий на доступный объект возвращает `403`; конфликты состояния — `409`.

## Groups и students CRUD

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/api/v1/groups` | видимые группы с cursor pagination / создать с self-assignment (`201`) |
| GET/PATCH | `/api/v1/groups/{group_id}` | карточка / conditional update по `expected_version` |
| POST | `/api/v1/groups/{group_id}/archive` | архивировать, сохранив `status_before_archive` (`200`) |
| POST | `/api/v1/groups/{group_id}/restore` | восстановить предыдущий lifecycle status (`200`) |
| GET/POST | `/api/v1/groups/{group_id}/students` | admin-состав / создать профиль без аккаунта (`201`) |
| GET/PATCH | `/api/v1/students/{student_id}` | профиль; student читает только себя, PATCH только admin |
| POST | `/api/v1/students/{student_id}/archive` | архивировать профиль без деактивации аккаунта (`200`) |
| POST | `/api/v1/students/{student_id}/restore` | восстановить профиль (`200`) |
| GET/POST | `/api/v1/students/{id}/meetings` | существующая история встреч |

Все реализованные изменяющие маршруты требуют cookie-сессию, same-origin и CSRF checks. Create и
Update schemas запрещают лишние поля; `curator_id`, `group_id`, `user_id`, роли и security fields
нельзя назначить через payload. PATCH не стирает отсутствующие поля, а JSON `links` объединяет
переданные ключи с существующими. Списки сортируются по стабильному `id` и используют непрозрачный
cursor. Групповой список учениц доступен только admin; student использует собственный
`GET /students/{student_id}`. В student-ответах скрыты личные заметки и внутренний curator ID.

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

