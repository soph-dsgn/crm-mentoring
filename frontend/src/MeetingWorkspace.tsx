import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeftIcon as ArrowLeft, ArrowDownIcon as ArrowDown, ArrowUpIcon as ArrowUp, CheckCircleIcon as CheckCircle, ClipboardTextIcon as ClipboardText, PlusIcon as Plus, XIcon as X } from '@phosphor-icons/react'
import Avatar from './Avatar'
import Select from './Select'
import { copyText } from './clipboard'
import { homeworkDescription, STUDY_STATUS } from './data'
import { useDialogA11y } from './dialogA11y'
import { useCalmMotion } from './motion'
import type { AppData, Group, GroupMeeting, Homework, StrategyTask, StudyStatus } from './types'

type Props = {
  data: AppData; group: Group; meeting: GroupMeeting; onClose: () => void
  onStatus: (taskId:string,status:StudyStatus)=>void; onOpenTask:(taskId:string)=>void
  onTogglePlan:(studentId:string,taskId:string)=>void; onMovePlan:(studentId:string,taskId:string,delta:number)=>void
  onSummary:(studentId:string,summary:string)=>void; onReviewed:(studentId:string,reviewed:boolean)=>void
  onQuickTask:(studentId:string,sectionId:string,title:string)=>void
  onCreateHomework:(studentId:string,taskIds:string[],text:string)=>string
  onUpdateHomework:(id:string,patch:Partial<Homework>)=>void; onComplete:()=>void
}

const telegramText=(name:string,tasks:StrategyTask[])=>[
  `${name}, твоё ДЗ на неделю:`, '',
  ...tasks.flatMap((task,index)=>{
    const description=homeworkDescription(task)
    const links=[...task.materials,task.url].filter((value,i,list)=>/^https?:\/\//i.test(value||'')&&list.indexOf(value)===i)
    return [`${index+1}. ${task.title}${description?` — ${description}`:''}`,...links,'']
  }),
].join('\n').trim()

export default function MeetingWorkspace({data,group,meeting,onClose,onStatus,onOpenTask,onTogglePlan,onMovePlan,onSummary,onReviewed,onQuickTask,onCreateHomework,onUpdateHomework,onComplete}:Props){
  const calm=useCalmMotion()
  const members=data.students.filter(student=>meeting.studentIds.includes(student.id))
  const firstPending=members.find(student=>!meeting.students.find(item=>item.studentId===student.id)?.reviewed)
  const [studentId,setStudentId]=useState(firstPending?.id||members[0]?.id||'')
  const [quick,setQuick]=useState('')
  const [draftId,setDraftId]=useState('')
  const [draftText,setDraftText]=useState('')
  const [copied,setCopied]=useState(false)
  const student=members.find(item=>item.id===studentId)
  const record=meeting.students.find(item=>item.studentId===studentId)
  const tasks=data.tasks.filter(task=>task.studentId===studentId)
  const sections=data.sections.filter(section=>section.studentId===studentId).sort((a,b)=>a.order-b.order)
  const displaySections=sections.length?sections:[{id:'',studentId,title:'Без раздела',order:0,createdAt:''}]
  const planned=useMemo(()=>record?.plannedTaskIds.map(id=>tasks.find(task=>task.id===id)).filter((task):task is StrategyTask=>Boolean(task))||[],[record?.plannedTaskIds,tasks])
  const currentHomework=record?.homeworkId?data.homeworks.find(item=>item.id===record.homeworkId):undefined
  const previousMeeting=[...data.groupMeetings].filter(item=>item.groupId===group.id&&item.id!==meeting.id&&item.studentIds.includes(studentId)&&(item.date<meeting.date||(item.date===meeting.date&&item.createdAt<meeting.createdAt))).sort((a,b)=>b.date.localeCompare(a.date)||b.createdAt.localeCompare(a.createdAt))[0]
  const previousHomeworkId=previousMeeting?.students.find(item=>item.studentId===studentId)?.homeworkId
  const previousHomework=(previousHomeworkId?data.homeworks.find(item=>item.id===previousHomeworkId&&!item.deletedAt):undefined)||data.homeworks.filter(item=>item.studentId===studentId&&!item.deletedAt&&item.id!==record?.homeworkId&&!item.groupMeetingId).sort((a,b)=>b.createdAt.localeCompare(a.createdAt))[0]
  const readOnly=meeting.status==='completed'
  const planRows=readOnly&&record?.plannedTaskSnapshot?.length?record.plannedTaskSnapshot.map(item=>({id:item.taskId,title:item.title,sectionTitle:item.sectionTitle})):planned.map(task=>({id:task.id,title:task.title,sectionTitle:displaySections.find(section=>section.id===task.sectionId)?.title||'Без раздела'}))
  const dialogRef=useDialogA11y(Boolean(draftId),()=>setDraftId(''))
  if(!student||!record)return <div className="meeting-workspace"><button className="back-link" onClick={onClose}><ArrowLeft size={16}/> Вернуться в группу</button><div className="profile-empty"><strong>В группе пока нет учениц</strong></div></div>
  const createHomework=()=>{if(!planned.length)return;const text=telegramText(student.shortName?.trim()||student.name.trim().split(/\s+/)[0],planned);const id=onCreateHomework(student.id,planned.map(task=>task.id),text);setDraftId(id);setDraftText(text);setCopied(false)}
  const copy=async()=>{await copyText(draftText);setCopied(true);window.setTimeout(()=>setCopied(false),1800)}
  const addQuick=()=>{const title=quick.trim();if(!title)return;onQuickTask(student.id,sections[0]?.id||'',title);setQuick('')}
  return <div className="meeting-workspace">
    <button className="back-link" onClick={onClose}><ArrowLeft size={16}/> Вернуться в группу</button>
    <div className="meeting-heading"><div><p>{group.name} · {new Date(`${meeting.date}T00:00:00`).toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'})}</p><h1>{meeting.status==='draft'?'Групповая встреча':'Итоги встречи'}</h1></div><button className="btn dark" onClick={meeting.status==='draft'?onComplete:onClose}><CheckCircle size={18}/>{meeting.status==='draft'?'Завершить встречу':'Закрыть историю'}</button></div>
    <div className="meeting-layout">
      <aside className="meeting-roster"><h2>Ученицы</h2>{members.map(member=>{const item=meeting.students.find(value=>value.studentId===member.id);return <button key={member.id} className={member.id===studentId?'active':''} onClick={()=>{setStudentId(member.id);setDraftId('');setDraftText('')}}><Avatar student={member} size="sm"/><span><strong>{member.name}</strong><small>{item?.reviewed?'Разбор завершён':item?.plannedTaskIds.length?`В плане ${item.plannedTaskIds.length}`:'Ещё не разобрали'}</small></span>{item?.reviewed&&<CheckCircle size={18}/>}</button>})}</aside>
      <div className="meeting-student">
        <div className="meeting-student-head"><div><h2>{student.name}</h2><p>{readOnly?'Сохранённые итоги групповой встречи':'Подвести итоги → спланировать неделю → сформировать ДЗ'}</p></div><label className="meeting-reviewed"><input type="checkbox" disabled={readOnly} checked={record.reviewed} onChange={event=>onReviewed(student.id,event.target.checked)}/> Разбор завершён</label></div>
        <section className="meeting-block"><div className="section-head"><div><h2>Прошлая неделя</h2><p>{previousHomework?readOnly?'Состояние задач на момент завершения встречи':'Статусы обновляются в общей стратегии':'Предыдущего домашнего задания нет'}</p></div></div>{previousHomework?<div className="meeting-previous-list">{previousHomework.items.map(item=>{const task=tasks.find(value=>value.id===item.taskId);const historicalStatus=record.statusSnapshot?.[item.taskId];return <div key={item.taskId}><button onClick={()=>task&&onOpenTask(task.id)}>{item.title}</button>{task?<Select disabled={readOnly} value={readOnly&&historicalStatus?historicalStatus:task.studyStatus} aria-label={`Статус ${task.title}`} onChange={event=>onStatus(task.id,event.target.value as StudyStatus)}>{Object.entries(STUDY_STATUS).map(([value,label])=><option key={value} value={value}>{label}</option>)}</Select>:<span>Задача удалена</span>}</div>})}</div>:<p className="work-empty">На прошлой встрече ДЗ не формировалось</p>}</section>
        <section className="meeting-block"><div className="section-head"><div><h2>План на неделю</h2><p>{readOnly?'План сохранён в истории':'Выбор не меняет основной статус задачи'}</p></div>{!readOnly&&<div className="meeting-homework-actions">{currentHomework&&<button className="btn secondary" onClick={()=>{setDraftId(currentHomework.id);setDraftText(currentHomework.text)}}><ClipboardText size={17}/> Открыть ДЗ</button>}{currentHomework?.status!=='issued'&&<button className="btn dark" disabled={!planned.length} onClick={createHomework}><ClipboardText size={17}/>{currentHomework?'Обновить ДЗ':'Сформировать ДЗ'}</button>}</div>}</div>{planRows.length?<div className="meeting-plan-list">{planRows.map((task,index)=><div key={task.id}><span><strong>{index+1}. {task.title}</strong><small>{task.sectionTitle}</small></span>{!readOnly&&<div><button disabled={index===0} onClick={()=>onMovePlan(student.id,task.id,-1)} aria-label="Выше"><ArrowUp size={15}/></button><button disabled={index===planRows.length-1} onClick={()=>onMovePlan(student.id,task.id,1)} aria-label="Ниже"><ArrowDown size={15}/></button><button onClick={()=>onTogglePlan(student.id,task.id)}>Убрать</button></div>}</div>)}</div>:<p className="work-empty">{readOnly?'На этой встрече план не формировался':'Отметьте задачи в стратегии ниже'}</p>}{readOnly&&currentHomework&&<button className="btn secondary" onClick={()=>{setDraftId(currentHomework.id);setDraftText(currentHomework.text)}}><ClipboardText size={17}/> Открыть сохранённое ДЗ</button>}</section>
        <section className="meeting-block"><div className="section-head"><div><h2>Стратегия</h2><p>{readOnly?'Актуальная стратегия ученицы':'Можно выбирать задачи из разных разделов'}</p></div></div><div className="meeting-strategy">{displaySections.map(section=>{const sectionTasks=tasks.filter(task=>task.sectionId===section.id).sort((a,b)=>a.order-b.order);return <details key={section.id||'unassigned'} open><summary>{section.title}<span>{sectionTasks.filter(task=>task.studyStatus==='done').length} / {sectionTasks.length}</span></summary><div>{sectionTasks.map(task=><div className="meeting-task" key={task.id}><label><input type="checkbox" disabled={readOnly} checked={record.plannedTaskIds.includes(task.id)} onChange={()=>onTogglePlan(student.id,task.id)}/><span><strong>{task.title}</strong>{task.description&&<small>{task.description}</small>}</span></label><Select disabled={readOnly} value={readOnly&&record.statusSnapshot?.[task.id]?record.statusSnapshot[task.id]:task.studyStatus} aria-label={`Статус ${task.title}`} onChange={event=>onStatus(task.id,event.target.value as StudyStatus)}>{Object.entries(STUDY_STATUS).map(([value,label])=><option key={value} value={value}>{label}</option>)}</Select><button onClick={()=>onOpenTask(task.id)}>Открыть</button></div>)}{sectionTasks.length===0&&<p className="work-empty">В разделе пока нет задач</p>}</div></details>})}</div>{!readOnly&&<form className="study-quick" onSubmit={event=>{event.preventDefault();addQuick()}}><input value={quick} onChange={event=>setQuick(event.target.value)} placeholder="Быстро добавить задачу"/><button type="submit"><Plus size={16}/> Добавить</button></form>}</section>
        <section className="meeting-block"><label className="field"><span>Итоги и договорённости</span><textarea readOnly={readOnly} rows={4} value={record.summary} onChange={event=>onSummary(student.id,event.target.value)} placeholder="Что обсудили и на чём договорились"/></label></section>
      </div>
    </div>
    <AnimatePresence>{draftId&&<motion.div className="modal-backdrop" {...calm.backdrop} onMouseDown={event=>{if(event.target===event.currentTarget)setDraftId('')}}><motion.div ref={dialogRef} tabIndex={-1} className="dialog wide" role="dialog" aria-modal="true" aria-label="Домашнее задание" {...calm.modal}><div className="dialog-head"><h2>Домашнее задание</h2><button className="icon-btn" onClick={()=>setDraftId('')} aria-label="Закрыть"><X size={17}/></button></div><div className="form"><p>{readOnly?'Сохранённая версия домашнего задания':'Черновик сохранён в истории ученицы'}</p><textarea readOnly={readOnly||currentHomework?.status!=='draft'} rows={14} value={draftText} onChange={event=>{setDraftText(event.target.value);onUpdateHomework(draftId,{text:event.target.value})}}/><div className="dialog-actions"><button className="btn secondary" onClick={copy}>{copied?'Скопировано':'Скопировать ДЗ'}</button>{!readOnly&&<button className="btn dark" disabled={currentHomework?.status==='issued'} onClick={()=>onUpdateHomework(draftId,{status:'issued',issuedAt:new Date().toISOString()})}>{currentHomework?.status==='issued'?'Отмечено выданным':'Отметить выданным'}</button>}</div></div></motion.div></motion.div>}</AnimatePresence>
  </div>
}
