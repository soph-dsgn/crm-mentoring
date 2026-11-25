import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react'
import type { ChangePasswordRequest, LoginRequest } from '../api/contracts'
import { authApi } from '../api/auth'
import { ApiError, setSessionExpiredHandler } from '../api/http'
import { authReducer, initialAuthState } from './authState'
import { AuthContext } from './authContext'
import { closeSession, refreshSession, restoreSession } from './session'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialAuthState)
  // The temporary password typed at login is kept in memory only, so the forced change
  // screen does not ask for it a second time. A reload clears it and the field returns.
  const temporaryPassword = useRef<string | null>(null)
  const [temporaryPasswordKnown, setTemporaryPasswordKnown] = useState(false)
  const forgetTemporaryPassword = useCallback(() => { temporaryPassword.current = null; setTemporaryPasswordKnown(false) }, [])

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

  const authenticatedId = state.status === 'authenticated' ? state.user.id : null
  useEffect(() => {
    if (!authenticatedId) return
    let pending: AbortController | undefined
    const reconcile = () => {
      if (document.visibilityState !== 'visible') return
      pending?.abort()
      const controller = new AbortController()
      pending = controller
      void authApi.current(controller.signal).then(user => {
        if (!controller.signal.aborted) dispatch({ type: 'RECONCILE', previousUserId: authenticatedId, user })
      }).catch(error => {
        if (!controller.signal.aborted && error instanceof ApiError && error.status === 401) {
          dispatch({ type: 'RECONCILE', previousUserId: authenticatedId, user: null })
        }
      })
    }
    document.addEventListener('visibilitychange', reconcile)
    return () => {
      pending?.abort()
      document.removeEventListener('visibilitychange', reconcile)
    }
  }, [authenticatedId])

  const login = useCallback(async (payload: LoginRequest) => {
    const user = await authApi.login(payload)
    temporaryPassword.current = user.must_change_password ? payload.password : null
    setTemporaryPasswordKnown(user.must_change_password)
    dispatch({ type: 'AUTHENTICATED', user })
  }, [])

  const logout = useCallback(async () => {
    const action = await closeSession(() => authApi.logout())
    forgetTemporaryPassword()
    dispatch(action)
  }, [forgetTemporaryPassword])

  const changePassword = useCallback(async (payload: ChangePasswordRequest) => {
    const current = payload.current_password || temporaryPassword.current || ''
    try {
      const user = await authApi.changePassword({ ...payload, current_password: current })
      forgetTemporaryPassword()
      dispatch({ type: 'AUTHENTICATED', user })
    } catch (error) {
      if (error instanceof ApiError && error.code === 'invalid_credentials') forgetTemporaryPassword()
      throw error
    }
  }, [forgetTemporaryPassword])

  const refreshCurrentUser = useCallback(async () => {
    dispatch(await refreshSession(() => authApi.current()))
  }, [])

  const retrySession = useCallback(() => checkSession(), [checkSession])
  const value = useMemo(() => ({ state, login, logout, changePassword, refreshCurrentUser, retrySession, temporaryPasswordKnown }), [state, login, logout, changePassword, refreshCurrentUser, retrySession, temporaryPasswordKnown])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
