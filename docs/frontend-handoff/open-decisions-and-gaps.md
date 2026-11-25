# Открытые решения и пробелы

## Релизная ветка

Серверные перенос ученицы, удаление пустого раздела и перемещение задач подключены к React. Кураторский процесс поддерживает сдачу ДЗ с атрибуцией действующего аккаунта. База знаний использует серверную активацию и явный импорт. Для локальной проверки используйте [чеклист приёмки](../release/FINAL_ACCEPTANCE.md).

Разделы ниже фиксируют историческое состояние до финальной интеграции.

## Backend/API gaps

| Gap | Статус | Безопасное решение сейчас |
|---|---|---|
| Перенос Student между groups | BLOCKED BY BACKEND | Скрыть local action; спроектировать отдельную атомарную команду |
| Delete/archive StrategySection | BLOCKED BY BACKEND | Не вызывать локальное delete после cutover |
| Перенос Task между sections | BLOCKED BY BACKEND | Разрешать reorder только внутри section |
| Knowledge records/sync | IMPLEMENTED | Server state authoritative; IndexedDB остаётся отдельной неизменяемой локальной копией |
| File uploads | MISSING | Хранить только поддерживаемые links/text; отдельный будущий scope |
| Student product shell | MISSING frontend | Создать после auth и core domain integration |

## Product decisions

1. Нужен ли перенос ученицы между группами и кто имеет право его выполнять
2. Архивируется ли section целиком, запрещается ли удаление при истории, либо действие убирается
3. Нужен ли cross-section task move и как сохраняются position/version/history
4. Какие поля student-facing profile/strategy показываются помимо уже безопасных backend responses
5. Как оператор передаёт temporary credentials пользователю; автоматическая email/Telegram отправка
   в текущий scope не входит
6. Допускается ли ограниченный offline read cache; скрытая очередь offline mutations не рекомендуется
7. Когда прекращается localStorage source-of-truth и как долго хранится rollback backup

## Knowledge Base

Исходная KnowledgeData v1 по-прежнему хранится в IndexedDB `crm-mentoring-knowledge`, documents
store, key `content-v1`, и не изменяется при server cutover. Рабочим источником после явной
активации служит server library state. Владелец отдельно проверяет initial import и checksum;
после активации действующие кураторы могут импортировать дополнительные DOCX/HTML/Markdown/JSON.
Эти данные не входят в AppData v1-v3 и legacy backend import.

### Option A — временно browser-local

Подходит для MVP, только если команда принимает ограничения: один browser/profile, нет RBAC,
cross-device sync, общей истории или server backup. UI и документация должны явно говорить «локально
на этом устройстве», а Knowledge export выполняется отдельно.

### Option B — отдельный Knowledge API

Нужны отдельные models/API/RBAC, import mapping, sanitizer boundary, versioning и conflict strategy.
Это отдельный backend+frontend проект; Knowledge нельзя помещать в Task/Strategy/Homework поля.

### Принятое решение

Реализована Option B: общая server-backed библиотека с личным избранным. Browser-local KnowledgeData
сохраняется только как rollback/source backup и никогда не импортируется автоматически.

## Deployment boundary

Deployment package и production-readiness backend подготовлены, но пользовательская React↔API
интеграция отсутствует. Production rollout frontend возможен только после auth/cutover milestones,
проверки hostname/origin/cookie contract и операторского плана backup/rollback. Юрий выполняет
инфраструктурные действия; frontend PR не меняет production самостоятельно.

