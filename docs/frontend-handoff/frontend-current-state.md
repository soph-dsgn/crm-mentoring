# Текущее состояние frontend

## Что уже работает локально

| Возможность | Статус | Реализация сейчас |
|---|---|---|
| Основная CRM-навигация и responsive UI | IMPLEMENTED | React components и CSS |
| Группы, ученицы, стратегии, задачи | PARTIALLY IMPLEMENTED | CRUD только в `AppData` |
| Встречи, ДЗ, согласования с Аней | PARTIALLY IMPLEMENTED | Локальные workflow helpers |
| Backup AppData v1-v3 | IMPLEMENTED | JSON import/export и normalization |
| Authentication/session | MISSING | Нет вызовов `/api/v1/auth/*` |
| Server synchronization | MISSING | В `frontend/src` нет business API client |
| Owner/user administration | MISSING | Нет экранов управления аккаунтами |
| Student-specific experience | MISSING | Текущие экраны ориентированы на куратора |
| Knowledge Base sync | BLOCKED BY BACKEND | Только IndexedDB, Knowledge API отсутствует |

## App state и persistence

`App.tsx` держит весь `AppData`, навигацию и mutation callbacks. `data.ts` читает и сохраняет ключ
`crm-mentoring-v1` в localStorage. Текущая schema version — 3; `normalizeData()` поддерживает
документированные экспорты v1-v3. Импортированный backup и raw localStorage не следует считать
одинаковыми форматами без normalization.

Основные локальные сущности: groups, students, strategy sections/tasks, meetings и homeworks.
Frontend использует camelCase и несколько legacy status values; backend wire contract использует
snake_case и канонические enums. Нужны явные mappers, а не изменение сохранённых данных на месте.

`types.ts` фиксирует текущие модели:

- `Group`: lifecycle/dates/notes; curator relation в local model отсутствует
- `Student`: `groupId`, profile fields и фиксированный набор links
- `StrategySection`: `studentId`, title, numeric `order`
- `StrategyTask`: local `status` (`backlog|progress|done`) рядом с каноническими `studyStatus`,
  `reviewStatus`, approval fields, materials/history и `sectionId`
- `Meeting`: student/date/title/summary без backend version/private notes
- `Homework`: student, text/items, lifecycle, submission/review timestamps and comment
- `AppData`: version 3 и массивы этих сущностей

Backend добавляет отдельные stable relations, versions, histories, archive timestamps и безопасные
role-specific responses. Local `Owner = Не назначен|Софья|Аня` — presentation legacy field, не
server identity.

## Экраны и компоненты

- `Overview` — группы, встречи и задачи внимания
- `Groups` и profile views — состав группы и профиль ученицы
- `StrategyPlan`, `TaskCard`, `TaskDetail`, `TaskForm` — разделы/задачи стратегии
- `AnyaPage` — отдельная очередь согласований той же `StrategyTask`
- `HomeworkPage` — формирование, выдача и проверка ДЗ
- meetings views — текущая встреча и история
- prompts/textbook/knowledge — локальные материалы и пользовательские документы
- общие dialogs обеспечивают focus trap, возврат фокуса и pending states

FlowBackground — один декоративный WebGL2 canvas с CSS fallback, reduced-motion, visibility/
intersection pause, 30 FPS cap, DPR и framebuffer limits. Он остаётся presentation-only.

## Безопасность отображения

Импортированный rich content очищается DOMPurify. Внешние URL проходят allowlist безопасных
протоколов; ссылки с `target="_blank"` получают `noopener noreferrer`. Эти меры нужно сохранить при
переходе на API: серверные строки также считаются недоверенным содержимым.

## Локальная логика, которую заменяет API

- создание/редактирование/архивирование domain entities
- status transitions, reorder и history
- проверка прав и доступности объектов
- выдача/проверка ДЗ и прогресс задач
- создание аккаунтов, reset temporary password
- legacy validation/import и business-data export
- multi-user consistency и conflict detection

React сохраняет presentation state: выбранные вкладки, открытые dialogs, фильтры, draft формы,
layout/motion, форматирование и понятные подтверждения действий.

## Несовпадения, которые нельзя переносить напрямую

- локальное физическое удаление group/student/meeting заменяется серверным archive/restore
- обычный Student PATCH не переносит ученицу между группами
- backend не предоставляет delete/archive для `StrategySection`
- backend reorder задачи работает внутри section и не переносит её между sections
- frontend-подпись owner не является серверной identity или permission
- KnowledgeData не входит в AppData и legacy business import

Эти случаи требуют продуктового решения или отдельного backend-контракта; frontend не должен
обходить их цепочкой несогласованных запросов.

