import type {
  CuratorSummary,
  GroupAssignmentResponse,
  GroupListResponse,
  GroupSummary,
  OffboardResponse,
  SafeUser,
  TemporaryCredentialResponse,
} from './contracts'
import { ApiError, apiRequest } from './http'

const ADMIN_BASE = '/api/v1/admin'

export { ApiError }

export const usersApi = {
  listCurators(signal?: AbortSignal) {
    return apiRequest<CuratorSummary[]>(`${ADMIN_BASE}/curators`, { signal })
  },
  getCurator(userId: string, signal?: AbortSignal) {
    return apiRequest<SafeUser>(`${ADMIN_BASE}/curators/${encodeURIComponent(userId)}`, { signal })
  },
  createCurator(login: string, signal?: AbortSignal) {
    return apiRequest<TemporaryCredentialResponse>(`${ADMIN_BASE}/curators`, { method: 'POST', body: { login }, signal })
  },
  deactivateCurator(userId: string, signal?: AbortSignal) {
    return apiRequest<SafeUser>(`${ADMIN_BASE}/curators/${encodeURIComponent(userId)}/deactivate`, { method: 'POST', signal })
  },
  offboardCurator(userId: string, successorCuratorId: string, signal?: AbortSignal) {
    return apiRequest<OffboardResponse>(`${ADMIN_BASE}/curators/${encodeURIComponent(userId)}/offboard`, {
      method: 'POST',
      body: { successor_curator_id: successorCuratorId },
      signal,
    })
  },
  transferOwnership(userId: string, signal?: AbortSignal) {
    return apiRequest<SafeUser>(`${ADMIN_BASE}/curators/${encodeURIComponent(userId)}/transfer-ownership`, { method: 'POST', signal })
  },
  reassignGroup(groupId: string, curatorId: string, signal?: AbortSignal) {
    return apiRequest<GroupAssignmentResponse>(`${ADMIN_BASE}/groups/${encodeURIComponent(groupId)}/reassign-curator`, {
      method: 'POST',
      body: { curator_id: curatorId },
      signal,
    })
  },
  async listCuratorGroups(curatorId: string, signal?: AbortSignal): Promise<GroupSummary[]> {
    const groups: GroupSummary[] = []
    let cursor: string | null = null
    do {
      const query = new URLSearchParams({ curator_id: curatorId, limit: '100' })
      if (cursor) query.set('cursor', cursor)
      const page = await apiRequest<GroupListResponse>(`/api/v1/groups?${query.toString()}`, { signal })
      groups.push(...page.items)
      cursor = page.next_cursor
    } while (cursor)
    return groups
  },
}
