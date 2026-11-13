import type { ChangePasswordRequest, CurrentUser, LoginRequest } from './contracts'
import { apiRequest } from './http'

const AUTH_BASE = '/api/v1/auth'

export const authApi = {
  login(payload: LoginRequest, signal?: AbortSignal) {
    return apiRequest<CurrentUser>(`${AUTH_BASE}/login`, { method: 'POST', body: payload, signal }, { notifyUnauthorized: false })
  },
  current(signal?: AbortSignal) {
    return apiRequest<CurrentUser>(`${AUTH_BASE}/me`, { signal }, { notifyUnauthorized: false })
  },
  logout(signal?: AbortSignal) {
    return apiRequest<void>(`${AUTH_BASE}/logout`, { method: 'POST', signal }, { notifyUnauthorized: false })
  },
  changePassword(payload: ChangePasswordRequest, signal?: AbortSignal) {
    return apiRequest<void>(`${AUTH_BASE}/change-password`, { method: 'POST', body: payload, signal }, { notifyUnauthorized: false })
  },
}
