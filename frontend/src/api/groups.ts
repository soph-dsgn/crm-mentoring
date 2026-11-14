import type { GroupCreateRequest, GroupListResponse, GroupRead, GroupSummary, GroupUpdateRequest } from './contracts'
import { ApiError, apiRequest } from './http'

const BASE = '/api/v1/groups'
const idPath = (id: string) => `${BASE}/${encodeURIComponent(id)}`

export { ApiError }

export const groupsApi = {
  listPage(query: { lifecycle?: GroupSummary['status']; curator_id?: string; cursor?: string; limit?: number } = {}, signal?: AbortSignal) {
    const search = new URLSearchParams()
    if (query.lifecycle) search.set('lifecycle', query.lifecycle)
    if (query.curator_id) search.set('curator_id', query.curator_id)
    if (query.cursor) search.set('cursor', query.cursor)
    search.set('limit', String(query.limit ?? 100))
    return apiRequest<GroupListResponse>(`${BASE}?${search}`, { signal })
  },
  async listAll(query: { lifecycle?: GroupSummary['status']; curator_id?: string } = {}, signal?: AbortSignal) {
    const items: GroupSummary[] = []
    let cursor: string | undefined
    do {
      const page = await this.listPage({ ...query, cursor, limit: 100 }, signal)
      items.push(...page.items)
      cursor = page.next_cursor ?? undefined
    } while (cursor)
    return items
  },
  get(groupId: string, signal?: AbortSignal) {
    return apiRequest<GroupRead>(idPath(groupId), { signal })
  },
  create(payload: GroupCreateRequest, signal?: AbortSignal) {
    return apiRequest<GroupRead>(BASE, { method: 'POST', body: payload, signal })
  },
  update(groupId: string, payload: GroupUpdateRequest, signal?: AbortSignal) {
    return apiRequest<GroupRead>(idPath(groupId), { method: 'PATCH', body: payload, signal })
  },
  archive(groupId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<GroupRead>(`${idPath(groupId)}/archive`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
  restore(groupId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<GroupRead>(`${idPath(groupId)}/restore`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
}
