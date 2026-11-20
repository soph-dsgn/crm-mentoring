import assert from 'node:assert/strict'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { load } from 'cheerio'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'error' })

try {
  const meetings = await server.ssrLoadModule('/src/api/meetings.ts')
  const homeworks = await server.ssrLoadModule('/src/api/homeworks.ts')
  const state = await server.ssrLoadModule('/src/learning/learningState.ts')
  const learningHook = await server.ssrLoadModule('/src/learning/useServerLearning.ts')
  const http = await server.ssrLoadModule('/src/api/http.ts')
  const { HomeworkCard } = await server.ssrLoadModule('/src/HomeworkPage.tsx')
  const { default: StrategyPlan } = await server.ssrLoadModule('/src/StrategyPlan.tsx')

  const meetingWire = { id: 'meeting-1', student_id: 'student-1', date: '2026-11-12', title: 'Разбор портфолио', summary: 'Определили следующий шаг', notes: 'Заметка куратора', archived_at: null, created_at: '2026-11-12T10:00:00Z', updated_at: '2026-11-12T10:00:00Z', version: 2 }
  const taskWire = { id: 'task-1', task_id: 'task-1', position: 0, title: 'Собрать кейс', description: 'Описать решение', materials: ['Чек-лист'], links: { brief: 'https://example.com/brief' }, period_text: 'Неделя 1', due_at: null }
  const homeworkWire = { id: 'homework-1', strategy_id: 'strategy-1', title: 'Домашнее задание', description: 'Соберите материалы', links: {}, submission_text: 'Работа готова', submission_links: { work: 'https://example.com/work' }, curator_feedback: 'Добавьте выводы', due_at: null, status: 'submitted', issued_at: '2026-11-12T11:00:00Z', submitted_at: '2026-11-13T11:00:00Z', reviewed_at: null, archived_at: null, created_at: '2026-11-12T10:30:00Z', updated_at: '2026-11-13T11:00:00Z', version: 4, items: [taskWire] }
  const mappedMeeting = state.meetingFromApi(meetingWire)
  const mappedHomework = state.homeworkFromApi(homeworkWire, 'student-1')
  assert.equal(mappedMeeting.serverBacked, true)
  assert.equal(mappedMeeting.notes, 'Заметка куратора')
  assert.equal(mappedMeeting.version, 2)
  assert.equal(mappedHomework.serverBacked, true)
  assert.equal(mappedHomework.studentId, 'student-1')
  assert.equal(mappedHomework.workUrl, 'https://example.com/work')
  assert.equal(mappedHomework.items[0].description, 'Описать решение')
  assert.deepEqual(mappedHomework.items[0].links, taskWire.links)
  assert.equal(mappedHomework.items[0].period, 'Неделя 1')

  assert.deepEqual(state.homeworkActions({ ...mappedHomework, status: 'draft' }, true), ['issue', 'archive'])
  assert.deepEqual(state.homeworkActions({ ...mappedHomework, status: 'submitted' }, true), ['revision', 'accept'])
  assert.deepEqual(state.homeworkActions({ ...mappedHomework, status: 'accepted' }, true), ['archive'])
  assert.deepEqual(state.homeworkActions({ ...mappedHomework, archivedAt: '2026-11-14T10:00:00Z' }, true), ['restore'])
  assert.deepEqual(state.homeworkActions(mappedHomework, false), [])

  const legacy = { version: 3, groups: [], students: [{ id: 'student-1', serverBacked: true }], sections: [], tasks: [], meetings: [{ id: 'legacy-meeting', studentId: 'legacy-student' }], homeworks: [{ id: 'legacy-homework', studentId: 'legacy-student' }], demo: false }
  const merged = state.withServerLearning(legacy, [mappedMeeting], [mappedHomework])
  assert.deepEqual(merged.meetings.map(item => item.id), ['meeting-1'])
  assert.deepEqual(merged.homeworks.map(item => item.id), ['homework-1'])
  assert.equal(legacy.meetings[0].id, 'legacy-meeting')
  assert.equal(legacy.homeworks[0].id, 'legacy-homework')

  const previousRecords=[mappedMeeting,{...mappedMeeting,id:'meeting-2',studentId:'student-2'}]
  const refreshedRecords=learningHook.mergeLearningRecords(previousRecords,new Set(['student-1','student-2']),new Map([['student-1',[]]]))
  assert.deepEqual(refreshedRecords.map(item=>item.id),['meeting-2'],'успешный пустой ответ очищает только свою ученицу, а ошибка другого API сохраняет последние валидные данные')
  assert.equal(learningHook.shouldEvictLearningRecords(new http.ApiError(403,'forbidden','scope changed')),true)
  assert.equal(learningHook.shouldEvictLearningRecords(new http.ApiError(503,'connection_error','temporary')),false)

  const requests = []
  const originalFetch = globalThis.fetch
  globalThis.document = { cookie: 'kuratorskaya_csrf=csrf-learning' }
  globalThis.fetch = async (input, init = {}) => {
    requests.push([String(input), init])
    if (String(input).includes('/meetings')) return Response.json(String(input).endsWith('/meetings') && init.method !== 'POST' ? { items: [meetingWire], next_cursor: null } : meetingWire)
    if (String(input).endsWith('/history')) return Response.json({ items: [], next_cursor: null })
    return Response.json(String(input).includes('/homeworks?') ? { items: [homeworkWire], next_cursor: null } : homeworkWire)
  }
  try {
    await meetings.meetingsApi.list('student-1', undefined, true)
    await meetings.meetingsApi.create('student-1', { date: '2026-11-12', title: 'Разбор', summary: '', notes: '' })
    await meetings.meetingsApi.update('meeting-1', { expected_version: 2, summary: 'Итог' })
    await meetings.meetingsApi.archive('meeting-1', 3)
    await homeworks.homeworksApi.list('strategy-1', undefined, true)
    await homeworks.homeworksApi.create('strategy-1', { title: 'ДЗ', description: '', task_ids: ['task-1'], links: {}, due_at: null })
    await homeworks.homeworksApi.update('homework-1', { expected_version: 1, description: 'Текст' })
    await homeworks.homeworksApi.transition('homework-1', { expected_version: 2, status: 'issued' })
    await homeworks.homeworksApi.transition('homework-1', { expected_version: 3, status: 'submitted', submission_text: 'Работа', submission_links: { work: 'https://example.com/work' } })
    await homeworks.homeworksApi.history('homework-1')
  } finally {
    globalThis.fetch = originalFetch
    delete globalThis.document
  }
  assert.deepEqual(JSON.parse(requests[2][1].body), { expected_version: 2, summary: 'Итог' })
  assert.deepEqual(JSON.parse(requests[5][1].body).task_ids, ['task-1'])
  assert.deepEqual(JSON.parse(requests[7][1].body), { expected_version: 2, status: 'issued' })
  assert.deepEqual(JSON.parse(requests[8][1].body), { expected_version: 3, status: 'submitted', submission_text: 'Работа', submission_links: { work: 'https://example.com/work' } })
  assert.equal(requests.filter(([, init]) => init.method && init.method !== 'GET').every(([, init]) => init.headers.get('X-CSRF-Token') === 'csrf-learning'), true)

  assert.match(state.learningErrorMessage(new http.ApiError(409, 'version_conflict', 'stale')), /актуальн/)
  assert.match(state.learningErrorMessage(new http.ApiError(409, 'task_review_conflict', 'locked')), /другом домашнем задании/)
  assert.match(state.learningErrorMessage(new http.ApiError(403, 'forbidden', 'no')), /прав/)
  assert.match(state.learningErrorMessage(new Error('strategy_refresh_failed')), /ДЗ обновлено|Домашнее задание обновлено/)

  const noop=()=>{}
  const homeworkMarkup=renderToStaticMarkup(React.createElement(HomeworkCard,{homework:mappedHomework,onUpdate:noop,onTask:noop,taskExists:()=>true,onDelete:noop,onRestore:noop,onHistory:noop,canWrite:true}))
  assert.ok(homeworkMarkup.includes('Описать решение'))
  assert.ok(homeworkMarkup.includes('Чек-лист'))
  assert.ok(homeworkMarkup.includes('Вернуть на доработку'))
  assert.ok(homeworkMarkup.includes('Принять работу'))
  const snapshotDom=load(homeworkMarkup)
  assert.equal(snapshotDom('.homework-snapshot').length,1)
  assert.equal(snapshotDom('a[href="https://example.com/brief"]').length,1)

  const strategyTask={id:'task-done',studentId:'student-1',title:'Уже выполненная задача',description:'',stage:'start',status:'done',owner:'Не назначен',dueAt:'',url:'',comments:'',order:0,blocker:false,createdAt:'',updatedAt:'',reviewStatus:'accepted',approvalStatus:null,approvalType:'',approvalSentAt:'',approvalComment:'',history:[],sectionId:'section-1',studyStatus:'done',period:'',materials:[],serverBacked:true,strategyId:'strategy-1',version:2}
  const strategyMarkup=renderToStaticMarkup(React.createElement(StrategyPlan,{student:{id:'student-1',name:'Тестовая ученица',stage:'start',stageKnown:true},groupName:'Тестовая группа',sections:[{id:'section-1',studentId:'student-1',title:'Раздел',order:0,createdAt:'',serverBacked:true}],tasks:[strategyTask],onOpenTask:noop,onStatus:noop,onAddTask:noop,onAddSection:noop,onRenameSection:noop,onDeleteSection:noop,onMoveTask:noop,onMoveSection:noop,onChangeSection:noop,onGenerate:async()=>'',onUpdateHomework:noop,serverManaged:true,hasStrategy:true,canEdit:true}))
  assert.ok(strategyMarkup.includes('Выбрать для ДЗ'))
  assert.equal(load(strategyMarkup)('input[type="checkbox"]').length,1)
  console.log('Meetings/homeworks integration verification passed')
} finally {
  await server.close()
}
