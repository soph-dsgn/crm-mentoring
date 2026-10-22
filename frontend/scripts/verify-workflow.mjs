import assert from 'node:assert/strict'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { readFile } from 'node:fs/promises'

const server = await createServer({ server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'error' })
try {
  const dataModule = await server.ssrLoadModule('/src/data.ts')
  const { default: StrategyPlan } = await server.ssrLoadModule('/src/StrategyPlan.tsx')
  const { default: AnyaPage } = await server.ssrLoadModule('/src/AnyaPage.tsx')
  const { default: TaskDetail } = await server.ssrLoadModule('/src/TaskDetail.tsx')
  const { default: TaskForm } = await server.ssrLoadModule('/src/TaskForm.tsx')
  const { default: MeetingWorkspace } = await server.ssrLoadModule('/src/MeetingWorkspace.tsx')
  const { GroupsPage } = await server.ssrLoadModule('/src/GroupViews.tsx')
  const { normalizeData, applyApprovalStatus, applyHomeworkPatch, needsAnyaApproval, planProgress, curriculumProgress, taskColumn, homeworkText, addCalendarMonths } = dataModule
  const { mergeStrategies } = await server.ssrLoadModule('/src/strategyImport.ts')
  const seed = JSON.parse(await readFile(new URL('../public/strategies/strategy-seed.json', import.meta.url), 'utf8'))
  const seeded = mergeStrategies(dataModule.emptyData(), seed)
  assert.equal(seeded.groups.length, 4)
  assert.equal(seeded.students.length, 19)
  assert.equal(seeded.sections.length, 90)
  assert.equal(seeded.tasks.length, 749)
  assert.deepEqual(seeded.groups.map(g=>[g.name,g.startsAt,g.endsAt]), [
    ['Группа 1','2026-08-03','2027-01-18'],
    ['Группа 2','2026-09-07','2027-03-07'],
    ['Группа 3','2026-09-17','2027-03-17'],
    ['Группа 4','2026-10-01','2027-04-01'],
  ])
  assert.equal(addCalendarMonths('2024-08-31',6),'2025-02-28')
  assert.equal(seeded.tasks.filter(t=>t.studyStatus==='done').length,384)
  assert.equal(seeded.tasks.filter(t=>t.studyStatus==='hold').length,131)
  assert.equal(seeded.tasks.filter(t=>t.studyStatus==='in_progress').length,110)
  assert.equal(seeded.tasks.filter(t=>t.studyStatus==='not_started').length,124)
  assert.equal(mergeStrategies(seeded, seed).tasks.length, 749)
  const partlyImported={...seeded,sections:seeded.sections.slice(1),tasks:seeded.tasks.slice(1)}
  const restored=mergeStrategies(partlyImported,seed)
  assert.equal(restored.sections.length,90)
  assert.equal(restored.tasks.length,749)
  assert.equal(mergeStrategies(restored,seed).tasks.length,749)
  const edited={...seeded,tasks:seeded.tasks.map((task,index)=>index===0?{...task,title:'Моя правка',studyStatus:'hold'}:task)}
  const afterMerge=mergeStrategies(edited,seed)
  assert.equal(afterMerge.tasks[0].title,'Моя правка')
  assert.equal(afterMerge.tasks[0].studyStatus,'hold')
  assert.equal(afterMerge.tasks.length,749)
  const previousStorage=globalThis.localStorage
  const beforeWeekly={...edited,version:3}
  const browserStore=new Map([[dataModule.STORAGE_KEY,JSON.stringify(beforeWeekly)]])
  globalThis.localStorage={getItem:key=>browserStore.get(key)??null,setItem:(key,value)=>browserStore.set(key,value)}
  try {
    assert.equal(dataModule.loadData().tasks[0].title,'Моя правка')
    assert.equal(JSON.parse(browserStore.get(dataModule.PRE_SECTION_BACKUP_KEY)).tasks[0].title,'Моя правка')
    assert.equal(JSON.parse(browserStore.get(dataModule.PRE_WEEKLY_BACKUP_KEY)).version,3)
  } finally { globalThis.localStorage=previousStorage }
  const legacy = normalizeData({ version: 1, groups: [], students: [], tasks: [
    { id: 'old', studentId: 'student', title: 'Старое задание', status: 'progress', dueAt: '', description: 'Инструкция', comments: '', materials: [], url: '' },
  ] })
  assert.equal(legacy.tasks.length, 1)
  assert.deepEqual(legacy.groupMeetings, [])
  assert.equal(taskColumn(legacy.tasks[0]), 'progress')
  const anyaLegacy = normalizeData({ version: 3, groups: [], students: [], tasks: [{ id: 'anya', studentId: 'student', title: 'Ревью', status: 'done', studyStatus: 'done', owner: 'Аня', approvalStatus: 'revision', reviewStatus: 'revision' }] })
  assert.equal(anyaLegacy.tasks[0].reviewStatus, 'none')
  assert.equal(taskColumn(anyaLegacy.tasks[0]), 'done')
  const approvalTask = { ...legacy.tasks[0], id: 'approval', title: 'Резюме', owner: 'Софья', approvalStatus: 'to_send', approvalType: 'Проверка резюме', approvalSentAt: '', approvalComment: '', url: 'https://example.com/resume' }
  const approvalData = { ...legacy, tasks: [approvalTask] }
  assert.ok(needsAnyaApproval(approvalTask))
  let approval = applyApprovalStatus(approvalData, 'approval', 'sent', '2026-10-21T10:00:00.000Z')
  approval = applyApprovalStatus(approval, 'approval', 'reviewing', '2026-10-21T11:00:00.000Z')
  approval = applyApprovalStatus(approval, 'approval', 'revision', '2026-10-21T12:00:00.000Z')
  assert.equal(approval.tasks[0].approvalStatus, 'revision')
  assert.equal(approval.tasks[0].studyStatus, approvalTask.studyStatus)
  assert.equal(approval.tasks[0].reviewStatus, approvalTask.reviewStatus)
  approval = {...approval,tasks:approval.tasks.map(task=>({...task,url:'https://example.com/resume-v2'}))}
  approval = applyApprovalStatus(approval, 'approval', 'sent', '2026-10-22T10:00:00.000Z')
  approval = applyApprovalStatus(approval, 'approval', 'approved', '2026-10-22T11:00:00.000Z')
  assert.equal(approval.tasks[0].approvalStatus, 'approved')
  assert.equal(approval.tasks[0].url, 'https://example.com/resume-v2')
  assert.equal(approval.tasks.length, 1)
  assert.equal(approval.tasks[0].approvalSentAt, '2026-10-22T10:00:00.000Z')
  assert.equal(approval.tasks[0].history.length, 5)
  assert.equal(normalizeData(JSON.parse(JSON.stringify(approval))).tasks[0].approvalStatus, 'approved')
  assert.deepEqual(planProgress([]), { done: 0, total: 0, percent: null })
  assert.deepEqual(curriculumProgress([]), { done: 0, total: 0, percent: null })
  const old = legacy.tasks[0]
  const backlog = { ...old, id: 'backlog', status: 'backlog', studyStatus: 'not_started', reviewStatus: 'none' }
  const data = { ...legacy, tasks: [old, backlog], homeworks: [{ id: 'homework', studentId: 'student', title: 'ДЗ', text: 'Исходный текст', items: [{ taskId: old.id, title: old.title, description: old.description, url: '', materials: [], dueAt: '' }], status: 'issued', issuedAt: '2026-10-21T10:00:00.000Z', submittedAt: '', workUrl: '', comment: '', dueAt: '', createdAt: '2026-10-21T09:00:00.000Z' }] }
  assert.deepEqual(planProgress(data.tasks), { done: 0, total: 1, percent: 0 })
  assert.deepEqual(curriculumProgress(data.tasks), { done: 0, total: 2, percent: 0 })
  const submitted = applyHomeworkPatch(data, 'homework', { status: 'submitted', workUrl: 'https://example.com/work', submittedAt: '2026-10-21T11:00:00.000Z' }, '2026-10-21T11:00:00.000Z')
  assert.equal(submitted.tasks[0].reviewStatus, 'pending')
  assert.equal(taskColumn(submitted.tasks[0]), 'progress')
  assert.equal(planProgress(submitted.tasks).percent, 0)
  const revision = applyHomeworkPatch(submitted, 'homework', { status: 'revision', comment: 'Уточнить кейс' }, '2026-10-21T12:00:00.000Z')
  assert.equal(revision.tasks[0].reviewStatus, 'revision')
  const resubmitted = applyHomeworkPatch(revision, 'homework', { status: 'submitted' }, '2026-10-21T13:00:00.000Z')
  const accepted = applyHomeworkPatch(resubmitted, 'homework', { status: 'accepted' }, '2026-10-21T14:00:00.000Z')
  assert.equal(taskColumn(accepted.tasks[0]), 'done')
  assert.deepEqual(planProgress(accepted.tasks), { done: 1, total: 1, percent: 100 })
  assert.deepEqual(curriculumProgress(accepted.tasks), { done: 1, total: 2, percent: 50 })
  assert.equal(accepted.tasks[0].history.length, 4)
  const afterEdit = applyHomeworkPatch(accepted, 'homework', { text: 'Перезаписанный текст', items: [] })
  assert.equal(afterEdit.homeworks[0].text, 'Исходный текст')
  assert.equal(afterEdit.homeworks[0].items.length, 1)
  const reloaded = normalizeData(JSON.parse(JSON.stringify(afterEdit)))
  assert.equal(reloaded.tasks[0].reviewStatus, 'accepted')
  assert.equal(reloaded.homeworks[0].text, 'Исходный текст')
  assert.match(homeworkText('Настя, твоё ДЗ:', [{ taskId: '1', title: 'Резюме', description: 'Собрать опыт', url: 'https://example.com/template', materials: [], dueAt: '' }]), /1\. Резюме — Собрать опыт\nhttps:\/\/example.com\/template/)
  const noop = () => {}
  const anyaMarkup = renderToStaticMarkup(React.createElement(AnyaPage, { data: { ...approvalData, tasks: [approvalTask], students: [{ id: 'student', groupId: 'group', name: 'Настя' }], groups: [{ id: 'group', name: 'Группа 1' }] }, onStudent: noop, onTask: noop, onApproval: noop, onComment: noop, onType: noop, onMaterial: noop, onDeadline: noop }))
  assert.ok(anyaMarkup.includes('Проверка резюме'))
  assert.ok(anyaMarkup.includes('Настя'))
  assert.ok(anyaMarkup.includes('Группа 1'))
  assert.ok(anyaMarkup.includes('Передать Ане на проверку'))
  assert.ok(anyaMarkup.includes('Материал, тип и заметки'))
  const detailMarkup = renderToStaticMarkup(React.createElement(TaskDetail, { task: submitted.tasks[0], studentName: 'Настя', groupName: 'Группа 1', sectionTitle: 'Часть 1', homeworkTitle: 'ДЗ', onHomework: noop, onStatus: noop, onPrepareApproval: noop, onEdit: noop }))
  assert.ok(detailMarkup.includes('Группа 1 · Настя'))
  assert.ok(detailMarkup.includes('Раздел стратегии: Часть 1'))
  assert.ok(detailMarkup.includes('Статус выполнения изменится после проверки'))
  assert.ok(detailMarkup.includes('Проверить работу · ДЗ'))
  assert.ok(detailMarkup.includes('Редактировать задачу'))
  const formMarkup = renderToStaticMarkup(React.createElement(TaskForm, { draft: old, setDraft: noop, sections: [], existing: true, onSave: noop, onCancel: noop, onDelete: noop }))
  assert.ok(formMarkup.includes('Этап и ответственные'))
  assert.ok(formMarkup.includes('Сроки и материалы'))
  const groupMarkup=renderToStaticMarkup(React.createElement(GroupsPage,{data:seeded,view:'groups',onView:noop,filter:'active',onFilter:noop,onOpen:noop,onStudent:noop,onNew:noop,onEdit:noop,onStatus:noop,onDelete:noop}))
  assert.ok(groupMarkup.includes('Что показать'))
  assert.ok(!groupMarkup.includes('Все ученицы'))
  const rosterMarkup=renderToStaticMarkup(React.createElement(GroupsPage,{data:seeded,view:'students',onView:noop,filter:'active',onFilter:noop,onOpen:noop,onStudent:noop,onNew:noop,onEdit:noop,onStatus:noop,onDelete:noop}))
  assert.ok(rosterMarkup.includes('Все ученицы'))
  const section={id:'section',studentId:'student',title:'Часть 1',order:0,createdAt:''}
  const markup = renderToStaticMarkup(React.createElement(StrategyPlan, { student: { id: 'student', name: 'Настя', stage: 'start' }, groupName:'Группа 1', sections: [section], tasks: [{...old,sectionId:'section'}], onOpenTask: noop, onStatus: noop, onQuickTask: noop, onAddSection: noop, onRenameSection: noop, onDeleteSection: noop, onMoveTask: noop, onChangeSection: noop, onGenerate: () => '', onUpdateHomework: noop }))
  assert.ok(markup.includes('Часть 1'))
  assert.ok(markup.includes('Стратегия Настя'))
  assert.ok(!markup.includes('study-board'))
  assert.ok(markup.includes('Статус задачи: Старое задание'))
  assert.ok(!markup.includes('Выбрать для ДЗ'))
  assert.ok(!markup.includes('Сформировать ДЗ'))
  const pendingMarkup = renderToStaticMarkup(React.createElement(StrategyPlan, { student: { id: 'student', name: 'Настя', stage: 'start' }, groupName:'Группа 1', sections: [], tasks: [submitted.tasks[0]], onOpenTask: noop, onStatus: noop, onQuickTask: noop, onAddSection: noop, onRenameSection: noop, onDeleteSection: noop, onMoveTask: noop, onChangeSection: noop, onGenerate: () => '', onUpdateHomework: noop }))
  assert.ok(pendingMarkup.includes('На проверке'))
  assert.match(pendingMarkup, /role="combobox"[^>]*disabled=""[^>]*class="ui-select-trigger study-status"/)
  assert.match(pendingMarkup, /class="ui-select-trigger study-status"[^>]*data-status="in_progress"[^>]*>.*?В процессе/)
  const group4=seeded.groups.find(group=>group.name==='Группа 4')
  const group4Members=seeded.students.filter(student=>student.groupId===group4.id)
  const firstStudent=group4Members[0]
  const weeklyTask=seeded.tasks.find(task=>task.studentId===firstStudent.id)
  const weeklyHomework={id:'weekly-homework',studentId:firstStudent.id,groupMeetingId:'weekly',title:'Домашнее задание',text:`${firstStudent.name.split(' ')[0]}, твоё ДЗ на неделю:\n\n1. ${weeklyTask.title}`,items:[{taskId:weeklyTask.id,title:weeklyTask.title,description:weeklyTask.description,url:weeklyTask.url,materials:weeklyTask.materials,dueAt:''}],status:'draft',issuedAt:'',submittedAt:'',workUrl:'',comment:'',dueAt:'',createdAt:'2026-10-22T09:00:00.000Z'}
  const weeklyMeeting={id:'weekly',groupId:group4.id,date:'2026-10-22',status:'draft',studentIds:group4Members.map(student=>student.id),students:group4Members.map((student,index)=>({studentId:student.id,reviewed:true,summary:index===0?'Обсудили результаты недели':'',plannedTaskIds:index===0?[weeklyTask.id]:[],homeworkId:index===0?weeklyHomework.id:'',plannedTaskSnapshot:index===0?[{taskId:weeklyTask.id,title:weeklyTask.title,sectionTitle:'Вводная часть',status:weeklyTask.studyStatus}]:[]})),createdAt:'2026-10-22T09:00:00.000Z',updatedAt:'2026-10-22T09:00:00.000Z',completedAt:''}
  const weeklyData=normalizeData(JSON.parse(JSON.stringify({...seeded,groupMeetings:[weeklyMeeting],homeworks:[...seeded.homeworks,weeklyHomework]})))
  assert.equal(weeklyData.groupMeetings.length,1)
  assert.equal(weeklyData.groupMeetings[0].students.length,group4Members.length)
  assert.deepEqual(weeklyData.groupMeetings[0].students[0].plannedTaskIds,[weeklyTask.id])
  assert.equal(weeklyData.groupMeetings[0].students[0].plannedTaskSnapshot[0].title,weeklyTask.title)
  assert.equal(weeklyData.homeworks.find(item=>item.id==='weekly-homework').text,weeklyHomework.text)
  const meetingMarkup=renderToStaticMarkup(React.createElement(MeetingWorkspace,{data:weeklyData,group:group4,meeting:weeklyData.groupMeetings[0],onClose:noop,onStatus:noop,onOpenTask:noop,onTogglePlan:noop,onMovePlan:noop,onSummary:noop,onReviewed:noop,onQuickTask:noop,onCreateHomework:()=>'',onUpdateHomework:noop,onComplete:noop}))
  assert.ok(meetingMarkup.includes('Групповая встреча'))
  assert.ok(meetingMarkup.includes('Прошлая неделя'))
  assert.ok(meetingMarkup.includes('План на неделю'))
  assert.ok(meetingMarkup.includes('Открыть ДЗ'))
  assert.equal((weeklyData.groupMeetings[0].students[0].plannedTaskIds.filter(id=>id===weeklyTask.id)).length,1)
  const completedMeeting={...weeklyData.groupMeetings[0],status:'completed',completedAt:'2026-10-22T12:00:00.000Z'}
  const historyData={...weeklyData,tasks:weeklyData.tasks.filter(task=>task.id!==weeklyTask.id),groupMeetings:[completedMeeting]}
  const historyMarkup=renderToStaticMarkup(React.createElement(MeetingWorkspace,{data:historyData,group:group4,meeting:completedMeeting,onClose:noop,onStatus:noop,onOpenTask:noop,onTogglePlan:noop,onMovePlan:noop,onSummary:noop,onReviewed:noop,onQuickTask:noop,onCreateHomework:()=>'',onUpdateHomework:noop,onComplete:noop}))
  assert.ok(historyMarkup.includes('Итоги встречи'))
  assert.ok(historyMarkup.includes(weeklyTask.title))
  assert.ok(historyMarkup.includes('Сохранённые итоги групповой встречи'))
  console.log('Workflow verification passed: migration, weekly group meeting, plan reuse, homework snapshot, review, Anya approval, Telegram text, UI render.')
} finally {
  await server.close()
}
