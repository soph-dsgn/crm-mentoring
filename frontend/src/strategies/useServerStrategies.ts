import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ApprovalRead, StrategyRead, StrategyTaskRead, TaskHistoryRead } from '../api/contracts'
import { ApiError } from '../api/http'
import { strategiesApi } from '../api/strategies'
import { partitionSettled } from '../api/settled'
import type { ApprovalStatus, StrategySection, StrategyTask, Student, StudyStatus } from '../types'
import { sectionFromApi, taskFromApi } from './strategyState'

type LoadStatus = 'loading' | 'ready' | 'error'

type StudentStrategyBundle = {
  strategy: StrategyRead | null
  sections: StrategySection[]
  tasks: StrategyTask[]
  partialErrorCount: number
}

const replaceById = <T extends { id: string }>(items: T[], next: T) => items.some(item => item.id === next.id) ? items.map(item => item.id === next.id ? next : item) : [...items, next]

function taskLinks(task: StrategyTask): Record<string,string> {
  const links = { ...task.serverLinks }
  const primaryKey = Object.keys(links)[0] ?? 'material'
  if (task.url) links[primaryKey] = task.url
  else delete links[primaryKey]
  return links
}

async function optionalApproval(taskId: string, signal?: AbortSignal): Promise<ApprovalRead | null> {
  try { return await strategiesApi.getApproval(taskId, signal) }
  catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error }
}

async function loadStudentBundle(student: Student, signal?: AbortSignal): Promise<StudentStrategyBundle> {
  let strategy: StrategyRead
  try { strategy = await strategiesApi.getForStudent(student.id, signal) }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) return { strategy: null, sections: [], tasks: [], partialErrorCount: 0 }
    throw error
  }
  const sectionWires = await strategiesApi.listSections(strategy.id, signal)
  const taskResults = partitionSettled(await Promise.allSettled(sectionWires.map(section => strategiesApi.listTasks(section.id, true, signal))))
  const taskWires = taskResults.values.flat()
  const approvalResults = await Promise.allSettled(taskWires.map(task => optionalApproval(task.id, signal)))
  const approvals = approvalResults.map(result => result.status === 'fulfilled' ? result.value : null)
  return {
    strategy,
    sections: sectionWires.map(section => sectionFromApi(section, student.id)),
    tasks: taskWires.map((task, index) => taskFromApi(task, student.id, approvals[index], student.stage)),
    partialErrorCount: taskResults.errors.length + approvalResults.filter(result => result.status === 'rejected').length,
  }
}

export function useServerStrategies(identityKey: string, students: Student[]) {
  const [strategies, setStrategies] = useState<Record<string, StrategyRead | null>>({})
  const [sections, setSections] = useState<StrategySection[]>([])
  const [tasks, setTasks] = useState<StrategyTask[]>([])
  const [status, setStatus] = useState<LoadStatus>('loading')
  const [error, setError] = useState<unknown>(null)
  const [partialErrorCount, setPartialErrorCount] = useState(0)
  const studentKey = useMemo(() => students.map(student => `${student.id}:${student.version ?? 0}`).sort().join('|'), [students])
  const studentsRef = useRef(students)
  studentsRef.current = students

  const applyBundle = useCallback((studentId: string, bundle: StudentStrategyBundle) => {
    setStrategies(current => ({ ...current, [studentId]: bundle.strategy }))
    setSections(current => [...current.filter(section => section.studentId !== studentId), ...bundle.sections])
    setTasks(current => {
      const previousById = new Map(current.filter(task => task.studentId === studentId).map(task => [task.id, task]))
      const refreshed = bundle.tasks.map(task => ({ ...task, history: previousById.get(task.id)?.history ?? task.history }))
      return [...current.filter(task => task.studentId !== studentId), ...refreshed]
    })
  }, [])

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus(current => current === 'ready' ? 'ready' : 'loading')
    setError(null)
    try {
      const currentStudents = studentsRef.current
      const bundleResults = await Promise.allSettled(currentStudents.map(student => loadStudentBundle(student, signal)))
      if (signal?.aborted) return
      const settled = partitionSettled(bundleResults)
      if (currentStudents.length && !settled.values.length) throw settled.errors[0]
      const nextStrategies: Record<string, StrategyRead | null> = {}
      const nextSections: StrategySection[] = []
      const nextTasks: StrategyTask[] = []
      let nestedPartialErrors = 0
      bundleResults.forEach((result, index) => {
        if (result.status !== 'fulfilled') return
        const student = currentStudents[index]
        nextStrategies[student.id] = result.value.strategy
        nextSections.push(...result.value.sections)
        nextTasks.push(...result.value.tasks)
        nestedPartialErrors += result.value.partialErrorCount
      })
      setStrategies(nextStrategies); setSections(nextSections); setTasks(nextTasks); setPartialErrorCount(settled.errors.length+nestedPartialErrors); setStatus('ready')
    } catch (nextError) {
      if (nextError instanceof DOMException && nextError.name === 'AbortError') return
      setPartialErrorCount(0); setError(nextError); setStatus('error')
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [identityKey, studentKey, load])

  const refreshStudent = useCallback(async (studentId: string, signal?: AbortSignal) => {
    const student = students.find(item => item.id === studentId)
    if (!student) return null
    const bundle = await loadStudentBundle(student, signal)
    applyBundle(studentId, bundle)
    return bundle
  }, [applyBundle, students])

  const evictStudent = useCallback((studentId: string) => {
    setStrategies(current => { const next={...current};delete next[studentId];return next })
    setSections(current => current.filter(section => section.studentId !== studentId))
    setTasks(current => current.filter(task => task.studentId !== studentId))
  }, [])

  const withConflictRefresh = useCallback(async <T,>(studentId: string, request: () => Promise<T>) => {
    try { return await request() }
    catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) await refreshStudent(studentId).catch(() => undefined)
      throw requestError
    }
  }, [refreshStudent])

  const ensureStrategy = useCallback(async (studentId: string) => {
    const current = strategies[studentId]
    if (current) return current
    try {
      const created = await strategiesApi.createForStudent(studentId)
      setStrategies(items => ({ ...items, [studentId]: created }))
      return created
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) {
        const fresh = await strategiesApi.getForStudent(studentId)
        setStrategies(items => ({ ...items, [studentId]: fresh }))
        return fresh
      }
      throw requestError
    }
  }, [strategies])

  const createSection = useCallback(async (studentId: string, title: string) => {
    const strategy = await ensureStrategy(studentId)
    const position = sections.filter(section => section.studentId === studentId).length
    const next = sectionFromApi(await strategiesApi.createSection(strategy.id, title, position), studentId)
    setSections(items => replaceById(items, next))
    return next
  }, [ensureStrategy, sections])

  const renameSection = useCallback(async (section: StrategySection, title: string) => {
    const next = sectionFromApi(await withConflictRefresh(section.studentId, () => strategiesApi.updateSection(section.id, section.version ?? 1, title)), section.studentId)
    setSections(items => replaceById(items, next))
    return next
  }, [withConflictRefresh])

  const reorderSections = useCallback(async (studentId: string, ordered: StrategySection[]) => {
    const strategy = strategies[studentId]
    if (!strategy || ordered.length < 1) return
    const wires = await withConflictRefresh(studentId, () => strategiesApi.reorderSections(strategy.id, ordered.map((section, position) => ({ id: section.id, expected_version: section.version ?? 1, position }))))
    setSections(items => [...items.filter(section => section.studentId !== studentId), ...wires.map(section => sectionFromApi(section, studentId))])
  }, [strategies, withConflictRefresh])

  const approvalForTask = useCallback((taskId: string) => {
    const task = tasks.find(item => item.id === taskId)
    return task?.approvalId ? { id: task.approvalId, task_id: task.id, status: task.approvalStatus!, comment: task.approvalComment, created_at: task.approvalSentAt || task.updatedAt, updated_at: task.updatedAt, version: task.approvalVersion ?? 1 } satisfies ApprovalRead : null
  }, [tasks])

  const mapTaskWire = useCallback((wire: StrategyTaskRead, approval?: ApprovalRead | null, history?: TaskHistoryRead[]) => {
    const student = students.find(item => strategies[item.id]?.id === wire.strategy_id)
    if (!student) throw new Error('Strategy student is unavailable')
    const previous = tasks.find(item => item.id === wire.id)
    const next = taskFromApi(wire, student.id, approval === undefined ? approvalForTask(wire.id) : approval, student.stage, history ?? [])
    return { ...next, history: history ? next.history : previous?.history ?? [] }
  }, [approvalForTask, strategies, students, tasks])

  const createTask = useCallback(async (draft: StrategyTask) => {
    if (!draft.sectionId) throw new ApiError(422, 'section_required', 'Section is required')
    const wire = await strategiesApi.createTask(draft.sectionId, { title: draft.title.trim(), description: draft.description, materials: draft.materials, links: taskLinks(draft), period_text: draft.period, due_at: draft.dueAt || null, position: draft.order })
    const next = mapTaskWire(wire, null)
    setTasks(items => replaceById(items, next))
    return next
  }, [mapTaskWire])

  const updateTask = useCallback(async (task: StrategyTask) => {
    const wire = await withConflictRefresh(task.studentId, () => strategiesApi.updateTask(task.id, { expected_version: task.version ?? 1, title: task.title.trim(), description: task.description, materials: task.materials, links: taskLinks(task), period_text: task.period, due_at: task.dueAt || null }))
    const next = mapTaskWire(wire)
    setTasks(items => replaceById(items, next))
    return next
  }, [mapTaskWire, withConflictRefresh])

  const changeStatus = useCallback(async (task: StrategyTask, studyStatus: StudyStatus) => {
    const wire = await withConflictRefresh(task.studentId, () => strategiesApi.changeStatus(task.id, task.version ?? 1, studyStatus))
    const next = mapTaskWire(wire)
    setTasks(items => replaceById(items, next))
    return next
  }, [mapTaskWire, withConflictRefresh])

  const setTaskArchived = useCallback(async (task: StrategyTask, archived: boolean) => {
    const wire = await withConflictRefresh(task.studentId, () => archived ? strategiesApi.archiveTask(task.id, task.version ?? 1) : strategiesApi.restoreTask(task.id, task.version ?? 1))
    const next = mapTaskWire(wire)
    setTasks(items => replaceById(items, next))
    return next
  }, [mapTaskWire, withConflictRefresh])

  const reorderTasks = useCallback(async (task: StrategyTask, delta: number) => {
    const peers = tasks.filter(item => item.sectionId === task.sectionId).sort((a, b) => a.order - b.order)
    const index = peers.findIndex(item => item.id === task.id)
    const target = peers[index + delta]
    if (!target) return
    const ordered = [...peers]
    ;[ordered[index], ordered[index + delta]] = [ordered[index + delta], ordered[index]]
    const wires = await withConflictRefresh(task.studentId, () => strategiesApi.reorderTasks(task.sectionId, ordered.map((item, position) => ({ id: item.id, expected_version: item.version ?? 1, position }))))
    const mapped = wires.map(wire => mapTaskWire(wire))
    const mappedIds = new Set(mapped.map(item => item.id))
    setTasks(items => [...items.filter(item => !mappedIds.has(item.id)), ...mapped])
  }, [mapTaskWire, tasks, withConflictRefresh])

  const loadHistory = useCallback(async (task: StrategyTask) => {
    const first = await strategiesApi.history(task.id)
    const all = [...first.items]
    let cursor = first.next_cursor
    while (cursor) { const page = await strategiesApi.history(task.id, cursor); all.push(...page.items); cursor = page.next_cursor }
    const wire = await strategiesApi.getTask(task.id)
    const next = mapTaskWire(wire, undefined, all)
    setTasks(items => replaceById(items, next))
    return next
  }, [mapTaskWire])

  const createApproval = useCallback(async (task: StrategyTask, comment = '') => {
    if (task.approvalId) return approvalForTask(task.id)!
    let approval: ApprovalRead
    try { approval = await strategiesApi.createApproval(task.id, comment) }
    catch (requestError) {
      if (!(requestError instanceof ApiError) || requestError.code !== 'approval_exists') throw requestError
      approval = await strategiesApi.getApproval(task.id)
    }
    const next = { ...task, approvalId: approval.id, approvalVersion: approval.version, approvalStatus: approval.status, approvalComment: approval.comment, updatedAt: approval.updated_at }
    setTasks(items => replaceById(items, next))
    return approval
  }, [approvalForTask])

  const transitionApproval = useCallback(async (task: StrategyTask, approvalStatus: ApprovalStatus, comment?: string) => {
    const existing = task.approvalId ? approvalForTask(task.id) : await createApproval(task, comment ?? '')
    if (!existing) throw new Error('Approval is unavailable')
    if (existing.status === approvalStatus) return existing
    const approval = await withConflictRefresh(task.studentId, () => strategiesApi.transitionApproval(task.id, existing.version, approvalStatus, comment))
    setTasks(items => items.map(item => item.id === task.id ? { ...item, approvalId: approval.id, approvalVersion: approval.version, approvalStatus: approval.status, approvalComment: approval.comment, updatedAt: approval.updated_at, approvalSentAt: approval.status === 'sent' ? approval.updated_at : item.approvalSentAt } : item))
    return approval
  }, [approvalForTask, createApproval, withConflictRefresh])

  return { strategies, sections, tasks, status, error, partialErrorCount, load, refreshStudent, evictStudent, ensureStrategy, createSection, renameSection, reorderSections, createTask, updateTask, changeStatus, setTaskArchived, reorderTasks, loadHistory, createApproval, transitionApproval }
}
