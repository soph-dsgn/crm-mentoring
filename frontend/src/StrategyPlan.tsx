import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowDownIcon as ArrowDown, ArrowUpIcon as ArrowUp, CaretDownIcon as ChevronDown, ArrowSquareOutIcon as ExternalLink, PencilSimpleIcon as Pencil, PlusIcon as Plus, TrashIcon as Trash, XIcon as X } from '@phosphor-icons/react'
import Select from './Select'
import Avatar from './Avatar'
import TaskCard from './TaskCard'
import { copyText } from './clipboard'
import { APPROVAL_STATUS, curriculumProgress, homeworkDescription, homeworkText, REVIEW_STATUS, taskColumn } from './data'
import type { Homework, StrategySection, StrategyTask, Student, StudyStatus } from './types'
import { useCalmMotion } from './motion'
import { useDialogA11y } from './dialogA11y'

type Props = {
  student: Student; groupName: string; sections: StrategySection[]; tasks: StrategyTask[]
  onOpenTask: (id:string)=>void; onStatus: (id:string,status:StudyStatus)=>void
  onAddTask: (sectionId:string)=>void
  onAddSection: (title:string)=>void; onRenameSection: (id:string,title:string)=>void
  onDeleteSection: (id:string)=>void; onMoveTask: (task:StrategyTask,delta:number)=>void
  onChangeSection: (id:string,sectionId:string)=>void
  onGenerate: (ids:string[],title:string,text:string)=>string
  onUpdateHomework: (id:string,patch:Partial<Homework>)=>void
}

export default function StrategyPlan({student,groupName,sections,tasks,onOpenTask,onStatus,onAddTask,onAddSection,onRenameSection,onDeleteSection,onMoveTask,onChangeSection,onGenerate,onUpdateHomework}:Props) {
  const calm = useCalmMotion()
  const [collapsed,setCollapsed] = useState<string[]>([])
  const [selected,setSelected] = useState<string[]>([])
  const [newSection,setNewSection] = useState('')
  const [draftId,setDraftId] = useState('')
  const previewRef=useDialogA11y(Boolean(draftId),()=>setDraftId(''))
  const [draftText,setDraftText] = useState('')
  const [copied,setCopied] = useState(false)
  const [copyError,setCopyError] = useState('')
  const ordered = [...sections].sort((a,b)=>a.order-b.order)
  const sectionOrder = new Map(ordered.map((section,index)=>[section.id,index]))
  const unsectioned = tasks.filter(task=>!sectionOrder.has(task.sectionId))
  const displaySections = unsectioned.length ? [...ordered,{id:'__unsorted',studentId:student.id,title:'Без раздела',order:999999,createdAt:''}] : ordered
  const progress = curriculumProgress(tasks)
  const next = [...tasks].filter(task=>task.studyStatus==='in_progress'&&task.reviewStatus!=='pending').sort((a,b)=>a.order-b.order).slice(0,2)
  const sourceFile = tasks.find(task=>task.sourceFile)?.sourceFile
  const firstName = student.name.trim().split(/\s+/)[0]

  const toggle = (id:string) => setSelected(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id])
  const generate = () => {
    const chosen=tasks.filter(task=>selected.includes(task.id)).sort((a,b)=>(sectionOrder.get(a.sectionId)??999999)-(sectionOrder.get(b.sectionId)??999999)||a.order-b.order)
    if (!chosen.length) return
    const items=chosen.map(task=>({taskId:task.id,title:task.title,description:homeworkDescription(task),url:task.url,materials:[...task.materials],dueAt:task.dueAt}))
    const message=homeworkText(`${firstName}, твоё ДЗ:`,items,'')
    const id=onGenerate(chosen.map(task=>task.id),'Домашнее задание',message)
    if (id) { setDraftId(id); setDraftText(message); setCopied(false); setCopyError('') }
  }
  const copy = async () => {
    try {
      await copyText(draftText)
      onUpdateHomework(draftId,{text:draftText,status:'issued',issuedAt:new Date().toISOString()})
      setCopied(true); setCopyError(''); setSelected([])
    } catch { setCopyError('Не удалось скопировать сообщение. Выделите текст и скопируйте вручную') }
  }

  return <div className="study-plan">
    <div className="study-plan-head">
      <div className="study-plan-identity"><Avatar student={student} size="sm"/><div><h2>Стратегия {student.name}</h2><p>{groupName}{groupName?' · ':''}{student.stageKnown===false?'Этап не указан':student.stage==='start'?'Начало':student.stage==='portfolio'?'Портфолио':'Отклики'} · {progress.total?`${progress.done} из ${progress.total} выполнено · ${progress.percent}%`:'Задач пока нет'}</p></div></div>
      {selected.length>0&&<button className="btn dark" onClick={generate}>Сформировать ДЗ · {selected.length}</button>}
    </div>
    {next.length>0&&<p className="study-next">Сейчас: {next.map(task=>task.title).join(' · ')}</p>}
    {sourceFile&&<a className="study-source" href={encodeURI('/'+sourceFile.replace(/^public\//,''))} target="_blank" rel="noreferrer">Открыть исходную стратегию <ExternalLink size={15} weight="regular"/></a>}
    {displaySections.length ? <div className="study-section-list">{displaySections.map(section=>{
      const members=tasks.filter(task=>section.id==='__unsorted'?!sectionOrder.has(task.sectionId):task.sectionId===section.id).sort((a,b)=>a.order-b.order)
      const closed=collapsed.includes(section.id)
      return <section className="study-section" key={section.id}>
        <div className="study-section-head">
          <button className="study-section-toggle" aria-expanded={!closed} onClick={()=>setCollapsed(ids=>ids.includes(section.id)?ids.filter(id=>id!==section.id):[...ids,section.id])}><ChevronDown size={18} className={closed?'closed':''}/><strong>{section.title}</strong><span>{members.filter(task=>taskColumn(task)==='done').length} / {members.length}</span></button>
          {section.id!=='__unsorted'&&<div className="study-section-actions"><button className="study-add-task" onClick={()=>onAddTask(section.id)}><Plus size={15} weight="regular"/> Добавить задачу</button><button onClick={()=>{const title=prompt('Название раздела',section.title);if(title?.trim())onRenameSection(section.id,title.trim())}}><Pencil size={15} weight="regular"/> Переименовать</button><button onClick={()=>{if(members.length){alert('Сначала переместите задачи в другой раздел');return}if(confirm(`Удалить раздел «${section.title}»?`))onDeleteSection(section.id)}}><Trash size={15} weight="regular"/> Удалить</button></div>}
        </div>
        {!closed&&<div className="study-section-body">
          {members.map((task,index)=>{
            const reviewing=task.reviewStatus==='pending'||task.reviewStatus==='revision'
            const badge=<>{reviewing&&<small className="study-review">{REVIEW_STATUS[task.reviewStatus]}</small>}{task.approvalStatus==='revision'&&<small className="study-review">{APPROVAL_STATUS.revision}</small>}</>
            const actions=<><div className="study-task-actions"><button disabled={index===0} aria-label={`Переместить выше: ${task.title}`} title="Выше" onClick={()=>onMoveTask(task,-1)}><ArrowUp size={15} weight="regular"/></button><button disabled={index===members.length-1} aria-label={`Переместить ниже: ${task.title}`} title="Ниже" onClick={()=>onMoveTask(task,1)}><ArrowDown size={15} weight="regular"/></button></div><Select className="study-move" aria-label={`Раздел задачи: ${task.title}`} value={sectionOrder.has(task.sectionId)?task.sectionId:''} onChange={event=>onChangeSection(task.id,event.target.value)}><option value="">Без раздела</option>{ordered.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</Select></>
            return <div key={task.id}><TaskCard task={task} selected={selected.includes(task.id)} onSelect={()=>toggle(task.id)} onOpen={()=>onOpenTask(task.id)} onStatus={status=>onStatus(task.id,status)} statusDisabled={reviewing} statusTitle={reviewing?'Статус изменится после проверки домашнего задания':undefined} badge={badge} actions={actions}/></div>
          })}
        </div>}
      </section>
    })}</div> : <div className="profile-empty"><strong>Стратегия пока пуста</strong><p>Добавьте первый раздел и задачи после знакомства с ученицей</p></div>}
    <form className="study-new-section" onSubmit={event=>{event.preventDefault();if(newSection.trim()){onAddSection(newSection.trim());setNewSection('')}}}><input aria-label="Название нового раздела" placeholder="Название нового раздела" value={newSection} onChange={event=>setNewSection(event.target.value)}/><button className="btn secondary" type="submit"><Plus size={16} weight="regular"/> Добавить раздел</button></form>
    <AnimatePresence initial={false}>{draftId&&<motion.div key="homework-preview" className="modal-backdrop" {...calm.backdrop} onMouseDown={event=>{if(event.target===event.currentTarget)setDraftId('')}}><motion.div ref={previewRef} tabIndex={-1} className="dialog wide" role="dialog" aria-modal="true" aria-label="Домашнее задание" {...calm.modal}><div className="dialog-head"><h2>Домашнее задание</h2><button className="icon-btn" onClick={()=>setDraftId('')} aria-label="Закрыть"><X size={16} weight="regular"/></button></div><div className="form"><p>Черновик сохранён в истории ученицы. Отредактируйте сообщение и скопируйте его для Telegram</p><textarea className="homework-preview-text" readOnly={copied} rows={Math.min(20,Math.max(9,selected.length*4))} value={draftText} onChange={event=>{setDraftText(event.target.value);onUpdateHomework(draftId,{text:event.target.value})}}/>{copied&&<p>ДЗ выдано и сохранено в истории. Исходный текст больше не меняется</p>}{copyError&&<p role="alert">{copyError}</p>}<div className="dialog-actions"><button className="btn secondary" onClick={()=>setDraftId('')}>Закрыть</button><button className="btn dark" onClick={copy}>{copied?'Скопировано':'Скопировать текст'}</button></div></div></motion.div></motion.div>}</AnimatePresence>
  </div>
}
