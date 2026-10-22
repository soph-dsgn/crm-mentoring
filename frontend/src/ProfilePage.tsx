import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowDownIcon as ArrowDown, ArrowLeftIcon as ArrowLeft, ArrowRightIcon as ArrowRight, ClipboardTextIcon as ClipboardList, ArrowSquareOutIcon as ExternalLink, PlusIcon as Plus, TrashIcon as Trash2 } from '@phosphor-icons/react'
import Avatar from './Avatar'
import { curriculumProgress, dateLabel, GROUP_STATUS, nearestTask, REVIEW_STATUS, STAGES, taskColumn } from './data'
import type { AppData, Homework, StrategyTask, Student, StudyStatus, TaskStatus } from './types'
import { HomeworkCard } from './HomeworkPage'
import StrategyPlan from './StrategyPlan'
import { useCalmMotion } from './motion'

export type ProfileTab = 'overview'|'strategy'|'homework'|'meetings'|'notes'
type Tab = ProfileTab
const tabs: {id:Tab;label:string}[] = [{id:'overview',label:'Обзор'},{id:'strategy',label:'Стратегия'},{id:'homework',label:'Домашние задания'},{id:'meetings',label:'История встреч'},{id:'notes',label:'Заметки'}]

export default function ProfilePage({ data, student, tasks, initialTab, navigationKey, focusedHomeworkId, onTabChange, onBack, onAllGroups, onReturn, returnLabel, onEdit, onDelete, onNewTask, onQuickTask, onEditTask, onStudyStatus, onMove, onAddSection, onRenameSection, onDeleteSection, onChangeSection, onPatch, onUpdateHomework, onDeleteHomework }: {
  data:AppData; student:Student; tasks:StrategyTask[]; initialTab:Tab; navigationKey:number; focusedHomeworkId:string|null; onTabChange:(tab:Tab)=>void;
  onBack:()=>void; onAllGroups:()=>void; onReturn?:()=>void; returnLabel?:string; onEdit:()=>void; onDelete:()=>void; onNewTask:()=>void; onQuickTask:(title:string,sectionId:string,status?:TaskStatus)=>void; onEditTask:(id:string)=>void; onStudyStatus:(id:string,status:StudyStatus)=>void; onMove:(t:StrategyTask,delta:number)=>void; onAddSection:(title:string)=>void; onRenameSection:(id:string,title:string)=>void; onDeleteSection:(id:string)=>void; onChangeSection:(id:string,sectionId:string)=>void;
  onPatch:(patch:Partial<Student>)=>void; onUpdateHomework:(id:string,patch:Partial<Homework>)=>void; onDeleteHomework:(id:string)=>void
}) {
  const calm=useCalmMotion()
  const [tab,setTab] = useState<Tab>(initialTab)
  const [notesDraft,setNotesDraft] = useState(student.notes)
  const [aboutOpen,setAboutOpen] = useState(false)
  const [selectedHomeworkId,setSelectedHomeworkId]=useState<string|null>(focusedHomeworkId)
  const selectTab=(next:Tab)=>{setTab(next);onTabChange(next)}
  useEffect(() => { setTab(initialTab) }, [student.id,navigationKey,initialTab])
  useEffect(() => setNotesDraft(student.notes), [student.notes, student.id])
  useEffect(() => setSelectedHomeworkId(focusedHomeworkId), [focusedHomeworkId,student.id])
  useEffect(() => { if(tab!=='homework'||!selectedHomeworkId)return; const timer=window.setTimeout(()=>document.getElementById(`homework-${selectedHomeworkId}`)?.scrollIntoView({block:'center',behavior:'smooth'}),0);return()=>window.clearTimeout(timer) },[tab,selectedHomeworkId])
  const group = data.groups.find(g => g.id === student.groupId)
  const groupMeetings = data.groupMeetings.filter(meeting=>meeting.studentIds.includes(student.id)).sort((a,b)=>b.date.localeCompare(a.date)||b.createdAt.localeCompare(a.createdAt))
  const latestMeetingRecord=groupMeetings[0]?.students.find(item=>item.studentId===student.id)
  const legacyMeetings = data.meetings.filter(m=>m.studentId===student.id).sort((a,b)=>b.date.localeCompare(a.date))
  const homeworks = data.homeworks.filter(h=>h.studentId===student.id&&!h.deletedAt).sort((a,b)=>b.createdAt.localeCompare(a.createdAt))
  const activeTasks = tasks.filter(t=>taskColumn(t)==='progress'&&t.reviewStatus!=='pending'&&t.studyStatus!=='hold')
  const pausedTasks = tasks.filter(t=>t.studyStatus==='hold')
  const currentTasks = tasks.filter(t=>taskColumn(t)==='progress'&&t.reviewStatus!=='pending'&&t.studyStatus==='in_progress').sort((a,b)=>a.order-b.order)
  const pending = homeworks.filter(h=>h.status==='submitted')
  const next = nearestTask(tasks)
  const plan=curriculumProgress(tasks)
  const about = [
    ['Бэкграунд',student.background],['Опыт и проекты',student.experience],['Сильные стороны',student.strengths],
    ['Зоны роста',student.growthAreas],['Текущие сложности',student.difficulties],['Карьерные ожидания',student.expectations],['Особенности и заметки',student.personalNotes],
  ]
  return <>
    {onReturn&&<button className="back-link" onClick={onReturn}><ArrowLeft size={16}/> Вернуться: {returnLabel}</button>}
    <nav className="profile-breadcrumb" aria-label="Путь к ученице"><button onClick={onAllGroups}>Все группы</button><span>/</span><button onClick={onBack}>{group?.name||'Группа'}</button><span>/</span><strong aria-current="page">{student.name}</strong></nav>
    <div className="profile-header"><div className="profile-identity"><Avatar student={student} size="xl"/><div><div className="eyebrow">{group?GROUP_STATUS[group.status]:'Персональная стратегия'}</div><h1>{student.name}</h1><p>{group?.name} · {student.desiredPosition||student.careerGoal||'Позиция не указана'}</p></div></div><div className="heading-actions"><button className="btn secondary" onClick={onEdit}>Редактировать профиль</button><button className="btn dark" onClick={()=>{selectTab('strategy');onNewTask()}}><Plus size={17}/> Добавить задачу</button></div></div>
    <div className="profile-tabs" role="tablist" aria-label="Разделы профиля">{tabs.map(t=><button key={t.id} role="tab" aria-selected={tab===t.id} className={tab===t.id?'selected':''} onClick={()=>selectTab(t.id)}>{t.label}{t.id==='strategy'&&<span>{tasks.length}</span>}{t.id==='meetings'&&<span>{groupMeetings.length+legacyMeetings.length}</span>}{tab===t.id&&<motion.i className="motion-tab-indicator" layoutId="profile-tab-indicator" transition={calm.tab}/>}</button>)}</div>
    {tab==='overview'&&<>
      <div className="student-workspace">
        <section className="profile-focus"><div className="eyebrow">Текущий этап</div><div className="profile-focus-main"><div><h2>{student.stageKnown===false?'Этап не указан':STAGES.find(s=>s.id===student.stage)?.label}</h2><p>{tasks.length?next?`Следующий шаг: ${next.title}`:'Все задачи стратегии выполнены':'Задач в стратегии пока нет'}</p></div><div className="profile-big-progress">{plan.percent===null?'—':`${plan.percent}%`}</div></div><div className="profile-track"><span style={{width:`${plan.percent??0}%`}}/></div><div className="profile-workflow-facts"><span>{plan.total?`${plan.done} из ${plan.total} выполнено`:'Стратегия пока пуста'}</span><span>{activeTasks.length} в процессе</span><span>{pausedTasks.length} на паузе</span><span>{pending.length} на проверке</span><span>{latestMeetingRecord?.plannedTaskIds.length?`${latestMeetingRecord.plannedTaskIds.length} в плане недели`:'План недели не сформирован'}</span></div><button onClick={()=>selectTab('strategy')}>Открыть стратегию <ArrowRight size={16}/></button></section>
        <section className="surface work-panel"><div className="section-head"><h2>Текущие задачи <span>{currentTasks.length}</span></h2></div>{currentTasks.length?currentTasks.slice(0,5).map(t=><button className="work-row" key={t.id} onClick={()=>onEditTask(t.id)}><span><strong>{t.title}</strong><small>{t.reviewStatus==='none'?'В процессе':REVIEW_STATUS[t.reviewStatus]}</small></span><span className="work-row-action">Открыть задачу <ArrowRight size={16}/></span></button>):<p className="work-empty">Текущих задач нет. Откройте стратегию, чтобы выбрать следующий шаг</p>}</section>
        <section className="surface work-panel"><div className="section-head"><h2>Проверить <span>{pending.length}</span></h2>{homeworks.length>0&&<button className="text-link" onClick={()=>selectTab('homework')}>История ДЗ <ArrowRight size={16}/></button>}</div>{pending.length?pending.slice(0,4).map(h=><button className="work-row" key={h.id} onClick={()=>{setSelectedHomeworkId(h.id);selectTab('homework')}}><span><strong>{h.title}</strong><small>Отправлено {dateLabel(h.submittedAt.slice(0,10))}</small></span><span className="work-row-action">Проверить работу <ArrowRight size={16}/></span></button>):<p className="work-empty">Работ на проверке нет</p>}</section>
      </div>
      <div className="profile-background"><button className="profile-background-toggle" aria-expanded={aboutOpen} onClick={()=>setAboutOpen(value=>!value)}>Об ученице · вводная информация</button><AnimatePresence initial={false}>{aboutOpen&&<motion.div key="about" className="profile-content-grid" {...calm.collapse} style={{overflow:"hidden"}}><section className="surface about-card"><div className="section-head"><h2>Об ученице</h2><button className="text-link" onClick={onEdit}>Редактировать <ArrowRight size={16}/></button></div><div className="about-grid">{about.map(([label,value])=><div key={label}><small>{label}</small><p>{value||'Не заполнено'}</p></div>)}</div></section><div className="profile-side-stack"><section className="surface point-card"><div><small>Точка А</small><p>{student.pointA||'Пока не заполнена'}</p></div><ArrowDown size={18}/><div><small>Точка Б</small><p>{student.pointB||'Пока не заполнена'}</p></div></section><section className="surface links-card"><h2>Материалы и связь</h2>{Object.entries(student.links).filter(([,url])=>url).length?Object.entries(student.links).filter(([,url])=>url).map(([key,url])=><a key={key} href={url} target="_blank" rel="noreferrer"><span>{key==='resume'?'Резюме':key==='portfolio'?'Портфолио':key==='telegram'?'Telegram':key==='notion'?'Notion':'Figma'}</span><ExternalLink size={15}/></a>):<p>Ссылки пока не добавлены</p>}</section></div></motion.div>}</AnimatePresence></div>
      <button className="delete-student" onClick={onDelete}><Trash2 size={15}/> Удалить ученицу и её данные</button>
    </>}
    {tab==='strategy'&&<StrategyPlan student={student} groupName={group?.name||''} sections={data.sections.filter(s=>s.studentId===student.id)} tasks={tasks} onOpenTask={onEditTask} onStatus={onStudyStatus} onQuickTask={onQuickTask} onAddSection={onAddSection} onRenameSection={onRenameSection} onDeleteSection={onDeleteSection} onMoveTask={onMove} onChangeSection={onChangeSection}/>}
    {tab==='homework'&&(homeworks.length?<div className="homework-list">{homeworks.map(h=><HomeworkCard key={h.id} homework={h} focused={selectedHomeworkId===h.id} onUpdate={onUpdateHomework} onTask={onEditTask} taskExists={id=>data.tasks.some(task=>task.id===id)} onDelete={onDeleteHomework}/>)}</div>:<div className="profile-empty"><ClipboardList size={27}/><strong>Домашних заданий пока нет</strong><p>Выберите задачи стратегии и сформируйте первое ДЗ</p><button className="btn secondary" onClick={()=>selectTab('strategy')}>Открыть стратегию</button></div>)}
    {tab==='meetings'&&<section className="surface profile-tab-surface"><div className="section-head"><div><div className="eyebrow">Групповые созвоны</div><h2>История встреч</h2></div></div>{groupMeetings.length||legacyMeetings.length?<div className="meeting-list">{groupMeetings.map(meeting=>{const record=meeting.students.find(item=>item.studentId===student.id);const homework=record?.homeworkId?data.homeworks.find(item=>item.id===record.homeworkId):undefined;return <article key={meeting.id}><div className="meeting-date">{dateLabel(meeting.date)}</div><div><h3>{meeting.status==='draft'?'Незавершённая встреча':group?.name||'Групповая встреча'}</h3><p>{record?.summary||'Итоги для ученицы не заполнены'}{homework?` · ДЗ: ${homework.items.length} задач`:''}</p></div></article>})}{legacyMeetings.map(item=><article key={item.id}><div className="meeting-date">{dateLabel(item.date)}</div><div><h3>{item.title}</h3><p>{item.summary||'Без заметок'} · старая индивидуальная запись</p></div></article>)}</div>:<div className="profile-empty"><strong>Встреч пока нет</strong><p>История появится после группового разбора</p></div>}</section>}
    {tab==='notes'&&<section className="surface profile-tab-surface"><div className="eyebrow">Личные заметки куратора</div><h2>Заметки</h2><p className="notes-hint">Здесь можно хранить рабочие наблюдения, не привязанные к отдельной встрече</p><textarea className="notes-editor" rows={12} value={notesDraft} onChange={e=>setNotesDraft(e.target.value)} placeholder="Наблюдения, важные детали, идеи для следующей встречи…"/><div className="notes-actions"><button className="btn primary" disabled={notesDraft===student.notes} onClick={()=>onPatch({notes:notesDraft})}>Сохранить заметки</button></div></section>}
  </>
}

