# Фактический frontend-facing API

Этот inventory сверён с FastAPI routes, Pydantic schemas и tests на commit `64b413c`. Wire format —
JSON со `snake_case`. Все `/api/v1` endpoints, кроме login, требуют server session; mutations также
требуют same-origin и `X-CSRF-Token`.

Указанные после каждой таблицы source files относятся ко всем endpoints этой таблицы; точные
response fields определяются названными Pydantic schemas, а не локальными frontend types.

## Общие правила

- session cookie: `kuratorskaya_session` (`HttpOnly`); CSRF cookie: `kuratorskaya_csrf`
- browser requests используют `credentials: "include"`; CSRF header берётся из CSRF cookie
- ошибка: `{"error":{"code": string, "message": string, "details": object}}`
- `401` — session отсутствует/истекла; `403` — действие запрещено; `404` — объект отсутствует или
  скрыт; `409` — version/state/integrity conflict; `422` — request validation
- list endpoints с pagination принимают `cursor` и `limit` (до 100) и возвращают opaque
  `next_cursor`; cursor нельзя интерпретировать на клиенте
- mutations версионируемых ресурсов передают `expected_version`; после `409` нужно refetch и
  явное решение пользователя, а не автоматическое повторение поверх новых данных
- `must_change_password=true` закрывает business API до успешного change-password

## Authentication и User Management

| Method и route | Scope | Request → response | Важное поведение / экран |
|---|---|---|---|
| `POST /api/v1/auth/login` | anonymous | `{login,password}` → `{id,login,role,is_owner,must_change_password,is_active}` | Same-origin; `401`, `429`, `422`; login screen |
| `GET /api/v1/auth/me` | session | — → current user | Session bootstrap/refresh |
| `POST /api/v1/auth/logout` | session+CSRF | — → `204` | Всегда очистить local auth state |
| `POST /api/v1/auth/change-password` | session+CSRF | `{current_password,new_password}` → `204` | Новый пароль min 12; отзывает sessions; повторный login |
| `GET /api/v1/admin/curators` | admin/owner | — → `CuratorPublicResponse[]` | Публичный список сотрудников |
| `POST /api/v1/admin/curators` | owner | `{login}` → user + `temporary_password` | `201`; показать/copy один раз |
| `GET /api/v1/admin/curators/{user_id}` | owner | — → safe user | Staff details |
| `POST /api/v1/admin/curators/{user_id}/deactivate` | owner | — → `SafeUserResponse` | Нельзя последнего owner/curator с группами |
| `POST /api/v1/admin/students/{student_id}/account` | owner/assigned admin | `{login}` → account + one-time password | `201`; Student profile уже существует |
| `GET /api/v1/admin/students/{student_id}/account` | owner/assigned admin | — → account | Пароль никогда не возвращается |
| `POST /api/v1/admin/students/{student_id}/deactivate-account` | owner/assigned admin | — → `StudentAccountResponse` | Profile/history сохраняются |
| `POST /api/v1/admin/users/{user_id}/reset-password` | owner; assigned admin для своей student | — → one-time password | Отзывает sessions, `must_change_password=true` |
| `POST /api/v1/admin/groups/{group_id}/reassign-curator` | owner | `{curator_id}` → assignment | Target — active admin |
| `POST /api/v1/admin/curators/{user_id}/offboard` | owner | `{successor_curator_id}` → result | Перенос групп и деактивация атомарны |
| `POST /api/v1/admin/curators/{user_id}/transfer-ownership` | owner | — → `SafeUserResponse` | Target — active admin; self-promotion отсутствует |

Источники: `backend/app/api/routes/auth.py`, `admin_users.py`,
`backend/app/modules/users/schemas.py`.

## Groups и Students

| Method и route | Scope | Request / query | Response и UI mapping |
|---|---|---|---|
| `GET /api/v1/groups` | admin all; student own | `lifecycle`, `curator_id`, `cursor`, `limit` | `GroupList` или student-safe `GroupStudentList` |
| `POST /api/v1/groups` | active admin/owner | `GroupCreate`; curator server-side=self | `201 GroupRead` |
| `GET /api/v1/groups/{group_id}` | admin all; student own | — | `GroupRead` или `GroupStudentRead`; чужой student получает `404` |
| `PATCH /api/v1/groups/{group_id}` | owner/assigned admin | `GroupUpdate` + `expected_version` | Edit form |
| `POST /api/v1/groups/{group_id}/archive` | owner/assigned admin | `{expected_version}` → `GroupRead` | Состав/история сохраняются |
| `POST /api/v1/groups/{group_id}/restore` | owner/assigned admin | `{expected_version}` → `GroupRead` | Восстанавливает previous lifecycle |
| `GET /api/v1/groups/{group_id}/students` | admin only | `cursor`, `limit`, `include_archived` | `StudentList`; student roster запрещён |
| `POST /api/v1/groups/{group_id}/students` | owner/assigned admin | `StudentCreate`; без `group_id/user_id` | `201 StudentRead` |
| `GET /api/v1/students/{student_id}` | admin all; student self | — | `StudentRead` или self response без private notes |
| `PATCH /api/v1/students/{student_id}` | owner/assigned admin | `StudentUpdate` + `expected_version` | Не меняет `group_id`/`user_id` |
| `POST /api/v1/students/{student_id}/archive` | owner/assigned admin | `{expected_version}` → `StudentRead` | Account и история сохраняются |
| `POST /api/v1/students/{student_id}/restore` | owner/assigned admin | `{expected_version}` → `StudentRead` | Возврат profile |

`GroupCreate`: `name`, `starts_at`, optional dates/status/notes/duration. `StudentCreate/Update`
содержат профильные поля и `links`; отсутствующие PATCH fields не стираются. Enums: group
`backlog|active|completed|archived`, student stage `start|portfolio|search`.

Источники: `backend/app/api/routes/groups.py`, `students.py`, соответствующие `schemas.py`.

## Strategies, Sections, Tasks и AnyaApproval

| Method и route | Scope | Contract | UI mapping |
|---|---|---|---|
| `GET/POST /api/v1/students/{student_id}/strategy` | read admin/self; write owner/assigned admin | create `{source_metadata}` → `StrategyRead`; одна strategy | Strategy tab |
| `GET/POST /api/v1/strategies/{strategy_id}/sections` | то же | create `{title,position}` → `SectionRead[]`/`SectionRead` | Ordered sections |
| `PATCH /api/v1/strategy-sections/{section_id}` | owner/assigned admin | `{expected_version,title}` | Rename section |
| `POST /api/v1/strategies/{strategy_id}/sections/reorder` | owner/assigned admin | `{items:[{id,expected_version,position}]}` | Полный атомарный reorder |
| `GET/POST /api/v1/strategy-sections/{section_id}/tasks` | read admin/self; write owner/assigned | create title/position + content → `TaskRead[]`/`TaskRead` | Task list/create |
| `POST /api/v1/strategy-sections/{section_id}/tasks/reorder` | owner/assigned admin | полный versioned item set → `TaskRead[]` | Reorder внутри section |
| `GET/PATCH /api/v1/strategy-tasks/{task_id}` | read admin/self; write owner/assigned | update content + `expected_version` | Task detail/edit |
| `POST /api/v1/strategy-tasks/{task_id}/study-status` | owner/assigned admin | `{expected_version,study_status}` → `TaskRead` | `not_started|in_progress|hold|done` |
| `POST /api/v1/strategy-tasks/{task_id}/archive` | owner/assigned admin | `{expected_version}` → `TaskRead` | Soft removal from active UI |
| `POST /api/v1/strategy-tasks/{task_id}/restore` | owner/assigned admin | `{expected_version}` → `TaskRead` | Return to active UI |
| `GET /api/v1/strategy-tasks/{task_id}/history` | admin/self | `cursor`, `limit` → paged history | Append-only; student не видит staff actor id |
| `GET/POST /api/v1/strategy-tasks/{task_id}/approval` | read admin/self; create owner/assigned | create `{comment?}` → `ApprovalRead` | Одна approval той же task; create `201` |
| `POST /api/v1/strategy-tasks/{task_id}/approval/transition` | owner/assigned admin | `{expected_version,status,comment?}` → `ApprovalRead` | `to_send|sent|reviewing|revision|approved` |

Task content: `title`, `description`, `materials[]`, `links{}`, `period_text`, optional `due_at`,
`position`. `review_status` (`none|pending|revision|accepted`) изменяется homework workflow, не
обычным Task PATCH. Backend не предоставляет section delete и cross-section task move.

Источники: `backend/app/api/routes/strategies.py`, `backend/app/modules/strategies/schemas.py`.

## Meetings и Homeworks

| Method и route | Scope | Contract | UI mapping |
|---|---|---|---|
| `GET/POST /api/v1/students/{student_id}/meetings` | read admin/self; write owner/assigned | list query; create date/title/summary/notes → `MeetingList|MeetingSelfList`/`MeetingRead` | Meetings history/create |
| `GET/PATCH /api/v1/meetings/{meeting_id}` | read admin/self; write owner/assigned | update + `expected_version` → `MeetingRead|MeetingSelfRead` | Student response не содержит curator notes |
| `POST /api/v1/meetings/{meeting_id}/archive` | owner/assigned admin | `{expected_version}` → `MeetingRead` | История сохраняется |
| `POST /api/v1/meetings/{meeting_id}/restore` | owner/assigned admin | `{expected_version}` → `MeetingRead` | Возврат в active list |
| `GET/POST /api/v1/strategies/{strategy_id}/homeworks` | read admin/self; write owner/assigned | list query; create `{title,description,task_ids,links,due_at}` → `HomeworkList`/`HomeworkRead` | Immutable task snapshots |
| `GET/PATCH /api/v1/homeworks/{homework_id}` | read admin/self; write owner/assigned | read/update draft fields + `expected_version` → `HomeworkRead` | Issued content не редактируется |
| `POST /api/v1/homeworks/{homework_id}/transitions` | по lifecycle | `{expected_version,status,submission_text?,submission_links?,curator_feedback?}` → `HomeworkRead` | Issue/submit/revision/accept |
| `POST /api/v1/homeworks/{homework_id}/archive` | owner/assigned admin | `{expected_version}` → `HomeworkRead` | Active review нельзя архивировать |
| `POST /api/v1/homeworks/{homework_id}/restore` | owner/assigned admin | `{expected_version}` → `HomeworkRead` | История/snapshots сохраняются |
| `GET /api/v1/homeworks/{homework_id}/history` | admin/self | cursor/limit → paged history | Student не видит staff actor id |

Homework lifecycle: `draft → issued → progress/submitted → revision → submitted → accepted`.
Student может только narrowly scoped submit/resubmit собственного ДЗ; curator выдаёт, возвращает и
принимает. `submitted` ставит tasks `in_progress/pending`, `revision` — `in_progress/revision`,
`accepted` — `done/accepted`. Два active reviews одной task запрещены.

Источники: `backend/app/api/routes/meetings.py`, `homeworks.py`, domain schemas/services.

## Legacy data, export и infrastructure

| Method и route | Scope | Contract | Назначение |
|---|---|---|---|
| `POST /api/v1/imports/legacy/validate` | owner | `{source,curator_assignments,confirmation_checksum?,confirm?}`; max 5 MiB/depth 32 | `ValidationReport`; no-write preview, `413/422` |
| `POST /api/v1/imports/legacy` | owner | тот же payload с checksum + `confirm=true` | `ImportResult`; atomic/idempotent, `201` или replay `200` |
| `GET /api/v1/exports/backup` | owner | — | Versioned logical business export, не operational DB backup |
| `GET /health` | public probe | — → `{status:"ok"}` | Backward-compatible process health alias |
| `GET /health/live` | public probe | — | Process responsiveness, без DB query |
| `GET /health/ready` | public probe | — | Bounded DB dependency check; не UI feature |

Import поддерживает AppData v1-v3, но не IndexedDB KnowledgeData. Операционные PostgreSQL backup и
restore выполняются CLI/runbook, а не browser endpoint.

Источники: `backend/app/api/routes/imports.py`, `health.py`,
`backend/app/modules/legacy_io/schemas.py`.

