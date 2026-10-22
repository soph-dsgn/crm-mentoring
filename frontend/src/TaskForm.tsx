import Select from './Select'
import { Field } from './Forms'
import { STUDY_STATUS, STAGES } from './data'
import type { Stage, StrategySection, StrategyTask, StudyStatus } from './types'

type Props = {
  draft: StrategyTask
  setDraft: (task: StrategyTask) => void
  sections: StrategySection[]
  existing: boolean
  onSave: () => void
  onCancel: () => void
  onDelete: () => void
}

export default function TaskForm({draft,setDraft,sections,existing,onSave,onCancel,onDelete}:Props) {
  const update=(patch:Partial<StrategyTask>)=>setDraft({...draft,...patch})
  return <form className="form task-form" onSubmit={event=>{event.preventDefault();onSave()}}>
    <Field label="Название задачи"><input required autoFocus value={draft.title} onChange={event=>update({title:event.target.value})} placeholder="Что нужно сделать?"/></Field>
    <Field label="Описание результата"><textarea rows={3} value={draft.description} onChange={event=>update({description:event.target.value})} placeholder="Что должно получиться"/></Field>
    <div className="form-grid"><Field label="Статус"><Select className="study-status" value={draft.studyStatus} onChange={event=>{const studyStatus=event.target.value as StudyStatus;update({studyStatus,status:studyStatus==='done'?'done':studyStatus==='not_started'?'backlog':'progress'})}}>{Object.entries(STUDY_STATUS).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Select></Field><Field label="Раздел стратегии"><Select value={draft.sectionId} onChange={event=>update({sectionId:event.target.value})}><option value="">Без раздела</option>{[...sections].sort((a,b)=>a.order-b.order).map(section=><option key={section.id} value={section.id}>{section.title}</option>)}</Select></Field></div>
    <details className="form-more"><summary>Этап и ответственные</summary><div className="form-grid"><Field label="Этап обучения"><Select value={draft.stage} onChange={event=>update({stage:event.target.value as Stage})}>{STAGES.map(stage=><option key={stage.id} value={stage.id}>{stage.number}. {stage.label}</option>)}</Select></Field><Field label="Ответственная"><Select value={draft.owner} onChange={event=>update({owner:event.target.value as StrategyTask['owner']})}><option>Не назначен</option><option>Софья</option><option>Аня</option></Select></Field></div><label className="check-row"><input type="checkbox" checked={draft.owner==='Аня'||draft.approvalStatus!==null} disabled={draft.owner==='Аня'} onChange={event=>{if(!event.target.checked&&draft.approvalStatus&&draft.approvalStatus!=='to_send'&&!confirm('Убрать задачу из очереди согласований? История задачи сохранится'))return;update({approvalStatus:event.target.checked?'to_send':null})}}/> Требуется согласование Ани</label><label className="check-row"><input type="checkbox" checked={draft.blocker} onChange={event=>update({blocker:event.target.checked})}/> Блокирует дальнейшую работу</label></details>
    <details className="form-more"><summary>Сроки и материалы</summary><Field label="Период из стратегии"><input value={draft.period} onChange={event=>update({period:event.target.value})} placeholder="Необязательно"/></Field><Field label="Срок задачи, если нужен"><input type="date" value={draft.dueAt} onChange={event=>update({dueAt:event.target.value})}/></Field><Field label="Основная ссылка"><input type="url" value={draft.url} onChange={event=>update({url:event.target.value})} placeholder="https://"/></Field><Field label="Другие материалы, по одному на строку"><textarea rows={3} value={draft.materials.join('\n')} onChange={event=>update({materials:event.target.value.split('\n').map(value=>value.trim()).filter(Boolean)})}/></Field></details>
    <details className="form-more"><summary>Комментарии к задаче</summary><Field label="Рабочие заметки"><textarea rows={3} value={draft.comments} onChange={event=>update({comments:event.target.value})} placeholder="Контекст проверки и договорённости"/></Field></details>
    <div className="dialog-actions">{existing&&<button type="button" className="btn danger" onClick={onDelete}>Удалить задачу</button>}<button type="button" className="btn secondary" onClick={onCancel}>Отмена</button><button className="btn primary" type="submit">Сохранить задачу</button></div>
  </form>
}
