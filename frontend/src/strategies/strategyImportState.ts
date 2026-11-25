import type { StrategyImportApply, StrategyImportDraft, StrategyImportProfile } from '../api/contracts'
import { ApiError } from '../api/http'
import { STUDY_STATUS } from '../data'
import type { Student, StudyStatus } from '../types'

export const MAX_STRATEGY_PDF_BYTES = 10 * 1024 * 1024
export type ProfileField = 'point_a' | 'point_b' | 'telegram'
export type ProfileSelection = Record<ProfileField, boolean>

export const profileFieldLabels: Record<ProfileField, string> = { point_a: 'Точка А', point_b: 'Точка Б', telegram: 'Telegram' }

const warningLabels: Record<string, string> = {
  status_missing: 'Без статуса в Notion — будут отмечены как «Не начато»',
  orphan_row: 'Фрагмент текста вне задач пропущен',
  section_missing: 'Задачи до первого заголовка попадут в раздел «Вводная часть»',
  title_truncated: 'Слишком длинное название сокращено до 255 символов',
  text_truncated: 'Слишком длинный текст сокращён',
}

export function importWarningLabel(code: string): string {
  return warningLabels[code] ?? 'Часть данных требует проверки'
}

export function currentProfileValue(student: Student, field: ProfileField): string {
  if (field === 'point_a') return student.pointA
  if (field === 'point_b') return student.pointB
  return student.links.telegram ?? ''
}

// Import fills empty profile fields by default and never replaces curator notes silently.
export function defaultProfileSelection(student: Student, profile: StrategyImportProfile): ProfileSelection {
  const fields: ProfileField[] = ['point_a', 'point_b', 'telegram']
  return Object.fromEntries(fields.map(field => [field, Boolean(profile[field]) && !currentProfileValue(student, field).trim()])) as ProfileSelection
}

export function statusCounts(draft: StrategyImportDraft): Array<[StudyStatus, string, number]> {
  const counts: Record<StudyStatus, number> = { done: 0, in_progress: 0, hold: 0, not_started: 0 }
  for (const section of draft.sections) for (const task of section.tasks) counts[task.study_status] += 1
  return (Object.keys(STUDY_STATUS) as StudyStatus[]).filter(status => counts[status]).map(status => [status, STUDY_STATUS[status], counts[status]])
}

export function countLabel(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10, mod100 = count % 100
  const form = mod10 === 1 && mod100 !== 11 ? one : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many
  return `${count} ${form}`
}

export function taskTotal(draft: StrategyImportDraft): number {
  return draft.sections.reduce((sum, section) => sum + section.tasks.length, 0)
}

// The PDF title is "Имя | Стратегия действий"; a different name usually means a wrong file.
export function sourceNameMismatch(draft: StrategyImportDraft, student: Student): string | null {
  const sourceName = draft.source_title.split('|')[0]?.trim() ?? ''
  if (!sourceName) return null
  const normalize = (value: string) => value.toLocaleLowerCase('ru').replace(/ё/g, 'е')
  const studentWords = normalize(student.name).split(/\s+/).filter(Boolean)
  return studentWords.some(word => normalize(sourceName).includes(word)) ? null : sourceName
}

export function buildImportPayload(draft: StrategyImportDraft, student: Student, selection: ProfileSelection, fileName: string): StrategyImportApply {
  const profile: StrategyImportProfile = {}
  for (const field of Object.keys(selection) as ProfileField[]) if (selection[field] && draft.profile[field]) profile[field] = draft.profile[field]
  return {
    expected_version: student.version ?? 1,
    source: { file_name: fileName.slice(0, 255), title: draft.source_title.slice(0, 255), sha256: draft.sha256 },
    profile,
    sections: draft.sections,
  }
}

export function strategyImportErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось импортировать стратегию. Попробуйте ещё раз'
  switch (error.code) {
    case 'connection_error': return 'Нет соединения с сервером. Проверьте интернет и повторите попытку'
    case 'unsupported_file': return 'Выберите PDF, экспортированный из Notion'
    case 'unreadable_pdf': return 'Не удалось прочитать PDF. Экспортируйте страницу из Notion заново'
    case 'too_many_pages': return 'В файле больше 80 страниц. Разделите стратегию или уберите лишние вложения'
    case 'payload_too_large': return 'Файл больше 10 МБ. Экспортируйте страницу без вложенных страниц'
    case 'no_strategy_found': return 'В файле не найдены таблицы стратегии с колонками «Этап» и «Статус»'
    case 'strategy_not_empty': return 'У ученицы уже есть разделы стратегии. Импорт доступен только в пустую стратегию'
    case 'version_conflict': return 'Профиль ученицы изменился в другой сессии. Загрузите файл заново'
    case 'curator_assignment_changed': return 'Назначение куратора изменилось. Обновите страницу'
    case 'forbidden': return 'У вас нет прав изменять эту ученицу'
    case 'not_found': return 'Ученица больше недоступна'
    case 'validation_error': return 'Данные из файла не прошли проверку. Проверьте файл и повторите'
    default: return 'Сервер не смог выполнить импорт. Попробуйте ещё раз'
  }
}
