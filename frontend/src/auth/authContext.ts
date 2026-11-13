import { createContext, useContext } from 'react'
import type { ChangePasswordRequest, CurrentUser, LoginRequest } from '../api/contracts'
import type { AuthState } from './authState'

export type AuthContextValue = {
  state: AuthState
  login: (payload: LoginRequest) => Promise<void>
  logout: () => Promise<void>
  changePassword: (payload: ChangePasswordRequest) => Promise<void>
  retrySession: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

export function useCurrentUser(): CurrentUser {
  const { state } = useAuth()
  if (state.status !== 'authenticated' && state.status !== 'password_change') throw new Error('Current user is unavailable')
  return state.user
}
