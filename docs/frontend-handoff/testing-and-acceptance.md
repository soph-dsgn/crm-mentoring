# Тестирование и production acceptance

## Уровни проверок

- **Frontend unit:** mappers, error envelope, status labels, capability selectors
- **Frontend integration:** mocked HTTP вокруг AuthProvider/screens; cookies/CSRF behavior проверяется
  через browser tests, а не подменяется unit assertion
- **Backend integration:** TestClient/real DB подтверждают RBAC, transactions и schemas; frontend не
  дублирует эти гарантии
- **Full-system E2E:** собранный frontend + FastAPI + disposable PostgreSQL, независимые sessions для
  owner/admin/student
- **Manual browser acceptance:** responsive, keyboard/focus, temporary password handling, conflict
  wording, визуальная целостность

Тесты используют синтетические identities и данные. Реальные данные учениц и production credentials
запрещены.

## Обязательные E2E journeys

1. **First owner:** secure bootstrap выполняет оператор; owner входит временным паролем, видит только
   change-password, меняет пароль и входит снова
2. **Curator onboarding:** owner создаёт curator, передаёт one-time password вне приложения; curator
   меняет пароль; обычный curator не видит owner mutations
3. **Group/student:** curator создаёт self-assigned group и Student profile; другой curator читает,
   но не изменяет; owner переназначает группу, write capability меняется после refetch
4. **Student account:** assigned curator создаёт account; student меняет password и видит только
   собственные данные
5. **Password reset:** authorized curator сбрасывает пароль своей student; прежняя session отозвана;
   чужая student возвращает safe denial
6. **Group lifecycle:** edit с version, complete/archive/restore; состав и student read сохраняются
7. **Strategy:** создать strategy, sections/tasks, reorder, status, archive; stale edit получает 409
   и не перезаписывает новое состояние
8. **AnyaApproval:** создать, отправить, вернуть, повторно отправить/approve; task не дублируется,
   study status независим, history сохраняется
9. **Homework:** draft/issue не завершают tasks; student submit; curator revision; resubmit; accept
   завершает tasks; snapshot не меняется после task edit/archive
10. **Meetings:** curator создаёт/редактирует/archive meeting; student читает историю без private notes
11. **Session expiry:** pending action получает 401, не считается сохранённым, login восстанавливает
   fresh server state
12. **Conflict:** два browser contexts редактируют ресурс; второй получает 409, refetch показывает
   новое состояние и позволяет осознанно повторить draft
13. **Cross-device:** изменения одного пользователя видны другому после refetch/reload; localStorage
   не возвращает старые business records
14. **Unauthorized:** прямые чужие IDs, student admin routes, missing CSRF и wrong origin не раскрывают
   данные и не меняют БД
15. **Migration:** owner validates synthetic v1-v3 export, подтверждает checksum, сверяет counts,
   snapshots/approvals/history; повторный import idempotent
16. **Recovery boundary:** logical export скачивается без auth secrets; UI и docs не называют его
   полным operational backup

## Acceptance по интерфейсу

- loading, empty, offline, forbidden, not-found и validation states различимы
- destructive/one-time actions имеют понятное подтверждение и pending lock
- keyboard focus возвращается после dialogs; mobile не получает horizontal overflow
- rich content и внешние URL сохраняют текущую sanitization policy
- browser console не содержит tokens, passwords, personal payload dumps или новых runtime errors
- refresh не теряет server-confirmed changes и не применяет незавершённый local draft автоматически

## Quality gates каждого PR

Минимум: затронутые tests, `npm run lint`, `npm run build`, `npm run verify:workflow`,
`git diff --check`. Перед cutover/production acceptance — полный CI-контракт и full-system E2E на
disposable PostgreSQL.

