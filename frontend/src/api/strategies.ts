import { apiRequest } from './http'
import type { ApprovalRead, ReorderItem, StrategyImportApply, StrategyImportDraft, StrategyImportResult, StrategyRead, StrategySectionRead, StrategyTaskRead, StrategyTaskUpdate, StrategyTaskWrite, TaskHistoryList } from './contracts'

const encoded = (value: string) => encodeURIComponent(value)

export const strategiesApi = {
  getForStudent(studentId: string, signal?: AbortSignal) {
    return apiRequest<StrategyRead>(`/api/v1/students/${encoded(studentId)}/strategy`, { signal })
  },
  createForStudent(studentId: string, signal?: AbortSignal) {
    return apiRequest<StrategyRead>(`/api/v1/students/${encoded(studentId)}/strategy`, { method: 'POST', body: {}, signal })
  },
  previewImport(studentId: string, file: Blob, signal?: AbortSignal) {
    return apiRequest<StrategyImportDraft>(`/api/v1/students/${encoded(studentId)}/strategy-import/preview`, { method: 'POST', body: file, headers: { 'Content-Type': 'application/pdf' }, signal })
  },
  applyImport(studentId: string, payload: StrategyImportApply, signal?: AbortSignal) {
    return apiRequest<StrategyImportResult>(`/api/v1/students/${encoded(studentId)}/strategy-import`, { method: 'POST', body: payload, signal })
  },
  listSections(strategyId: string, signal?: AbortSignal) {
    return apiRequest<StrategySectionRead[]>(`/api/v1/strategies/${encoded(strategyId)}/sections`, { signal })
  },
  createSection(strategyId: string, title: string, position: number, signal?: AbortSignal) {
    return apiRequest<StrategySectionRead>(`/api/v1/strategies/${encoded(strategyId)}/sections`, { method: 'POST', body: { title, position }, signal })
  },
  updateSection(sectionId: string, expectedVersion: number, title: string, signal?: AbortSignal) {
    return apiRequest<StrategySectionRead>(`/api/v1/strategy-sections/${encoded(sectionId)}`, { method: 'PATCH', body: { expected_version: expectedVersion, title }, signal })
  },
  removeSection(sectionId: string, expectedVersion: number) {
    return apiRequest<void>(`/api/v1/strategy-sections/${encoded(sectionId)}/remove`, {
      method: 'POST', body: { expected_version: expectedVersion },
    })
  },
  moveTask(taskId: string, targetSectionId: string, expectedVersion: number) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/move`, {
      method: 'POST', body: { target_section_id: targetSectionId, expected_version: expectedVersion },
    })
  },
  reorderSections(strategyId: string, items: ReorderItem[], signal?: AbortSignal) {
    return apiRequest<StrategySectionRead[]>(`/api/v1/strategies/${encoded(strategyId)}/sections/reorder`, { method: 'POST', body: { items }, signal })
  },
  listTasks(sectionId: string, includeArchived = false, signal?: AbortSignal) {
    const query = includeArchived ? '?include_archived=true' : ''
    return apiRequest<StrategyTaskRead[]>(`/api/v1/strategy-sections/${encoded(sectionId)}/tasks${query}`, { signal })
  },
  createTask(sectionId: string, payload: StrategyTaskWrite, signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-sections/${encoded(sectionId)}/tasks`, { method: 'POST', body: payload, signal })
  },
  reorderTasks(sectionId: string, items: ReorderItem[], signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead[]>(`/api/v1/strategy-sections/${encoded(sectionId)}/tasks/reorder`, { method: 'POST', body: { items }, signal })
  },
  getTask(taskId: string, signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-tasks/${encoded(taskId)}`, { signal })
  },
  updateTask(taskId: string, payload: StrategyTaskUpdate, signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-tasks/${encoded(taskId)}`, { method: 'PATCH', body: payload, signal })
  },
  changeStatus(taskId: string, expectedVersion: number, studyStatus: StrategyTaskRead['study_status'], signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/study-status`, { method: 'POST', body: { expected_version: expectedVersion, study_status: studyStatus }, signal })
  },
  archiveTask(taskId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/archive`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
  restoreTask(taskId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<StrategyTaskRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/restore`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
  history(taskId: string, cursor?: string, signal?: AbortSignal) {
    const params = new URLSearchParams({ limit: '100' })
    if (cursor) params.set('cursor', cursor)
    return apiRequest<TaskHistoryList>(`/api/v1/strategy-tasks/${encoded(taskId)}/history?${params}`, { signal })
  },
  async listApprovals(strategyId: string, signal?: AbortSignal) {
    const items: ApprovalRead[] = []
    let cursor: string | null = null
    do {
      const query = new URLSearchParams({ limit: '100' })
      if (cursor) query.set('cursor', cursor)
      const page: { items: ApprovalRead[]; next_cursor: string | null } = await apiRequest(
        `/api/v1/strategies/${encoded(strategyId)}/approvals?${query}`, { signal },
      )
      items.push(...page.items)
      cursor = page.next_cursor
    } while (cursor)
    return items
  },
  getApproval(taskId: string, signal?: AbortSignal) {
    return apiRequest<ApprovalRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/approval`, { signal })
  },
  createApproval(taskId: string, comment = '', signal?: AbortSignal) {
    return apiRequest<ApprovalRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/approval`, { method: 'POST', body: { comment }, signal })
  },
  transitionApproval(taskId: string, expectedVersion: number, status: ApprovalRead['status'], comment?: string, signal?: AbortSignal) {
    return apiRequest<ApprovalRead>(`/api/v1/strategy-tasks/${encoded(taskId)}/approval/transition`, { method: 'POST', body: { expected_version: expectedVersion, status, ...(comment === undefined ? {} : { comment }) }, signal })
  },
}
