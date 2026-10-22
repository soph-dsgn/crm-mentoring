import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowSquareOutIcon as ExternalLink, MagnifyingGlassIcon as Search } from '@phosphor-icons/react'
import Select from './Select'
import { APPROVAL_STATUS, approvalState, dateLabel, needsAnyaApproval } from './data'
import type { AppData, ApprovalStatus } from './types'
import { useCalmMotion } from './motion'

type Props = {
  data: AppData
  onStudent: (id: string) => void
  onTask: (id: string) => void
  onApproval: (id: string, status: ApprovalStatus) => void
  onComment: (id: string, comment: string) => void
  onType: (id: string, type: string) => void
  onMaterial: (id: string, url: string) => void
  onDeadline: (id: string, date: string) => void
}

const filters: (ApprovalStatus|'all')[] = ['to_send','sent','reviewing','revision','approved','all']

export default function AnyaPage({data,onStudent,onTask,onApproval,onComment,onType,onMaterial,onDeadline}:Props) {
  const calm=useCalmMotion()
  const [filter,setFilter] = useState<ApprovalStatus|'all'>('to_send')
  const [groupId,setGroupId] = useState('all')
  const [query,setQuery] = useState('')
  const all = data.tasks.filter(needsAnyaApproval)
  const counts = Object.fromEntries(filters.map(status=>[status,status==='all'?all.length:all.filter(task=>approvalState(task)===status).length])) as Record<ApprovalStatus|'all',number>
  const normalizedQuery = query.trim().toLocaleLowerCase('ru-RU')
  const tasks = all.filter(task=>{
    const student=data.students.find(item=>item.id===task.studentId)
    if (filter!=='all' && approvalState(task)!==filter) return false
    if (groupId!=='all' && student?.groupId!==groupId) return false
    return !normalizedQuery || [task.title,task.approvalType,student?.name].some(value=>value?.toLocaleLowerCase('ru-RU').includes(normalizedQuery))
  }).sort((a,b)=>a.dueAt&&b.dueAt?a.dueAt.localeCompare(b.dueAt):a.dueAt?-1:b.dueAt?1:b.updatedAt.localeCompare(a.updatedAt))

  return <div className="approval-page">
    <div className="page-heading"><div><h1>Задачи Ани</h1><p>Все согласования связаны с задачами стратегий</p></div></div>
    <div className="approval-summary" aria-label="Состояние согласований"><div><strong>{counts.to_send}</strong><span>Нужно передать</span></div><div><strong>{counts.sent+counts.reviewing}</strong><span>Ожидают ответа</span></div><div><strong>{counts.revision}</strong><span>Есть правки</span></div></div>
    <div className="tabs approval-tabs" role="tablist" aria-label="Статус согласования">{filters.map(status=><button key={status} role="tab" aria-selected={filter===status} className={filter===status?'selected':''} onClick={()=>setFilter(status)}>{status==='all'?'Все':APPROVAL_STATUS[status]} <span>{counts[status]}</span>{filter===status&&<motion.i className="motion-tab-indicator" layoutId="approval-tab-indicator" transition={calm.tab}/>}</button>)}</div>
    <div className="approval-filters"><label><Search size={17}/><input aria-label="Поиск согласований" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Задача, ученица или тип проверки"/></label><Select aria-label="Фильтр по группе" value={groupId} onChange={e=>setGroupId(e.target.value)}><option value="all">Все группы</option>{data.groups.map(group=><option key={group.id} value={group.id}>{group.name}</option>)}</Select></div>
    {tasks.length?<div className="approval-list"><AnimatePresence initial={false}>{tasks.map(task=>{
      const student=data.students.find(item=>item.id===task.studentId)
      const group=data.groups.find(item=>item.id===student?.groupId)
      const status=approvalState(task)
      const material=task.url || task.materials.find(value=>/^https?:\/\//i.test(value)) || ''
      const next=status==='to_send'?(material?'Передать материал Ане':'Добавить материал или передать контекст Ане'):status==='sent'?'Уточнить, взята ли работа на проверку':status==='reviewing'?'Дождаться ответа Ани':status==='revision'?'Внести правки и отправить повторно':'Согласование завершено'
      return <motion.article className="approval-card" key={task.id} layout="position" layoutDependency={status} {...calm.list} transition={{...calm.list.transition,layout:calm.layout}}>
        <div className="approval-card-head"><div><button className="approval-title" onClick={()=>onTask(task.id)}>{task.title}</button><p>{student?<button onClick={()=>onStudent(student.id)}>{student.name}</button>:<span>Ученица удалена</span>} · {group?.name||'Группа удалена'}</p></div><span className="approval-status">{APPROVAL_STATUS[status]}</span></div>
        <div className="approval-card-meta"><span>{task.approvalType||'Тип проверки не указан'}</span>{task.approvalSentAt&&<span>Передано {dateLabel(task.approvalSentAt.slice(0,10))}</span>}{task.dueAt&&<span>Срок {dateLabel(task.dueAt)}</span>}</div>
        {material&&<a className="approval-material" href={material} target="_blank" rel="noreferrer">Открыть материал <ExternalLink size={15}/></a>}
        {task.approvalComment&&<p className="approval-note">{task.approvalComment}</p>}
        <p className="approval-next">Следующий шаг: <strong>{next}</strong></p>
        <div className="approval-actions">
          {status==='to_send'&&<button className="btn dark" onClick={()=>onApproval(task.id,'sent')}>Передать Ане на проверку</button>}
          {status==='sent'&&<button className="btn secondary" onClick={()=>onApproval(task.id,'reviewing')}>Аня взяла на проверку</button>}
          {(status==='sent'||status==='reviewing')&&<button className="btn secondary" onClick={()=>onApproval(task.id,'revision')}>Получены правки</button>}
          {status==='revision'&&<button className="btn dark" onClick={()=>onApproval(task.id,'sent')}>Отправить повторно</button>}
          {(status==='sent'||status==='reviewing')&&<button className="btn dark" onClick={()=>onApproval(task.id,'approved')}>Согласовано</button>}
          {status==='approved'&&<button className="btn secondary" onClick={()=>onApproval(task.id,'to_send')}>Возобновить согласование</button>}
        </div>
        <details className="approval-details"><summary>Материал, тип и заметки</summary><div className="approval-card-fields"><label>Тип проверки<input value={task.approvalType} placeholder="Например, резюме" onChange={e=>onType(task.id,e.target.value)}/></label><label>Ссылка на материал<input type="url" value={task.url} placeholder={material||'https://'} onChange={e=>onMaterial(task.id,e.target.value)}/></label><label>Срок, если нужен<input type="date" value={task.dueAt} onChange={e=>onDeadline(task.id,e.target.value)}/></label></div><label className="approval-comment">Комментарий Ани или мои заметки<textarea rows={2} value={task.approvalComment} onChange={e=>onComment(task.id,e.target.value)} placeholder="Правки, ответ Ани или контекст передачи"/></label></details>
      </motion.article>
    })}</AnimatePresence></div>:<div className="profile-empty"><strong>{all.length?'По выбранным фильтрам задач нет':'Согласований пока нет'}</strong><p>{all.length?'Выберите другой статус или группу':'Откройте задачу стратегии и добавьте её в очередь Ани'}</p></div>}
  </div>
}
