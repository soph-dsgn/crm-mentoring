export type Stage = 'start' | 'portfolio' | 'search'
export type TaskStatus = 'backlog' | 'progress' | 'done'
export type StudyStatus = 'not_started' | 'in_progress' | 'hold' | 'done'
export type ReviewStatus = 'none' | 'pending' | 'revision' | 'accepted'
export type ApprovalStatus = 'to_send' | 'sent' | 'reviewing' | 'revision' | 'approved'
export type HomeworkStatus = 'draft' | 'issued' | 'progress' | 'submitted' | 'revision' | 'accepted'
export type GroupStatus = 'backlog' | 'active' | 'completed' | 'archived'
export type Owner = 'Не назначен' | 'Софья' | 'Аня'

export interface Group {
  id: string; name: string; startsAt: string; endsAt: string; actualEndsAt: string;
  status: GroupStatus; statusBeforeArchive: Exclude<GroupStatus, 'archived'> | null;
  notes: string; createdAt: string; durationMonths?: number
}
export interface Student {
  id: string; groupId: string; name: string; age: number | null; photo: string; avatarIndex: number;
  stage: Stage; stageKnown?: boolean; startsAt: string; level: string; desiredPosition: string; careerGoal: string;
  links: { figma: string; portfolio: string; resume: string; telegram: string; notion: string };
  background: string; experience: string; strengths: string; growthAreas: string;
  difficulties: string; expectations: string; personalNotes: string;
  pointA: string; pointB: string; notes: string; strategyUpdatedAt: string; createdAt: string
}
export interface StrategyTask {
  id: string; studentId: string; title: string; description: string; stage: Stage; status: TaskStatus; owner: Owner;
  dueAt: string; url: string; comments: string; order: number; blocker: boolean; createdAt: string; updatedAt: string;
  reviewStatus: ReviewStatus; approvalStatus: ApprovalStatus | null; approvalType: string; approvalSentAt: string; approvalComment: string;
  history: { at: string; label: string }[]
  sectionId: string; studyStatus: StudyStatus; period: string; sourceFile?: string
  materials: string[]
}
export interface StrategySection { id: string; studentId: string; title: string; order: number; createdAt: string }
export interface Meeting { id: string; studentId: string; date: string; title: string; summary: string; createdAt: string }
export interface HomeworkItem { taskId: string; title: string; description: string; url: string; materials?: string[]; dueAt: string }
export interface Homework { id: string; studentId: string; title: string; text: string; items: HomeworkItem[]; status: HomeworkStatus; issuedAt: string; submittedAt: string; reviewedAt?: string; workUrl: string; comment: string; dueAt: string; createdAt: string; deletedAt?: string }
export interface AppData { version: 3; groups: Group[]; students: Student[]; sections: StrategySection[]; tasks: StrategyTask[]; meetings: Meeting[]; homeworks: Homework[]; demo: boolean; demoRevision?: number; importConflicts?: string[] }
