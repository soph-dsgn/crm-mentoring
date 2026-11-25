import type { ApprovalRead, StrategySectionRead, StrategyTaskRead, TaskHistoryRead } from '../api/contracts'
import { ApiError } from '../api/http'
import type { AppData, Stage, StrategySection, StrategyTask, StudyStatus } from '../types'

const transitions: Record<StudyStatus, StudyStatus[]> = {
  not_started: ['not_started','in_progress','hold'],
  in_progress: ['in_progress','hold','done'],
  hold: ['hold','in_progress','done'],
  done: ['done','in_progress'],
}

export const studyStatusOptions = (status: StudyStatus) => transitions[status]

const historyLabels: Record<string, string> = {
  task_created: 'Задача создана', task_updated: 'Данные задачи обновлены', task_reordered: 'Порядок задачи изменён',
  task_moved: 'Задача перемещена в другой раздел',
  study_status_changed: 'Статус выполнения изменён', task_archived: 'Задача перемещена в архив', task_restored: 'Задача восстановлена',
  approval_created: 'Создано согласование с Аней', approval_changed: 'Статус согласования изменён',
}

export function sectionFromApi(section: StrategySectionRead, studentId: string): StrategySection {
  return { id: section.id, studentId, title: section.title, order: section.position, createdAt: section.created_at, serverBacked: true, strategyId: section.strategy_id, updatedAt: section.updated_at, version: section.version }
}

export function historyFromApi(item: TaskHistoryRead): StrategyTask['history'][number] {
  return { at: item.created_at, label: historyLabels[item.event_type] ?? 'Задача обновлена' }
}

export function taskFromApi(task: StrategyTaskRead, studentId: string, approval?: ApprovalRead | null, stage: Stage = 'start', history: TaskHistoryRead[] = []): StrategyTask {
  const links = Object.values(task.links)
  return {
    id: task.id, studentId, title: task.title, description: task.description, stage,
    status: task.study_status === 'done' ? 'done' : task.study_status === 'not_started' ? 'backlog' : 'progress',
    studyStatus: task.study_status, sectionId: task.section_id, period: task.period_text, materials: task.materials,
    owner: 'Не назначен', dueAt: task.due_at ?? '', url: links[0] ?? '', comments: '', order: task.position,
    blocker: task.blocker, createdAt: task.created_at, updatedAt: task.updated_at, reviewStatus: task.review_status,
    approvalStatus: approval?.status ?? null, approvalType: '', approvalSentAt: approval && approval.status !== 'to_send' ? approval.created_at : '',
    approvalComment: approval?.comment ?? '', history: history.map(historyFromApi), archivedAt: task.archived_at ?? '',
    serverBacked: true, strategyId: task.strategy_id, version: task.version, approvalId: approval?.id, approvalVersion: approval?.version, serverLinks: { ...task.links },
  }
}

export function withServerStrategies(base: AppData, sections: StrategySection[], tasks: StrategyTask[]): AppData {
  const accessibleStudents = new Set(base.students.filter(student => student.serverBacked).map(student => student.id))
  const accessibleSections = sections.filter(section => accessibleStudents.has(section.studentId))
  const accessibleSectionIds = new Set(accessibleSections.map(section => section.id))
  const accessibleTasks = tasks.filter(task => accessibleStudents.has(task.studentId) && accessibleSectionIds.has(task.sectionId))
  return { ...base, sections: accessibleSections, tasks: accessibleTasks }
}

export function strategyErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить действие'
  switch (error.code) {
    case 'connection_error': return 'Не удалось подключиться к серверу'
    case 'forbidden': return 'У вас нет прав изменять эту стратегию'
    case 'approval_owner_only': return 'Решение по согласованию принимает только Аня'
    case 'approval_comment_required': return 'Напишите, что нужно поправить'
    case 'not_found': return 'Стратегия или задача больше недоступна'
    case 'section_imported': return 'Раздел связан с исходным импортом. Удаление недоступно'
    case 'section_not_empty': return 'В разделе остались задачи, включая архивные. Переместите задачи перед удалением'
    case 'position_limit': return 'Сначала обновите порядок задач в разделе назначения'
    case 'version_conflict': return 'Данные изменились в другой сессии. Мы загрузили актуальную версию — проверьте изменения и повторите действие'
    case 'homework_review_pending': return 'Статус задачи заблокирован, пока домашняя работа находится на проверке'
    case 'task_archived': return 'Сначала восстановите задачу из архива'
    case 'invalid_status_transition': return 'Этот переход статуса недоступен. Обновите стратегию и выберите допустимый статус'
    case 'invalid_approval_transition': return 'Статус согласования уже изменился. Проверьте актуальное состояние'
    case 'curator_assignment_changed': return 'Назначение куратора изменилось. Доступ и данные стратегии обновлены'
    case 'approval_exists': return 'Согласование уже создано и загружено из сервера'
    default: return error.status === 422 ? 'Проверьте заполненные поля' : 'Не удалось выполнить действие'
  }
}
