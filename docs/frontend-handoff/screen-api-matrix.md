# Матрица экранов и API

`Current state` описывает текущий React, а не наличие backend capability.

| Screen / action | Role | API | Current state | Missing work / acceptance |
|---|---|---|---|---|
| Login, session restore, logout | all | `/auth/login`, `/auth/me`, `/auth/logout` | MISSING | Credentialed client, 401 handling, reload restores session |
| Forced password change | all accounts with flag | `/auth/change-password` | MISSING | Gate all business screens; logout/re-login after success |
| Overview lists | admin/owner | groups, meetings, tasks/homeworks | PARTIALLY IMPLEMENTED locally | Server queries, loading/error/empty, no local mutations |
| Group list/filter/create | admin/owner | `GET/POST /groups` | PARTIALLY IMPLEMENTED locally | Cursor paging; server assigns actor as curator |
| Group details/edit/archive | owner/assigned admin; student read own | group routes | PARTIALLY IMPLEMENTED locally | Versioned edit, 409 recovery, archive instead of delete |
| Reassign group | owner | admin reassign route | MISSING | Owner-only UI, active-admin target, refresh affected views |
| Group roster | admin/owner | `/groups/{id}/students` | PARTIALLY IMPLEMENTED locally | Student must never receive group roster |
| Student profile create/edit/archive | owner/assigned admin | student routes | PARTIALLY IMPLEMENTED locally | No `group_id/user_id` mass assignment; archive not delete |
| Student moves group | owner/admin TBD | none | BLOCKED BY BACKEND | Product/API decision; do not emulate with delete/create |
| Curator list/create/deactivate/offboard | owner; admin list only | admin curator routes | MISSING | One-time password dialog; owner safeguards |
| Student account/create/deactivate/reset | owner/assigned admin | admin student/user routes | MISSING | Scope-aware actions; copy password once; never persist it |
| Ownership transfer | owner | transfer-ownership route | MISSING | Explicit confirmation and current-user refresh |
| Strategy read/create | admin/self; assigned write | student strategy route | PARTIALLY IMPLEMENTED locally | One strategy, source metadata, role-aware read-only mode |
| Sections create/rename/reorder | assigned admin/owner | section routes | PARTIALLY IMPLEMENTED locally | Atomic full reorder with all versions |
| Section delete | curator | none | BLOCKED BY BACKEND | Decide archive/delete semantics before retaining local action |
| Task create/edit/status/archive | assigned admin/owner | task routes | PARTIALLY IMPLEMENTED locally | Separate content/status commands; review lock errors |
| Move task within section | assigned admin/owner | task reorder route | PARTIALLY IMPLEMENTED locally | Full version set; rollback UI on 409 |
| Move task across sections | curator | none | BLOCKED BY BACKEND | Product/API decision; current local action cannot be mapped |
| Task history | admin/self | task history route | MISSING server UI | Cursor paging; hide unavailable actor details |
| Anya queue/create/transition/recall | assigned admin/owner | approval routes | PARTIALLY IMPLEMENTED locally | Same task identity, independent approval/study status |
| Meeting list/create/edit/archive | admin/self; assigned write | meeting routes | PARTIALLY IMPLEMENTED locally | Student-safe response; history survives archive |
| Homework draft and issue | assigned admin/owner | homework routes/transitions | PARTIALLY IMPLEMENTED locally | Use immutable snapshots; issue never completes task |
| Student homework list/read/submit | student self | homework routes/transitions | MISSING student shell | Own only; submit/resubmit fields only |
| Curator review/revision/acceptance | assigned admin/owner | homework transitions | PARTIALLY IMPLEMENTED locally | Task review/progress follow server result; no client recompute |
| Prompts/favorites/textbook | curator/student TBD | no Knowledge API | IMPLEMENTED browser-local | Keep explicitly local or approve separate backend project |
| AppData validate/import | owner | legacy import routes | MISSING UI | Preview counts/conflicts, explicit checksum confirmation |
| Logical business export | owner | `/exports/backup` | MISSING UI | Secure download; describe exclusions and Knowledge gap |
| Session expiry on any screen | all | response `401` | MISSING | Stop mutations, preserve safe drafts, redirect to login |
| Concurrent edit | writers | response `409` | MISSING | Refetch, explain conflict, never blind retry |
| Health/readiness | operator | `/health/live`, `/health/ready` | infrastructure only | Not a user-facing dashboard |

## Cross-screen acceptance

- navigation is derived from authenticated capability, but server response remains authoritative
- student UI never renders curator-only notes/actions or group membership lists
- a successful mutation reconciles every view of the same entity; no local duplicate task/approval
- temporary passwords live only in the immediate success dialog and clipboard action
- refresh/cross-device reads server state, not stale localStorage
- offline state is explicit and read-only unless a future synchronization contract is approved

