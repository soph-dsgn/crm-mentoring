import type { CurrentUser } from '../api/contracts'
import { ApiError } from '../api/http'

export type TemporaryCredential = {
  login: string
  temporaryPassword: string
}

export type TemporaryCredentialAction =
  | { type: 'show'; credential: TemporaryCredential }
  | { type: 'dismiss' }

export function temporaryCredentialReducer(_state: TemporaryCredential | null, action: TemporaryCredentialAction): TemporaryCredential | null {
  return action.type === 'show' ? action.credential : null
}

export function canManageAccounts(user: CurrentUser): boolean {
  return user.role === 'admin' && user.is_owner && user.is_active && !user.must_change_password
}

export function accountErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить действие'
  switch (error.code) {
    case 'connection_error': return 'Не удалось подключиться к серверу'
    case 'session_refresh_failed': return 'Права переданы, но не удалось обновить сессию. Перезагрузите страницу'
    case 'forbidden': return 'Недостаточно прав для этого действия'
    case 'login_conflict': return 'Этот логин уже используется'
    case 'invalid_login': return 'Проверьте формат логина'
    case 'user_inactive': return 'Аккаунт уже деактивирован'
    case 'curator_has_groups': return 'Сначала передайте группы другому куратору'
    case 'invalid_curator': return 'Выберите другого активного куратора'
    case 'invalid_owner': return 'Передать права можно другому активному куратору'
    case 'version_conflict':
    case 'curator_assignment_changed': return 'Назначение группы уже изменилось. Обновите данные'
    case 'not_found': return 'Аккаунт или группа больше недоступны'
    default: return error.status === 422 ? 'Проверьте введённые данные' : 'Не удалось выполнить действие'
  }
}
