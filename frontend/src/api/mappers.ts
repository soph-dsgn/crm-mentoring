import type { GroupCreateRequest, GroupRead, GroupSummary, GroupUpdateRequest, StudentCreateRequest, StudentRead, StudentSummary, StudentUpdateRequest } from './contracts'
import type { Group, Student } from '../types'

const emptyLinks = () => ({ figma: '', portfolio: '', resume: '', telegram: '', notion: '' })

export function groupFromApi(group: GroupSummary | GroupRead): Group {
  const detail = group as Partial<GroupRead>
  return {
    id: group.id,
    name: group.name,
    startsAt: group.starts_at,
    endsAt: group.ends_at ?? '',
    actualEndsAt: detail.actual_ends_at ?? '',
    status: group.status,
    statusBeforeArchive: detail.status_before_archive ?? null,
    notes: detail.notes ?? '',
    createdAt: detail.created_at ?? group.updated_at,
    durationMonths: detail.duration_months == null ? undefined : Number(detail.duration_months),
    serverBacked: true,
    curatorId: group.curator_id,
    updatedAt: group.updated_at,
    version: group.version,
  }
}

export function studentFromApi(student: StudentSummary | StudentRead): Student {
  const detail = student as Partial<StudentRead>
  const links = emptyLinks()
  for (const key of Object.keys(links) as (keyof typeof links)[]) links[key] = detail.links?.[key] ?? ''
  return {
    id: student.id,
    groupId: student.group_id,
    name: student.name,
    age: detail.age ?? null,
    photo: detail.photo ?? '',
    avatarIndex: detail.avatar_index ?? -1,
    stage: student.stage,
    stageKnown: detail.stage_known ?? undefined,
    startsAt: detail.starts_at ?? '',
    level: detail.level ?? '',
    desiredPosition: detail.desired_position ?? '',
    careerGoal: detail.career_goal ?? '',
    links,
    background: detail.background ?? '',
    experience: detail.experience ?? '',
    strengths: detail.strengths ?? '',
    growthAreas: detail.growth_areas ?? '',
    difficulties: detail.difficulties ?? '',
    expectations: detail.expectations ?? '',
    personalNotes: detail.personal_notes ?? '',
    pointA: detail.point_a ?? '',
    pointB: detail.point_b ?? '',
    notes: detail.notes ?? '',
    strategyUpdatedAt: detail.strategy_updated_at ?? student.updated_at,
    createdAt: detail.created_at ?? student.updated_at,
    serverBacked: true,
    userId: detail.user_id ?? null,
    archivedAt: student.archived_at ?? '',
    updatedAt: student.updated_at,
    version: student.version,
  }
}

export function groupCreateToApi(group: Group): GroupCreateRequest {
  return {
    name: group.name.trim(),
    starts_at: group.startsAt,
    ends_at: group.endsAt || null,
    actual_ends_at: group.actualEndsAt || null,
    status: group.status === 'archived' ? 'backlog' : group.status,
    notes: group.notes,
    duration_months: group.durationMonths ?? null,
  }
}

export function groupUpdateToApi(group: Group): GroupUpdateRequest {
  return { ...groupCreateToApi(group), expected_version: group.version ?? 1 }
}

export function studentCreateToApi(student: Student): StudentCreateRequest {
  const links = Object.fromEntries(Object.entries(student.links).filter(([, value]) => value.trim()))
  return {
    name: student.name.trim(), age: student.age, photo: student.photo, avatar_index: student.avatarIndex,
    stage: student.stage, stage_known: student.stageKnown ?? null, starts_at: student.startsAt || null,
    level: student.level, desired_position: student.desiredPosition, career_goal: student.careerGoal, links,
    background: student.background, experience: student.experience, strengths: student.strengths,
    growth_areas: student.growthAreas, difficulties: student.difficulties, expectations: student.expectations,
    personal_notes: student.personalNotes, point_a: student.pointA, point_b: student.pointB, notes: student.notes,
  }
}

export function studentUpdateToApi(student: Student): StudentUpdateRequest {
  return {
    ...studentCreateToApi(student),
    expected_version: student.version ?? 1,
    links: Object.fromEntries(Object.entries(student.links).map(([key, value]) => [key, value.trim() || null])),
  }
}
