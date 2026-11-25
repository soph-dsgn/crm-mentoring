export type FieldErrors = Record<string, string>

export function validateLogin(login: string, password: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!login.trim()) errors.login = 'Введите логин'
  if (!password) errors.password = 'Введите пароль'
  return errors
}

export const PASSWORD_MIN_LENGTH = 8

export function passwordRequirements(password: string) {
  return {
    length: password.length >= PASSWORD_MIN_LENGTH,
    digit: /\p{Nd}/u.test(password),
    special: /[^\p{L}\p{N}\s]/u.test(password),
  }
}

export function validatePasswordChange(currentPassword: string, newPassword: string, confirmation: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!currentPassword) errors.currentPassword = 'Введите временный пароль'
  if (!newPassword) errors.newPassword = 'Введите новый пароль'
  else {
    const met = passwordRequirements(newPassword)
    if (!met.length) errors.newPassword = `Минимум ${PASSWORD_MIN_LENGTH} символов`
    else if (!met.digit && !met.special) errors.newPassword = 'Добавьте цифру и спецсимвол'
    else if (!met.digit) errors.newPassword = 'Добавьте хотя бы одну цифру'
    else if (!met.special) errors.newPassword = 'Добавьте спецсимвол, например ! ? # %'
  }
  if (!confirmation) errors.confirmation = 'Повторите новый пароль'
  else if (newPassword !== confirmation) errors.confirmation = 'Пароли не совпадают'
  return errors
}
