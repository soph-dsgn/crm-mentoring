import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { BookOpenIcon as BookOpen, ClipboardTextIcon as ClipboardList, DownloadIcon as Download, FileTextIcon as FileText, SquaresFourIcon as LayoutDashboard, MagnifyingGlassIcon as Search, SlidersHorizontalIcon as Settings2, SparkleIcon as Sparkles, UploadIcon as Upload, UsersIcon as Users } from '@phosphor-icons/react'
import Select from './Select'
import PlanOverview from './PlanOverview'
import { GroupsPage, GroupDetailPage } from './GroupViews'
import ProfilePage, { type ProfileTab } from './ProfilePage'
import TaskDetail from './TaskDetail'
import TaskForm from './TaskForm'
import { hasTechnicalUntitledTitle } from './taskPresentation'
import { GroupForm, StudentForm } from './Forms'
import { activeTasks, addCalendarMonths, applyApprovalStatus, applyHomeworkPatch, archiveTask, homeworkDescription, homeworkText, isAppData, loadData, normalizeData, PRE_SECTION_BACKUP_KEY, recallApproval, STUDY_STATUS, STORAGE_KEY, studentTasks, taskColumn, today, uid } from './data'
import type { AppData, ApprovalStatus, Group, GroupStatus, Homework, Meeting, Stage, StrategyTask, Student, StudyStatus, TaskStatus } from './types'
import HomeworkPage from './HomeworkPage'
import AnyaPage from './AnyaPage'
import { mergeStrategies } from './strategyImport'
import { useCalmMotion } from './motion'
import { ConfirmDialog, DeleteConfirmDialog, Dialog, NoticeDialog } from './Dialogs'
import { FlowBackground } from './FlowBackground'

type Page = 'overview' | 'strategies' | 'homework' | 'anya' | 'prompts' | 'textbook'
const KnowledgePage = lazy(() => import('./KnowledgePage'))
type Modal = 'group' | 'student' | 'task' | 'taskDetail' | 'backup' | null
type ConfirmState = { title:string; description:string; confirmLabel:string; danger?:boolean; action:()=>void|Promise<void> }
const nav: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Обзор', icon: LayoutDashboard }, { id: 'strategies', label: 'Стратегии', icon: Users },
  { id: 'homework', label: 'Домашние задания', icon: ClipboardList }, { id: 'anya', label: 'Задачи Ани', icon: Sparkles },
  { id: 'prompts', label: 'Промпты', icon: FileText }, { id: 'textbook', label: 'Учебник', icon: BookOpen },
]
const blankLinks = { figma: '', portfolio: '', resume: '', telegram: '', notion: '' }
const newGroup = (): Group => ({ id: uid(), name: '', startsAt: today(), endsAt: '', actualEndsAt: '', status: 'backlog', statusBeforeArchive: null, notes: '', createdAt: new Date().toISOString() })
const newStudent = (groupId: string): Student => ({ id: uid(), groupId, name: '', age: null, photo: '', avatarIndex: -1, stage: 'start', startsAt: today(), level: '', desiredPosition: '', careerGoal: '', links: { ...blankLinks }, background: '', experience: '', strengths: '', growthAreas: '', difficulties: '', expectations: '', personalNotes: '', pointA: '', pointB: '', notes: '', strategyUpdatedAt: new Date().toISOString(), createdAt: new Date().toISOString() })
const newTask = (studentId: string, order: number, stage: Stage): StrategyTask => ({ id: uid(), studentId, title: '', description: '', stage, status: 'backlog', studyStatus:'not_started', sectionId:'', period:'', materials:[], owner: 'Не назначен', dueAt: '', url: '', comments: '', order, blocker: false, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), reviewStatus:'none', approvalStatus:null, approvalType:'', approvalSentAt:'', approvalComment:'', history:[] })

function App() {
  const calm = useCalmMotion()
  const [data, setData] = useState<AppData>(loadData)
  const [page, setPage] = useState<Page>('overview')
  const [groupsView,setGroupsView]=useState<'groups'|'students'>('groups')
  const [groupsFilter,setGroupsFilter]=useState<GroupStatus>('active')
  const [groupId, setGroupId] = useState<string | null>(null)
  const [studentId, setStudentId] = useState<string | null>(null)
  const [modal, setModal] = useState<Modal>(null)
  const [draftGroup, setDraftGroup] = useState<Group | null>(null)
  const [draftStudent, setDraftStudent] = useState<Student | null>(null)
  const [draftTask, setDraftTask] = useState<StrategyTask | null>(null)
  const [focusedTaskId, setFocusedTaskId] = useState<string | null>(null)
  const [focusedHomeworkId, setFocusedHomeworkId] = useState<string | null>(null)
  const [profileTab, setProfileTab] = useState<ProfileTab>('overview')
  const [returnPage,setReturnPage]=useState<Page|null>(null)
  const [studentBackToRoster,setStudentBackToRoster]=useState(false)
  const [profileNavigationKey,setProfileNavigationKey]=useState(0)
      const [searchOpen, setSearchOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [saveError, setSaveError] = useState(false)
  const [importError,setImportError] = useState('')
  const [confirmState,setConfirmState] = useState<ConfirmState|null>(null)
  const [notice,setNotice] = useState<{title:string;description:string}|null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const dataRef = useRef(data)
  dataRef.current = data

  useEffect(() => { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); setSaveError(false) } catch { setSaveError(true) } }, [data])
  useEffect(() => { let cancelled=false; const marker=`${STORAGE_KEY}-strategies-imported-v1`;if(localStorage.getItem(marker))return; const previous=localStorage.getItem(STORAGE_KEY); const backupKey=`${STORAGE_KEY}-before-strategies-import`; if(previous&&!localStorage.getItem(backupKey)){try{localStorage.setItem(backupKey,previous)}catch{setImportError('Не удалось сохранить копию данных до импорта. Освободите место в браузере и перезагрузите страницу');return}} fetch('/strategies/strategy-seed.json').then(r=>{if(!r.ok)throw new Error('Нет файла стратегий');return r.json()}).then(seed=>{if(!cancelled)setData(current=>{const merged=mergeStrategies(current,seed);try{localStorage.setItem(STORAGE_KEY,JSON.stringify(merged));localStorage.setItem(marker,'1')}catch{setImportError('Не удалось сохранить импортированные стратегии. Проверьте свободное место в браузере');return current}return merged})}).catch(error=>{console.error('Не удалось загрузить стратегии',error);setImportError('Не удалось загрузить файл стратегий')});return()=>{cancelled=true} },[])
  const group = data.groups.find(g => g.id === groupId) ?? null
  const student = data.students.find(s => s.id === studentId) ?? null
  const focusedTask = data.tasks.find(t => t.id === focusedTaskId) ?? null
  const focusedStudent = data.students.find(s=>s.id===focusedTask?.studentId)
  const focusedGroup = data.groups.find(g=>g.id===focusedStudent?.groupId)
  const focusedHomework = focusedTask ? data.homeworks.filter(homework=>!homework.deletedAt&&homework.items.some(item=>item.taskId===focusedTask.id)).sort((a,b)=>b.createdAt.localeCompare(a.createdAt)).find(homework=>focusedTask.reviewStatus==='pending'?homework.status==='submitted':focusedTask.reviewStatus==='revision'?homework.status==='revision':true) : undefined
  const currentTasks = student ? studentTasks(data, student.id) : []
  const activeGroups = data.groups.filter(g => g.status === 'active')
  const hasDemo = data.groups.some(g => g.id.startsWith('demo-'))
  const tasksInActiveGroups = activeTasks(data.tasks).filter(t => {
    const s = data.students.find(student => student.id === t.studentId)
    return s && data.groups.some(g => g.id === s.groupId && g.status === 'active')
  })
  const openPage = (next: Page) => { setPage(next); setReturnPage(null); setSearchOpen(false) }
  const openGroup = (id: string) => { setReturnPage(page==='strategies'?returnPage:page);setPage('strategies'); setGroupId(id); setStudentId(null) }
  const openStudent = (id: string, tab: ProfileTab = 'overview', homeworkId: string | null = null) => { const s = data.students.find(v => v.id === id); if (!s) return;if(page!=='strategies')setStudentBackToRoster(false);setReturnPage(page==='strategies'?returnPage:page); setPage('strategies'); setGroupId(s.groupId); setStudentId(id); setProfileTab(tab); setFocusedHomeworkId(homeworkId);setProfileNavigationKey(key=>key+1) }
  const returnToSource=()=>{if(!returnPage)return;setPage(returnPage);setStudentId(null);setGroupId(null);setReturnPage(null);setStudentBackToRoster(false);setModal(null)}
  const openTask = (id: string) => { const task = data.tasks.find(t => t.id === id); if (!task) return; if(page==='strategies'&&studentId===task.studentId){setProfileTab('strategy');setProfileNavigationKey(key=>key+1)}else openStudent(task.studentId, 'strategy'); setFocusedTaskId(id); setModal('taskDetail') }
  const openReview = (id: string) => { const homework=data.homeworks.find(h=>h.id===id&&!h.deletedAt); if (homework) openStudent(homework.studentId,'homework',id) }
  const saveGroup = () => { if (!draftGroup?.name.trim()) return; const groupDraft={...draftGroup,endsAt:draftGroup.durationMonths?addCalendarMonths(draftGroup.startsAt,draftGroup.durationMonths):draftGroup.endsAt};const existing=data.groups.some(group=>group.id===groupDraft.id); setData(d => ({ ...d, demo: false, groups: existing ? d.groups.map(g => g.id === groupDraft.id ? groupDraft : g) : [...d.groups, groupDraft] })); setModal(null);if(!existing){setGroupsView('groups');setGroupsFilter(groupDraft.status);openGroup(groupDraft.id)} }
  const setGroupStatus = (group: Group, status: GroupStatus) => setData(d => ({ ...d, demo: false, groups: d.groups.map(g => g.id === group.id ? { ...g, status, statusBeforeArchive: status === 'archived' ? (g.status === 'archived' ? g.statusBeforeArchive : g.status) : g.statusBeforeArchive, actualEndsAt: status === 'completed' && !g.actualEndsAt ? today() : g.actualEndsAt } : g) }))
  const saveStudent = () => { if (!draftStudent?.name.trim() || !draftStudent.groupId) return;const existing=data.students.some(student=>student.id===draftStudent.id); setData(d => ({ ...d, demo: false, students: existing ? d.students.map(s => s.id === draftStudent.id ? draftStudent : s) : [...d.students, draftStudent] })); if(studentId===draftStudent.id)setGroupId(draftStudent.groupId);if(!existing){setPage('strategies');setGroupId(draftStudent.groupId);setStudentId(draftStudent.id);setProfileTab('overview');setProfileNavigationKey(key=>key+1)} setModal(null) }
  const patchStudent = (patch: Partial<Student>) => { if (!student) return; setData(d => ({ ...d, demo: false, students: d.students.map(s => s.id === student.id ? { ...s, ...patch } : s) })) }
  const addMeeting = (meeting: Meeting) => setData(d => ({ ...d, demo: false, meetings: [...d.meetings, meeting] }))
  const deleteMeeting = (id: string) => setData(d => ({ ...d, demo: false, meetings: d.meetings.filter(m => m.id !== id) }))
  const saveTask = () => {
    if (!draftTask?.title.trim()) return
    if (['pending','revision'].includes(draftTask.reviewStatus) && data.tasks.find(task=>task.id===draftTask.id)?.studyStatus !== draftTask.studyStatus) {
      setNotice({title:'Статус пока недоступен',description:'Сначала завершите проверку или доработку в домашнем задании'})
      return
    }
    const now = new Date().toISOString()
    const task = { ...draftTask, status:draftTask.studyStatus==='done'?'done' as TaskStatus:draftTask.studyStatus==='not_started'?'backlog' as TaskStatus:'progress' as TaskStatus, reviewStatus:draftTask.studyStatus==='done'?'accepted' as const:draftTask.reviewStatus==='accepted'?'none' as const:draftTask.reviewStatus, updatedAt: now }
    const next = { ...data, demo: false, tasks: data.tasks.some(item => item.id === task.id) ? data.tasks.map(item => item.id === task.id ? {...task, history:[...item.history,{at:now,label:item.studyStatus!==task.studyStatus?`Статус: ${STUDY_STATUS[task.studyStatus]}`:'Данные задачи обновлены'}]} : item) : [...data.tasks, {...task,history:[{at:now,label:'Задача создана'}]}], students: data.students.map(item => item.id === task.studentId ? { ...item, strategyUpdatedAt: now } : item) }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      setSaveError(true)
      return
    }
    setData(next)
    setModal(null)
  }
  const changeTask = (id: string, patch: Partial<StrategyTask>, label = 'Задача обновлена') => setData(d => { const now = new Date().toISOString(); const task = d.tasks.find(t => t.id === id); return { ...d, demo: false, tasks: d.tasks.map(t => t.id === id ? { ...t, ...patch, updatedAt: now, history:[...t.history,{at:now,label}] } : t), students: d.students.map(s => s.id === task?.studentId ? { ...s, strategyUpdatedAt: now } : s) } })
  const changeStudyStatus = (id:string,studyStatus:StudyStatus) => { const task=data.tasks.find(t=>t.id===id);if(!task)return;if(studyStatus!==task.studyStatus&&['pending','revision'].includes(task.reviewStatus)){setNotice({title:'Статус пока недоступен',description:'Сначала завершите проверку или доработку в домашнем задании'});return} const status:TaskStatus=studyStatus==='done'?'done':studyStatus==='not_started'?'backlog':'progress'; const reviewStatus=studyStatus==='done'?'accepted':task.reviewStatus==='accepted'?'none':task.reviewStatus;changeTask(id,{studyStatus,status,reviewStatus},`Статус: ${STUDY_STATUS[studyStatus]}`) }
  const addSection = (title:string) => { if(!student)return;setData(d=>({...d,sections:[...d.sections,{id:uid(),studentId:student.id,title,order:d.sections.filter(s=>s.studentId===student.id).length,createdAt:new Date().toISOString()}]})) }
  const renameSection = (id:string,title:string) => setData(d=>({...d,sections:d.sections.map(s=>s.id===id?{...s,title}:s)}))
  const deleteSection = (id:string) => { if(data.tasks.some(task=>task.sectionId===id)){setNotice({title:'Раздел хранит историю задач',description:'Переместите активные задачи. Архивные связи сохраняются и не позволяют удалить раздел'});return}setData(d=>({...d,sections:d.sections.filter(s=>s.id!==id)})) }
  const changeSection = (id:string,sectionId:string) => changeTask(id,{sectionId,order:Math.max(0,...data.tasks.filter(t=>t.sectionId===sectionId).map(t=>t.order))+1},'Перемещена в другой раздел')
  const createHomework = (taskIds: string[], title: string, text: string):string => { if (!student || !taskIds.length) return ''; const items = taskIds.map(id => data.tasks.find(t => t.id === id)).filter((t):t is StrategyTask => Boolean(t)).map(t => ({taskId:t.id,title:t.title,description:homeworkDescription(t),url:t.url,materials:[...t.materials],dueAt:t.dueAt})); const now = new Date().toISOString(); const id=uid(); const homework: Homework = {id,studentId:student.id,title:title.trim()||'Домашнее задание',text:text.trim()||homeworkText(title,items,''),items,status:'draft',issuedAt:'',submittedAt:'',workUrl:'',comment:'',dueAt:'',createdAt:now}; setData(d => ({...d,demo:false,homeworks:[...d.homeworks,homework]})); return id }
  const updateHomework = (id: string, patch: Partial<Homework>) => setData(d => applyHomeworkPatch(d,id,patch))
  const deleteHomework = (id:string) => setData(d=>({...d,homeworks:d.homeworks.map(h=>h.id===id?{...h,deletedAt:new Date().toISOString()}:h)}))
  const setApproval = (id: string, status: ApprovalStatus) => setData(d=>applyApprovalStatus(d,id,status))
  const recallTaskApproval = (id:string) => setData(d=>recallApproval(d,id))
  const patchApprovalField = (id:string, patch:Partial<StrategyTask>, label:string) => setData(d=>{const now=new Date().toISOString();return {...d,demo:false,tasks:d.tasks.map(t=>t.id===id?{...t,...patch,updatedAt:now,history:[...t.history,{at:now,label}]}:t)}})
  const moveOrder = (task: StrategyTask, delta: number) => { const peers = currentTasks.filter(t => t.sectionId === task.sectionId).sort((a,b) => a.order - b.order); const i = peers.findIndex(t => t.id === task.id); const other = peers[i + delta]; if (!other) return; setData(d => ({ ...d, demo: false, tasks: d.tasks.map(t => t.id === task.id ? { ...t, order: other.order } : t.id === other.id ? { ...t, order: task.order } : t) })) }
  const removeGroup = (g: Group) => { if (data.students.some(s => s.groupId === g.id)) { setNotice({title:'Нельзя удалить группу',description:'Сначала переместите или удалите учениц этой группы'}); return } setConfirmState({title:'Удалить группу?',description:`Группа «${g.name}» будет удалена`,confirmLabel:'Удалить группу',danger:true,action:()=>{setData(d=>({...d,demo:false,groups:d.groups.filter(x=>x.id!==g.id)}));setGroupId(null)}}) }
  const removeStudent = (s: Student) => setConfirmState({title:'Удалить ученицу и её данные?',description:`Профиль «${s.name}», стратегия, домашние задания и история встреч будут удалены без возможности восстановления`,confirmLabel:'Удалить ученицу',danger:true,action:()=>{setData(d => ({ ...d, demo: false, students: d.students.filter(x => x.id !== s.id), sections:d.sections.filter(section=>section.studentId!==s.id), tasks: d.tasks.filter(t => t.studentId !== s.id), meetings: d.meetings.filter(m => m.studentId !== s.id), homeworks:d.homeworks.filter(h=>h.studentId!==s.id) }));setStudentId(null)}})
  const removeTask = (task: StrategyTask) => {
    const linkedHomeworks=data.homeworks.filter(homework=>homework.items.some(item=>item.taskId===task.id)).length
    const linkedLabel=linkedHomeworks?` Связанные домашние задания (${linkedHomeworks}) и их снимки останутся в истории.`:''
    setConfirmState({title:'Удалить задачу?',description:`«${task.title}» исчезнет из активной стратегии и очереди Ани.${linkedLabel}`,confirmLabel:'Удалить задачу',danger:true,action:()=>{
      const next=archiveTask(dataRef.current,task.id)
      localStorage.setItem(STORAGE_KEY,JSON.stringify(next))
      dataRef.current=next;setData(next);setModal(null)
    }})
  }
  const exportBackup = () => { const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `kuratorskaya-backup-${today()}.json`; a.click(); URL.revokeObjectURL(url) }
  const exportBeforeImport = () => { const raw=localStorage.getItem(`${STORAGE_KEY}-before-strategies-import`);if(!raw)return;const blob=new Blob([raw],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`kuratorskaya-before-import-${today()}.json`;a.click();URL.revokeObjectURL(url) }
  const exportBeforeSections = () => { const raw=localStorage.getItem(PRE_SECTION_BACKUP_KEY);if(!raw)return;const blob=new Blob([raw],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`kuratorskaya-before-section-strategies-${today()}.json`;a.click();URL.revokeObjectURL(url) }
  const importBackup = async (file?: File) => { if (!file) return; try { const json: unknown = JSON.parse(await file.text()); if (!isAppData(json)) throw new Error(); const restored=normalizeData(json);setConfirmState({title:'Восстановить резервную копию?',description:'Текущие данные в браузере будут заменены данными из выбранного файла',confirmLabel:'Восстановить данные',danger:true,action:()=>{setData(restored);setGroupId(null);setStudentId(null);setPage('overview');setModal(null)}}) } catch { setNotice({title:'Не удалось открыть файл',description:'Нужна резервная копия приложения в формате JSON'}) } }

  const attention = useMemo(() => data.students.filter(s => data.groups.some(g => g.id === s.groupId && g.status === 'active')).map(s => {
    const tasks = studentTasks(data, s.id)
    const blockers = tasks.filter(t => t.blocker && taskColumn(t) !== 'done').length
    const stale = Date.now() - new Date(s.strategyUpdatedAt).getTime() > 14 * 86400000
    return { student: s, blockers, stale }
  }).filter(x => x.blockers || x.stale).sort((a,b) => (b.blockers + Number(b.stale)) - (a.blockers + Number(a.stale))), [data])
  const upcoming = tasksInActiveGroups.filter(t => t.studyStatus === 'in_progress').sort((a,b) => a.order-b.order)
  const normalizedSearch = searchTerm.trim().toLocaleLowerCase('ru-RU')
  const foundStudents = normalizedSearch ? data.students.filter(s => s.name.toLocaleLowerCase('ru-RU').includes(normalizedSearch)).slice(0, 5) : []
  const foundGroups = normalizedSearch ? data.groups.filter(g => g.name.toLocaleLowerCase('ru-RU').includes(normalizedSearch)).slice(0, 4) : []
  return <div className={`app-shell ${page === 'overview' ? 'overview-shell' : ''}`}>
    <FlowBackground className="app-flow-background"/>
    <header className="workspace-toolbar">
      <div className="workspace-toolbar-left"><button className="brand-logo" aria-label="Кураторская — обзор" title="Обзор" onClick={() => openPage('overview')}><img src="/brand-star.svg" width="28" height="28" alt=""/><span>Кураторская</span></button></div>
      <nav className="toolbar-nav" aria-label="Основная навигация">{nav.map(({ id, label, icon: Icon }) => <button key={id} className={page === id ? 'active' : ''} aria-current={page===id?'page':undefined} title={label} onClick={() => openPage(id)}><Icon size={17}/><span>{label}</span></button>)}</nav>
      <div className="workspace-toolbar-right"><div className="group-switch"><Select aria-label="Перейти к группе" value={page==='strategies'?groupId ?? '':''} onChange={e => e.target.value ? openGroup(e.target.value) : (setGroupId(null),setStudentId(null),setPage('strategies'))}><option value="">Все группы</option>{data.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</Select></div><button className="toolbar-icon" aria-label="Поиск" title="Поиск" onClick={() => setSearchOpen(v => !v)}><Search size={16} weight="regular"/></button><button className="toolbar-icon" aria-label="Данные и копии" title="Данные и копии" onClick={() => setModal('backup')}><Settings2 size={16} weight="regular"/></button></div>
      <AnimatePresence initial={false}>{searchOpen && <motion.div key="search" className="toolbar-search-panel" {...calm.popover}><input autoFocus aria-label="Поиск группы или ученицы" placeholder="Группа или ученица" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}/>{normalizedSearch && <div className="toolbar-search-results">{foundStudents.map(s => <button key={s.id} onClick={() => { openStudent(s.id); setSearchOpen(false); setSearchTerm('') }}><strong>{s.name}</strong><small>{data.groups.find(group=>group.id===s.groupId)?.name||'Группа не найдена'} · ученица</small></button>)}{foundGroups.map(g => <button key={g.id} onClick={() => { openGroup(g.id); setSearchOpen(false); setSearchTerm('') }}><strong>{g.name}</strong><small>Группа</small></button>)}{!foundStudents.length && !foundGroups.length && <p>Ничего не найдено</p>}</div>}</motion.div>}</AnimatePresence>
    </header>
    <main className={`main ${page === 'overview' ? 'overview-main' : ''}`}>
      {saveError && <div className="save-error">Не удалось сохранить данные в браузере. Экспортируйте резервную копию и проверьте свободное место</div>}
      {importError && <div className="save-error">{importError}</div>}
      {hasDemo && <div className="demo-banner"><span><strong>Демонстрационные данные</strong> Четыре тестовые группы и профили можно редактировать</span><button onClick={() => setConfirmState({title:'Убрать демонстрационные данные?',description:'Тестовые группы, ученицы, задачи, домашние задания и встречи будут удалены. Ваши собственные записи сохранятся',confirmLabel:'Убрать пример',danger:true,action:()=>{setData(d => ({ ...d, demo: false, groups: d.groups.filter(g => !g.id.startsWith('demo-')), students: d.students.filter(s => !s.id.startsWith('demo-')), tasks: d.tasks.filter(t => !t.id.startsWith('demo-')), meetings: d.meetings.filter(m => !m.id.startsWith('demo-')),homeworks:d.homeworks.filter(h=>!h.studentId.startsWith('demo-')) }));setGroupId(null);setStudentId(null);setPage('overview')}})}>Убрать пример</button></div>}
      <div className="content"><div className="page-motion">
        {page === 'overview' && <PlanOverview data={data} activeGroups={activeGroups} tasks={tasksInActiveGroups} attention={attention} upcoming={upcoming} onGroup={openGroup} onStudent={openStudent} onTask={openTask} onReview={openReview} onNewGroup={() => { setDraftGroup(newGroup()); setModal('group') }} onStrategies={() => {setGroupId(null);setStudentId(null);setPage('strategies')}} onAnya={() => openPage('anya')} onHomework={() => openPage('homework')}/>}
        {page === 'strategies' && !group && <GroupsPage data={data} view={groupsView} onView={setGroupsView} filter={groupsFilter} onFilter={setGroupsFilter} onOpen={openGroup} onStudent={id=>{setStudentBackToRoster(true);openStudent(id)}} onNew={() => { setDraftGroup(newGroup()); setModal('group') }} onEdit={g => { setDraftGroup({ ...g }); setModal('group') }} onStatus={setGroupStatus} onDelete={removeGroup}/>}
        {page === 'strategies' && group && !student && <GroupDetailPage data={data} group={group} onBack={returnPage?returnToSource:()=>setGroupId(null)} backLabel={returnPage?`Вернуться: ${nav.find(item=>item.id===returnPage)?.label}`:'Все группы'} onStudent={id=>{setStudentBackToRoster(false);openStudent(id)}} onNewStudent={() => { setDraftStudent(newStudent(group.id)); setModal('student') }} onEditGroup={() => { setDraftGroup({ ...group }); setModal('group') }} onStatus={status => setGroupStatus(group,status)}/>} 
        {page === 'strategies' && student && <ProfilePage key={student.id} data={data} student={student} tasks={currentTasks} initialTab={profileTab} navigationKey={profileNavigationKey} focusedHomeworkId={focusedHomeworkId} onTabChange={setProfileTab} onBack={() => {setStudentId(null);setStudentBackToRoster(false)}} onAllGroups={() => {setStudentId(null);setGroupId(null);setGroupsView('groups');setReturnPage(null);setStudentBackToRoster(false)}} onReturn={returnPage?returnToSource:studentBackToRoster?()=>{setStudentId(null);setGroupId(null);setGroupsView('students');setStudentBackToRoster(false)}:undefined} returnLabel={returnPage?nav.find(item=>item.id===returnPage)?.label:studentBackToRoster?'список учениц':undefined} onEdit={() => { setDraftStudent({ ...student, links: { ...student.links } }); setModal('student') }} onDelete={() => removeStudent(student)} onNewTask={sectionId => { const order=Math.max(-1,...currentTasks.filter(task=>!sectionId||task.sectionId===sectionId).map(task=>task.order))+1;setDraftTask({...newTask(student.id,order,student.stage),sectionId:sectionId||''});setModal('task') }} onEditTask={openTask} onStudyStatus={changeStudyStatus} onMove={moveOrder} onAddSection={addSection} onRenameSection={renameSection} onDeleteSection={deleteSection} onChangeSection={changeSection} onPatch={patchStudent} onAddMeeting={addMeeting} onDeleteMeeting={deleteMeeting} onCreateHomework={createHomework} onUpdateHomework={updateHomework} onDeleteHomework={deleteHomework}/>}
        {page === 'anya' && <AnyaPage data={data} onStudent={openStudent} onTask={openTask} onApproval={setApproval} onRecall={recallTaskApproval} onComment={(id,comment)=>patchApprovalField(id,{approvalComment:comment},'Комментарий согласования обновлён')} onType={(id,type)=>patchApprovalField(id,{approvalType:type},'Тип проверки обновлён')} onMaterial={(id,url)=>patchApprovalField(id,{url},'Материал согласования обновлён')}/>}
        {page === 'homework' && <HomeworkPage data={data} onStudent={(id,homeworkId)=>openStudent(id,'homework',homeworkId)} onTask={openTask} onUpdate={updateHomework} onDelete={deleteHomework} onRestore={id=>updateHomework(id,{deletedAt:''})}/>}
        {page === 'prompts' && <Suspense fallback={<div className="knowledge-loading">Загружаем библиотеку…</div>}><KnowledgePage kind="prompts"/></Suspense>}
        {page === 'textbook' && <Suspense fallback={<div className="knowledge-loading">Загружаем учебник…</div>}><KnowledgePage kind="chapters"/></Suspense>}
      </div></div>
    </main>
    <Dialog open={modal === 'group'&&Boolean(draftGroup)} title={draftGroup&&data.groups.some(g => g.id === draftGroup.id) ? 'Редактировать группу' : 'Новая группа'} onClose={() => setModal(null)}>{draftGroup&&<GroupForm draft={draftGroup} setDraft={setDraftGroup} onSave={saveGroup} onCancel={() => setModal(null)}/>}</Dialog>
    <Dialog open={modal === 'student'&&Boolean(draftStudent)} title={draftStudent&&data.students.some(s => s.id === draftStudent.id) ? 'Профиль ученицы' : 'Новая ученица'} onClose={() => setModal(null)} wide>{draftStudent&&<StudentForm draft={draftStudent} setDraft={setDraftStudent} groups={data.groups} onSave={saveStudent} onCancel={() => setModal(null)}/>}</Dialog>
    <Dialog open={modal === 'taskDetail'&&Boolean(focusedTask)} title={focusedTask&&hasTechnicalUntitledTitle(focusedTask)?'Задача':focusedTask?.title||'Задача'} onClose={() => setModal(null)} wide>{focusedTask&&<TaskDetail task={focusedTask} studentName={focusedStudent?.name||''} groupName={focusedGroup?.name||''} sectionTitle={data.sections.find(section=>section.id===focusedTask.sectionId)?.title} onStatus={status=>changeStudyStatus(focusedTask.id,status)} onPrepareApproval={()=>changeTask(focusedTask.id,{approvalStatus:'to_send'},'Подготовлено согласование с Аней')} homeworkTitle={focusedHomework?.title} onHomework={focusedHomework?()=>{setModal(null);setFocusedHomeworkId(focusedHomework.id);setProfileTab('homework');setProfileNavigationKey(key=>key+1)}:undefined} onEdit={()=>{setDraftTask({...focusedTask});setModal('task')}}/>}</Dialog>
    <Dialog open={modal === 'task'&&Boolean(draftTask)} title={draftTask&&data.tasks.some(task=>task.id===draftTask.id)?'Редактировать задачу':'Новая задача'} onClose={()=>setModal(null)} wide>{draftTask&&<TaskForm draft={draftTask} setDraft={setDraftTask} sections={data.sections.filter(section=>section.studentId===draftTask.studentId)} existing={data.tasks.some(task=>task.id===draftTask.id)} onSave={saveTask} onCancel={()=>setModal(null)} onDelete={()=>removeTask(draftTask)}/>}</Dialog>
    <Dialog open={modal === 'backup'} title="Данные и резервные копии" onClose={() => setModal(null)}><div className="backup-content"><p>Данные этой версии хранятся в текущем браузере. Перед повседневным использованием нужна серверная синхронизация и защита доступа</p><button className="btn primary full" onClick={exportBackup}><Download size={17}/> Скачать резервную копию</button>{localStorage.getItem(PRE_SECTION_BACKUP_KEY)&&<button className="btn secondary full" onClick={exportBeforeSections}><Download size={17}/> Скачать копию до обновления стратегий</button>}{localStorage.getItem(`${STORAGE_KEY}-before-strategies-import`)&&<button className="btn secondary full" onClick={exportBeforeImport}><Download size={17}/> Скачать копию до импорта стратегий</button>}<button className="btn secondary full" onClick={() => fileInput.current?.click()}><Upload size={17}/> Восстановить из файла</button>{Boolean(data.importConflicts?.length)&&<div><strong>Требуют сверки после импорта</strong><ul>{data.importConflicts?.map(item=><li key={item}>{item}</li>)}</ul></div>}<input ref={fileInput} type="file" accept="application/json,.json" hidden onChange={e => { void importBackup(e.target.files?.[0]); e.target.value = '' }}/></div></Dialog>
    {confirmState?.danger?<DeleteConfirmDialog open title={confirmState.title} description={confirmState.description} confirmLabel={confirmState.confirmLabel} onConfirm={confirmState.action} onClose={()=>setConfirmState(null)}/>:<ConfirmDialog open={Boolean(confirmState)} title={confirmState?.title||''} description={confirmState?.description||''} confirmLabel={confirmState?.confirmLabel} onConfirm={confirmState?.action||(()=>{})} onClose={()=>setConfirmState(null)}/>}
    <NoticeDialog open={Boolean(notice)} title={notice?.title||''} description={notice?.description||''} onClose={()=>setNotice(null)}/>
  </div>
}

export default App
