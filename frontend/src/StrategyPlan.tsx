import { useRef, useState } from 'react'
import { ArrowDownIcon as ArrowDown, ArrowUpIcon as ArrowUp, CaretDownIcon as ChevronDown, FileArrowUpIcon as FileArrowUp, PencilSimpleIcon as Pencil, PlusIcon as Plus, TrashIcon as Trash } from '@phosphor-icons/react'
import Select from './Select'
import TaskCard from './TaskCard'
import { copyText } from './clipboard'
import { APPROVAL_STATUS, homeworkDescription, homeworkText, REVIEW_STATUS, taskColumn } from './data'
import type { Homework, StrategySection, StrategyTask, Student, StudyStatus } from './types'
import { DeleteConfirmDialog, Dialog, InputDialog, NoticeDialog } from './Dialogs'
import { strategyErrorMessage, studyStatusOptions } from './strategies/strategyState'

type Props = {
  student: Student; groupName: string; sections: StrategySection[]; tasks: StrategyTask[]
  onOpenTask: (id:string)=>void; onStatus: (id:string,status:StudyStatus)=>void; canEdit?: boolean; serverManaged?: boolean; hasStrategy?: boolean
  onAddTask: (sectionId:string)=>void
  onAddSection: (title:string)=>void|Promise<void>; onRenameSection: (id:string,title:string)=>void|Promise<void>
  onDeleteSection: (id:string)=>void|Promise<void>; onMoveTask: (task:StrategyTask,delta:number)=>void
  onMoveSection?: (section:StrategySection,delta:number)=>void; onCreateStrategy?:()=>void; onImportStrategy?:()=>void
  onChangeSection: (id:string,sectionId:string)=>void
  onGenerate: (ids:string[],title:string,text:string)=>string|Promise<string>
  onUpdateHomework: (id:string,patch:Partial<Homework>)=>void|Promise<void>
}

export default function StrategyPlan({student,sections,tasks,onOpenTask,onStatus,onAddTask,onAddSection,onRenameSection,onDeleteSection,onMoveTask,onMoveSection,onChangeSection,onGenerate,onUpdateHomework,canEdit=true,serverManaged=false,hasStrategy=true,onCreateStrategy,onImportStrategy}:Props) {
  const [collapsed,setCollapsed] = useState<string[]>([])
  const [selected,setSelected] = useState<string[]>([])
  const [newSection,setNewSection] = useState('')
  const [addingSection,setAddingSection] = useState(false)
  const [sectionError,setSectionError] = useState('')
  const addingSectionRef = useRef(false)
  const [draftId,setDraftId] = useState('')
  const [renameSection,setRenameSection]=useState<StrategySection|null>(null)
  const [deleteSection,setDeleteSection]=useState<StrategySection|null>(null)
  const [sectionNotice,setSectionNotice]=useState(false)
  const [draftText,setDraftText] = useState('')
  const [copied,setCopied] = useState(false)
  const [copyError,setCopyError] = useState('')
  const [draftPending,setDraftPending] = useState(false)
  const draftPendingRef=useRef(false)
  const ordered = [...sections].sort((a,b)=>a.order-b.order)
  const sectionOrder = new Map(ordered.map((section,index)=>[section.id,index]))
  const unsectioned = tasks.filter(task=>!sectionOrder.has(task.sectionId))
  const displaySections = unsectioned.length ? [...ordered,{id:'__unsorted',studentId:student.id,title:'Без раздела',order:999999,createdAt:''}] : ordered
  const sourceFile = tasks.find(task=>task.sourceFile)?.sourceFile
  const firstName = student.name.trim().split(/\s+/)[0]

  const toggle = (id:string) => setSelected(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id])
  const submitSection = async () => {
    if (!newSection.trim() || addingSectionRef.current) return
    addingSectionRef.current = true
    setAddingSection(true)
    setSectionError('')
    try {
      await onAddSection(newSection.trim())
      setNewSection('')
    } catch (error) {
      setSectionError(strategyErrorMessage(error))
    } finally {
      addingSectionRef.current = false
      setAddingSection(false)
    }
  }
  const generate = async () => {
    const chosen=tasks.filter(task=>selected.includes(task.id)).sort((a,b)=>(sectionOrder.get(a.sectionId)??999999)-(sectionOrder.get(b.sectionId)??999999)||a.order-b.order)
    if (!chosen.length||draftPendingRef.current) return
    const items=chosen.map(task=>({taskId:task.id,title:task.title,description:homeworkDescription(task),url:task.url,materials:[...task.materials],dueAt:task.dueAt}))
    const message=homeworkText(`${firstName}, твоё ДЗ:`,items,'')
    draftPendingRef.current=true;setDraftPending(true);setCopyError('')
    try { const id=await onGenerate(chosen.map(task=>task.id),'Домашнее задание',message);if(id){setDraftId(id);setDraftText(message);setCopied(false)} }
    catch { setCopyError('Не удалось создать черновик. Обновите данные и повторите попытку') }
    finally { draftPendingRef.current=false;setDraftPending(false) }
  }
  const copy = async () => {
    if(draftPendingRef.current)return
    draftPendingRef.current=true;setDraftPending(true)
    try {
      await copyText(draftText)
      await onUpdateHomework(draftId,{text:draftText})
      setCopied(true); setCopyError(''); setSelected([])
    } catch { setCopyError('Не удалось скопировать или сохранить текст. Черновик остаётся в истории') }
    finally { draftPendingRef.current=false;setDraftPending(false) }
  }

  if(serverManaged&&!hasStrategy)return <div className="study-plan"><div className="profile-empty"><strong>Стратегия пока не создана</strong><p>{canEdit?'Импортируйте стратегию из Notion или создайте пустую и добавьте разделы вручную':'Куратор ещё не создал стратегию для этого профиля'}</p>{canEdit&&<div className="profile-empty-actions">{onImportStrategy&&<button className="btn dark" onClick={onImportStrategy}><FileArrowUp size={17}/> Импортировать из Notion</button>}{onCreateStrategy&&<button className="btn secondary" onClick={onCreateStrategy}>Создать пустую</button>}</div>}</div></div>

  return <div className="study-plan">
    <div className="study-plan-head">
      <div className="study-plan-identity"><div><h2>Индивидуальная стратегия</h2><p>{student.stageKnown===false?'Этап не указан':student.stage==='start'?'Начало':student.stage==='portfolio'?'Портфолио':'Отклики'}</p></div></div>
      {selected.length>0&&<button className="btn dark" disabled={draftPending} onClick={()=>void generate()}>{draftPending?'Создаём черновик…':`Сформировать ДЗ · ${selected.length}`}</button>}
    </div>
    {sourceFile&&<p className="study-source">Исходный PDF хранится у оператора</p>}
    {displaySections.length ? <div className="study-section-list">{displaySections.map(section=>{
      const members=tasks.filter(task=>section.id==='__unsorted'?!sectionOrder.has(task.sectionId):task.sectionId===section.id).sort((a,b)=>a.order-b.order)
      const closed=collapsed.includes(section.id)
      return <section className="study-section" key={section.id}>
        <div className="study-section-head">
          <button className="study-section-toggle" aria-expanded={!closed} onClick={()=>setCollapsed(ids=>ids.includes(section.id)?ids.filter(id=>id!==section.id):[...ids,section.id])}><ChevronDown size={18} className={closed?'closed':''}/><strong>{section.title}</strong><span>{members.filter(task=>taskColumn(task)==='done').length} / {members.length}</span></button>
          {canEdit&&section.id!=='__unsorted'&&<div className="study-section-actions">{serverManaged&&onMoveSection&&<><button disabled={ordered[0]?.id===section.id} aria-label={`Переместить раздел выше: ${section.title}`} onClick={()=>onMoveSection(section,-1)}><ArrowUp size={15}/> Выше</button><button disabled={ordered[ordered.length-1]?.id===section.id} aria-label={`Переместить раздел ниже: ${section.title}`} onClick={()=>onMoveSection(section,1)}><ArrowDown size={15}/> Ниже</button></>}<button className="study-add-task" onClick={()=>onAddTask(section.id)}><Plus size={15} weight="regular"/> Добавить задачу</button><button onClick={()=>setRenameSection(section)}><Pencil size={15} weight="regular"/> Переименовать</button><button onClick={()=>members.length?setSectionNotice(true):setDeleteSection(section)}><Trash size={15} weight="regular"/> Удалить</button></div>}
        </div>
        {!closed&&<div className="study-section-body">
          {members.map((task,index)=>{
            const reviewing=task.reviewStatus==='pending'||task.reviewStatus==='revision'
            const badge=<>{reviewing&&<small className="study-review">{REVIEW_STATUS[task.reviewStatus]}</small>}{task.approvalStatus==='revision'&&<small className="study-review">{APPROVAL_STATUS.revision}</small>}</>
            const actions=canEdit&&!task.archivedAt?<><div className="study-task-actions"><button disabled={index===0} aria-label={`Переместить выше: ${task.title}`} title="Выше" onClick={()=>onMoveTask(task,-1)}><ArrowUp size={15} weight="regular"/></button><button disabled={index===members.length-1} aria-label={`Переместить ниже: ${task.title}`} title="Ниже" onClick={()=>onMoveTask(task,1)}><ArrowDown size={15} weight="regular"/></button></div>{ordered.length>1&&<Select disabled={task.reviewStatus==='pending'||task.reviewStatus==='revision'} className="study-move" aria-label={`Раздел задачи: ${task.title}`} value={sectionOrder.has(task.sectionId)?task.sectionId:''} onChange={event=>onChangeSection(task.id,event.target.value)}>{ordered.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</Select>}</>:undefined
            const taskBadge=<>{task.archivedAt&&<small className="study-review">В архиве</small>}{badge}</>
            return <div key={task.id}><TaskCard task={task} selected={selected.includes(task.id)} onSelect={canEdit&&!task.archivedAt?()=>toggle(task.id):undefined} onOpen={()=>onOpenTask(task.id)} onStatus={status=>onStatus(task.id,status)} statusDisabled={!canEdit||Boolean(task.archivedAt)||reviewing} statusTitle={task.archivedAt?'Сначала восстановите задачу':reviewing?'Статус изменится после проверки домашнего задания':undefined} statusOptions={task.serverBacked?studyStatusOptions(task.studyStatus):undefined} badge={taskBadge} actions={actions}/></div>
          })}
        </div>}
      </section>
    })}</div> : <div className="profile-empty"><strong>Стратегия пока пуста</strong><p>{canEdit?'Импортируйте стратегию из Notion или добавьте первый раздел вручную':'Куратор ещё не заполнил стратегию'}</p>{canEdit&&serverManaged&&onImportStrategy&&<button className="btn dark" onClick={onImportStrategy}><FileArrowUp size={17}/> Импортировать из Notion</button>}</div>}
    {canEdit&&<form className="study-new-section" onSubmit={event=>{event.preventDefault();void submitSection()}}><input aria-label="Название нового раздела" placeholder="Название нового раздела" disabled={addingSection} maxLength={255} value={newSection} onChange={event=>setNewSection(event.target.value)}/><button className="btn secondary" type="submit" disabled={addingSection||!newSection.trim()}><Plus size={16} weight="regular"/> Добавить раздел</button></form>}
    {sectionError&&<p role="alert">{sectionError}</p>}
    <Dialog open={Boolean(draftId)} title="Домашнее задание" onClose={()=>{if(!draftPending)setDraftId('')}} dismissible={!draftPending} wide><div className="form"><p>Черновик сохранён в истории ученицы. Отредактируйте сообщение и скопируйте его для Telegram</p><textarea className="homework-preview-text" readOnly={copied||draftPending} rows={Math.min(20,Math.max(9,selected.length*4))} value={draftText} onChange={event=>{setDraftText(event.target.value);if(!serverManaged)void onUpdateHomework(draftId,{text:event.target.value})}}/>{copied&&<p>Текст сохранён и скопирован. Выдайте ДЗ в профиле ученицы</p>}{copyError&&<p role="alert">{copyError}</p>}<div className="dialog-actions"><button className="btn secondary" disabled={draftPending} onClick={()=>setDraftId('')}>Закрыть</button><button className="btn dark" disabled={draftPending||copied} onClick={()=>void copy()}>{draftPending?'Сохраняем…':copied?'Скопировано':'Скопировать текст'}</button></div></div></Dialog>
    <InputDialog open={Boolean(renameSection)} title="Переименовать раздел" label="Название раздела" initialValue={renameSection?.title||''} onConfirm={title=>renameSection ? onRenameSection(renameSection.id,title) : undefined} onClose={()=>setRenameSection(null)}/>
    <DeleteConfirmDialog open={Boolean(deleteSection)} title="Удалить раздел?" description={`Раздел «${deleteSection?.title||''}» будет удалён`} confirmLabel="Удалить раздел" getErrorMessage={strategyErrorMessage} onConfirm={()=>deleteSection ? onDeleteSection(deleteSection.id) : undefined} onClose={()=>setDeleteSection(null)}/>
    <NoticeDialog open={sectionNotice} title="Раздел пока нельзя удалить" description="Сначала переместите задачи в другой раздел" onClose={()=>setSectionNotice(false)}/>
  </div>
}
