import { addCalendarMonths, normalizeData } from './data'
import type { AppData, Group, StrategySection, StrategyTask, Student } from './types'

type Seed = Pick<AppData, 'groups' | 'students' | 'sections' | 'tasks'>
const sameName = (a: string, b: string) => a.trim().toLocaleLowerCase('ru') === b.trim().toLocaleLowerCase('ru')

// Seed IDs are stable across builds. Existing records always win on collision.
export function mergeStrategies(current: AppData, source: unknown): AppData {
  const seed = normalizeData(source) as Seed
  const groups = current.groups.filter(g => !g.id.startsWith('demo-'))
  const students = current.students.filter(s => !s.id.startsWith('demo-'))
  const sections = current.sections.filter(s => !s.id.startsWith('demo-'))
  const tasks = current.tasks.filter(t => !t.id.startsWith('demo-'))
  const conflicts = new Set(current.importConflicts || [])
  const groupIds = new Map<string, string>()
  for (const imported of seed.groups) {
    const existing = groups.find(g => g.id === imported.id || (sameName(g.name, imported.name) && g.startsAt === imported.startsAt))
    if (existing) {
      groupIds.set(imported.id, existing.id)
      if (existing.id !== imported.id) conflicts.add(`Группа «${imported.name}» уже была создана: сохранены её данные и статус.`)
    } else {
      const durationMonths = imported.name === 'Группа 1' ? 5.5 : 6
      const endsAt = addCalendarMonths(imported.startsAt, durationMonths)
      groups.push({ ...imported, durationMonths, endsAt, status: 'active' } as Group)
      groupIds.set(imported.id, imported.id)
    }
  }
  for (const imported of seed.students) {
    const groupId = groupIds.get(imported.groupId)
    if (!groupId) continue
    const existing = students.find(s => s.id === imported.id || (s.groupId === groupId && sameName(s.name, imported.name)))
    if (existing) {
      if (existing.id !== imported.id) {
        conflicts.add(`Ученица «${imported.name}», ${groups.find(g => g.id === groupId)?.name}: импорт пропущен, существующий профиль сохранён. Сверьте стратегию вручную.`)
        continue
      }
      // Stable IDs let us add source records that are still missing without touching user edits.
      sections.push(...seed.sections.filter(s => s.studentId === imported.id && !sections.some(old => old.id === s.id)) as StrategySection[])
      tasks.push(...seed.tasks.filter(t => t.studentId === imported.id && !tasks.some(old => old.id === t.id)) as StrategyTask[])
      continue
    }
    students.push({ ...imported, groupId } as Student)
    sections.push(...seed.sections.filter(s => s.studentId === imported.id && !sections.some(old => old.id === s.id)) as StrategySection[])
    tasks.push(...seed.tasks.filter(t => t.studentId === imported.id && !tasks.some(old => old.id === t.id)) as StrategyTask[])
  }
  return { ...current, version: 4, demo: false, groups, students, sections, tasks,
    meetings: current.meetings.filter(m => !m.id.startsWith('demo-') && !m.studentId.startsWith('demo-')),
    homeworks: current.homeworks.filter(h => !h.id.startsWith('demo-') && !h.studentId.startsWith('demo-')),
    importConflicts: [...conflicts] }
}
