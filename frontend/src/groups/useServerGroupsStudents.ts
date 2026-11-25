import { useCallback, useEffect, useState } from 'react'
import { groupsApi } from '../api/groups'
import { groupCreateToApi, groupFromApi, groupUpdateToApi, studentCreateToApi, studentFromApi, studentUpdateToApi } from '../api/mappers'
import { studentsApi } from '../api/students'
import { ApiError } from '../api/http'
import { filterFulfilledSources, partitionSettled } from '../api/settled'
import type { Group, GroupStatus, Student } from '../types'

type LoadStatus = 'loading' | 'ready' | 'error'

function replaceById<T extends { id: string }>(items: T[], next: T): T[] {
  return items.some(item => item.id === next.id) ? items.map(item => item.id === next.id ? next : item) : [...items, next]
}

export function useServerGroupsStudents(identityKey: string) {
  const [groups, setGroups] = useState<Group[]>([])
  const [students, setStudents] = useState<Student[]>([])
  const [status, setStatus] = useState<LoadStatus>('loading')
  const [error, setError] = useState<unknown>(null)
  const [partialErrorCount, setPartialErrorCount] = useState(0)

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus(current => current === 'ready' ? 'ready' : 'loading')
    setError(null)
    try {
      const groupWires = await groupsApi.listAll({}, signal)
      const nextGroups = groupWires.map(groupFromApi)
      const rosterResults = await Promise.allSettled(nextGroups.map(group => studentsApi.listAll(group.id, signal)))
      if (signal?.aborted) return
      const rosterPages = partitionSettled(rosterResults)
      if (nextGroups.length && !rosterPages.values.length) throw rosterPages.errors[0]
      const nextStudents = rosterPages.values.flat().map(studentFromApi)
      const loadedGroups = filterFulfilledSources(nextGroups, rosterResults)
      setGroups(loadedGroups)
      setStudents(nextStudents)
      setPartialErrorCount(rosterPages.errors.length)
      setStatus('ready')
    } catch (nextError) {
      if (nextError instanceof DOMException && nextError.name === 'AbortError') return
      setPartialErrorCount(0)
      setError(nextError)
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [identityKey, load])

  const refreshGroup = useCallback(async (groupId: string, signal?: AbortSignal) => {
    const next = groupFromApi(await groupsApi.get(groupId, signal))
    setGroups(current => replaceById(current, next))
    return next
  }, [])

  const refreshStudent = useCallback(async (studentId: string, signal?: AbortSignal) => {
    const next = studentFromApi(await studentsApi.get(studentId, signal))
    setStudents(current => replaceById(current, next))
    return next
  }, [])

  const withConflictRefresh = useCallback(async <T,>(request: () => Promise<T>, refresh: () => Promise<unknown>) => {
    try {
      return await request()
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) await refresh().catch(() => undefined)
      throw requestError
    }
  }, [])

  const saveGroup = useCallback(async (group: Group) => {
    const wire = group.serverBacked
      ? await withConflictRefresh(() => groupsApi.update(group.id, groupUpdateToApi(group)), () => refreshGroup(group.id))
      : await groupsApi.create(groupCreateToApi(group))
    const next = groupFromApi(wire)
    setGroups(current => replaceById(current, next))
    return next
  }, [refreshGroup, withConflictRefresh])

  const changeGroupStatus = useCallback(async (group: Group, nextStatus: GroupStatus) => {
    const expectedVersion = group.version ?? 1
    const request = nextStatus === 'archived'
      ? () => groupsApi.archive(group.id, expectedVersion)
      : group.status === 'archived'
        ? () => groupsApi.restore(group.id, expectedVersion)
        : () => groupsApi.update(group.id, { expected_version: expectedVersion, status: nextStatus, ...(nextStatus === 'completed' && !group.actualEndsAt ? { actual_ends_at: new Date().toISOString().slice(0, 10) } : {}) })
    const next = groupFromApi(await withConflictRefresh(request, () => refreshGroup(group.id)))
    setGroups(current => replaceById(current, next))
    return next
  }, [refreshGroup, withConflictRefresh])

  const saveStudent = useCallback(async (student: Student) => {
    const wire = student.serverBacked
      ? await withConflictRefresh(() => studentsApi.update(student.id, studentUpdateToApi(student)), () => refreshStudent(student.id))
      : await studentsApi.create(student.groupId, studentCreateToApi(student))
    const next = studentFromApi(wire)
    setStudents(current => replaceById(current, next))
    return next
  }, [refreshStudent, withConflictRefresh])

  const setStudentArchived = useCallback(async (student: Student, archived: boolean) => {
    const expectedVersion = student.version ?? 1
    const request = archived ? () => studentsApi.archive(student.id, expectedVersion) : () => studentsApi.restore(student.id, expectedVersion)
    const next = studentFromApi(await withConflictRefresh(request, () => refreshStudent(student.id)))
    setStudents(current => replaceById(current, next))
    return next
  }, [refreshStudent, withConflictRefresh])

  const transferStudent = async (student: Student, targetGroupId: string) => {
    const wire = await withConflictRefresh(
      () => studentsApi.transfer(student.id, targetGroupId, student.version ?? 1),
      () => refreshStudent(student.id),
    )
    const next = studentFromApi(wire)
    setStudents(current => replaceById(current, next))
    return next
  }

  return { transferStudent, groups, students, status, error, partialErrorCount, load, refreshGroup, refreshStudent, saveGroup, changeGroupStatus, saveStudent, setStudentArchived }
}
