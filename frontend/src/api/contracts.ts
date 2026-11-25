export type UserRole = 'admin' | 'student'

export type CurrentUser = {
  id: string
  login: string
  display_name?: string
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

export type CuratorSummary = Pick<CurrentUser, 'id' | 'login' | 'display_name' | 'role' | 'is_owner' | 'is_active'>

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

export type GroupStudentRead = {
  id: string
  name: string
  starts_at: string
  ends_at: string | null
  actual_ends_at: string | null
  status: GroupSummary['status']
  version: number
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

export type StudentSelfRead = Omit<StudentRead, 'user_id' | 'personal_notes' | 'notes'>

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
export type StudentUpdateRequest = Partial<Omit<StudentWriteFields, 'links'>> & { expected_version: number; links?: Record<string, string | null> }

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

export type StrategyRead = {
  id: string
  student_id: string
  source_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  version: number
}

export type StrategySectionRead = {
  id: string
  strategy_id: string
  title: string
  position: number
  created_at: string
  updated_at: string
  version: number
}

export type StrategyTaskRead = {
  id: string
  strategy_id: string
  section_id: string
  title: string
  description: string
  materials: string[]
  links: Record<string, string>
  blocker: boolean
  period_text: string
  due_at: string | null
  position: number
  study_status: 'not_started' | 'in_progress' | 'hold' | 'done'
  review_status: 'none' | 'pending' | 'revision' | 'accepted'
  archived_at: string | null
  created_at: string
  updated_at: string
  version: number
}

export type ReorderItem = { id: string; expected_version: number; position: number }
export type StrategyTaskWrite = {
  title: string
  description?: string
  materials?: string[]
  links?: Record<string, string>
  blocker?: boolean
  period_text?: string
  due_at?: string | null
  position: number
}
export type StrategyTaskUpdate = Partial<Omit<StrategyTaskWrite, 'position'>> & { expected_version: number }

export type TaskHistoryRead = {
  id: string
  task_id: string
  actor_user_id?: string
  event_type: string
  details: Record<string, unknown>
  created_at: string
}
export type TaskHistoryList = { items: TaskHistoryRead[]; next_cursor: string | null }

export type ApprovalRead = {
  id: string
  task_id: string
  status: 'to_send' | 'sent' | 'reviewing' | 'revision' | 'approved'
  comment: string
  created_at: string
  updated_at: string
  version: number
}

export type MeetingRead = {
  id:string; student_id:string; date:string; title:string; summary:string; notes?:string
  archived_at:string|null; created_at:string; updated_at:string; version:number
}
export type MeetingList = { items:MeetingRead[]; next_cursor:string|null }
export type MeetingCreateRequest = { date:string; title:string; summary?:string; notes?:string }
export type MeetingUpdateRequest = Partial<MeetingCreateRequest> & { expected_version:number }

export type HomeworkItemRead = {
  id:string; task_id:string; position:number; title:string; description:string; materials:string[]
  links:Record<string,string>; period_text:string; due_at:string|null
}
export type HomeworkRead = {
  id:string; strategy_id:string; title:string; description:string; links:Record<string,string>
  submission_text:string; submission_links:Record<string,string>; curator_feedback:string; due_at:string|null
  status:'draft'|'issued'|'progress'|'submitted'|'revision'|'accepted'
  issued_at:string|null; submitted_at:string|null; reviewed_at:string|null; archived_at:string|null
  created_at:string; updated_at:string; version:number; items:HomeworkItemRead[]
}
export type HomeworkList = { items:HomeworkRead[]; next_cursor:string|null }
export type HomeworkCreateRequest = { title:string; description?:string; task_ids:string[]; links?:Record<string,string>; due_at?:string|null }
export type HomeworkUpdateRequest = { expected_version:number; title?:string; description?:string; links?:Record<string,string>; due_at?:string|null }
export type HomeworkTransitionRequest = { expected_version:number; status:HomeworkRead['status']; submission_text?:string; submission_links?:Record<string,string>; curator_feedback?:string }
export type HomeworkHistoryRead = { id:string; homework_id:string; actor_user_id?:string; event_type:string; from_status:HomeworkRead['status']|null; to_status:HomeworkRead['status']|null; details:Record<string,unknown>; created_at:string }
export type HomeworkHistoryList = { items:HomeworkHistoryRead[]; next_cursor:string|null }

export type LegacyImportRequest = {
  source: Record<string, unknown>
  curator_assignments: Record<string, string>
  confirmation_checksum?: string
  confirm?: boolean
}

export type LegacyImportIssue = {
  code: string
  entity: string
  legacy_id: string | null
}

export type LegacyValidationReport = {
  valid: boolean
  checksum: string
  source_version: number | null
  counts: Record<string, number>
  conflicts: LegacyImportIssue[]
  warnings: string[]
}

export type LegacyImportResult = {
  import_run_id: string
  checksum: string
  counts: Record<string, number>
  mappings: Record<string, Record<string, string>>
  idempotent_replay: boolean
}

export type KnowledgeKind = 'prompt' | 'chapter'
export type KnowledgeLibraryStatus = 'pending' | 'active'

export type KnowledgeDocumentSummary = {
  id: string
  kind: KnowledgeKind
  title: string
  category: string | null
  excerpt: string
  position: number
  archived_at: string | null
  updated_at: string
  version: number
  is_favorite: boolean
}

export type KnowledgeDocumentRead = Omit<KnowledgeDocumentSummary, 'excerpt'> & {
  html: string
  plain_text: string
  created_at: string
}

export type KnowledgeDocumentList = {
  items: KnowledgeDocumentSummary[]
  next_cursor: string | null
}

export type KnowledgeDocumentCreate = {
  kind: KnowledgeKind
  title: string
  category?: string | null
  html: string
  position?: number
}

export type KnowledgeDocumentUpdate = Partial<Omit<KnowledgeDocumentCreate, 'kind'>> & {
  expected_version: number
}

export type KnowledgeLibraryState = {
  status: KnowledgeLibraryStatus
  version: number
  activated_at: string | null
}

export type KnowledgeImportMode = 'initial' | 'additional'
export type KnowledgeSourceFormat = 'knowledge_data_v1' | 'parsed_documents'
export type KnowledgeConflictAction = 'skip' | 'create_copy' | 'overwrite'

export type KnowledgeConflictResolution = {
  action: KnowledgeConflictAction
  expected_version?: number
}

export type KnowledgeImportRequest = {
  source: Record<string, unknown>
  source_format: KnowledgeSourceFormat
  mode: KnowledgeImportMode
  resolutions?: Record<string, KnowledgeConflictResolution>
  confirmation_checksum?: string
  confirm?: boolean
}

export type KnowledgeImportItem = {
  source_key: string
  classification: 'new' | 'archived' | 'exact_duplicate' | 'conflict' | 'overwrite' | 'skipped'
  target_id: string | null
  conflict_code: string | null
  resolved: boolean
}

export type KnowledgeImportIssue = {
  code: string
  source_key: string | null
  fields: string[]
}

export type KnowledgeImportValidation = {
  valid: boolean
  checksum: string
  source_version: number | null
  source_format: KnowledgeSourceFormat
  mode: KnowledgeImportMode
  library_status: KnowledgeLibraryStatus
  counts: Record<string, number>
  items: KnowledgeImportItem[]
  issues: KnowledgeImportIssue[]
}

export type KnowledgeImportResult = {
  import_run_id: string
  checksum: string
  counts: Record<string, number>
  mappings: Record<string, string>
  library_status: KnowledgeLibraryStatus
  idempotent_replay: boolean
}

export type StrategyImportTask = {
  title: string
  description: string
  period_text: string
  materials: string[]
  study_status: StrategyTaskRead['study_status']
}

export type StrategyImportSection = { title: string; tasks: StrategyImportTask[] }
export type StrategyImportProfile = { point_a?: string | null; point_b?: string | null; telegram?: string | null }
export type StrategyImportWarning = { code: string; count: number; examples: string[] }

export type StrategyImportDraft = {
  source_title: string
  sha256: string
  page_count: number
  profile: StrategyImportProfile
  sections: StrategyImportSection[]
  warnings: StrategyImportWarning[]
}

export type StrategyImportApply = {
  expected_version: number
  source: { file_name: string; title: string; sha256: string }
  profile: StrategyImportProfile
  sections: StrategyImportSection[]
}

export type StrategyImportResult = { strategy: StrategyRead; student_version: number; section_count: number; task_count: number }
