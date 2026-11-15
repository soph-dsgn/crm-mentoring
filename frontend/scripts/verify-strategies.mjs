import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'error' })

try {
  const api = await server.ssrLoadModule('/src/api/strategies.ts')
  const state = await server.ssrLoadModule('/src/strategies/strategyState.ts')
  const http = await server.ssrLoadModule('/src/api/http.ts')
  const settled = await server.ssrLoadModule('/src/api/settled.ts')

  const strategy = { id: 'strategy-1', student_id: 'student-1', source_metadata: {}, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:00:00Z', version: 1 }
  const section = { id: 'section-1', strategy_id: strategy.id, title: 'Портфолио', position: 0, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:00:00Z', version: 2 }
  const task = { id: 'task-1', strategy_id: strategy.id, section_id: section.id, title: 'Собрать кейс', description: 'Описание', materials: ['Чек-лист'], links: { portfolio: 'https://example.com/work' }, period_text: 'Неделя 1', due_at: null, position: 0, study_status: 'in_progress', review_status: 'none', archived_at: null, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-02T10:00:00Z', version: 3 }
  const approval = { id: 'approval-1', task_id: task.id, status: 'revision', comment: 'Поправить структуру', created_at: '2026-11-02T10:00:00Z', updated_at: '2026-11-03T10:00:00Z', version: 4 }
  const mappedSection = state.sectionFromApi(section, strategy.student_id)
  const mappedTask = state.taskFromApi(task, strategy.student_id, approval)
  assert.equal(mappedSection.serverBacked, true)
  assert.equal(mappedSection.version, 2)
  assert.equal(mappedTask.id, task.id)
  assert.equal(mappedTask.serverBacked, true)
  assert.equal(mappedTask.approvalId, approval.id)
  assert.equal(mappedTask.approvalStatus, 'revision')
  assert.equal(mappedTask.studyStatus, 'in_progress')
  assert.equal(mappedTask.reviewStatus, 'none')
  assert.equal(mappedTask.url, 'https://example.com/work')
  assert.deepEqual(mappedTask.serverLinks, task.links)

  const partial = settled.partitionSettled([
    { status: 'fulfilled', value: 'loaded' },
    { status: 'rejected', reason: new Error('section unavailable') },
  ])
  assert.deepEqual(partial.values, ['loaded'])
  assert.equal(partial.errors.length, 1)
  assert.deepEqual(settled.filterFulfilledSources(['available','revoked'], [
    { status: 'fulfilled', value: [] },
    { status: 'rejected', reason: new Error('permission changed') },
  ]), ['available'])

  const legacy = { version: 3, groups: [], students: [{ id: strategy.student_id, serverBacked: true }], sections: [{ id: 'same-id' }], tasks: [{ id: task.id, title: 'Локальная задача' }], meetings: [], homeworks: [], demo: false }
  const inaccessibleSection = { ...mappedSection, id: 'inaccessible-section', studentId: 'student-removed' }
  const inaccessibleTask = { ...mappedTask, id: 'inaccessible-task', studentId: 'student-removed', sectionId: inaccessibleSection.id }
  const merged = state.withServerStrategies(legacy, [mappedSection, inaccessibleSection], [mappedTask, inaccessibleTask])
  assert.equal(merged.sections[0], mappedSection)
  assert.equal(merged.tasks[0], mappedTask)
  assert.equal(merged.sections.length, 1)
  assert.equal(merged.tasks.length, 1)
  assert.equal(legacy.tasks[0].title, 'Локальная задача')

  const requests = []
  const originalFetch = globalThis.fetch
  globalThis.document = { cookie: 'kuratorskaya_csrf=csrf-strategy' }
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    requests.push([url, init])
    if (url.endsWith('/strategy')) return Response.json(strategy)
    if (url.endsWith('/sections')) return Response.json([section])
    if (url.endsWith('/tasks')) return Response.json([task])
    if (url.endsWith('/approval')) return Response.json(approval)
    if (url.endsWith('/history')) return Response.json({ items: [], next_cursor: null })
    return Response.json(url.includes('reorder') ? [url.includes('sections/reorder') ? section : task] : url.includes('approval/transition') ? approval : task)
  }
  try {
    await api.strategiesApi.getForStudent('student-1')
    await api.strategiesApi.listSections(strategy.id)
    await api.strategiesApi.listTasks(section.id, true)
    await api.strategiesApi.reorderSections(strategy.id, [{ id: section.id, expected_version: 2, position: 0 }])
    await api.strategiesApi.reorderTasks(section.id, [{ id: task.id, expected_version: 3, position: 0 }])
    await api.strategiesApi.changeStatus(task.id, 3, 'hold')
    await api.strategiesApi.transitionApproval(task.id, 4, 'sent', 'Готово')
    await api.strategiesApi.history(task.id)
  } finally {
    globalThis.fetch = originalFetch
    delete globalThis.document
  }
  assert.deepEqual(JSON.parse(requests[3][1].body), { items: [{ id: section.id, expected_version: 2, position: 0 }] })
  assert.deepEqual(JSON.parse(requests[4][1].body), { items: [{ id: task.id, expected_version: 3, position: 0 }] })
  assert.deepEqual(JSON.parse(requests[5][1].body), { expected_version: 3, study_status: 'hold' })
  assert.deepEqual(JSON.parse(requests[6][1].body), { expected_version: 4, status: 'sent', comment: 'Готово' })
  assert.equal(requests.slice(3, 7).every(([, init]) => init.headers.get('X-CSRF-Token') === 'csrf-strategy'), true)

  assert.equal(state.strategyErrorMessage(new http.ApiError(409, 'version_conflict', 'stale')), 'Данные изменились в другой сессии. Мы загрузили актуальную версию — проверьте изменения и повторите действие')
  assert.equal(state.strategyErrorMessage(new http.ApiError(409, 'homework_review_pending', 'locked')), 'Статус задачи заблокирован, пока домашняя работа находится на проверке')
  assert.equal(state.strategyErrorMessage(new http.ApiError(403, 'forbidden', 'no')), 'У вас нет прав изменять эту стратегию')

  console.log('Strategies/tasks/Anya approval integration verification passed')
} finally {
  await server.close()
}
