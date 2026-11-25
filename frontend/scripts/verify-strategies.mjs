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

  const importState = await server.ssrLoadModule('/src/strategies/strategyImportState.ts')
  const importDraft = {
    source_title: 'Тестовая | Стратегия действий', sha256: 'a'.repeat(64), page_count: 2,
    profile: { point_a: 'Опыт: дизайн', point_b: null, telegram: 'https://t.me/test_handle' },
    sections: [{ title: 'Часть 1', tasks: [
      { title: 'Первая', description: '', period_text: '', materials: [], study_status: 'done' },
      { title: 'Вторая', description: '', period_text: '', materials: [], study_status: 'hold' },
      { title: 'Третья', description: '', period_text: '', materials: [], study_status: 'done' },
    ] }],
    warnings: [{ code: 'status_missing', count: 2, examples: [] }],
  }
  const importStudent = { id: 'student-1', name: 'Тестовая Ученица', pointA: 'Уже заполнено', pointB: '', links: { telegram: '' }, version: 4 }
  const selection = importState.defaultProfileSelection(importStudent, importDraft.profile)
  assert.deepEqual(selection, { point_a: false, point_b: false, telegram: true })
  assert.deepEqual(importState.statusCounts(importDraft), [['hold', 'На паузе', 1], ['done', 'Выполнено', 2]])
  assert.equal(importState.taskTotal(importDraft), 3)
  assert.equal(importState.sourceNameMismatch(importDraft, importStudent), null)
  assert.equal(importState.sourceNameMismatch(importDraft, { ...importStudent, name: 'Другая' }), 'Тестовая')
  const importPayload = importState.buildImportPayload(importDraft, importStudent, selection, 'strategy.pdf')
  assert.deepEqual(importPayload.profile, { telegram: 'https://t.me/test_handle' })
  assert.equal(importPayload.expected_version, 4)
  assert.equal(importPayload.source.sha256, importDraft.sha256)
  assert.match(importState.importWarningLabel('status_missing'), /Не начато/)
  assert.match(importState.strategyImportErrorMessage(new http.ApiError(409, 'strategy_not_empty', 'x')), /пустую стратегию/)
  const previewCalls = []
  const fetchBeforePreview = globalThis.fetch
  globalThis.fetch = async (url, init) => { previewCalls.push({ url, init }); return new Response(JSON.stringify(importDraft), { status: 200, headers: { 'content-type': 'application/json' } }) }
  try {
    const preview = await api.strategiesApi.previewImport('student-1', new Blob(['%PDF'], { type: '' }))
    assert.equal(preview.sha256, importDraft.sha256)
    assert.equal(previewCalls[0].url, '/api/v1/students/student-1/strategy-import/preview')
    assert.equal(new Headers(previewCalls[0].init.headers).get('Content-Type'), 'application/pdf')
  } finally {
    globalThis.fetch = fetchBeforePreview
  }
} finally {
  await server.close()
}
