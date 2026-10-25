import type { AppData, ApprovalStatus, Group, GroupStatus, Homework, Meeting, Stage, StrategySection, StrategyTask, Student, TaskStatus } from './types'

export const STAGES: { id: Stage; label: string; number: string }[] = [
  { id: 'start', label: 'Начало', number: '01' }, { id: 'portfolio', label: 'Портфолио', number: '02' }, { id: 'search', label: 'Отклики', number: '03' },
]
export const STATUS = { backlog: 'Бэклог', progress: 'В работе', done: 'Готово' } as const
export const STUDY_STATUS = { not_started: 'Не начато', in_progress: 'В процессе', hold: 'На паузе', done: 'Выполнено' } as const
export const REVIEW_STATUS = { none: 'Не отправлена', pending: 'На проверке', revision: 'На доработке', accepted: 'Принята' } as const
export const APPROVAL_STATUS = { to_send: 'Нужно передать', sent: 'Передано Ане', reviewing: 'На проверке', revision: 'Есть правки', approved: 'Согласовано' } as const
export const HOMEWORK_STATUS = { draft: 'Черновик', issued: 'Выдано', progress: 'В работе', submitted: 'На проверке', revision: 'На доработке', accepted: 'Принято' } as const
export const GROUP_STATUS: Record<GroupStatus, string> = { backlog: 'Бэклог', active: 'Активная', completed: 'Завершена', archived: 'Архив' }
export const STORAGE_KEY = 'crm-mentoring-v1'
export const PRE_SECTION_BACKUP_KEY = `${STORAGE_KEY}-before-section-strategies-v1`
export const uid = () => crypto.randomUUID()
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }
export const dateLabel = (date: string) => date ? new Date(`${date}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : 'Без даты'
export const isOverdue = (date: string) => Boolean(date && date < today())
export const daysUntil = (date: string) => date ? Math.ceil((new Date(`${date}T00:00:00`).getTime() - new Date(`${today()}T00:00:00`).getTime()) / 86400000) : null
export const addCalendarMonths = (start: string, months: number) => { const [year,month,day]=start.split('-').map(Number); const whole=Math.trunc(months); const targetMonth=month-1+whole; const y=year+Math.floor(targetMonth/12); const m=((targetMonth%12)+12)%12; const last=new Date(y,m+1,0).getDate(); const result=new Date(y,m,Math.min(day,last)); if(months%1) result.setDate(result.getDate()+Math.round((months%1)*30)); return `${result.getFullYear()}-${String(result.getMonth()+1).padStart(2,'0')}-${String(result.getDate()).padStart(2,'0')}` }
export const elapsedDays = (date:string) => date ? Math.max(0,-(daysUntil(date)??0)) : null
export const activeTasks = (tasks: StrategyTask[]) => tasks.filter(task => !task.archivedAt)
export const studentTasks = (data: AppData, studentId: string) => activeTasks(data.tasks).filter(t => t.studentId === studentId)
export const taskColumn = (task: StrategyTask): TaskStatus => task.reviewStatus === 'pending' || task.reviewStatus === 'revision' ? 'progress' : task.studyStatus === 'done' ? 'done' : task.studyStatus === 'not_started' ? 'backlog' : 'progress'
export const needsAnyaApproval = (task: StrategyTask) => !task.archivedAt && task.approvalStatus !== null
export const approvalState = (task: StrategyTask): ApprovalStatus => task.approvalStatus || 'to_send'
export function applyApprovalStatus(data: AppData, id: string, status: ApprovalStatus, now = new Date().toISOString()): AppData {
  const current = data.tasks.find(task => task.id === id)
  if (!current || !needsAnyaApproval(current)) return data
  if (approvalState(current) === status) return data
  return {...data,demo:false,tasks:data.tasks.map(task=>task.id===id?{
    ...task,approvalStatus:status,approvalSentAt:status==='sent'?now:task.approvalSentAt,
    updatedAt:now,history:[...task.history,{at:now,label:`Согласование с Аней: ${APPROVAL_STATUS[status]}`}],
  }:task)}
}
export function recallApproval(data: AppData, id: string, now = new Date().toISOString()): AppData {
  const current = data.tasks.find(task => task.id === id)
  if (!current || !needsAnyaApproval(current)) return data
  return {...data,demo:false,tasks:data.tasks.map(task=>task.id===id?{
    ...task,approvalStatus:null,updatedAt:now,
    history:[...task.history,{at:now,label:'Согласование с Аней отозвано'}],
  }:task)}
}
export function archiveTask(data: AppData, id: string, now = new Date().toISOString()): AppData {
  const current = data.tasks.find(task => task.id === id)
  if (!current || current.archivedAt) return data
  return {...data,demo:false,tasks:data.tasks.map(task=>task.id===id?{
    ...task,archivedAt:now,approvalStatus:null,updatedAt:now,
    history:[...task.history,{at:now,label:'Задача удалена из активной стратегии'}],
  }:task)}
}
export const planProgress = (tasks: StrategyTask[]) => { const agreed=tasks.filter(t=>taskColumn(t)!=='backlog'); const done=agreed.filter(t=>taskColumn(t)==='done').length; return {done,total:agreed.length,percent:agreed.length?Math.round(done/agreed.length*100):null} }
export const curriculumProgress = (tasks: StrategyTask[]) => { const done=tasks.filter(t=>taskColumn(t)==='done').length; return {done,total:tasks.length,percent:tasks.length?Math.round(done/tasks.length*100):null} }
export const progress = (tasks: StrategyTask[]) => curriculumProgress(tasks).percent ?? 0
export const groupProgress = (data: AppData, group: Group) => { const ids = new Set(data.students.filter(s => s.groupId === group.id).map(s => s.id)); return progress(activeTasks(data.tasks).filter(t => ids.has(t.studentId))) }
export const nearestTask = (tasks: StrategyTask[]) => tasks.filter(t => taskColumn(t) !== 'done').sort((a,b) => a.studyStatus === b.studyStatus ? a.order-b.order : a.studyStatus === 'in_progress' ? -1 : b.studyStatus === 'in_progress' ? 1 : a.order-b.order)[0]
export const groupNextTask = (data: AppData, group: Group) => { const ids = new Set(data.students.filter(s => s.groupId === group.id).map(s => s.id)); return nearestTask(activeTasks(data.tasks).filter(t => ids.has(t.studentId))) }
export const emptyData = (): AppData => ({ version: 3, groups: [], students: [], sections:[], tasks: [], meetings: [], homeworks: [], demo: false })
export const homeworkDescription = (task: StrategyTask) => {
  const description = task.description.trim()
  if (description && !/^Ссылка:\s*https?:\/\//i.test(description)) return description
  return task.comments.match(/(?:^|\n)(?:ДЗ|Для ученицы):\s*([^\n]+)/i)?.[1]?.trim() || ''
}
export const homeworkText = (title: string, items: Homework['items'], dueAt: string) => [title, '', ...items.flatMap((item, i) => [`${i + 1}. ${item.title}${item.description ? ` — ${item.description}` : ''}`, ...([...(item.materials||[]),item.url].filter((value,index,list)=>/^https?:\/\//i.test(value||'')&&list.indexOf(value)===index)), ...(item.dueAt ? [`Срок: ${dateLabel(item.dueAt)}`] : []), '']), ...(dueAt ? [`Общий дедлайн: ${dateLabel(dueAt)}`] : [])].join('\n').trim()

export function applyHomeworkPatch(data: AppData, id: string, patch: Partial<Homework>, now = new Date().toISOString()): AppData {
  const current = data.homeworks.find(h => h.id === id)
  if (!current) return data
  const safePatch = {...patch}
  if (current.status !== 'draft') { delete safePatch.text; delete safePatch.items; delete safePatch.title }
  const next = {...current,...safePatch,reviewedAt:patch.status==='submitted'?'':patch.status==='revision'||patch.status==='accepted'?now:current.reviewedAt}
  const ids = new Set(current.items.map(item => item.taskId))
  const reviewChange = patch.status==='submitted'||patch.status==='revision'||patch.status==='accepted'
  return {...data,demo:false,homeworks:data.homeworks.map(h => h.id === id ? next : h),tasks:data.tasks.map(t => {
    if (!ids.has(t.id) || !reviewChange) return t
    const accepted = patch.status==='accepted'
    const reviewStatus = accepted?'accepted':patch.status==='submitted'?'pending':'revision'
    const label = accepted?'Работа принята куратором':patch.status==='submitted'?'Работа отправлена на проверку':'Работа возвращена на доработку'
    return {...t,status:accepted?'done' as const:'progress' as const,studyStatus:accepted?'done' as const:'in_progress' as const,reviewStatus,updatedAt:now,history:[...t.history,{at:now,label}]}
  }),students:reviewChange?data.students.map(s=>s.id===current.studentId?{...s,strategyUpdatedAt:now}:s):data.students}
}

type StoredRecord=Record<string,unknown>
const hasOptionalStrings=(value:unknown,fields:string[])=>Boolean(value&&typeof value==='object'&&fields.every(field=>{
  const item=(value as StoredRecord)[field]
  return item===undefined||typeof item==='string'
}))
const hasOptionalNumber=(value:unknown,field:string,nullable=false)=>{
  const item=(value as StoredRecord)[field]
  return item===undefined||nullable&&item===null||typeof item==='number'&&Number.isFinite(item)
}
const hasOptionalBoolean=(value:unknown,field:string)=>{
  const item=(value as StoredRecord)[field]
  return item===undefined||typeof item==='boolean'
}
const hasStringArray=(value:unknown,field:string)=>{
  const item=(value as StoredRecord)[field]
  return item===undefined||Array.isArray(item)&&item.every(entry=>typeof entry==='string')
}

export function normalizeData(value: unknown): AppData {
  if (!value || typeof value !== 'object') throw new Error('Invalid data')
  const raw = value as {version:number;groups:(Partial<Group>&{archived?:boolean})[];students:Partial<Student>[];sections?:StrategySection[];tasks:Partial<StrategyTask>[];meetings?:Meeting[];homeworks?:Homework[];demo?:boolean;demoRevision?:number;importConflicts?:string[]}
  if (!Array.isArray(raw.groups) || !Array.isArray(raw.students) || !Array.isArray(raw.tasks) || ![1,2,3].includes(raw.version)) throw new Error('Invalid data')
  if (!raw.groups.every(g => typeof g?.id === 'string' && typeof g?.name === 'string') || !raw.students.every(s => typeof s?.id === 'string' && typeof s?.groupId === 'string') || !raw.tasks.every(t => typeof t?.id === 'string' && typeof t?.studentId === 'string')) throw new Error('Invalid data')
  const groupsValid=raw.groups.every(group=>hasOptionalStrings(group,['id','name','startsAt','endsAt','actualEndsAt','status','notes','createdAt'])&&(group.statusBeforeArchive===undefined||group.statusBeforeArchive===null||typeof group.statusBeforeArchive==='string')&&hasOptionalNumber(group,'durationMonths')&&hasOptionalBoolean(group,'archived'))
  const studentsValid=raw.students.every(student=>hasOptionalStrings(student,['id','groupId','name','photo','stage','startsAt','level','desiredPosition','careerGoal','background','experience','strengths','growthAreas','difficulties','expectations','personalNotes','pointA','pointB','notes','strategyUpdatedAt','createdAt'])&&hasOptionalNumber(student,'age',true)&&hasOptionalNumber(student,'avatarIndex')&&hasOptionalBoolean(student,'stageKnown')&&(!student.links||hasOptionalStrings(student.links,['figma','portfolio','resume','telegram','notion'])))
  const tasksValid=raw.tasks.every(task=>hasOptionalStrings(task,['id','studentId','title','description','stage','status','owner','dueAt','url','comments','createdAt','updatedAt','reviewStatus','approvalType','approvalSentAt','approvalComment','sectionId','studyStatus','period','sourceFile','archivedAt'])&&((task.approvalStatus??null)===null||typeof task.approvalStatus==='string')&&hasOptionalNumber(task,'order')&&hasOptionalBoolean(task,'blocker')&&hasStringArray(task,'materials')&&(!task.history||Array.isArray(task.history)&&task.history.every(event=>hasOptionalStrings(event,['at','label']))))
  const sectionsValid=!raw.sections||Array.isArray(raw.sections)&&raw.sections.every(section=>hasOptionalStrings(section,['id','studentId','title','createdAt'])&&hasOptionalNumber(section,'order'))
  const meetingsValid=!raw.meetings||Array.isArray(raw.meetings)&&raw.meetings.every(meeting=>hasOptionalStrings(meeting,['id','studentId','date','title','summary','createdAt']))
  const homeworksValid=!raw.homeworks||Array.isArray(raw.homeworks)&&raw.homeworks.every(homework=>hasOptionalStrings(homework,['id','studentId','title','text','status','issuedAt','submittedAt','reviewedAt','workUrl','comment','dueAt','createdAt','deletedAt'])&&Array.isArray(homework.items)&&homework.items.every(item=>hasOptionalStrings(item,['taskId','title','description','url','dueAt'])&&hasStringArray(item,'materials')))
  if(!groupsValid||!studentsValid||!tasksValid||!sectionsValid||!meetingsValid||!homeworksValid)throw new Error('Invalid data')
  const groups: Group[] = raw.groups.map(g => ({ id:g.id!, name:g.name!, startsAt:g.startsAt||'', endsAt:g.endsAt||'', actualEndsAt:g.actualEndsAt||'', status:g.status || (g.archived?'archived':'active'), statusBeforeArchive:g.archived?'completed':g.statusBeforeArchive||null, notes:g.notes||'', createdAt:g.createdAt||new Date().toISOString(),durationMonths:g.durationMonths }))
  const students: Student[] = raw.students.map(s => ({ id:s.id!, groupId:s.groupId!, name:s.name||'', age:s.age??null, photo:s.photo||'', avatarIndex:s.avatarIndex??-1, stage:s.stage||'start',stageKnown:s.stageKnown, startsAt:s.startsAt||'', level:s.level||'', desiredPosition:s.desiredPosition||'', careerGoal:s.careerGoal||'', links:{figma:s.links?.figma||'',portfolio:s.links?.portfolio||'',resume:s.links?.resume||'',telegram:s.links?.telegram||'',notion:s.links?.notion||''}, background:s.background||'',experience:s.experience||'',strengths:s.strengths||'',growthAreas:s.growthAreas||'',difficulties:s.difficulties||'',expectations:s.expectations||'',personalNotes:s.personalNotes||'',pointA:s.pointA||'',pointB:s.pointB||'',notes:s.notes||'',strategyUpdatedAt:s.strategyUpdatedAt||new Date().toISOString(),createdAt:s.createdAt||new Date().toISOString() }))
  const tasks: StrategyTask[] = raw.tasks.filter(t => typeof t?.id === 'string' && typeof t?.studentId === 'string' && typeof t?.title === 'string').map(t => ({...t as StrategyTask, reviewStatus:t.reviewStatus || (t.status === 'done' ? 'accepted' : 'none'), approvalStatus:Object.prototype.hasOwnProperty.call(t,'approvalStatus') ? t.approvalStatus ?? null : (t.owner === 'Аня' ? (t.status === 'done' ? 'approved' : 'to_send') : null), approvalType:t.approvalType || '', approvalSentAt:t.approvalSentAt || '', approvalComment:t.approvalComment || '', history:Array.isArray(t.history) ? t.history : [],sectionId:t.sectionId||'',studyStatus:t.studyStatus|| (t.status==='done'?'done':t.status==='progress'?'in_progress':'not_started'),period:t.period||'',materials:Array.isArray(t.materials)?t.materials:[],archivedAt:t.archivedAt||undefined}))
  const meetings = (Array.isArray(raw.meetings)?raw.meetings:[]).filter(m => typeof m?.id === 'string' && typeof m?.studentId === 'string') as Meeting[]
  const homeworks = (Array.isArray(raw.homeworks)?raw.homeworks:[]).filter(h => typeof h?.id === 'string' && typeof h?.studentId === 'string' && Array.isArray(h.items)) as Homework[]
  for (const task of tasks) {
    if (task.owner === 'Аня' && task.reviewStatus === 'revision' && !homeworks.some(h => !h.deletedAt && h.status === 'revision' && h.items.some(item => item.taskId === task.id))) task.reviewStatus = 'none'
  }
  const sections=Array.isArray(raw.sections)?raw.sections.filter(s=>typeof s.id==='string'&&typeof s.studentId==='string'):[]
  return {version:3,groups,students,sections,tasks,meetings,homeworks,demo:Boolean(raw.demo),demoRevision:raw.demoRevision,importConflicts:Array.isArray(raw.importConflicts)?raw.importConflicts:[]}
}
export function loadData(): AppData { const raw=localStorage.getItem(STORAGE_KEY); if(!raw)return emptyData(); try { if(!localStorage.getItem(PRE_SECTION_BACKUP_KEY)) localStorage.setItem(PRE_SECTION_BACKUP_KEY,raw); if(!localStorage.getItem(`${STORAGE_KEY}-before-strategies-import`)) localStorage.setItem(`${STORAGE_KEY}-before-strategies-import`,raw) } catch { console.warn('Не удалось сохранить локальную копию данных перед обновлением стратегии') } try{return normalizeData(JSON.parse(raw))}catch{try{localStorage.setItem(`${STORAGE_KEY}-recovery-${Date.now()}`,raw)}catch{/* storage unavailable */}return emptyData()} }
export function isAppData(value: unknown): value is AppData { try { normalizeData(value); return true } catch { return false } }
