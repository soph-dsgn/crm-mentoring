import { useCallback, useEffect, useMemo, useReducer, type ReactNode } from 'react'
import type { ChangePasswordRequest, LoginRequest } from '../api/contracts'
import { authApi } from '../api/auth'
import { setSessionExpiredHandler } from '../api/http'
import { authReducer, initialAuthState } from './authState'
import { AuthContext } from './authContext'
import { closeSession, restoreSession } from './session'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialAuthState)

  const checkSession = useCallback((signal?: AbortSignal) => {
    dispatch({ type: 'CHECKING' })
    void restoreSession(() => authApi.current(signal)).then(action => {
      if (action) dispatch(action)
    })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    checkSession(controller.signal)
    return () => controller.abort()
  }, [checkSession])

  useEffect(() => {
    setSessionExpiredHandler(() => dispatch({ type: 'SESSION_EXPIRED' }))
    return () => setSessionExpiredHandler(null)
  }, [])

  const login = useCallback(async (payload: LoginRequest) => {
    const user = await authApi.login(payload)
    dispatch({ type: 'AUTHENTICATED', user })
  }, [])

  const logout = useCallback(async () => {
    const action = await closeSession(() => authApi.logout())
    dispatch(action)
  }, [])

  const changePassword = useCallback(async (payload: ChangePasswordRequest) => {
    await authApi.changePassword(payload)
    dispatch({ type: 'PASSWORD_CHANGED' })
  }, [])

  const retrySession = useCallback(() => checkSession(), [checkSession])
  const value = useMemo(() => ({ state, login, logout, changePassword, retrySession }), [state, login, logout, changePassword, retrySession])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
