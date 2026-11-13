import type { ReactNode } from 'react'
import { useAuth } from './authContext'
import { getAccessProfile } from './access'
import { ChangePasswordScreen, LoginScreen, SessionErrorScreen, SessionLoadingScreen, StudentAccessScreen } from './AuthScreens'

export function AuthGate({ children }: { children: ReactNode }) {
  const { state, login, logout, changePassword, retrySession } = useAuth()
  if (state.status === 'checking') return <SessionLoadingScreen/>
  if (state.status === 'error') return <SessionErrorScreen onRetry={retrySession}/>
  if (state.status === 'anonymous') return <LoginScreen reason={state.reason} notice={null} onSubmit={login}/>
  if (state.status === 'password_change') return <ChangePasswordScreen login={state.user.login} onSubmit={changePassword} onLogout={logout}/>
  if (!getAccessProfile(state.user).canUseCrm) return <StudentAccessScreen onLogout={logout}/>
  return children
}
