import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  ArrowClockwiseIcon as ArrowClockwise,
  ArrowSquareOutIcon as ExternalLink,
  CalendarDotsIcon as CalendarDots,
  CheckCircleIcon as CheckCircle,
  ClipboardTextIcon as ClipboardText,
  HouseIcon as House,
  ListChecksIcon as ListChecks,
  SignOutIcon as SignOut,
  UserCircleIcon as UserCircle,
} from '@phosphor-icons/react'
import { HOMEWORK_STATUS, REVIEW_STATUS, STAGES, STUDY_STATUS } from '../data'
import { safeExternalUrl } from '../safeExternalUrl'
import type { Homework, Meeting, StrategySection, StrategyTask, Student } from '../types'
import { useAuth, useCurrentUser } from '../auth/authContext'
import { studentErrorMessage, studentHomeworkAction, studentProfileIdFromUrl } from './studentState'
import { useStudentWorkspace } from './useStudentWorkspace'

type StudentPage='profile'|'strategy'|'homeworks'|'meetings'
type ResourceState={status:'loading'|'ready'|'error';error:unknown}

const nav:{id:StudentPage;label:string;icon:typeof House}[]=[
  {id:'profile',label:'Мой профиль',icon:House},
  {id:'strategy',label:'Стратегия',icon:ListChecks},
  {id:'homeworks',label:'Домашние задания',icon:ClipboardText},
  {id:'meetings',label:'Встречи',icon:CalendarDots},
]

const dateTime=(value:string)=>value?new Date(value).toLocaleString('ru-RU',{day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'}):'—'
const dateOnly=(value:string)=>value?new Date(`${value.slice(0,10)}T00:00:00`).toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'}):'—'
const taskCount=(tasks:StrategyTask[],status:StrategyTask['studyStatus'])=>tasks.filter(task=>task.studyStatus===status&&!task.archivedAt).length

function StudentState({state,onRetry,children,emptyTitle,emptyText}:{state:ResourceState;onRetry:()=>void;children:ReactNode;emptyTitle?:string;emptyText?:string}){
  if(state.status==='loading')return <div className="student-state" role="status"><span className="account-spinner"/>Загружаем данные…</div>
  if(state.status==='error')return <div className="student-state student-state-error" role="alert"><strong>Не удалось загрузить данные</strong><p>{studentErrorMessage(state.error)}</p><button className="btn secondary" onClick={onRetry}><ArrowClockwise size={16}/> Повторить</button></div>
  if(!children&&emptyTitle)return <div className="student-empty"><strong>{emptyTitle}</strong><p>{emptyText}</p></div>
  return <>{children}</>
}

function ProfileView({profile,groupName,groupStatus,tasks}:{profile:Student;groupName:string;groupStatus:string;tasks:StrategyTask[]}){
  const stage=STAGES.find(item=>item.id===profile.stage)?.label??'Обучение'
  const publicLinks=Object.entries(profile.links).filter(([,value])=>safeExternalUrl(value))
  return <div className="student-view">
    <div className="student-hero"><div><span className="student-eyebrow">Личное пространство</span><h1>{profile.name}</h1><p>{stage} · {groupName}</p></div><div className="student-progress-ring"><strong>{taskCount(tasks,'done')}</strong><span>задач выполнено</span></div></div>
    {profile.archivedAt&&<div className="student-notice">Профиль находится в архиве. История и принятые работы остаются доступными</div>}
    <div className="student-profile-grid">
      <section className="student-card"><span className="student-card-label">Моя цель</span><h2>{profile.desiredPosition||'Цель уточняется'}</h2><p>{profile.careerGoal||'Обсудите цель с куратором на ближайшей встрече'}</p></section>
      <section className="student-card"><span className="student-card-label">Точка А</span><p>{profile.pointA||'Пока не заполнено'}</p></section>
      <section className="student-card"><span className="student-card-label">Точка Б</span><p>{profile.pointB||'Пока не заполнено'}</p></section>
      <section className="student-card"><span className="student-card-label">Группа</span><h2>{groupName}</h2><p>{groupStatus}</p></section>
    </div>
    {publicLinks.length>0&&<section className="student-card student-links"><span className="student-card-label">Мои материалы</span><div>{publicLinks.map(([label,url])=><a key={label} href={url} target="_blank" rel="noopener noreferrer">{label}<ExternalLink size={15}/></a>)}</div></section>}
  </div>
}

function StrategyView({sections,tasks}:{sections:StrategySection[];tasks:StrategyTask[]}){
  const ordered=[...sections].sort((a,b)=>a.order-b.order)
  if(!ordered.length)return <div className="student-empty"><ListChecks size={30}/><strong>Стратегия пока не готова</strong><p>Когда куратор добавит разделы и задачи, они появятся здесь</p></div>
  return <div className="student-view"><div className="student-page-head"><span className="student-eyebrow">Мой маршрут</span><h1>Стратегия</h1><p>Задачи расположены в том порядке, в котором их удобнее проходить</p></div><div className="student-strategy-summary"><span><strong>{taskCount(tasks,'in_progress')}</strong> в процессе</span><span><strong>{taskCount(tasks,'done')}</strong> выполнено</span><span><strong>{tasks.filter(task=>Boolean(task.archivedAt)).length}</strong> в архиве</span></div><div className="student-sections">{ordered.map(section=>{
    const sectionTasks=tasks.filter(task=>task.sectionId===section.id).sort((a,b)=>a.order-b.order)
    return <section className="student-section" key={section.id}><div className="student-section-head"><h2>{section.title}</h2><span>{sectionTasks.length} задач</span></div>{sectionTasks.length?<div className="student-task-list">{sectionTasks.map(task=><article className={`student-task${task.archivedAt?' is-archived':''}`} key={task.id}><div className="student-task-main"><div><h3>{task.title}</h3>{task.description&&<p>{task.description}</p>}</div><span className={`student-status status-${task.studyStatus}`}>{STUDY_STATUS[task.studyStatus]}</span></div><div className="student-task-meta"><span>{task.reviewStatus==='none'?'Без проверки':REVIEW_STATUS[task.reviewStatus]}</span>{task.period&&<span>{task.period}</span>}{task.archivedAt&&<span>Архив</span>}</div>{task.materials.length>0&&<ul>{task.materials.map((material,index)=><li key={`${task.id}-${index}`}>{safeExternalUrl(material)?<a href={material} target="_blank" rel="noopener noreferrer">Материал {index+1}<ExternalLink size={14}/></a>:material}</li>)}</ul>}</article>)}</div>:<p className="student-section-empty">В этом разделе пока нет задач</p>}</section>
  })}</div></div>
}

function MeetingView({meetings}:{meetings:Meeting[]}){
  if(!meetings.length)return <div className="student-empty"><CalendarDots size={30}/><strong>Встреч пока нет</strong><p>После встречи здесь появятся итог и договорённости</p></div>
  return <div className="student-view"><div className="student-page-head"><span className="student-eyebrow">История работы</span><h1>Встречи</h1><p>Итоги персональных встреч и следующие ориентиры</p></div><div className="student-timeline">{[...meetings].sort((a,b)=>b.date.localeCompare(a.date)).map(meeting=><article key={meeting.id} className={`student-meeting${meeting.archivedAt?' is-archived':''}`}><time>{dateOnly(meeting.date)}</time><div><h2>{meeting.title}</h2><p>{meeting.summary||'Итоги встречи пока не добавлены'}</p>{meeting.archivedAt&&<span>Архивная встреча</span>}</div></article>)}</div></div>
}

function HomeworkSnapshots({homework}:{homework:Homework}){
  return <div className="student-snapshots">{homework.items.map(item=><article key={item.id??item.taskId}><h4>{item.title}</h4>{item.description&&<p>{item.description}</p>}{item.period&&<small>{item.period}</small>}{Object.entries(item.links??{}).map(([label,url])=>safeExternalUrl(url)&&<a key={label} href={url} target="_blank" rel="noopener noreferrer">{label}<ExternalLink size={14}/></a>)}</article>)}</div>
}

function StudentHomeworkCard({homework,pending,onSubmit,onHistory}:{homework:Homework;pending:boolean;onSubmit:(homework:Homework,text:string,url:string)=>Promise<unknown>;onHistory:(id:string)=>Promise<unknown>}){
  const action=studentHomeworkAction(homework)
  const [text,setText]=useState(homework.submissionText??'')
  const [url,setUrl]=useState(homework.workUrl??'')
  const [error,setError]=useState('')
  const [sent,setSent]=useState(false)
  const [historyStatus,setHistoryStatus]=useState<'idle'|'loading'|'loaded'|'error'>('idle')
  useEffect(()=>{setText(homework.submissionText??'');setUrl(homework.workUrl??'');setSent(false)},[homework.id,homework.submissionText,homework.workUrl,homework.version])
  const validUrl=!url.trim()||Boolean(safeExternalUrl(url))
  const submit=async(event:FormEvent)=>{event.preventDefault();if(pending||(!text.trim()&&!url.trim())||!validUrl)return;setError('');setSent(false);try{await onSubmit(homework,text,url);setSent(true)}catch(caught){setError(studentErrorMessage(caught))}}
  const loadHistory=async()=>{if(historyStatus==='loading')return;setHistoryStatus('loading');try{await onHistory(homework.id);setHistoryStatus('loaded')}catch{setHistoryStatus('error')}}
  return <article className={`student-homework${homework.archivedAt?' is-archived':''}`} aria-busy={pending}><div className="student-homework-head"><div><span>{homework.archivedAt?'Архив':HOMEWORK_STATUS[homework.status]}</span><h2>{homework.title}</h2></div>{homework.dueAt&&<time>до {dateOnly(homework.dueAt)}</time>}</div>{homework.text&&<p className="student-homework-description">{homework.text}</p>}<HomeworkSnapshots homework={homework}/>{homework.comment&&<div className={`student-feedback${homework.status==='revision'?' needs-work':''}`}><strong>{homework.status==='revision'?'Что нужно доработать':'Комментарий куратора'}</strong><p>{homework.comment}</p></div>}{homework.submissionText&&homework.status!=='revision'&&<div className="student-submission"><strong>Моя отправка</strong><p>{homework.submissionText}</p>{safeExternalUrl(homework.workUrl)&&<a href={homework.workUrl} target="_blank" rel="noopener noreferrer">Открыть работу<ExternalLink size={14}/></a>}</div>}
    {action&&<form className="student-submit" onSubmit={event=>void submit(event)}><label><span>{action==='resubmit'?'Исправленная работа':'Результат работы'}</span><textarea rows={3} value={text} onChange={event=>setText(event.target.value)} placeholder="Коротко опишите, что сделано"/></label><label><span>Ссылка на результат</span><input type="url" value={url} onChange={event=>setUrl(event.target.value)} placeholder="https://…" aria-invalid={!validUrl}/></label>{!validUrl&&<p className="student-field-error">Проверьте ссылку</p>}{error&&<p className="student-field-error" role="alert">{error}</p>}{sent&&<p className="student-submit-success" role="status"><CheckCircle size={17}/> Работа отправлена куратору</p>}<button className="btn dark" type="submit" disabled={pending||(!text.trim()&&!url.trim())||!validUrl}>{pending?'Отправляем…':action==='resubmit'?'Отправить повторно':'Отправить на проверку'}</button></form>}
    <details className="student-history" onToggle={event=>{if(event.currentTarget.open&&!homework.history?.length&&historyStatus==='idle')void loadHistory()}}><summary>История задания</summary>{homework.history?.length?<ol>{homework.history.map(item=><li key={item.id}><span>{item.toStatus?HOMEWORK_STATUS[item.toStatus]:'Задание обновлено'}</span><time>{dateTime(item.createdAt)}</time></li>)}</ol>:historyStatus==='loading'?<p role="status">Загружаем историю…</p>:historyStatus==='error'?<div className="student-history-error" role="alert"><p>Не удалось загрузить историю</p><button className="btn secondary" type="button" onClick={()=>void loadHistory()}><ArrowClockwise size={14}/> Повторить</button></div>:historyStatus==='loaded'?<p>История пока пуста</p>:<p>Откройте раздел, чтобы загрузить историю</p>}</details>
  </article>
}

function HomeworksView({homeworks,pending,onSubmit,onHistory}:{homeworks:Homework[];pending:Set<string>;onSubmit:(homework:Homework,text:string,url:string)=>Promise<unknown>;onHistory:(id:string)=>Promise<unknown>}){
  if(!homeworks.length)return <div className="student-empty"><ClipboardText size={30}/><strong>Домашних заданий пока нет</strong><p>Выданные задания появятся здесь</p></div>
  return <div className="student-view"><div className="student-page-head"><span className="student-eyebrow">Работа между встречами</span><h1>Домашние задания</h1><p>Отправляйте результат здесь и возвращайтесь к правкам куратора</p></div><div className="student-homework-list">{[...homeworks].sort((a,b)=>(b.issuedAt||b.createdAt).localeCompare(a.issuedAt||a.createdAt)).map(homework=><StudentHomeworkCard key={homework.id} homework={homework} pending={pending.has(homework.id)} onSubmit={onSubmit} onHistory={onHistory}/>)}</div></div>
}

function MissingStudentContext({onLogout}:{onLogout:()=>Promise<void>}){return <main className="student-context-missing"><div className="student-context-card"><UserCircle size={34}/><span className="student-eyebrow">Кураторская</span><h1>Нужна персональная ссылка</h1><p>Откройте ссылку, которую передал куратор вместе с данными для входа. В ней безопасно указан ваш профиль</p><button className="btn secondary" onClick={()=>void onLogout()}><SignOut size={16}/> Выйти</button></div></main>}

export default function StudentApp(){
  const user=useCurrentUser()
  const {logout}=useAuth()
  const studentId=studentProfileIdFromUrl(window.location.href)
  if(!studentId)return <MissingStudentContext onLogout={logout}/>
  return <StudentWorkspace key={`${user.id}:${studentId}`} studentId={studentId} login={user.login} onLogout={logout}/>
}

function StudentWorkspace({studentId,login,onLogout}:{studentId:string;login:string;onLogout:()=>Promise<void>}){
  const [page,setPage]=useState<StudentPage>('profile')
  const [logoutPending,setLogoutPending]=useState(false)
  const workspace=useStudentWorkspace(studentId)
  const groupStatus=workspace.group?.status==='active'?'Активная группа':workspace.group?.status==='completed'?'Обучение завершено':workspace.group?.status==='archived'?'Группа в архиве':'Подготовка к старту'
  const pageState=page==='strategy'?workspace.strategyState:page==='homeworks'?workspace.homeworkState:page==='meetings'?workspace.meetingState:workspace.profileState
  const retry=page==='strategy'?workspace.retryStrategy:page==='homeworks'?workspace.retryHomeworks:page==='meetings'?workspace.retryMeetings:workspace.reload
  const content=useMemo(()=>{
    if(!workspace.profile||!workspace.group)return null
    if(page==='profile')return <ProfileView profile={workspace.profile} groupName={workspace.group.name} groupStatus={groupStatus} tasks={workspace.tasks}/>
    if(page==='strategy')return <StrategyView sections={workspace.sections} tasks={workspace.tasks}/>
    if(page==='homeworks')return <HomeworksView homeworks={workspace.homeworks} pending={workspace.pendingHomeworks} onSubmit={workspace.submitHomework} onHistory={workspace.loadHomeworkHistory}/>
    return <MeetingView meetings={workspace.meetings}/>
  },[groupStatus,page,workspace.group,workspace.homeworks,workspace.loadHomeworkHistory,workspace.meetings,workspace.pendingHomeworks,workspace.profile,workspace.sections,workspace.submitHomework,workspace.tasks])
  const signOut=async()=>{if(logoutPending)return;setLogoutPending(true);try{await onLogout()}finally{setLogoutPending(false)}}
  return <div className="student-shell"><header className="student-topbar"><button className="student-brand" onClick={()=>setPage('profile')}><span>К</span><strong>Кураторская</strong></button><div className="student-account"><span>{login}</span><button aria-label="Выйти" title="Выйти" disabled={logoutPending} onClick={()=>void signOut()}><SignOut size={19}/></button></div></header><div className="student-layout"><nav className="student-nav" aria-label="Навигация ученицы">{nav.map(item=>{const Icon=item.icon;return <button key={item.id} className={page===item.id?'selected':''} aria-current={page===item.id?'page':undefined} onClick={()=>setPage(item.id)}><Icon size={20}/><span>{item.label}</span></button>})}</nav><main className="student-main"><StudentState state={workspace.profileState} onRetry={()=>void workspace.reload()}>{workspace.profileState.status==='ready'?<StudentState state={pageState} onRetry={()=>void retry()}>{content}</StudentState>:null}</StudentState></main></div></div>
}
