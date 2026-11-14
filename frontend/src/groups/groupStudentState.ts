import type { CurrentUser } from '../api/contracts'
import { ApiError } from '../api/http'
import type { AppData, Group, Student } from '../types'

type UserIdentity = Pick<CurrentUser, 'id' | 'role' | 'is_owner' | 'is_active' | 'must_change_password'>
export type RecordSource = 'server' | 'legacy'

export function recordForSource<T extends { id: string }>(id: string | null, source: RecordSource, server: T[], legacy: T[]): T | null {
  if (!id) return null
  return (source === 'server' ? server : legacy).find(item => item.id === id) ?? null
}

export function serverDomainData(legacy: AppData, groups: Group[], students: Student[]): AppData {
  return { ...legacy, groups, students, sections: [], tasks: [], meetings: [], homeworks: [] }
}

export function canWriteGroup(user: UserIdentity, group: Group): boolean {
  return user.role === 'admin' && user.is_active && !user.must_change_password && (user.is_owner || group.curatorId === user.id)
}

export function canWriteStudent(user: UserIdentity, student: Student, groups: Group[]): boolean {
  const group = groups.find(item => item.id === student.groupId)
  return Boolean(group && canWriteGroup(user, group))
}

export function groupStudentErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить действие'
  switch (error.code) {
    case 'connection_error': return 'Не удалось подключиться к серверу'
    case 'forbidden': return 'У вас нет прав изменять эту группу или профиль'
    case 'not_found': return 'Группа или профиль больше недоступны'
    case 'version_conflict': return 'Данные уже изменились в другой сессии. Мы загрузили актуальную версию — проверьте её перед повторным сохранением'
    case 'group_archived': return 'Сначала восстановите группу из архива'
    case 'group_changed': return 'Группа изменилась или была архивирована. Обновите данные'
    case 'invalid_group_transition': return 'Статус группы уже изменился. Обновите данные'
    case 'invalid_student_transition': return 'Статус профиля уже изменился. Обновите данные'
    case 'invalid_dates': return 'Проверьте даты начала и завершения'
    default: return error.status === 422 ? 'Проверьте заполненные поля' : 'Не удалось выполнить действие'
  }
}
