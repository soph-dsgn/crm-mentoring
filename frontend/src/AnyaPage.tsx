import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowSquareOutIcon as ExternalLink, MagnifyingGlassIcon as Search } from '@phosphor-icons/react'
import Select from './Select'
import { APPROVAL_STATUS, approvalState, dateLabel, needsAnyaApproval } from './data'
import type { AppData, ApprovalStatus, StrategyTask } from './types'
import { useCalmMotion } from './motion'
import { safeExternalUrl } from './safeExternalUrl'

type Props = {
  data: AppData
  onStudent: (id: string) => void
  onTask: (id: string) => void
  onApproval: (id: string, status: ApprovalStatus, comment?: string) => void | Promise<void>
  /** Anya (the owner) makes review decisions; curators only hand tasks over and resubmit. */
  reviewer?: boolean
  loading?: boolean
  error?: string
  partialErrorCount?: number
  onRetry?: () => void
  canWriteTask?: (task: StrategyTask) => boolean
}

type Filter = ApprovalStatus | 'all'
const reviewerFilters: Filter[] = ['sent', 'reviewing', 'revision', 'approved', 'all']
const curatorFilters: Filter[] = ['revision', 'sent', 'reviewing', 'to_send', 'approved', 'all']
const reviewerLabels: Partial<Record<Filter, string>> = { sent: 'Ждут проверки', reviewing: 'В работе', revision: 'Ушли на правки' }
const reviewerChips: Partial<Record<ApprovalStatus, string>> = { sent: 'Ждёт проверки', reviewing: 'В работе', revision: 'На правках у куратора' }

function approvalNextStep(status: ApprovalStatus, reviewer: boolean): string {
  if (reviewer) return status === 'sent' ? 'Проверить материал и принять решение' : status === 'reviewing' ? 'Согласовать или вернуть на доработку' : status === 'revision' ? 'Куратор вносит правки' : status === 'approved' ? 'Согласование завершено' : 'Куратор ещё не передал задачу'
  return status === 'to_send' ? 'Передать Ане, когда материал готов' : status === 'sent' ? 'Ждём, когда Аня возьмёт задачу' : status === 'reviewing' ? 'Аня проверяет — ничего делать не нужно' : status === 'revision' ? 'Внести правки и отправить повторно' : 'Согласовано — можно двигаться дальше'
}

export default function AnyaPage({data,onStudent,onTask,onApproval,reviewer=false,loading=false,error='',partialErrorCount=0,onRetry,canWriteTask=()=>true}:Props) {
  const calm=useCalmMotion()
  const all = data.tasks.filter(needsAnyaApproval)
  const countOf=(status:Filter)=>status==='all'?all.length:all.filter(task=>approvalState(task)===status).length
  const filters=(reviewer?reviewerFilters:curatorFilters).filter(status=>status!=='to_send'||countOf('to_send')>0)
  const [filter,setFilter] = useState<Filter>(()=>reviewer?'sent':countOf('revision')?'revision':'all')
  const [groupId,setGroupId] = useState('all')
  const [query,setQuery] = useState('')
  const [comments,setComments] = useState<Record<string,string>>({})
  const [returning,setReturning] = useState<string|null>(null)
  const [pendingTasks,setPendingTasks]=useState<Set<string>>(()=>new Set())
  const pendingRef=useRef(new Set<string>())
  const normalizedQuery = query.trim().toLocaleLowerCase('ru-RU')
  const tasks = all.filter(task=>{
    const student=data.students.find(item=>item.id===task.studentId)
    if (filter!=='all' && approvalState(task)!==filter) return false
    if (groupId!=='all' && student?.groupId!==groupId) return false
    return !normalizedQuery || [task.title,student?.name,task.approvalComment].some(value=>value?.toLocaleLowerCase('ru-RU').includes(normalizedQuery))
  }).sort((a,b)=>(a.approvalSentAt||a.updatedAt).localeCompare(b.approvalSentAt||b.updatedAt))
  const runMutation=async(taskId:string,mutation:()=>void|Promise<void>)=>{
    if(pendingRef.current.has(taskId))return
    pendingRef.current.add(taskId);setPendingTasks(new Set(pendingRef.current))
    try{await mutation();setComments(current=>{const next={...current};delete next[taskId];return next});setReturning(current=>current===taskId?null:current)}
    finally{pendingRef.current.delete(taskId);setPendingTasks(new Set(pendingRef.current))}
  }
  const label=(status:Filter)=>status==='all'?'Все':(reviewer&&reviewerLabels[status])||APPROVAL_STATUS[status]

  if(loading)return <div className="account-state" role="status"><span className="account-spinner"/>Загружаем согласования…</div>
  if(error)return <div className="account-state account-state-error" role="alert"><strong>Не удалось загрузить согласования</strong><p>{error}</p>{onRetry&&<button className="btn secondary" onClick={onRetry}>Повторить</button>}</div>

  const summary:[number,string][]=reviewer
    ?[[countOf('sent'),'ждут проверки'],[countOf('reviewing'),'в работе'],[countOf('revision'),'на правках у кураторов']]
    :[[countOf('revision'),'нужны правки'],[countOf('sent')+countOf('reviewing'),'у Ани'],[countOf('approved'),'согласовано']]

  return <div className="approval-page">
    <div className="page-heading"><div><h1>Задачи Ани</h1><p>{reviewer?'Задачи, которые кураторы передали на проверку. Решение принимаете только вы':'Передайте задачу из стратегии — Аня проверит её и согласует или вернёт с правками'}</p></div></div>
    {partialErrorCount>0&&<div className="account-state account-state-error" role="alert"><strong>Часть согласований не загрузилась</strong><p>Показаны доступные данные. Некоторые группы или статусы временно недоступны</p>{onRetry&&<button className="btn secondary" onClick={onRetry}>Загрузить ещё раз</button>}</div>}
    <div className="approval-summary" aria-label="Состояние согласований">{summary.map(([count,text])=><div key={text}><strong>{count}</strong><span>{text}</span></div>)}</div>
    <div className="tabs approval-tabs" role="tablist" aria-label="Статус согласования">{filters.map(status=><button key={status} role="tab" aria-selected={filter===status} className={filter===status?'selected':''} onClick={()=>setFilter(status)}>{label(status)} <span>{countOf(status)}</span>{filter===status&&<motion.i className="motion-tab-indicator" layoutId="approval-tab-indicator" transition={calm.tab}/>}</button>)}</div>
    <div className="approval-filters"><label><Search size={17} weight="regular"/><input aria-label="Поиск согласований" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Задача, ученица или комментарий"/></label><Select aria-label="Фильтр по группе" value={groupId} onChange={event=>setGroupId(event.target.value)}><option value="all">Все группы</option>{data.groups.map(group=><option key={group.id} value={group.id}>{group.name}</option>)}</Select></div>
    {tasks.length?<div className="approval-list">{tasks.map(task=>{
      const student=data.students.find(item=>item.id===task.studentId)
      const group=data.groups.find(item=>item.id===student?.groupId)
      const status=approvalState(task)
      const material=safeExternalUrl(task.url)||task.materials.map(safeExternalUrl).find(Boolean)||''
      const pending=pendingTasks.has(task.id)
      const comment=comments[task.id]??''
      const setComment=(value:string)=>setComments(current=>({...current,[task.id]:value}))
      const move=(nextStatus:ApprovalStatus,text?:string)=>void runMutation(task.id,()=>onApproval(task.id,nextStatus,text))
      const curatorCan=canWriteTask(task)&&!task.archivedAt
      const reviewOpen=reviewer&&!task.archivedAt&&['sent','reviewing','approved'].includes(status)
      const commentLabel=status==='revision'?'Комментарий Ани':status==='approved'?'Комментарий':'Что проверить'
      return <article className={`approval-card approval-${status}`} key={task.id} aria-busy={pending}>
        <div className="approval-card-head"><div><button className="approval-title" onClick={()=>onTask(task.id)}>{task.title}</button><p>{student?<button onClick={()=>onStudent(student.id)}>{student.name}</button>:<span>Ученица удалена</span>} · {group?.name||'Группа удалена'}</p></div><span className="approval-status">{reviewer&&reviewerChips[status]?reviewerChips[status]:APPROVAL_STATUS[status]}</span></div>
        <div className="approval-card-meta">{task.archivedAt&&<span>Задача в архиве</span>}{task.approvalSentAt&&status!=='to_send'&&<span>Передано {dateLabel(task.approvalSentAt.slice(0,10))}</span>}</div>
        {material&&<a className="approval-material" href={material} target="_blank" rel="noopener noreferrer">Открыть материал <ExternalLink size={15} weight="regular"/></a>}
        {task.approvalComment&&<div className="approval-note"><small>{commentLabel}</small><p>{task.approvalComment}</p></div>}
        <p className="approval-next">Следующий шаг: <strong>{approvalNextStep(status,reviewer)}</strong></p>
        {reviewOpen&&returning!==task.id&&<div className="approval-actions">
          {status==='sent'&&<button className="btn secondary" disabled={pending} onClick={()=>move('reviewing')}>Взять в работу</button>}
          {status!=='approved'&&<button className="btn dark" disabled={pending} onClick={()=>move('approved')}>{pending?'Сохраняем…':'Согласовать'}</button>}
          <button className="btn secondary" disabled={pending} onClick={()=>setReturning(task.id)}>{status==='approved'?'Отменить согласование':'Вернуть на доработку'}</button>
        </div>}
        {reviewOpen&&returning===task.id&&<form className="approval-reply" onSubmit={event=>{event.preventDefault();if(comment.trim())move('revision',comment.trim())}}>
          <label className="approval-comment">Что нужно поправить<textarea autoFocus rows={3} value={comment} onChange={event=>setComment(event.target.value)} placeholder="Куратор увидит этот комментарий"/></label>
          <div className="approval-actions"><button type="button" className="btn secondary" disabled={pending} onClick={()=>setReturning(null)}>Отмена</button><button className="btn dark" disabled={pending||!comment.trim()}>{pending?'Отправляем…':'Вернуть на доработку'}</button></div>
        </form>}
        {!reviewer&&curatorCan&&status==='sent'&&<div className="approval-actions"><button className="btn secondary" disabled={pending} onClick={()=>move('to_send')}>{pending?'Сохраняем…':'Отозвать'}</button></div>}
        {curatorCan&&(status==='revision'||status==='to_send')&&<form className="approval-reply" onSubmit={event=>{event.preventDefault();move('sent',comment.trim()||undefined)}}>
          <label className="approval-comment">{status==='revision'?'Что исправлено':'Что проверить'}<textarea rows={2} value={comment} onChange={event=>setComment(event.target.value)} placeholder={status==='revision'?'Коротко опишите изменения для Ани':'Контекст для Ани'}/></label>
          <div className="approval-actions"><button className="btn dark" disabled={pending}>{pending?'Отправляем…':status==='revision'?'Отправить Ане повторно':'Передать Ане'}</button></div>
        </form>}
      </article>
    })}</div>:<div className="profile-empty"><strong>{all.length?'Здесь пусто':reviewer?'Пока ничего не передали':'Согласований пока нет'}</strong><p>{all.length?'Выберите другую вкладку или группу':reviewer?'Задачи появятся, когда кураторы передадут их на проверку':'Откройте задачу в стратегии ученицы и нажмите «Передать Ане»'}</p></div>}
  </div>
}
