import { ArrowSquareOutIcon, PencilSimpleIcon } from '@phosphor-icons/react'
import TaskStatusSelect from './TaskStatusSelect'
import { APPROVAL_STATUS, dateLabel, needsAnyaApproval, REVIEW_STATUS, STAGES } from './data'
import type { StrategyTask, StudyStatus } from './types'
import { safeExternalUrl } from './safeExternalUrl'

type Props = {
  task: StrategyTask
  studentName: string
  groupName: string
  sectionTitle?: string
  onStatus: (status: StudyStatus) => void
  onPrepareApproval: () => void
  homeworkTitle?: string
  onHomework?: () => void
  onEdit: () => void
}

export default function TaskDetail({task,studentName,groupName,sectionTitle,onStatus,onPrepareApproval,homeworkTitle,onHomework,onEdit}:Props) {
  const reviewLocked = task.reviewStatus === 'pending' || task.reviewStatus === 'revision'
  const materialValues=[task.url,...task.materials].filter(Boolean)
  const materialLinks=materialValues.map(safeExternalUrl).filter((value):value is string=>Boolean(value))
  const otherMaterials=materialValues.filter(value=>!safeExternalUrl(value))
  return <div className="task-detail">
    <p className="task-detail-context">{groupName || 'Группа не найдена'} · {studentName || 'Ученица не найдена'}</p>
    <p className="task-detail-description">{task.description || 'Описание пока не добавлено'}</p>
    <div className="task-detail-primary">
      <div><span>Выполнение</span><TaskStatusSelect ariaLabel="Статус задачи" value={task.studyStatus} disabled={reviewLocked} onChange={onStatus}/></div>
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
    {(task.comments||task.approvalComment||task.history.length>0)&&<details className="task-detail-more"><summary>Комментарии и история</summary>{task.comments&&<div><h4>Комментарии к задаче</h4><p>{task.comments}</p></div>}{task.approvalComment&&<div><h4>Комментарий Ани</h4><p>{task.approvalComment}</p></div>}{task.history.length>0&&<div><h4>История изменений</h4><ol>{task.history.slice().reverse().map((event,index)=><li key={`${event.at}-${index}`}>{dateLabel(event.at.slice(0,10))} · {event.label}</li>)}</ol></div>}</details>}
    <div className="dialog-actions task-detail-actions">{!needsAnyaApproval(task)&&<button className="btn secondary" onClick={onPrepareApproval}>Подготовить согласование с Аней</button>}<button className="btn dark" onClick={onEdit}><PencilSimpleIcon size={16} weight="regular"/> Редактировать задачу</button></div>
  </div>
}
