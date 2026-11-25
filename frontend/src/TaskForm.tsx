import { useState } from 'react'
import DateField from './DateField'
import Select from './Select'
import TaskStatusSelect from './TaskStatusSelect'
import { Field } from './Forms'
import { STAGES } from './data'
import type { Stage, StrategySection, StrategyTask } from './types'
import { ConfirmDialog } from './Dialogs'

type Props = {
  draft: StrategyTask
  setDraft: (task: StrategyTask) => void
  sections: StrategySection[]
  existing: boolean
  onSave: () => void
  onCancel: () => void
  onDelete: () => void
  serverManaged?: boolean
  pending?: boolean
  error?: string
}

export default function TaskForm({draft,setDraft,sections,existing,onSave,onCancel,onDelete,serverManaged=false,pending=false,error=''}:Props) {
  const [confirmRecall,setConfirmRecall]=useState(false)
  const locked=serverManaged&&Boolean(draft.archivedAt)
  const update=(patch:Partial<StrategyTask>)=>setDraft({...draft,...patch})
  return <><form className="form task-form" onSubmit={event=>{event.preventDefault();onSave()}}>
    {locked&&<p className="notes-hint">Архивная задача доступна только для просмотра. Восстановите её, чтобы продолжить редактирование</p>}
    <Field label="Название задачи"><input required autoFocus disabled={pending||locked} value={draft.title} onChange={event=>update({title:event.target.value})} placeholder="Что нужно сделать?"/></Field>
    <Field label="Описание результата"><textarea rows={3} disabled={pending||locked} value={draft.description} onChange={event=>update({description:event.target.value})} placeholder="Что должно получиться"/></Field>
    {!serverManaged&&<div className="form-grid"><Field label="Статус"><TaskStatusSelect value={draft.studyStatus} ariaLabel="Статус задачи" onChange={studyStatus=>update({studyStatus,status:studyStatus==='done'?'done':studyStatus==='not_started'?'backlog':'progress'})}/></Field><Field label="Раздел стратегии"><Select value={draft.sectionId} onChange={event=>update({sectionId:event.target.value})}><option value="">Без раздела</option>{[...sections].sort((a,b)=>a.order-b.order).map(section=><option key={section.id} value={section.id}>{section.title}</option>)}</Select></Field></div>}
    {!serverManaged&&<details className="form-more"><summary>Этап и ответственные</summary><div className="form-grid"><Field label="Этап обучения"><Select value={draft.stage} onChange={event=>update({stage:event.target.value as Stage})}>{STAGES.map(stage=><option key={stage.id} value={stage.id}>{stage.number}. {stage.label}</option>)}</Select></Field><Field label="Ответственная"><Select value={draft.owner} onChange={event=>update({owner:event.target.value as StrategyTask['owner']})}><option>Не назначен</option><option>Софья</option><option>Аня</option></Select></Field></div><label className="check-row"><input type="checkbox" checked={draft.approvalStatus!==null} onChange={event=>{if(!event.target.checked&&draft.approvalStatus&&draft.approvalStatus!=='to_send'){setConfirmRecall(true);return}update({approvalStatus:event.target.checked?'to_send':null})}}/> Требуется согласование Ани</label><label className="check-row"><input type="checkbox" checked={draft.blocker} onChange={event=>update({blocker:event.target.checked})}/> Блокирует дальнейшую работу</label></details>}
    {serverManaged&&<div className="form-grid">
      <Field label="Срок выполнения"><DateField disabled={pending||locked} value={draft.dueAt} onChange={value=>update({dueAt:value ? `${value}T00:00:00Z` : ''})}/></Field>
      <label className="check-row"><input type="checkbox" disabled={pending||locked} checked={draft.blocker} onChange={event=>update({blocker:event.target.checked})}/> Блокирует дальнейшую работу</label>
    </div>}
    <details className="form-more"><summary>Материалы</summary><Field label="Период из стратегии"><input disabled={pending||locked} value={draft.period} onChange={event=>update({period:event.target.value})} placeholder="Необязательно"/></Field><Field label="Основная ссылка"><input disabled={pending||locked} type="url" value={draft.url} onChange={event=>update({url:event.target.value})} placeholder="https://"/></Field><Field label="Другие материалы, по одному на строку"><textarea disabled={pending||locked} rows={3} value={draft.materials.join('\n')} onChange={event=>update({materials:event.target.value.split('\n').map(value=>value.trim()).filter(Boolean)})}/></Field></details>
    {!serverManaged&&<details className="form-more"><summary>Комментарии к задаче</summary><Field label="Рабочие заметки"><textarea rows={3} value={draft.comments} onChange={event=>update({comments:event.target.value})} placeholder="Контекст проверки и договорённости"/></Field></details>}
    {error&&<p className="form-error" role="alert">{error}</p>}
    <div className="dialog-actions">{existing&&<button type="button" className={draft.archivedAt?'btn secondary':'btn danger'} disabled={pending} onClick={onDelete}>{serverManaged?(draft.archivedAt?'Восстановить задачу':'В архив'):'Удалить задачу'}</button>}<button type="button" className="btn secondary" disabled={pending} onClick={onCancel}>Отмена</button>{!locked&&<button className="btn primary" disabled={pending} type="submit">{pending?'Сохраняем…':'Сохранить задачу'}</button>}</div>
  </form><ConfirmDialog open={confirmRecall} title="Отозвать согласование?" description="Задача исчезнет из очереди Ани, но останется в стратегии вместе с историей" confirmLabel="Отозвать" onConfirm={()=>update({approvalStatus:null})} onClose={()=>setConfirmRecall(false)}/></>
}
