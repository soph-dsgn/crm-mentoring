import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'error' })

try {
  const groups = await server.ssrLoadModule('/src/api/groups.ts')
  const students = await server.ssrLoadModule('/src/api/students.ts')
  const mappers = await server.ssrLoadModule('/src/api/mappers.ts')
  const state = await server.ssrLoadModule('/src/groups/groupStudentState.ts')
  const users = await server.ssrLoadModule('/src/api/users.ts')

  const groupWire = {
    id: 'group-server-1', curator_id: 'curator-1', name: 'Серверная группа', starts_at: '2026-11-01', ends_at: null,
    actual_ends_at: null, status: 'active', status_before_archive: null, notes: 'Контекст', duration_months: '6.5',
    created_at: '2026-11-01T09:00:00Z', updated_at: '2026-11-02T09:00:00Z', version: 3,
  }
  const mappedGroup = mappers.groupFromApi(groupWire)
  assert.equal(mappedGroup.id, groupWire.id)
  assert.equal(mappedGroup.curatorId, 'curator-1')
  assert.equal(mappedGroup.version, 3)
  assert.equal(mappedGroup.durationMonths, 6.5)
  assert.equal(mappedGroup.serverBacked, true)

  const studentWire = {
    id: 'student-server-1', group_id: groupWire.id, user_id: null, name: 'Тестовая Ученица', age: 24, photo: '', avatar_index: 2,
    stage: 'portfolio', stage_known: true, starts_at: '2026-11-01', level: 'Junior', desired_position: 'Designer', career_goal: '',
    links: { portfolio: 'https://example.com/work' }, background: '', experience: '', strengths: '', growth_areas: '', difficulties: '',
    expectations: '', personal_notes: '', point_a: '', point_b: '', notes: '', archived_at: null,
    strategy_updated_at: '2026-11-02T10:00:00Z', created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-02T10:00:00Z', version: 4,
  }
  const mappedStudent = mappers.studentFromApi(studentWire)
  assert.equal(mappedStudent.groupId, groupWire.id)
  assert.equal(mappedStudent.links.portfolio, 'https://example.com/work')
  assert.equal(mappedStudent.version, 4)
  assert.equal(mappedStudent.serverBacked, true)

  const owner = { id: 'owner-1', role: 'admin', is_owner: true, is_active: true, must_change_password: false }
  const assigned = { ...owner, id: 'curator-1', is_owner: false }
  const unassigned = { ...assigned, id: 'curator-2' }
  assert.equal(state.canWriteGroup(owner, mappedGroup), true)
  assert.equal(state.canWriteGroup(assigned, mappedGroup), true)
  assert.equal(state.canWriteGroup(unassigned, mappedGroup), false)
  assert.equal(state.canWriteStudent(unassigned, mappedStudent, [mappedGroup]), false)

  const legacy = {
    version: 3, groups: [{ id: 'legacy-group' }], students: [{ id: 'legacy-student' }],
    sections: [{ id: 'legacy-section' }], tasks: [{ id: 'legacy-task', studentId: mappedStudent.id }],
    meetings: [{ id: 'legacy-meeting', studentId: mappedStudent.id }],
    homeworks: [{ id: 'legacy-homework', studentId: mappedStudent.id }], demo: false,
  }
  const isolated = state.serverDomainData(legacy, [mappedGroup], [mappedStudent])
  assert.deepEqual(isolated.groups, [mappedGroup])
  assert.deepEqual(isolated.students, [mappedStudent])
  assert.deepEqual(isolated.sections, [])
  assert.deepEqual(isolated.tasks, [])
  assert.deepEqual(isolated.meetings, [])
  assert.deepEqual(isolated.homeworks, [])
  assert.equal(legacy.groups[0].id, 'legacy-group')
  assert.equal(legacy.tasks[0].id, 'legacy-task')
  const collidingServer = { id: 'same-id', serverBacked: true }
  const collidingLegacy = { id: 'same-id' }
  assert.equal(state.recordForSource('same-id', 'server', [collidingServer], [collidingLegacy]), collidingServer)
  assert.equal(state.recordForSource('same-id', 'legacy', [collidingServer], [collidingLegacy]), collidingLegacy)

  const requests = []
  const originalFetch = globalThis.fetch
  globalThis.document = { cookie: 'kuratorskaya_csrf=csrf-value' }
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    requests.push([url, init])
    if (url.startsWith('/api/v1/groups?')) {
      const second = url.includes('cursor=next-groups')
      return Response.json({ items: second ? [{ ...groupWire, id: 'group-server-2' }] : [groupWire], next_cursor: second ? null : 'next-groups' })
    }
    if (url.includes('/students?')) {
      const second = url.includes('cursor=next-students')
      return Response.json({ items: second ? [{ ...studentWire, id: 'student-server-2' }] : [studentWire], next_cursor: second ? null : 'next-students' })
    }
    return Response.json(url.includes('/students/') ? studentWire : groupWire)
  }
  try {
    assert.equal((await groups.groupsApi.listAll()).length, 2)
    assert.equal((await students.studentsApi.listAll(groupWire.id)).length, 2)
    await groups.groupsApi.update(groupWire.id, { expected_version: 3, name: 'Обновлено' })
    await groups.groupsApi.archive(groupWire.id, 3)
    await students.studentsApi.create(groupWire.id, { name: 'Новая ученица' })
    await students.studentsApi.update(studentWire.id, { expected_version: 4, point_a: 'Старт' })
  } finally {
    globalThis.fetch = originalFetch
    delete globalThis.document
  }
  assert.match(requests[1][0], /cursor=next-groups/)
  assert.match(requests[3][0], /cursor=next-students/)
  assert.deepEqual(JSON.parse(requests[4][1].body), { expected_version: 3, name: 'Обновлено' })
  assert.deepEqual(JSON.parse(requests[5][1].body), { expected_version: 3 })
  assert.deepEqual(JSON.parse(requests[6][1].body), { name: 'Новая ученица' })
  assert.deepEqual(JSON.parse(requests[7][1].body), { expected_version: 4, point_a: 'Старт' })
  assert.equal(requests.slice(4).every(([, init]) => init.headers.get('X-CSRF-Token') === 'csrf-value'), true)

  const conflict = new groups.ApiError(409, 'version_conflict', 'stale')
  assert.equal(state.groupStudentErrorMessage(conflict), 'Данные уже изменились в другой сессии. Мы загрузили актуальную версию — проверьте её перед повторным сохранением')
  assert.equal(state.groupStudentErrorMessage(new groups.ApiError(403, 'forbidden', 'no')), 'У вас нет прав изменять эту группу или профиль')
  assert.equal(state.groupStudentErrorMessage(new groups.ApiError(0, 'connection_error', 'offline')), 'Не удалось подключиться к серверу')

  const accountRequests = []
  globalThis.fetch = async (input, init) => {
    accountRequests.push([String(input), init])
    return Response.json({ student_id: studentWire.id, user: { id: 'student-user', login: 'student.login' }, temporary_password: 'one-time' })
  }
  try {
    await users.usersApi.createStudentAccount(studentWire.id, 'student.login')
    await users.usersApi.getStudentAccount(studentWire.id)
    await users.usersApi.deactivateStudentAccount(studentWire.id)
    await users.usersApi.resetPassword('student-user')
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.deepEqual(JSON.parse(accountRequests[0][1].body), { login: 'student.login' })
  assert.equal(accountRequests[0][0], `/api/v1/admin/students/${studentWire.id}/account`)
  assert.equal(accountRequests[1][1].method ?? 'GET', 'GET')
  assert.match(accountRequests[2][0], /deactivate-account$/)
  assert.match(accountRequests[3][0], /users\/student-user\/reset-password$/)

  console.log('Groups/students integration verification passed')
} finally {
  await server.close()
}
