import type { CurrentUser, KnowledgeDocumentSummary, KnowledgeImportRequest, KnowledgeKind } from '../api/contracts'
import { ApiError } from '../api/http'
import type { KnowledgeData, KnowledgeRecord } from '../knowledge'

export const MAX_KNOWLEDGE_IMPORT_BYTES = 5 * 1024 * 1024

type AccessUser = Pick<CurrentUser, 'role' | 'is_owner' | 'is_active' | 'must_change_password'>

export function canUseKnowledge(user: AccessUser): boolean {
  return user.role === 'admin' && user.is_active && !user.must_change_password
}

export function canManageInitialMigration(user: AccessUser): boolean {
  return canUseKnowledge(user) && user.is_owner
}

export function knowledgeDataSource(data: KnowledgeData): Record<string, unknown> {
  return structuredClone(data) as unknown as Record<string, unknown>
}

export function parsedDocumentsSource(records: KnowledgeRecord[], kind: KnowledgeKind, format: 'docx' | 'html' | 'markdown'): Record<string, unknown> {
  return {
    version: 1,
    documents: records.map(record => ({ ...record, kind, format })),
    importedAt: new Date().toISOString(),
  }
}

export function importRequestBytes(request: KnowledgeImportRequest): number {
  return new TextEncoder().encode(JSON.stringify(request)).byteLength
}

export function summaryFromDocument(document: import('../api/contracts').KnowledgeDocumentRead): KnowledgeDocumentSummary {
  return {
    id: document.id,
    kind: document.kind,
    title: document.title,
    category: document.category,
    excerpt: document.plain_text.slice(0, 240),
    position: document.position,
    archived_at: document.archived_at,
    updated_at: document.updated_at,
    version: document.version,
    is_favorite: document.is_favorite,
  }
}

export function knowledgeErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить запрос. Проверьте соединение и повторите'
  switch (error.code) {
    case 'connection_error': return 'Не удалось связаться с сервером. Проверьте соединение и повторите'
    case 'version_conflict': return 'Материал изменён в другой сессии. Обновите его и повторите правку'
    case 'knowledge_library_pending': return 'Серверная база знаний ещё не активирована владельцем'
    case 'forbidden': return 'У вашей учётной записи нет доступа к базе знаний'
    case 'payload_too_large': return 'Данные превышают допустимый размер'
    case 'not_found': return 'Материал больше недоступен. Обновите список'
    default: return error.status === 422 ? 'Проверьте заполнение полей' : 'Не удалось выполнить запрос. Данные не изменены'
  }
}

export function knowledgeImportErrorMessage(error: unknown, operation: 'validate' | 'import' = 'validate'): string {
  if (!(error instanceof ApiError)) return 'Не удалось связаться с сервером. Локальная копия не изменена'
  switch (error.code) {
    case 'connection_error': return operation === 'import'
      ? 'Связь прервалась. Результат импорта неизвестен — не повторяйте его без новой проверки'
      : 'Не удалось выполнить проверку. Данные на сервер не записывались'
    case 'payload_too_large': return 'Импорт превышает допустимые 5 МиБ'
    case 'validation_changed': return 'Источник или состояние сервера изменились. Выполните проверку заново'
    case 'import_conflict': return 'Импорт остановлен из-за параллельных изменений. Выполните проверку заново'
    case 'knowledge_library_active': return 'База знаний уже активирована. Обновите страницу'
    case 'knowledge_library_pending': return 'Сначала владелец должен активировать серверную базу знаний'
    case 'forbidden': return 'Это действие недоступно вашей учётной записи'
    default: return error.status === 422 ? 'Сервер не смог проверить структуру данных' : 'Импорт не выполнен. Локальная копия не изменена'
  }
}
