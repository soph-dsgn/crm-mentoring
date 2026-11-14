import type { StudentCreateRequest, StudentListResponse, StudentRead, StudentSummary, StudentUpdateRequest } from './contracts'
import { ApiError, apiRequest } from './http'

const studentPath = (id: string) => `/api/v1/students/${encodeURIComponent(id)}`
const rosterPath = (groupId: string) => `/api/v1/groups/${encodeURIComponent(groupId)}/students`

export { ApiError }

export const studentsApi = {
  listPage(groupId: string, query: { cursor?: string; limit?: number } = {}, signal?: AbortSignal) {
    const search = new URLSearchParams({ limit: String(query.limit ?? 100) })
    if (query.cursor) search.set('cursor', query.cursor)
    return apiRequest<StudentListResponse>(`${rosterPath(groupId)}?${search}`, { signal })
  },
  async listAll(groupId: string, signal?: AbortSignal) {
    const items: StudentSummary[] = []
    let cursor: string | undefined
    do {
      const page = await this.listPage(groupId, { cursor, limit: 100 }, signal)
      items.push(...page.items)
      cursor = page.next_cursor ?? undefined
    } while (cursor)
    return items
  },
  get(studentId: string, signal?: AbortSignal) {
    return apiRequest<StudentRead>(studentPath(studentId), { signal })
  },
  create(groupId: string, payload: StudentCreateRequest, signal?: AbortSignal) {
    return apiRequest<StudentRead>(rosterPath(groupId), { method: 'POST', body: payload, signal })
  },
  update(studentId: string, payload: StudentUpdateRequest, signal?: AbortSignal) {
    return apiRequest<StudentRead>(studentPath(studentId), { method: 'PATCH', body: payload, signal })
  },
  archive(studentId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<StudentRead>(`${studentPath(studentId)}/archive`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
  restore(studentId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<StudentRead>(`${studentPath(studentId)}/restore`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
}
