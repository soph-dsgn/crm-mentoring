import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ClipboardTextIcon as ClipboardList, FileTextIcon as FileText, SquaresFourIcon as LayoutDashboard, MagnifyingGlassIcon as Search, SparkleIcon as Sparkles, UsersIcon as Users } from '@phosphor-icons/react'
import Select from './Select'
import PlanOverview from './PlanOverview'
import { GroupsPage, GroupDetailPage } from './GroupViews'
import ProfilePage, { type ProfileTab } from './ProfilePage'
import TaskDetail from './TaskDetail'
import TaskForm from './TaskForm'
import { hasTechnicalUntitledTitle } from './taskPresentation'
import { GroupForm, StudentForm } from './Forms'
import { activeTasks, addCalendarMonths, emptyData, studentTasks, taskColumn, today, uid } from './data'
import type { AppData, ApprovalStatus, Group, GroupStatus, Homework, Meeting, Stage, StrategySection, StrategyTask, Student, StudyStatus } from './types'
import HomeworkPage from './HomeworkPage'
import AnyaPage from './AnyaPage'
import { useCalmMotion } from './motion'
import { ConfirmDialog, DeleteConfirmDialog, Dialog, NoticeDialog } from './Dialogs'
import StrategyImportDialog from './strategies/StrategyImportDialog'
import AccountMenu from './accounts/AccountMenu'
import MyAccountPage from './accounts/MyAccountPage'
import { FlowBackground } from './FlowBackground'
import { useAuth, useCurrentUser } from './auth/authContext'
import { ChangePasswordForm } from './auth/AuthScreens'
import AccountAdminPage from './accounts/AccountAdminPage'
import StudentAccountPanel from './accounts/StudentAccountPanel'
import { useServerGroupsStudents } from './groups/useServerGroupsStudents'
import { canWriteGroup, canWriteStudent, groupStudentErrorMessage, serverDomainData } from './groups/groupStudentState'
import { ApiError } from './api/http'
import { useServerStrategies } from './strategies/useServerStrategies'
import { strategyErrorMessage, withServerStrategies } from './strategies/strategyState'
import { useServerLearning } from './learning/useServerLearning'
import { learningErrorMessage, withServerLearning } from './learning/learningState'
import { safeExternalUrl } from './safeExternalUrl'
import MigrationPage from './migration/MigrationPage'

type Page = 'overview' | 'strategies' | 'homework' | 'anya' | 'prompts' | 'accounts' | 'migration' | 'profile'
const KnowledgePage = lazy(() => import('./KnowledgePage'))
type Modal = 'strategyImport' | 'group' | 'student' | 'task' | 'taskDetail' | 'transfer' | 'password' | null
type ConfirmState = { title:string; description:string; confirmLabel:string; danger?:boolean; action:()=>void|Promise<void>; getErrorMessage?:(error:unknown)=>string }
const nav: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Обзор', icon: LayoutDashboard }, { id: 'strategies', label: 'Стратегии', icon: Users },
  { id: 'homework', label: 'Домашние задания', icon: ClipboardList }, { id: 'anya', label: 'Задачи Ани', icon: Sparkles },
  { id: 'prompts', label: 'Промпты', icon: FileText }
]
const extraPageLabels: Partial<Record<Page,string>> = { accounts: 'Аккаунты кураторов', migration: 'Перенос данных', profile: 'Мой профиль' }
const blankLinks = { figma: '', portfolio: '', resume: '', telegram: '', notion: '' }
const newGroup = (): Group => ({ id: uid(), name: '', startsAt: today(), endsAt: '', actualEndsAt: '', status: 'backlog', statusBeforeArchive: null, notes: '', createdAt: new Date().toISOString() })
const newStudent = (groupId: string): Student => ({ id: uid(), groupId, name: '', age: null, photo: '', avatarIndex: -1, stage: 'start', startsAt: today(), level: '', desiredPosition: '', careerGoal: '', links: { ...blankLinks }, background: '', experience: '', strengths: '', growthAreas: '', difficulties: '', expectations: '', personalNotes: '', pointA: '', pointB: '', notes: '', strategyUpdatedAt: new Date().toISOString(), createdAt: new Date().toISOString() })
const newTask = (studentId: string, order: number, stage: Stage): StrategyTask => ({ id: uid(), studentId, title: '', description: '', stage, status: 'backlog', studyStatus:'not_started', sectionId:'', period:'', materials:[], owner: 'Не назначен', dueAt: '', url: '', comments: '', order, blocker: false, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), reviewStatus:'none', approvalStatus:null, approvalType:'', approvalSentAt:'', approvalComment:'', history:[] })
const learningUiError=(error:unknown)=>Object.assign(new Error(learningErrorMessage(error)),{cause:error})

function App() {
  const calm = useCalmMotion()
  const currentUser = useCurrentUser()
  const { logout, changePassword, refreshCurrentUser } = useAuth()

  const [page, setPage] = useState<Page>('overview')
  const [groupsView,setGroupsView]=useState<'groups'|'students'>('groups')
  const [groupsFilter,setGroupsFilter]=useState<GroupStatus>('active')
  const [groupId, setGroupId] = useState<string | null>(null)
  const [studentId, setStudentId] = useState<string | null>(null)
  const [modal, setModal] = useState<Modal>(null)
  const [transferGroupId, setTransferGroupId] = useState('')
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

  const [confirmState,setConfirmState] = useState<ConfirmState|null>(null)
  const [notice,setNotice] = useState<{title:string;description:string}|null>(null)
  const [logoutPending,setLogoutPending] = useState(false)
  const [formPending,setFormPending]=useState(false)
  const formPendingRef=useRef(false)
  const [formError,setFormError]=useState('')

  const visibleNav = nav
  const serverDomain = useServerGroupsStudents(currentUser.id)
  const strategyDomain = useServerStrategies(currentUser.id,serverDomain.students)
  const learningDomain = useServerLearning(currentUser.id,serverDomain.students,strategyDomain.strategies,strategyDomain.refreshStudent)
  const domainData = useMemo<AppData>(() => withServerLearning(withServerStrategies(serverDomainData(emptyData(),serverDomain.groups,serverDomain.students),strategyDomain.sections,strategyDomain.tasks),learningDomain.meetings,learningDomain.homeworks), [serverDomain.groups, serverDomain.students, strategyDomain.sections, strategyDomain.tasks, learningDomain.meetings, learningDomain.homeworks])

  useEffect(() => { if ((page === 'accounts' || page === 'migration') && !currentUser.is_owner) setPage('overview') }, [currentUser.is_owner, page])

  const student = domainData.students.find(item => item.id === studentId)
  const group = domainData.groups.find(item => item.id === (student?.groupId ?? groupId))
  const focusedTask = domainData.tasks.find(t => t.id === focusedTaskId) ?? null
  const focusedStudent = domainData.students.find(s=>s.id===focusedTask?.studentId)
  const focusedGroup = domainData.groups.find(g=>g.id===focusedStudent?.groupId)
  const focusedHomework = focusedTask ? domainData.homeworks.filter(homework=>!homework.deletedAt&&homework.items.some(item=>item.taskId===focusedTask.id)).sort((a,b)=>b.createdAt.localeCompare(a.createdAt)).find(homework=>focusedTask.reviewStatus==='pending'?homework.status==='submitted':focusedTask.reviewStatus==='revision'?homework.status==='revision':true) : undefined
  const transferGroups = group && group.status !== 'archived' && canWriteGroup(currentUser,group)
    ? domainData.groups.filter(item => item.id !== group.id && item.status !== 'archived' && canWriteGroup(currentUser,item))
    : []
  const transferStudent = async () => {
    if (!student || !transferGroupId || formPendingRef.current) return
    formPendingRef.current = true
    setFormPending(true)
    setFormError('')
    try {
      const saved = await serverDomain.transferStudent(student, transferGroupId)
      setGroupId(saved.groupId)
      setModal(null)
    } catch (error) {
      setFormError(groupStudentErrorMessage(error))
      if (error instanceof ApiError && [403,404,409].includes(error.status)) void serverDomain.load()
    } finally {
      formPendingRef.current = false
      setFormPending(false)
    }
  }
  const currentTasks = student ? domainData.tasks.filter(task=>task.studentId===student.id) : []
  const activeGroups = domainData.groups.filter(g => g.status === 'active')

  const tasksInActiveGroups = activeTasks(domainData.tasks).filter(t => {
    const s = domainData.students.find(student => student.id === t.studentId)
    return s && !s.archivedAt && domainData.groups.some(g => g.id === s.groupId && g.status === 'active')
  })
  const openPage = (next: Page) => { if(next==='overview'||next==='strategies'||next==='anya'||next==='homework'){setGroupId(null);setStudentId(null)}if(next==='anya'||next==='homework'){void serverDomain.load();void strategyDomain.load();void learningDomain.load()}setPage(next); setReturnPage(null); setSearchOpen(false) }
  const openGroup = (id: string) => { setReturnPage(page==='strategies'?returnPage:page);setPage('strategies'); setGroupId(id); setStudentId(null);if(serverDomain.groups.some(item=>item.id===id))void serverDomain.refreshGroup(id).catch(error=>setNotice({title:'Не удалось обновить группу',description:groupStudentErrorMessage(error)})) }
  const openStudent = (id: string, tab: ProfileTab = 'overview', homeworkId: string | null = null) => { const s = domainData.students.find(v => v.id === id); if (!s) return;if(page!=='strategies')setStudentBackToRoster(false);setReturnPage(page==='strategies'?returnPage:page); setPage('strategies'); setGroupId(s.groupId); setStudentId(id); setProfileTab(tab); setFocusedHomeworkId(homeworkId);setProfileNavigationKey(key=>key+1);void Promise.all([serverDomain.refreshStudent(id),strategyDomain.refreshStudent(id),learningDomain.refreshStudent(id)]).catch(error=>setNotice({title:'Не удалось обновить профиль',description:error instanceof ApiError?learningErrorMessage(error):groupStudentErrorMessage(error)})) }

  const returnToSource=()=>{if(!returnPage)return;setPage(returnPage);setStudentId(null);setGroupId(null);setReturnPage(null);setStudentBackToRoster(false);setModal(null)}
  const openTask = (id: string) => {const task=domainData.tasks.find(item=>item.id===id);if(!task)return;openStudent(task.studentId,'strategy');setFocusedTaskId(id);setModal('taskDetail');void strategyDomain.loadHistory(task).catch(error=>setNotice({title:'Не удалось загрузить историю задачи',description:strategyErrorMessage(error)}))}
  const openReview = (id: string) => { const serverHomework=domainData.homeworks.find(h=>h.id===id&&!h.deletedAt);if(serverHomework){openStudent(serverHomework.studentId,'homework',id)} }
  const handleMutationError=(error:unknown)=>{if(error instanceof ApiError&&error.status===409){setFormError('Данные изменились в другой сессии. Скопируйте свои правки и откройте актуальную версию перед повторным сохранением');return}setFormError(groupStudentErrorMessage(error));if(error instanceof ApiError&&[403,404].includes(error.status))void serverDomain.load()}
  const saveGroup = async () => { if (!draftGroup?.name.trim()||formPendingRef.current) return;formPendingRef.current=true;setFormPending(true);setFormError('');try{const prepared={...draftGroup,endsAt:draftGroup.durationMonths?addCalendarMonths(draftGroup.startsAt,draftGroup.durationMonths):draftGroup.endsAt};const existing=Boolean(prepared.serverBacked);const saved=await serverDomain.saveGroup(prepared);setModal(null);if(!existing){setGroupsView('groups');setGroupsFilter(saved.status);openGroup(saved.id)}}catch(error){handleMutationError(error)}finally{formPendingRef.current=false;setFormPending(false)} }
  const setGroupStatus = async (target: Group, status: GroupStatus) => { try { await serverDomain.changeGroupStatus(target,status) } catch(error) { setNotice({title:'Не удалось изменить статус группы',description:groupStudentErrorMessage(error)});throw error } }
  const saveStudent = async () => { if (!draftStudent?.name.trim() || !draftStudent.groupId||formPendingRef.current) return;formPendingRef.current=true;setFormPending(true);setFormError('');try{const existing=Boolean(draftStudent.serverBacked);const saved=await serverDomain.saveStudent(draftStudent);setModal(null);if(!existing){setPage('strategies');setGroupId(saved.groupId);setStudentId(saved.id);setProfileTab('overview');setProfileNavigationKey(key=>key+1)}}catch(error){handleMutationError(error)}finally{formPendingRef.current=false;setFormPending(false)} }
  const patchStudent = (patch: Partial<Student>) => { if (!student) return;void serverDomain.saveStudent({...student,...patch}).catch(error=>setNotice({title:'Не удалось сохранить профиль',description:groupStudentErrorMessage(error)})) }
  const addMeeting = async (meeting: Meeting) => {try{await learningDomain.createMeeting(meeting.studentId,{date:meeting.date,title:meeting.title.trim(),summary:meeting.summary,notes:meeting.notes??''})}catch(error){throw learningUiError(error)} }
  const updateMeeting = async (meeting:Meeting) => {try{await learningDomain.updateMeeting(meeting,{date:meeting.date,title:meeting.title.trim(),summary:meeting.summary,notes:meeting.notes??''})}catch(error){throw learningUiError(error)} }
  const deleteMeeting = async (id: string) => {const meeting=domainData.meetings.find(item=>item.id===id);if(!meeting)return;try{await learningDomain.setMeetingArchived(meeting,true)}catch(error){throw learningUiError(error)} }
  const restoreMeeting=async(id:string)=>{const meeting=domainData.meetings.find(item=>item.id===id);if(!meeting)return;try{await learningDomain.setMeetingArchived(meeting,false)}catch(error){setNotice({title:'Не удалось восстановить встречу',description:learningErrorMessage(error)})}}
  const saveTask = async () => {
    if (!draftTask?.title.trim()) return
    if (formPendingRef.current) return
    formPendingRef.current = true
    setFormPending(true)
    setFormError('')
    try {
      await (draftTask.serverBacked ? strategyDomain.updateTask(draftTask) : strategyDomain.createTask(draftTask))
      setModal(null)
    } catch (error) {
      setFormError(strategyErrorMessage(error))
    } finally {
      formPendingRef.current = false
      setFormPending(false)
    }
  }

  const changeStudyStatus = (id:string,studyStatus:StudyStatus) => { const task=domainData.tasks.find(item=>item.id===id);if(task)void strategyDomain.changeStatus(task,studyStatus).catch(error=>setNotice({title:'Не удалось изменить статус',description:strategyErrorMessage(error)})) }
  const addSection = async (title: string) => {
    if (student) await strategyDomain.createSection(student.id,title)
  }
  const renameSection = async (id: string, title: string) => {
    const section = domainData.sections.find(item => item.id === id)
    if (section) await strategyDomain.renameSection(section,title)
  }
  const deleteSection = async (id: string) => {
    const section = domainData.sections.find(item => item.id === id)
    if (section) await strategyDomain.removeSection(section)
  }
  const changeSection = (id: string, sectionId: string) => {
    const task = domainData.tasks.find(item => item.id === id)
    if (task) void strategyDomain.moveTask(task, sectionId).catch(error=>setNotice({title:'Не удалось переместить задачу',description:strategyErrorMessage(error)}))
  }
  const createHomework = async (taskIds: string[], title: string, text: string):Promise<string> => { if (!student || !taskIds.length) return '';try{return (await learningDomain.createHomework(student.id,{title:title.trim()||'Домашнее задание',description:text,task_ids:taskIds,links:{},due_at:null})).id}catch(error){throw learningUiError(error)} }
  const updateHomework = async (id: string, patch: Partial<Homework>) => {const homework=domainData.homeworks.find(item=>item.id===id);if(!homework)return;try{let current=homework;if((patch.title!==undefined||patch.text!==undefined||patch.dueAt!==undefined||patch.links!==undefined)&&homework.status==='draft')current=await learningDomain.updateHomework(homework,{...(patch.title!==undefined?{title:patch.title}:{}),...(patch.text!==undefined?{description:patch.text}:{}),...(patch.dueAt!==undefined?{due_at:patch.dueAt||null}:{}),...(patch.links!==undefined?{links:patch.links}:{})});if(patch.status&&patch.status!==current.status){const submissionUrl=safeExternalUrl(patch.workUrl??current.workUrl);await learningDomain.transitionHomework(current,{status:patch.status,...(patch.status==='submitted'?{submission_text:patch.submissionText??current.submissionText??'',submission_links:submissionUrl?{work:submissionUrl}:{}}:{}),...(['revision','accepted'].includes(patch.status)?{curator_feedback:patch.comment??current.comment}:{})})}}catch(error){throw learningUiError(error)} }
  const deleteHomework = async (id:string) => {const homework=domainData.homeworks.find(item=>item.id===id);if(!homework)return;try{await learningDomain.setHomeworkArchived(homework,true)}catch(error){throw learningUiError(error)} }
  const restoreHomework=async(id:string)=>{const homework=domainData.homeworks.find(item=>item.id===id);if(!homework)return;try{await learningDomain.setHomeworkArchived(homework,false)}catch(error){throw learningUiError(error)} }
  const loadHomeworkHistory=async(id:string)=>{const homework=domainData.homeworks.find(item=>item.id===id);if(!homework)return;try{await learningDomain.loadHomeworkHistory(homework)}catch(error){throw learningUiError(error)}}
  const setApproval = async (id: string, status: ApprovalStatus, comment?:string) => {const task=domainData.tasks.find(item=>item.id===id);if(!task)return;try{await strategyDomain.transitionApproval(task,status,comment)}catch(error){setNotice({title:'Не удалось изменить согласование',description:strategyErrorMessage(error)});if(error instanceof ApiError&&[403,404].includes(error.status)){strategyDomain.evictStudent(task.studentId);void serverDomain.load()}} }
  const moveOrder = (task: StrategyTask, delta: number) => {void strategyDomain.reorderTasks(task,delta).catch(error=>setNotice({title:'Не удалось изменить порядок задач',description:strategyErrorMessage(error)})) }
  const moveSection=(section:StrategySection,delta:number)=>{if(!section.serverBacked)return;const ordered=domainData.sections.filter(item=>item.studentId===section.studentId).sort((a,b)=>a.order-b.order);const index=ordered.findIndex(item=>item.id===section.id);const target=ordered[index+delta];if(!target)return;[ordered[index],ordered[index+delta]]=[ordered[index+delta],ordered[index]];void strategyDomain.reorderSections(section.studentId,ordered).catch(error=>setNotice({title:'Не удалось изменить порядок разделов',description:strategyErrorMessage(error)}))}
  const removeGroup = (g: Group) => { setConfirmState({title:'Переместить группу в архив?',description:`Группа «${g.name}» и её состав сохранятся. Группу можно будет восстановить`,confirmLabel:'Переместить в архив',action:()=>setGroupStatus(g,'archived'),getErrorMessage:groupStudentErrorMessage}) }
  const removeStudent = (s: Student) => {setConfirmState({title:'Переместить профиль в архив?',description:`Профиль «${s.name}», аккаунт и учебная история сохранятся`,confirmLabel:'Переместить в архив',action:async()=>{await serverDomain.setStudentArchived(s,true)},getErrorMessage:groupStudentErrorMessage}) }
  const restoreStudent=(s:Student)=>setConfirmState({title:'Восстановить профиль?',description:`Профиль «${s.name}» снова появится среди активных`,confirmLabel:'Восстановить',action:async()=>{await serverDomain.setStudentArchived(s,false)},getErrorMessage:groupStudentErrorMessage})
  const removeTask = (task: StrategyTask) => {
    const restoring=Boolean(task.archivedAt);setConfirmState({title:restoring?'Восстановить задачу?':'Переместить задачу в архив?',description:restoring?`«${task.title}» снова появится в активной стратегии`:`«${task.title}» сохранится вместе с историей и согласованием`,confirmLabel:restoring?'Восстановить':'Переместить в архив',action:async()=>{await strategyDomain.setTaskArchived(task,!restoring);setModal(null)},getErrorMessage:strategyErrorMessage})

  }
  const completeCutover=async()=>{setGroupId(null);setStudentId(null);setModal(null);await Promise.allSettled([serverDomain.load(),strategyDomain.load(),learningDomain.load()])}

  const attention = useMemo(() => domainData.students.filter(s => !s.archivedAt && domainData.groups.some(g => g.id === s.groupId && g.status === 'active')).map(s => {
    const tasks = studentTasks(domainData, s.id)
    const blockers = tasks.filter(t => t.blocker && taskColumn(t) !== 'done').length
    const stale = Date.now() - new Date(s.strategyUpdatedAt).getTime() > 14 * 86400000
    return { student: s, blockers, stale }
  }).filter(x => x.blockers || x.stale).sort((a,b) => (b.blockers + Number(b.stale)) - (a.blockers + Number(a.stale))), [domainData])
  const upcoming = tasksInActiveGroups.filter(t => t.studyStatus === 'in_progress').sort((a,b) => a.order-b.order)
  // Badges show what waits for this user: Anya reviews handed-over tasks, curators fix returned ones.
  const writableStudentIds = new Set(domainData.students.filter(item=>canWriteStudent(currentUser,item,domainData.groups)).map(item=>item.id))
  const navBadges: Partial<Record<Page,number>> = {
    anya: domainData.tasks.filter(task=>!task.archivedAt&&(currentUser.is_owner?task.approvalStatus==='sent':task.approvalStatus==='revision'&&writableStudentIds.has(task.studentId))).length,
    homework: domainData.homeworks.filter(item=>item.status==='submitted'&&!item.deletedAt&&writableStudentIds.has(item.studentId)).length,
  }
  const normalizedSearch = searchTerm.trim().toLocaleLowerCase('ru-RU')
  const foundStudents = normalizedSearch ? domainData.students.filter(s => s.name.toLocaleLowerCase('ru-RU').includes(normalizedSearch)).slice(0, 5) : []
  const foundGroups = normalizedSearch ? domainData.groups.filter(g => g.name.toLocaleLowerCase('ru-RU').includes(normalizedSearch)).slice(0, 4) : []
  const domainPage=page==='overview'||page==='homework'||(page==='strategies')
  const canCreateGroups=currentUser.role==='admin'&&currentUser.is_active&&!currentUser.must_change_password
  const currentGroupWritable=Boolean(group&&(!group.serverBacked||canWriteGroup(currentUser,group)))
  const currentStudentWritable=Boolean(student&&(!student.serverBacked||canWriteStudent(currentUser,student,domainData.groups)))
  const focusedTaskWritable=Boolean(focusedTask&&(!focusedTask.serverBacked||focusedStudent&&canWriteStudent(currentUser,focusedStudent,domainData.groups)))
  const editGroup=async(target:Group)=>{setFormError('');try{const detail=target.serverBacked?await serverDomain.refreshGroup(target.id):target;setDraftGroup({...detail});setModal('group')}catch(error){setNotice({title:'Не удалось открыть редактирование',description:groupStudentErrorMessage(error)})}}
  const editStudent=async(target:Student)=>{setFormError('');try{const detail=target.serverBacked?await serverDomain.refreshStudent(target.id):target;setDraftStudent({...detail,links:{...detail.links}});setModal('student')}catch(error){setNotice({title:'Не удалось открыть редактирование',description:groupStudentErrorMessage(error)})}}
  return <div className={`app-shell ${page === 'overview' ? 'overview-shell' : ''}`}>
    <FlowBackground className="app-flow-background"/>
    <header className="workspace-toolbar">
      <div className="workspace-toolbar-left"><button className="brand-logo" aria-label="Кураторская — обзор" title="Обзор" onClick={() => openPage('overview')}><img src="/brand-star.svg" width="28" height="28" alt=""/><span>Кураторская</span></button></div>
      <nav className="toolbar-nav" aria-label="Основная навигация">{visibleNav.map(({ id, label, icon: Icon }) => { const badge=navBadges[id]; return <button key={id} className={page === id ? 'active' : ''} aria-current={page===id?'page':undefined} onClick={() => openPage(id)}><Icon size={17}/><span>{label}</span>{badge?<i className="toolbar-badge" aria-label={`требуют действия: ${badge}`}>{badge}</i>:null}</button> })}</nav>
      <div className="workspace-toolbar-right"><button className="toolbar-icon" aria-label="Поиск группы или ученицы" title="Поиск" onClick={() => setSearchOpen(v => !v)}><Search size={16} weight="regular"/></button><AccountMenu user={currentUser} logoutPending={logoutPending} onOpen={target => openPage(target)} onLogout={() => { setLogoutPending(true); void logout().catch(() => setNotice({title:'Не удалось выйти',description:'Сессия остаётся активной. Проверьте соединение с сервером и повторите попытку'})).finally(() => setLogoutPending(false)) }}/></div>
      <AnimatePresence initial={false}>{searchOpen && <motion.div key="search" className="toolbar-search-panel" {...calm.popover}><input autoFocus aria-label="Поиск группы или ученицы" placeholder="Группа или ученица" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}/>{normalizedSearch && <div className="toolbar-search-results">{foundStudents.map(s => <button key={s.id} onClick={() => { openStudent(s.id); setSearchOpen(false); setSearchTerm('') }}><strong>{s.name}</strong><small>{domainData.groups.find(group=>group.id===s.groupId)?.name||'Группа не найдена'} · ученица</small></button>)}{foundGroups.map(g => <button key={g.id} onClick={() => { openGroup(g.id); setSearchOpen(false); setSearchTerm('') }}><strong>{g.name}</strong><small>Группа</small></button>)}{!foundStudents.length && !foundGroups.length && <p>Ничего не найдено</p>}</div>}</motion.div>}</AnimatePresence>
    </header>
    <main className={`main ${page === 'overview' ? 'overview-main' : ''}`}>
      <div className="content"><div className="page-motion">
        {domainPage&&(serverDomain.status==='loading'||(page==='overview'&&strategyDomain.status==='loading'))&&<div className="account-state" role="status"><span className="account-spinner"/>Загружаем группы, профили и стратегии…</div>}
        {domainPage&&serverDomain.status==='error'&&<div className="account-state account-state-error" role="alert"><strong>Не удалось загрузить группы и профили</strong><p>{groupStudentErrorMessage(serverDomain.error)}</p><button className="btn secondary" onClick={()=>void serverDomain.load()}>Повторить</button></div>}
        {page==='overview'&&strategyDomain.status==='error'&&<div className="account-state account-state-error" role="alert"><strong>Не удалось загрузить стратегии</strong><p>{strategyErrorMessage(strategyDomain.error)}</p><button className="btn secondary" onClick={()=>void strategyDomain.load()}>Повторить</button></div>}
        {page === 'overview'&&serverDomain.status==='ready'&&strategyDomain.status==='ready' && <PlanOverview data={domainData} canLaunch={group=>canWriteGroup(currentUser,group)} activeGroups={activeGroups} tasks={tasksInActiveGroups} attention={attention} upcoming={upcoming} onGroup={openGroup} onStudent={openStudent} onTask={openTask} onReview={openReview} onNewGroup={() => { setFormError('');setDraftGroup(newGroup()); setModal('group') }} onStrategies={() => {setGroupId(null);setStudentId(null);setPage('strategies')}} onAnya={() => openPage('anya')} onHomework={() => openPage('homework')}/>}
        {page === 'strategies'&&serverDomain.status==='ready' && !group && <GroupsPage data={domainData} view={groupsView} onView={setGroupsView} filter={groupsFilter} onFilter={setGroupsFilter} onOpen={openGroup} onStudent={id=>{setStudentBackToRoster(true);openStudent(id)}} canCreate={canCreateGroups} canWrite={target=>canWriteGroup(currentUser,target)} onNew={() => { setFormError('');setDraftGroup(newGroup()); setModal('group') }} onEdit={g => {void editGroup(g)}} onStatus={(target,status)=>{void setGroupStatus(target,status).catch(()=>undefined)}} onDelete={removeGroup}/>}
        {page === 'strategies'&&(serverDomain.status==='ready') && group && !student && <GroupDetailPage data={domainData} group={group} canWrite={currentGroupWritable} onBack={returnPage?returnToSource:()=>{setGroupId(null)}} backLabel={returnPage?`Вернуться: ${(visibleNav.find(item=>item.id===returnPage)?.label??extraPageLabels[returnPage])}`:'Все группы'} onStudent={id=>{setStudentBackToRoster(false);openStudent(id)}} onNewStudent={() => { setFormError('');setDraftStudent(newStudent(group.id)); setModal('student') }} onEditGroup={() => {void editGroup(group)}} onStatus={status => {void setGroupStatus(group,status).catch(()=>undefined)}}/>}
        {page==='strategies'&&student&&strategyDomain.status==='loading'&&<div className="account-state" role="status"><span className="account-spinner"/>Загружаем стратегию…</div>}
        {page==='strategies'&&student&&strategyDomain.status==='error'&&<div className="account-state account-state-error" role="alert"><strong>Не удалось загрузить стратегию</strong><p>{strategyErrorMessage(strategyDomain.error)}</p><button className="btn secondary" onClick={()=>void strategyDomain.refreshStudent(student.id)}>Повторить</button></div>}
        {page === 'strategies'&&(serverDomain.status==='ready'&&strategyDomain.status==='ready') && student && <ProfilePage key={student.id} data={domainData} student={student} tasks={currentTasks} initialTab={profileTab} navigationKey={profileNavigationKey} focusedHomeworkId={focusedHomeworkId} onTabChange={setProfileTab} onBack={() => {setStudentId(null);setStudentBackToRoster(false)}} onAllGroups={() => {setStudentId(null);setGroupId(null);setGroupsView('groups');setReturnPage(null);setStudentBackToRoster(false)}} onReturn={returnPage?returnToSource:studentBackToRoster?()=>{setStudentId(null);setGroupId(null);setGroupsView('students');setStudentBackToRoster(false)}:undefined} returnLabel={returnPage?(visibleNav.find(item=>item.id===returnPage)?.label??extraPageLabels[returnPage]):studentBackToRoster?'список учениц':undefined} serverManaged={student.serverBacked} hasStrategy={!student.serverBacked||Boolean(strategyDomain.strategies[student.id])} onImportStrategy={student.serverBacked&&currentStudentWritable?()=>setModal('strategyImport'):undefined} onCreateStrategy={()=>{void strategyDomain.ensureStrategy(student.id).catch(error=>setNotice({title:'Не удалось создать стратегию',description:strategyErrorMessage(error)}))}} canEdit={currentStudentWritable} accountPanel={student.serverBacked?<StudentAccountPanel studentId={student.id} canManage={currentStudentWritable}/>:undefined} meetingLoading={Boolean(student.serverBacked&&learningDomain.meetingStatus==='loading')} meetingLoadError={student.serverBacked&&learningDomain.meetingErrorsByStudent.has(student.id)?learningErrorMessage(learningDomain.meetingErrorsByStudent.get(student.id)):''} homeworkLoading={Boolean(student.serverBacked&&learningDomain.homeworkStatus==='loading')} homeworkLoadError={student.serverBacked&&learningDomain.homeworkErrorsByStudent.has(student.id)?learningErrorMessage(learningDomain.homeworkErrorsByStudent.get(student.id)):''} onRetryMeetings={()=>void learningDomain.refreshMeetings(student.id).catch(()=>undefined)} onRetryHomeworks={() => void Promise.all([learningDomain.refreshHomeworks(student.id), strategyDomain.refreshStudent(student.id)]).catch(() => undefined)} onTransfer={transferGroups.length ? () => {setTransferGroupId('');setFormError('');setModal('transfer')} : undefined} onEdit={() => {void editStudent(student)}} onDelete={() => removeStudent(student)} onRestore={()=>restoreStudent(student)} onNewTask={sectionId => { const order=Math.max(-1,...currentTasks.filter(task=>!sectionId||task.sectionId===sectionId).map(task=>task.order))+1;setFormError('');setDraftTask({...newTask(student.id,order,student.stage),sectionId:sectionId||''});setModal('task') }} onEditTask={openTask} onStudyStatus={changeStudyStatus} onMove={moveOrder} onMoveSection={moveSection} onAddSection={addSection} onRenameSection={renameSection} onDeleteSection={deleteSection} onChangeSection={changeSection} onPatch={patchStudent} onAddMeeting={addMeeting} onUpdateMeeting={updateMeeting} onDeleteMeeting={deleteMeeting} onRestoreMeeting={restoreMeeting} onCreateHomework={createHomework} onUpdateHomework={updateHomework} onDeleteHomework={deleteHomework} onRestoreHomework={restoreHomework} onHomeworkHistory={loadHomeworkHistory}/>}
        {page === 'anya' && <AnyaPage data={domainData} reviewer={currentUser.is_owner} loading={serverDomain.status==='loading'||strategyDomain.status==='loading'} error={serverDomain.status==='error'?groupStudentErrorMessage(serverDomain.error):strategyDomain.status==='error'?strategyErrorMessage(strategyDomain.error):''} partialErrorCount={serverDomain.partialErrorCount+strategyDomain.partialErrorCount} onRetry={()=>{void serverDomain.load();void strategyDomain.load()}} onStudent={id=>openStudent(id,'strategy')} onTask={openTask} onApproval={setApproval} canWriteTask={task=>{const target=domainData.students.find(item=>item.id===task.studentId);return Boolean(target&&canWriteStudent(currentUser,target,domainData.groups))}}/>}
        {page === 'homework' && <HomeworkPage data={domainData} serverManaged loading={serverDomain.status==='loading'||strategyDomain.status==='loading'||learningDomain.homeworkStatus==='loading'} error={serverDomain.status==='error'?groupStudentErrorMessage(serverDomain.error):strategyDomain.status==='error'?strategyErrorMessage(strategyDomain.error):learningDomain.homeworkStatus==='error'?learningErrorMessage(learningDomain.homeworkError):''} partialErrorCount={serverDomain.partialErrorCount+strategyDomain.partialErrorCount+learningDomain.homeworkPartialErrorCount} onRetry={()=>{void serverDomain.load();void strategyDomain.load();void learningDomain.loadHomeworks()}} onStudent={(id,homeworkId)=>openStudent(id,'homework',homeworkId)} onTask={openTask} onUpdate={updateHomework} onDelete={deleteHomework} onRestore={restoreHomework} onHistory={loadHomeworkHistory} canWriteHomework={homework=>{const target=domainData.students.find(item=>item.id===homework.studentId);return Boolean(target&&canWriteStudent(currentUser,target,domainData.groups))}}/>}
        {page === 'prompts' && <Suspense fallback={<div className="knowledge-loading">Загружаем библиотеку…</div>}><KnowledgePage kind="prompts"/></Suspense>}
        {page === 'profile' && <MyAccountPage user={currentUser} groupCount={domainData.groups.filter(item=>item.curatorId===currentUser.id&&item.status!=='archived').length} onSaved={refreshCurrentUser} onChangePassword={() => setModal('password')} onLogout={() => { setLogoutPending(true); void logout().finally(() => setLogoutPending(false)) }}/>}
        {page === 'accounts' && <AccountAdminPage currentUser={currentUser} onRefreshUser={refreshCurrentUser}/>}
        {page === 'migration' && <MigrationPage currentUser={currentUser} onCutover={completeCutover}/>}
      </div></div>
    </main>
    {student&&student.serverBacked&&<StrategyImportDialog open={modal==='strategyImport'} student={student} onClose={()=>setModal(null)} onImported={async()=>{await Promise.allSettled([serverDomain.refreshStudent(student.id),strategyDomain.refreshStudent(student.id)]);setProfileTab('strategy')}}/>}
    <Dialog open={modal === 'password'} title="Сменить пароль" description="На других устройствах потребуется войти заново" onClose={() => setModal(null)}>
      {modal==='password'&&<ChangePasswordForm onSubmit={async payload => { await changePassword(payload); setModal(null); setNotice({title:'Пароль изменён',description:'Вы остаётесь в системе. На других устройствах потребуется войти с новым паролем'}) }}/>}
    </Dialog>
    <Dialog open={modal === 'transfer' && Boolean(student)} title="Перевести в другую группу" onClose={() => setModal(null)} dismissible={!formPending}>
      <form className="backup-content" onSubmit={event => {event.preventDefault();void transferStudent()}}>
        <p>Стратегия, аккаунт и учебная история ученицы сохранятся</p>
        <Select aria-label="Группа назначения" value={transferGroupId} disabled={formPending} onChange={event => setTransferGroupId(event.target.value)}>
          <option value="">Выберите группу</option>
          {transferGroups.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
        {formError&&<p role="alert">{formError}</p>}
        <button className="btn primary" type="submit" disabled={formPending || !transferGroups.some(item => item.id === transferGroupId)}>{formPending ? 'Переводим…' : 'Перевести'}</button>
        <button className="btn secondary" type="button" disabled={formPending} onClick={() => setModal(null)}>Отмена</button>
      </form>
    </Dialog>
    <Dialog open={modal === 'group'&&Boolean(draftGroup)} title={draftGroup&&(draftGroup.serverBacked) ? 'Редактировать группу' : 'Новая группа'} onClose={() => {if(!formPending)setModal(null)}} dismissible={!formPending}>{draftGroup&&<GroupForm draft={draftGroup} setDraft={setDraftGroup} onSave={()=>{void saveGroup()}} onCancel={() => setModal(null)} pending={formPending} error={formError}/>}</Dialog>
    <Dialog open={modal === 'student'&&Boolean(draftStudent)} title={draftStudent&&(draftStudent.serverBacked) ? 'Профиль ученицы' : 'Новая ученица'} onClose={() => {if(!formPending)setModal(null)}} dismissible={!formPending} wide>{draftStudent&&<StudentForm draft={draftStudent} setDraft={setDraftStudent} groups={domainData.groups} onSave={()=>{void saveStudent()}} onCancel={() => setModal(null)} pending={formPending} error={formError} groupLocked/>}</Dialog>
    <Dialog open={modal === 'taskDetail'&&Boolean(focusedTask)} title={focusedTask&&hasTechnicalUntitledTitle(focusedTask)?'Задача':focusedTask?.title||'Задача'} onClose={() => setModal(null)} wide>{focusedTask&&<TaskDetail task={focusedTask} studentName={focusedStudent?.name||''} groupName={focusedGroup?.name||''} sectionTitle={domainData.sections.find(section=>section.id===focusedTask.sectionId)?.title} onStatus={status=>changeStudyStatus(focusedTask.id,status)} onHandoff={comment=>strategyDomain.createApproval(focusedTask,comment).then(()=>undefined).catch(error=>setNotice({title:'Не удалось передать задачу Ане',description:strategyErrorMessage(error)}))} homeworkTitle={focusedHomework?.title} onHomework={focusedHomework?()=>{setModal(null);setFocusedHomeworkId(focusedHomework.id);setProfileTab('homework');setProfileNavigationKey(key=>key+1)}:undefined} onEdit={()=>{setFormError('');setDraftTask({...focusedTask});setModal('task')}} canEdit={focusedTaskWritable}/>}</Dialog>
    <Dialog open={modal === 'task'&&Boolean(draftTask)} title={draftTask&&(draftTask.serverBacked)?'Редактировать задачу':'Новая задача'} onClose={()=>{if(!formPending)setModal(null)}} dismissible={!formPending} wide>{draftTask&&<TaskForm draft={draftTask} setDraft={setDraftTask} sections={domainData.sections.filter(section=>section.studentId===draftTask.studentId)} existing={Boolean(draftTask.serverBacked)} serverManaged={Boolean(draftTask.serverBacked||domainData.students.some(item=>item.id===draftTask.studentId))} pending={formPending} error={formError} onSave={()=>{void saveTask()}} onCancel={()=>setModal(null)} onDelete={()=>removeTask(draftTask)}/>}</Dialog>
    {confirmState?.danger?<DeleteConfirmDialog open title={confirmState.title} description={confirmState.description} confirmLabel={confirmState.confirmLabel} getErrorMessage={confirmState.getErrorMessage} onConfirm={confirmState.action} onClose={()=>setConfirmState(null)}/>:<ConfirmDialog open={Boolean(confirmState)} title={confirmState?.title||''} description={confirmState?.description||''} confirmLabel={confirmState?.confirmLabel} getErrorMessage={confirmState?.getErrorMessage} onConfirm={confirmState?.action||(()=>{})} onClose={()=>setConfirmState(null)}/>}
    <NoticeDialog open={Boolean(notice)} title={notice?.title||''} description={notice?.description||''} onClose={()=>setNotice(null)}/>
  </div>
}

export default App
