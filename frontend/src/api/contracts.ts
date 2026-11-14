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

export type SafeUser = CurrentUser & {
  created_at: string
  deactivated_at: string | null
}

export type CuratorSummary = Pick<CurrentUser, 'id' | 'login' | 'role' | 'is_owner' | 'is_active'>

export type TemporaryCredentialResponse = {
  user: SafeUser
  temporary_password: string
}

export type GroupSummary = {
  id: string
  curator_id: string
  name: string
  starts_at: string
  ends_at: string | null
  status: 'backlog' | 'active' | 'completed' | 'archived'
  updated_at: string
  version: number
}

export type GroupListResponse = {
  items: GroupSummary[]
  next_cursor: string | null
}

export type GroupAssignmentResponse = {
  group_id: string
  curator_id: string
}

export type OffboardResponse = {
  user: SafeUser
  reassigned_group_ids: string[]
}
