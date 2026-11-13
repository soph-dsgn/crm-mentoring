export type FieldErrors = Record<string, string>

export function validateLogin(login: string, password: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!login.trim()) errors.login = 'Введите логин'
  if (!password) errors.password = 'Введите пароль'
  return errors
}

export function validatePasswordChange(currentPassword: string, newPassword: string, confirmation: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!currentPassword) errors.currentPassword = 'Введите временный пароль'
  if (!newPassword) errors.newPassword = 'Введите новый пароль'
  else if (newPassword.length < 12) errors.newPassword = 'Минимум 12 символов'
  if (!confirmation) errors.confirmation = 'Повторите новый пароль'
  else if (newPassword !== confirmation) errors.confirmation = 'Пароли не совпадают'
  return errors
}
