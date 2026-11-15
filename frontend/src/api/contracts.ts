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

export type GroupRead = GroupSummary & {
  actual_ends_at: string | null
  status_before_archive: Exclude<GroupSummary['status'], 'archived'> | null
  notes: string
  duration_months: string | number | null
  created_at: string
}

export type GroupListResponse = {
  items: GroupSummary[]
  next_cursor: string | null
}

export type GroupCreateRequest = {
  name: string
  starts_at: string
  ends_at?: string | null
  actual_ends_at?: string | null
  status?: Exclude<GroupSummary['status'], 'archived'>
  notes?: string
  duration_months?: number | null
}

export type GroupUpdateRequest = Partial<GroupCreateRequest> & { expected_version: number }

export type StudentSummary = {
  id: string
  group_id: string
  name: string
  stage: 'start' | 'portfolio' | 'search'
  archived_at: string | null
  updated_at: string
  version: number
}

export type StudentRead = StudentSummary & {
  user_id?: string | null
  age: number | null
  photo: string
  avatar_index: number
  stage_known: boolean | null
  starts_at: string | null
  level: string
  desired_position: string
  career_goal: string
  links: Record<string, string>
  background: string
  experience: string
  strengths: string
  growth_areas: string
  difficulties: string
  expectations: string
  personal_notes?: string
  point_a: string
  point_b: string
  notes?: string
  strategy_updated_at: string
  created_at: string
}

export type StudentListResponse = {
  items: StudentSummary[]
  next_cursor: string | null
}

export type StudentWriteFields = {
  name: string
  age?: number | null
  photo?: string
  avatar_index?: number
  stage?: StudentSummary['stage']
  stage_known?: boolean | null
  starts_at?: string | null
  level?: string
  desired_position?: string
  career_goal?: string
  links?: Record<string, string>
  background?: string
  experience?: string
  strengths?: string
  growth_areas?: string
  difficulties?: string
  expectations?: string
  personal_notes?: string
  point_a?: string
  point_b?: string
  notes?: string
}

export type StudentCreateRequest = StudentWriteFields
export type StudentUpdateRequest = Partial<StudentWriteFields> & { expected_version: number }

export type StudentAccountResponse = { student_id: string; user: SafeUser }
export type StudentTemporaryCredentialResponse = StudentAccountResponse & { temporary_password: string }
export type PasswordResetResponse = { user_id: string; must_change_password: boolean; temporary_password: string }

export type GroupAssignmentResponse = {
  group_id: string
  curator_id: string
}

export type OffboardResponse = {
  user: SafeUser
  reassigned_group_ids: string[]
}
