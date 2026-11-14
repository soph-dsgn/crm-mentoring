import type { CurrentUser } from '../api/contracts'

export type AnonymousReason = 'expired' | 'signed_out' | 'password_changed' | null
export type AuthState =
  | { status: 'checking'; user: null; reason: null; message: null }
  | { status: 'error'; user: null; reason: null; message: string }
  | { status: 'anonymous'; user: null; reason: AnonymousReason; message: null }
  | { status: 'password_change'; user: CurrentUser; reason: null; message: null }
  | { status: 'authenticated'; user: CurrentUser; reason: null; message: null }

export type AuthAction =
  | { type: 'CHECKING' }
  | { type: 'BOOTSTRAP_ANONYMOUS' }
  | { type: 'BOOTSTRAP_ERROR'; message: string }
  | { type: 'AUTHENTICATED'; user: CurrentUser }
  | { type: 'SESSION_EXPIRED' }
  | { type: 'SIGNED_OUT' }
  | { type: 'PASSWORD_CHANGED' }

export const initialAuthState: AuthState = { status: 'checking', user: null, reason: null, message: null }

export function authReducer(_state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'CHECKING': return initialAuthState
    case 'BOOTSTRAP_ANONYMOUS': return { status: 'anonymous', user: null, reason: null, message: null }
    case 'BOOTSTRAP_ERROR': return { status: 'error', user: null, reason: null, message: action.message }
    case 'AUTHENTICATED': return action.user.must_change_password
      ? { status: 'password_change', user: action.user, reason: null, message: null }
      : { status: 'authenticated', user: action.user, reason: null, message: null }
    case 'SESSION_EXPIRED': return { status: 'anonymous', user: null, reason: 'expired', message: null }
    case 'SIGNED_OUT': return { status: 'anonymous', user: null, reason: 'signed_out', message: null }
    case 'PASSWORD_CHANGED': return { status: 'anonymous', user: null, reason: 'password_changed', message: null }
  }
}
