import type { CurrentUser } from '../api/contracts'
import { ApiError } from '../api/http'
import type { AuthAction } from './authState'

export const sessionConnectionMessage = 'Не удалось подключиться к серверу. Проверьте соединение и повторите попытку'

export async function restoreSession(
  current: () => Promise<CurrentUser>,
): Promise<AuthAction | null> {
  try {
    return { type: 'AUTHENTICATED', user: await current() }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return null
    if (error instanceof ApiError && error.status === 401) return { type: 'BOOTSTRAP_ANONYMOUS' }
    return { type: 'BOOTSTRAP_ERROR', message: sessionConnectionMessage }
  }
}

export async function closeSession(logout: () => Promise<void>): Promise<AuthAction> {
  await logout()
  return { type: 'SIGNED_OUT' }
}
