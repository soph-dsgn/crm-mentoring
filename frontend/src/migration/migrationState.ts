import type { LegacyImportIssue } from '../api/contracts'
import { ApiError } from '../api/http'

export const MAX_LEGACY_IMPORT_BYTES = 5 * 1024 * 1024
export const SERVER_CUTOVER_KEY = 'kuratorskaya-server-cutover-v1'

export type LegacyGroupReference = { id: string; name: string }
export type ConflictGroup = { code: string; entity: string; count: number }

export function legacySource(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

export function legacyGroups(source: Record<string, unknown>): LegacyGroupReference[] {
  if (!Array.isArray(source.groups)) return []
  const seen = new Set<string>()
  return source.groups.flatMap((value, index) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    const group = value as Record<string, unknown>
    if (typeof group.id !== 'string' || !group.id.trim() || seen.has(group.id)) return []
    seen.add(group.id)
    return [{ id: group.id, name: typeof group.name === 'string' && group.name.trim() ? group.name.trim() : `Группа ${index + 1}` }]
  })
}

export function requestBytes(source: Record<string, unknown>, assignments: Record<string, string>, checksum?: string): number {
  return new TextEncoder().encode(JSON.stringify({
    source,
    curator_assignments: assignments,
    ...(checksum ? { confirmation_checksum: checksum, confirm: true } : {}),
  })).byteLength
}

export function groupConflicts(issues: LegacyImportIssue[]): ConflictGroup[] {
  const grouped = new Map<string, ConflictGroup>()
  for (const issue of issues) {
    const key = `${issue.code}:${issue.entity}`
    const current = grouped.get(key)
    grouped.set(key, current ? { ...current, count: current.count + 1 } : { code: issue.code, entity: issue.entity, count: 1 })
  }
  return [...grouped.values()]
}

const conflictLabels: Record<string, string> = {
  duplicate_id: 'Повторяющиеся идентификаторы',
  duplicate_order: 'Повторяющийся порядок записей',
  orphan_reference: 'Нарушенные связи между записями',
  invalid_curator_mapping: 'Не назначен действующий куратор',
  unsupported_version: 'Неподдерживаемая версия копии',
  unsupported_field: 'Неподдерживаемые поля',
  invalid_collection: 'Некорректная коллекция записей',
  invalid_record: 'Некорректная запись',
  invalid_id: 'Некорректный идентификатор',
  invalid_order: 'Некорректный порядок',
  invalid_task_status: 'Некорректный статус задачи',
  invalid_review_status: 'Некорректный статус проверки',
  invalid_approval_status: 'Некорректный статус согласования',
  invalid_homework_status: 'Некорректный статус домашнего задания',
  invalid_group_status: 'Некорректный статус группы',
  invalid_student_stage: 'Некорректный этап ученицы',
  invalid_title: 'Отсутствует обязательное название',
  invalid_url: 'Некорректная ссылка',
  invalid_date: 'Некорректная дата',
  invalid_date_order: 'Нарушен порядок дат',
  server_data_conflict: 'На сервере уже есть рабочие данные',
}

const entityLabels: Record<string, string> = {
  source: 'файл', database: 'база данных', groups: 'группы', students: 'ученицы',
  strategies: 'стратегии', sections: 'разделы', tasks: 'задачи', meetings: 'встречи',
  homeworks: 'домашние задания', homework_items: 'снимки задач', task_materials: 'материалы задач',
  homework_item_materials: 'материалы в снимках',
}

export function conflictLabel(conflict: ConflictGroup): string {
  const label = conflictLabels[conflict.code] ?? 'Данные требуют дополнительной проверки'
  return `${label} · ${entityLabels[conflict.entity] ?? 'записи'} · ${conflict.count}`
}

export function warningLabel(value: string): string {
  if (value.includes('task history has no actor')) return 'История задач без автора будет сохранена в метаданных стратегии'
  if (value.includes('without a section')) return 'Задачи без раздела будут помещены в технический раздел'
  if (value.includes('IndexedDB knowledge data')) return 'База знаний из IndexedDB не входит в эту миграцию и требует отдельной копии'
  return 'Сервер сообщил дополнительное ограничение. Обновите приложение или обратитесь к администратору'
}

export function migrationErrorMessage(error: unknown, operation: 'read' | 'import' = 'read'): string {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить запрос. Проверьте соединение и повторите проверку'
  switch (error.code) {
    case 'connection_error': return operation === 'import'
      ? 'Связь с сервером прервалась. Результат импорта неизвестен — не повторяйте его без новой проверки'
      : 'Не удалось связаться с сервером. Данные не записывались — проверьте соединение и повторите'
    case 'payload_too_large': return 'Файл вместе с назначениями превышает допустимые 5 МиБ'
    case 'validation_changed': return 'Источник или назначения изменились. Выполните проверку заново'
    case 'import_conflict': return 'Импорт остановлен: сервер обнаружил конфликт. Выполните проверку заново'
    case 'forbidden': return 'Миграция и серверная копия доступны только владельцу'
    default: return error.status === 422 ? 'Сервер не смог проверить структуру файла' : 'Не удалось выполнить запрос. Личные записи не изменены'
  }
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export function hasServerCutover(storage: StorageLike | null = typeof localStorage === 'undefined' ? null : localStorage): boolean {
  return storage?.getItem(SERVER_CUTOVER_KEY) === 'complete'
}

export function markServerCutover(storage: StorageLike | null = typeof localStorage === 'undefined' ? null : localStorage): void {
  storage?.setItem(SERVER_CUTOVER_KEY, 'complete')
}
