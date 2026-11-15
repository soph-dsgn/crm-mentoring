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
  onRecall: (id: string) => void | Promise<void>
  onComment: (id: string, comment: string) => void
  onType: (id: string, type: string) => void
  onMaterial: (id: string, url: string) => void
  serverManaged?: boolean
  loading?: boolean
  error?: string
  partialErrorCount?: number
  onRetry?: () => void
  canWriteTask?: (task: StrategyTask) => boolean
}

const filters: (ApprovalStatus|'all')[] = ['to_send','sent','reviewing','revision','approved','all']

export default function AnyaPage({data,onStudent,onTask,onApproval,onRecall,onComment,onType,onMaterial,serverManaged=false,loading=false,error='',partialErrorCount=0,onRetry,canWriteTask=()=>true}:Props) {
  const calm=useCalmMotion()
  const [filter,setFilter] = useState<ApprovalStatus|'all'>('to_send')
  const [groupId,setGroupId] = useState('all')
  const [query,setQuery] = useState('')
  const [comments,setComments] = useState<Record<string,string>>({})
  const [pendingTasks,setPendingTasks]=useState<Set<string>>(()=>new Set())
  const pendingRef=useRef(new Set<string>())
  const all = data.tasks.filter(needsAnyaApproval)
  const counts = Object.fromEntries(filters.map(status=>[status,status==='all'?all.length:all.filter(task=>approvalState(task)===status).length])) as Record<ApprovalStatus|'all',number>
  const normalizedQuery = query.trim().toLocaleLowerCase('ru-RU')
  const tasks = all.filter(task=>{
    const student=data.students.find(item=>item.id===task.studentId)
    if (filter!=='all' && approvalState(task)!==filter) return false
    if (groupId!=='all' && student?.groupId!==groupId) return false
    return !normalizedQuery || [task.title,task.approvalType,student?.name].some(value=>value?.toLocaleLowerCase('ru-RU').includes(normalizedQuery))
  }).sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt))
  const runMutation=async(taskId:string,mutation:()=>void|Promise<void>)=>{
    if(pendingRef.current.has(taskId))return
    pendingRef.current.add(taskId);setPendingTasks(new Set(pendingRef.current))
    try{await mutation()}finally{pendingRef.current.delete(taskId);setPendingTasks(new Set(pendingRef.current))}
  }

  if(loading)return <div className="account-state" role="status"><span className="account-spinner"/>Загружаем согласования…</div>
  if(error)return <div className="account-state account-state-error" role="alert"><strong>Не удалось загрузить согласования</strong><p>{error}</p>{onRetry&&<button className="btn secondary" onClick={onRetry}>Повторить</button>}</div>

  return <div className="approval-page">
    <div className="page-heading"><div><h1>Задачи Ани</h1><p>Все согласования связаны с задачами стратегий</p></div></div>
    {partialErrorCount>0&&<div className="account-state account-state-error" role="alert"><strong>Часть согласований не загрузилась</strong><p>Показаны доступные данные. Некоторые группы, разделы или статусы согласования временно недоступны</p>{onRetry&&<button className="btn secondary" onClick={onRetry}>Загрузить ещё раз</button>}</div>}
    <div className="approval-summary" aria-label="Состояние согласований"><div><strong>{counts.to_send}</strong><span>Нужно передать</span></div><div><strong>{counts.sent+counts.reviewing}</strong><span>Ожидают ответа</span></div><div><strong>{counts.revision}</strong><span>Есть правки</span></div></div>
    <div className="tabs approval-tabs" role="tablist" aria-label="Статус согласования">{filters.map(status=><button key={status} role="tab" aria-selected={filter===status} className={filter===status?'selected':''} onClick={()=>setFilter(status)}>{status==='all'?'Все':APPROVAL_STATUS[status]} <span>{counts[status]}</span>{filter===status&&<motion.i className="motion-tab-indicator" layoutId="approval-tab-indicator" transition={calm.tab}/>}</button>)}</div>
    <div className="approval-filters"><label><Search size={17} weight="regular"/><input aria-label="Поиск согласований" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Задача, ученица или тип проверки"/></label><Select aria-label="Фильтр по группе" value={groupId} onChange={event=>setGroupId(event.target.value)}><option value="all">Все группы</option>{data.groups.map(group=><option key={group.id} value={group.id}>{group.name}</option>)}</Select></div>
    {tasks.length?<div className="approval-list">{tasks.map(task=>{
      const student=data.students.find(item=>item.id===task.studentId)
      const group=data.groups.find(item=>item.id===student?.groupId)
      const status=approvalState(task)
      const material=safeExternalUrl(task.url)||task.materials.map(safeExternalUrl).find(Boolean)||''
      const next=status==='to_send'?(material?'Передать материал Ане':'Добавить материал или передать контекст Ане'):status==='sent'?'Уточнить, взята ли работа на проверку':status==='reviewing'?'Дождаться ответа Ани':status==='revision'?'Внести правки и отправить повторно':'Согласование завершено'
      const writable=canWriteTask(task)&&!task.archivedAt
      const pending=pendingTasks.has(task.id)
      const comment=comments[task.id]??task.approvalComment
      const transition=(nextStatus:ApprovalStatus)=>void runMutation(task.id,()=>onApproval(task.id,nextStatus,comment))
      return <article className="approval-card" key={task.id} aria-busy={pending}>
        <div className="approval-card-head"><div><button className="approval-title" onClick={()=>onTask(task.id)}>{task.title}</button><p>{student?<button onClick={()=>onStudent(student.id)}>{student.name}</button>:<span>Ученица удалена</span>} · {group?.name||'Группа удалена'}</p></div><span className="approval-status">{APPROVAL_STATUS[status]}</span></div>
        <div className="approval-card-meta"><span>{task.archivedAt?'Задача в архиве':task.approvalType||'Согласование задачи'}</span>{task.approvalSentAt&&<span>Передано {dateLabel(task.approvalSentAt.slice(0,10))}</span>}</div>
        {material&&<a className="approval-material" href={material} target="_blank" rel="noopener noreferrer">Открыть материал <ExternalLink size={15} weight="regular"/></a>}
        {task.approvalComment&&<p className="approval-note">{task.approvalComment}</p>}
        <p className="approval-next">Следующий шаг: <strong>{next}</strong></p>
        {writable&&<div className="approval-actions">
          {status==='to_send'&&<button className="btn dark" disabled={pending} onClick={()=>transition('sent')}>{pending?'Передаём…':'Передать Ане на проверку'}</button>}
          {status==='sent'&&<button className="btn secondary" disabled={pending} onClick={()=>transition('reviewing')}>{pending?'Сохраняем…':'Аня взяла на проверку'}</button>}
          {status==='reviewing'&&<button className="btn secondary" disabled={pending} onClick={()=>transition('revision')}>{pending?'Сохраняем…':'Получены правки'}</button>}
          {status==='revision'&&<button className="btn dark" disabled={pending} onClick={()=>transition('sent')}>{pending?'Передаём…':'Отправить повторно'}</button>}
          {status==='reviewing'&&<button className="btn dark" disabled={pending} onClick={()=>transition('approved')}>{pending?'Сохраняем…':'Согласовано'}</button>}
          {(!serverManaged||status!=='to_send')&&<button className="btn secondary" disabled={pending} onClick={()=>void runMutation(task.id,()=>onRecall(task.id))}>{pending?'Сохраняем…':'Отозвать из очереди'}</button>}
        </div>}
        {writable&&<details className="approval-details"><summary>Материал, тип и заметки</summary>{!serverManaged&&<div className="approval-card-fields"><label>Тип проверки<input key={`${task.id}-type-${task.approvalType}`} defaultValue={task.approvalType} placeholder="Например, резюме" onBlur={event=>{if(event.target.value!==task.approvalType)onType(task.id,event.target.value)}}/></label><label>Ссылка на материал<input key={`${task.id}-url-${task.url}`} type="url" defaultValue={task.url} placeholder={material||'https://'} onBlur={event=>{if(event.target.value!==task.url)onMaterial(task.id,event.target.value)}}/></label></div>}<label className="approval-comment">Комментарий к следующему переходу<textarea rows={2} value={comment} onChange={event=>{const value=event.target.value;setComments(current=>({...current,[task.id]:value}));if(!serverManaged)onComment(task.id,value)}} placeholder="Правки, ответ Ани или контекст передачи"/></label>{serverManaged&&<p className="form-helper">Комментарий сохранится вместе со следующим изменением статуса</p>}</details>}
      </article>
    })}</div>:<div className="profile-empty"><strong>{all.length?'По выбранным фильтрам задач нет':'Согласований пока нет'}</strong><p>{all.length?'Выберите другой статус или группу':'Откройте задачу стратегии и добавьте её в очередь Ани'}</p></div>}
  </div>
}
