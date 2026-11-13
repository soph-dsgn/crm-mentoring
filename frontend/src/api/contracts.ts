export type UserRole = 'admin' | 'student'

export type CurrentUser = {
  id: string
  login: string
  role: UserRole
  is_owner: boolean
  must_change_password: boolean
  is_active: boolean
}

export type ApiErrorEnvelope = {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}

export type LoginRequest = {
  login: string
  password: string
}

export type ChangePasswordRequest = {
  current_password: string
  new_password: string
}
