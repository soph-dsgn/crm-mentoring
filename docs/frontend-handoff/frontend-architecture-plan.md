# План frontend integration architecture

## Минимальные границы модулей

Сохранить текущие components и добавить небольшой typed fetch layer без нового state framework:

```text
frontend/src/api/
  http.ts                 # credentials, CSRF, error envelope, cancellation
  contracts.ts            # backend snake_case wire types
  auth.ts
  users.ts
  groups.ts
  students.ts
  strategies.ts
  meetings.ts
  homeworks.ts
  legacy.ts
  mappers.ts              # только явные wire ↔ view conversions
frontend/src/auth/
  AuthProvider.tsx
  RequireSession.tsx
  ChangePasswordGate.tsx
```

Feature hooks могут жить рядом с экранами. Сначала достаточно React state/effects и существующих
patterns; добавлять query/state library следует только после доказанной необходимости.

## HTTP и session contract

1. Каждый request использует `credentials: "include"`
2. Mutations читают `kuratorskaya_csrf` из cookie непосредственно перед отправкой и добавляют
   `X-CSRF-Token`; token не сохраняется в localStorage
3. `/auth/me` запускается при bootstrap приложения. `401` означает anonymous, не retry loop
4. `must_change_password` переводит пользователя только на change-password/logout
5. Успешная смена пароля отзывает sessions: очистить auth state и запросить новый login
6. `ApiError` сохраняет HTTP status, `error.code`, safe message и `details`; raw stack/HTML не
   показывается
7. Requests отменяются через `AbortController` при unmount/смене identity

Production frontend и API должны иметь согласованные HTTPS origin/cookie settings. Нельзя строить
same-origin обход через доверие к client-provided forwarded headers.

## Типы и mapping

Wire contracts повторяют backend `snake_case` без переименования. Existing view models могут
оставаться `camelCase`; преобразование выполняется один раз в `mappers.ts`. Enums отображаются через
полные switch mappings, неизвестное значение вызывает controlled unsupported-state UI, а не
подменяется выдуманным default.

Backend timestamps остаются ISO strings на transport boundary. UI форматирует их в timezone
пользователя, но не меняет перед сравнением version/state.

## Data flow

- server — единственный источник business entities после cutover
- form draft локален до submit; saved entity заменяется response сервера
- lists используют opaque `next_cursor`; filters сбрасывают cursor
- mutation button блокирует duplicate submit, но idempotency всё равно обеспечивает backend
- после `409` refetch entity/list, показать различия или предложить повторно применить draft
- после `401` остановить pending workflow, сохранить только нечувствительный form draft в памяти и
  открыть login
- после `403/404` убрать stale action/object из UI после refetch
- offline показывается явно; server mutations не ставятся в скрытую очередь

## Authorization-aware UI

Navigation и controls вычисляются из current user и resource context:

- owner получает account administration и global mutations
- admin видит global read, а write actions только для assigned resources
- student получает собственные profile/strategy/meeting/homework views и submit actions

Это UX-фильтр, не permission enforcement. Нельзя делать optimistic privilege escalation, передавать
role/owner/curator fields или считать известный UUID доказательством доступа.

## Temporary credentials

Temporary password показывается только из непосредственного create/reset response в modal с явным
copy action. Его нельзя писать в toast history, logs, analytics, URL, AppData или persistent state.
После закрытия modal повторное получение невозможно; UI должен предупредить об этом до закрытия.

## Cutover localStorage

1. Снять пользовательский backup через существующий UI
2. Owner выполняет server validation и изучает conflicts/warnings
3. После explicit confirmation выполнить idempotent import
4. Сверить counts и выборочные связи/истории
5. Переключить business reads на API одним milestone
6. Сохранить local backup как rollback artifact; не продолжать dual-write

Knowledge IndexedDB остаётся отдельной границей и не включается в этот cutover без отдельного
решения.

