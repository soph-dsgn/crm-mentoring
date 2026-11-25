import { useState } from 'react'
import { ArrowSquareOutIcon, PaperPlaneTiltIcon, PencilSimpleIcon } from '@phosphor-icons/react'
import TaskStatusSelect from './TaskStatusSelect'
import { APPROVAL_STATUS, dateLabel, needsAnyaApproval, REVIEW_STATUS, STAGES } from './data'
import type { StrategyTask, StudyStatus } from './types'
import { safeExternalUrl } from './safeExternalUrl'
import { studyStatusOptions } from './strategies/strategyState'

type Props = {
  task: StrategyTask
  studentName: string
  groupName: string
  sectionTitle?: string
  onStatus: (status: StudyStatus) => void
  onHandoff: (comment: string) => void | Promise<void>
  homeworkTitle?: string
  onHomework?: () => void
  onEdit: () => void
  canEdit?: boolean
}

export default function TaskDetail({task,studentName,groupName,sectionTitle,onStatus,onHandoff,homeworkTitle,onHomework,onEdit,canEdit=true}:Props) {
  const reviewLocked = task.reviewStatus === 'pending' || task.reviewStatus === 'revision'
  const [handoff,setHandoff]=useState<string|null>(null)
  const [handoffPending,setHandoffPending]=useState(false)
  const submitHandoff=async()=>{if(handoff===null||handoffPending)return;setHandoffPending(true);try{await onHandoff(handoff.trim());setHandoff(null)}finally{setHandoffPending(false)}}
  const materialValues=[task.url,...task.materials].filter(Boolean)
  const materialLinks=materialValues.map(safeExternalUrl).filter((value):value is string=>Boolean(value))
  const otherMaterials=materialValues.filter(value=>!safeExternalUrl(value))
  return <div className="task-detail">
    <p className="task-detail-context">{groupName || 'Группа не найдена'} · {studentName || 'Ученица не найдена'}</p>
    <p className="task-detail-description">{task.description || 'Описание пока не добавлено'}</p>
    <div className="task-detail-primary">
      <div><span>Выполнение</span><TaskStatusSelect ariaLabel="Статус задачи" value={task.studyStatus} disabled={!canEdit||Boolean(task.archivedAt)||reviewLocked} title={task.archivedAt?'Сначала восстановите задачу':undefined} options={task.serverBacked?studyStatusOptions(task.studyStatus):undefined} onChange={onStatus}/></div>
      {task.reviewStatus!=='none'&&<div><span>Проверка работы</span><strong>{REVIEW_STATUS[task.reviewStatus]}</strong></div>}
      {needsAnyaApproval(task)&&<div><span>Согласование с Аней</span><strong>{APPROVAL_STATUS[task.approvalStatus||'to_send']}</strong></div>}
    </div>
    {reviewLocked&&<div className="task-detail-review"><p className="task-detail-hint">Статус выполнения изменится после проверки домашнего задания</p>{onHomework&&<button className="btn secondary" onClick={onHomework}>{task.reviewStatus==='pending'?'Проверить работу':'Открыть доработку'} · {homeworkTitle}</button>}</div>}
    <div className="task-detail-facts">
      {sectionTitle&&<span>Раздел стратегии: {sectionTitle}</span>}
      <span>Этап: {STAGES.find(stage=>stage.id===task.stage)?.label || 'Не указан'}</span>
      {task.owner!=='Не назначен'&&<span>Ответственная: {task.owner}</span>}
      {task.period&&<span>Период: {task.period}</span>}
    </div>
    {(materialLinks.length>0||otherMaterials.length>0)&&<section className="task-detail-section"><h3>Материалы</h3>{materialLinks.map((url,index)=><a key={`${url}-${index}`} href={url} target="_blank" rel="noopener noreferrer">{index===0&&url===safeExternalUrl(task.url)?'Основной материал':`Материал ${index+1}`} <ArrowSquareOutIcon size={15} weight="regular"/></a>)}{otherMaterials.map((value,index)=><p key={`${value}-${index}`}>{value}</p>)}</section>}
    {(task.comments||task.approvalComment||task.history.length>0)&&<details className="task-detail-more"><summary>Комментарии и история</summary>{task.comments&&<div><h4>Комментарии к задаче</h4><p>{task.comments}</p></div>}{task.approvalComment&&<div><h4>Комментарий к согласованию</h4><p>{task.approvalComment}</p></div>}{task.history.length>0&&<div><h4>История изменений</h4><ol>{task.history.slice().reverse().map((event,index)=><li key={`${event.at}-${index}`}>{dateLabel(event.at.slice(0,10))} · {event.label}</li>)}</ol></div>}</details>}
    {task.archivedAt&&<p className="task-detail-hint">Задача находится в архиве и доступна только для чтения до восстановления</p>}
    {canEdit&&handoff!==null&&<form className="task-handoff" onSubmit={event=>{event.preventDefault();void submitHandoff()}}><label className="field"><span>Что проверить Ане</span><textarea autoFocus rows={3} value={handoff} onChange={event=>setHandoff(event.target.value)} placeholder="Например: проверь структуру резюме и первый кейс"/></label><div className="task-handoff-actions"><button type="button" className="btn secondary" disabled={handoffPending} onClick={()=>setHandoff(null)}>Отмена</button><button className="btn dark" disabled={handoffPending}><PaperPlaneTiltIcon size={16}/> {handoffPending?'Передаём…':'Передать'}</button></div></form>}
    {canEdit&&handoff===null&&<div className="dialog-actions task-detail-actions">{!task.archivedAt&&!needsAnyaApproval(task)&&<button className="btn secondary" onClick={()=>setHandoff('')}><PaperPlaneTiltIcon size={16}/> Передать Ане</button>}<button className="btn dark" onClick={onEdit}><PencilSimpleIcon size={16} weight="regular"/> {task.archivedAt?'Открыть восстановление':'Редактировать задачу'}</button></div>}
  </div>
}
