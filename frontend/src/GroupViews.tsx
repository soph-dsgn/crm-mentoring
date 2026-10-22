import { useState, type MouseEvent } from 'react'
import { motion } from 'framer-motion'
import { ArchiveIcon as Archive, ArrowLeftIcon as ArrowLeft, CheckCircleIcon as CheckCircle, DotsThreeIcon as More, PencilSimpleIcon as Pencil, PlayIcon as Play, PlusIcon as Plus, ArrowCounterClockwiseIcon as RotateCcw, MagnifyingGlassIcon as Search, TrashIcon as Trash, UsersIcon as Users } from '@phosphor-icons/react'
import Select from './Select'
import Avatar from './Avatar'
import { dateLabel, daysUntil, GROUP_STATUS, groupNextTask, groupProgress, nearestTask, progress, STAGES, studentTasks } from './data'
import type { AppData, Group, GroupStatus, Stage, Student } from './types'
import { useCalmMotion } from './motion'

const order:GroupStatus[] = ['active','backlog','completed','archived']
const plural = (n:number, one:string, few:string, many:string) => `${n} ${n%10===1&&n%100!==11?one:n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?few:many}`
const fullDate = (date:string) => date?new Date(`${date}T00:00:00`).toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'}):'Дата не указана'
const countdown = (group:Group) => { const days=daysUntil(group.status==='backlog'?group.startsAt:group.endsAt); if(days===null)return 'Дата не указана'; if(group.status==='backlog')return days<0?'Плановый старт прошёл — ожидает запуска':days===0?'Плановый старт сегодня':`До старта ${plural(days,'день','дня','дней')}`; if(group.status==='active')return days<0?'Плановый срок завершения прошёл':days===0?'Плановое завершение сегодня':`До завершения ${plural(days,'день','дня','дней')}`; return group.actualEndsAt?`Завершена ${dateLabel(group.actualEndsAt)}`:'Обучение завершено' }

export function GroupsPage({data,view,onView,filter,onFilter,onOpen,onStudent,onNew,onEdit,onStatus,onDelete}:{data:AppData;view:'groups'|'students';onView:(view:'groups'|'students')=>void;filter:GroupStatus;onFilter:(status:GroupStatus)=>void;onOpen:(id:string)=>void;onStudent:(id:string)=>void;onNew:()=>void;onEdit:(g:Group)=>void;onStatus:(g:Group,s:GroupStatus)=>void;onDelete:(g:Group)=>void}) {
  const calm=useCalmMotion()
  const [studentGroup,setStudentGroup]=useState('all')
  const [studentStage,setStudentStage]=useState<Stage|'all'>('all')
  const [search,setSearch]=useState('')
  const groups=data.groups.filter(g=>g.status===filter).sort((a,b)=>filter==='backlog'?a.startsAt.localeCompare(b.startsAt):b.startsAt.localeCompare(a.startsAt))
  const students=data.students.filter(s=>(studentGroup==='all'||s.groupId===studentGroup)&&(studentStage==='all'||(s.stageKnown!==false&&s.stage===studentStage))&&s.name.toLowerCase().includes(search.toLowerCase()))
  return <><div className="page-heading editorial-page-head"><div><h1>Группы и стратегии</h1></div><button className="btn dark" onClick={onNew}><Plus size={18}/> Новая группа</button></div>
    <div className="tabs collection-tabs" role="tablist" aria-label="Что показать"><button role="tab" aria-selected={view==='groups'} className={view==='groups'?'selected':''} onClick={()=>onView('groups')}>Группы <span>{data.groups.length}</span></button><button role="tab" aria-selected={view==='students'} className={view==='students'?'selected':''} onClick={()=>onView('students')}>Ученицы <span>{data.students.length}</span></button></div>
    {view==='groups'&&<><div className="tabs lifecycle-tabs">{order.map(status=><button key={status} className={filter===status?'selected':''} onClick={()=>onFilter(status)}>{status==='active'?'Активные':status==='backlog'?'Бэклог':status==='completed'?'Завершённые':'Архив'} <span>{data.groups.filter(g=>g.status===status).length}</span>{filter===status&&<motion.i className="motion-tab-indicator" layoutId="groups-tab-indicator" transition={calm.tab}/>}</button>)}</div>
    {groups.length?<div className="editorial-group-list">{groups.map(g=><div key={g.id}><GroupCard data={data} group={g} onOpen={()=>onOpen(g.id)} onEdit={()=>onEdit(g)} onStatus={s=>onStatus(g,s)} onDelete={()=>onDelete(g)}/></div>)}</div>:<div className="profile-empty"><Users size={28}/><strong>{filter==='backlog'?'Пока нет запланированных групп':filter==='archived'?'Архив пуст':filter==='completed'?'Завершённых групп пока нет':'Нет активных групп'}</strong><p>{filter==='active'?'Проверьте бэклог или создайте новую группу':'Группы этого статуса появятся здесь'}</p></div>}
    </>}
    {view==='students'&&<><div className="roster-head"><div><h2>Все ученицы <span>{students.length}</span></h2></div><div className="roster-filters"><label className="roster-search"><Search size={15}/><input aria-label="Поиск ученицы" placeholder="Поиск по имени" value={search} onChange={e=>setSearch(e.target.value)}/></label><Select aria-label="Фильтр группы" value={studentGroup} onChange={e=>setStudentGroup(e.target.value)}><option value="all">Все группы</option>{data.groups.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</Select><Select aria-label="Фильтр этапа" value={studentStage} onChange={e=>setStudentStage(e.target.value as Stage|'all')}><option value="all">Все этапы</option>{STAGES.map(s=><option key={s.id} value={s.id}>{s.number}. {s.label}</option>)}</Select></div></div>
    {students.length?<div className="roster-list">{students.map(s=>{const group=data.groups.find(g=>g.id===s.groupId);const tasks=studentTasks(data,s.id);const next=nearestTask(tasks);return <button className="roster-row" key={s.id} onClick={()=>onStudent(s.id)}><Avatar student={s} size="sm"/><span className="roster-name"><strong>{s.name}</strong><small>{group?.name} · {s.stageKnown===false?'Этап не указан':STAGES.find(st=>st.id===s.stage)?.label}</small></span><span className="roster-next">{next?next.title:'Нет ближайшей задачи'}</span><strong className="roster-progress">{tasks.length?`${progress(tasks)}%`:'—'}</strong><span className="roster-open">Открыть профиль</span></button>})}</div>:<div className="profile-empty"><strong>{data.students.length?'Ученицы не найдены':'Учениц пока нет'}</strong><p>{data.students.length?'Измените фильтры':'Создайте группу и добавьте в неё первую ученицу'}</p></div>}</>}
  </>
}

function GroupCard({data,group,onOpen,onEdit,onStatus,onDelete}:{data:AppData;group:Group;onOpen:()=>void;onEdit:()=>void;onStatus:(s:GroupStatus)=>void;onDelete:()=>void}) {
  const students=data.students.filter(s=>s.groupId===group.id)
  const studentIds=new Set(students.map(student=>student.id))
  const hasTasks=data.tasks.some(task=>studentIds.has(task.studentId))
  const next=groupNextTask(data,group)
  const value=groupProgress(data,group)
  const run=(action:()=>void)=>(event:MouseEvent<HTMLButtonElement>)=>{action();event.currentTarget.closest('details')?.removeAttribute('open')}
  return <article className="editorial-group-row">
    <div className="editorial-group-card-head"><div><span className="group-status-text">{GROUP_STATUS[group.status]}</span><h2>{group.name}</h2></div><details className="group-action-menu"><summary aria-label={`Действия с группой ${group.name}`} title="Действия"><More size={20}/></summary><div className="group-action-popover" role="menu"><button role="menuitem" onClick={run(onEdit)}><Pencil size={16}/> Редактировать</button>{group.status==='backlog'&&<button role="menuitem" onClick={run(()=>onStatus('active'))}><Play size={16}/> Запустить</button>}{group.status==='active'&&<button role="menuitem" onClick={run(()=>onStatus('completed'))}><CheckCircle size={16}/> Завершить</button>}{group.status==='completed'&&<button role="menuitem" onClick={run(()=>onStatus('archived'))}><Archive size={16}/> В архив</button>}{group.status==='archived'&&<button role="menuitem" onClick={run(()=>onStatus(group.statusBeforeArchive||'completed'))}><RotateCcw size={16}/> Восстановить</button>}<button role="menuitem" className="red" onClick={run(onDelete)}><Trash size={16}/> Удалить</button></div></details></div>
    <div className="editorial-group-dates"><span>Начало <strong>{fullDate(group.startsAt)}</strong></span><span>План <strong>{fullDate(group.endsAt)}</strong></span></div>
    <div className="editorial-group-team"><span className="editorial-group-people">{students.slice(0,4).map(s=><Avatar key={s.id} student={s} size="sm"/>)}</span><span>{plural(students.length,'ученица','ученицы','учениц')}</span></div>
    <div className="editorial-group-next"><small>Ближайшая задача</small><strong title={next?.title}>{next?next.title:'Задач пока нет'}</strong></div>
    <div className="editorial-group-footer"><div><strong>{hasTasks?`${value}%`:'—'}</strong><span>{hasTasks?'общий прогресс':'план не заполнен'} · {countdown(group)}</span></div><button onClick={onOpen}>Открыть группу</button></div>
  </article>
}

export function GroupDetailPage({data,group,onBack,backLabel='Все группы',onStudent,onNewStudent,onEditGroup,onStatus}:{data:AppData;group:Group;onBack:()=>void;backLabel?:string;onStudent:(id:string)=>void;onNewStudent:()=>void;onEditGroup:()=>void;onStatus:(s:GroupStatus)=>void}) {
  const [stage,setStage]=useState<Stage|'all'>('all')
  const all=data.students.filter(s=>s.groupId===group.id)
  const students=all.filter(s=>stage==='all'||(s.stageKnown!==false&&s.stage===stage))
  const hasTasks=data.tasks.some(task=>all.some(student=>student.id===task.studentId))
  return <><button className="back-link" onClick={onBack}><ArrowLeft size={16}/> {backLabel}</button><div className="page-heading group-detail-heading editorial-page-head"><div><div className="eyebrow">{GROUP_STATUS[group.status]} · {fullDate(group.startsAt)} — {fullDate(group.endsAt)}</div><h1>{group.name}</h1><p>{plural(all.length,'ученица','ученицы','учениц')} · {hasTasks?`Прогресс ${groupProgress(data,group)}%`:'Стратегии пока пусты'}{group.actualEndsAt?` · завершена ${fullDate(group.actualEndsAt)}`:''}</p></div><div className="heading-actions"><button className="btn secondary" onClick={onEditGroup}>Редактировать группу</button><button className="btn dark" onClick={onNewStudent}><Plus size={18}/> Добавить ученицу</button></div></div>
    <div className="roster-head"><div><h2>Ученицы <span>{students.length}</span></h2></div><Select aria-label="Фильтр учениц по этапу" value={stage} onChange={e=>setStage(e.target.value as Stage|'all')}><option value="all">Все этапы</option>{STAGES.map(s=><option value={s.id} key={s.id}>{s.number}. {s.label}</option>)}</Select></div>
    {students.length?<div className="editorial-student-list">{students.map(s=><div key={s.id}><StudentCard student={s} data={data} onOpen={()=>onStudent(s.id)}/></div>)}</div>:<div className="profile-empty"><strong>{all.length?'На этом этапе учениц нет':'В группе пока нет учениц'}</strong><p>{all.length?'Выберите другой этап, чтобы увидеть учениц группы':'Добавьте ученицу и начните готовить её профиль и стратегию'}</p></div>}
    <div className="group-detail-bar"><span>{countdown(group)}</span><div>{group.status==='backlog'&&<button className="btn primary" onClick={()=>onStatus('active')}><Play size={16}/> Запустить группу</button>}{group.status==='active'&&<button className="btn primary" onClick={()=>onStatus('completed')}><CheckCircle size={16}/> Отметить завершённой</button>}{group.status==='completed'&&<button className="btn secondary" onClick={()=>onStatus('archived')}><Archive size={16}/> Переместить в архив</button>}{group.status==='archived'&&<button className="btn secondary" onClick={()=>onStatus(group.statusBeforeArchive||'completed')}><RotateCcw size={16}/> Восстановить</button>}</div></div>
    {group.notes&&<div className="group-notes"><small>Заметки куратора</small><p>{group.notes}</p></div>}
  </>
}

function StudentCard({student,data,onOpen}:{student:Student;data:AppData;onOpen:()=>void}) {
  const tasks=studentTasks(data,student.id)
  const next=nearestTask(tasks)
  const value=progress(tasks)
  const stage=STAGES.find(v=>v.id===student.stage)
  return <button className="editorial-student-row" onClick={onOpen}><span className="student-card-top"><Avatar student={student} size="lg"/></span><span className="editorial-student-identity"><strong>{student.name}</strong><span>{student.stageKnown===false?'Этап не указан':stage?.label} · {student.desiredPosition||student.level||'Позиция не указана'}</span></span><span className="editorial-student-next"><small>Следующая задача</small><strong>{next?next.title:'Пока не назначена'}</strong></span><span className="student-card-bottom"><span>{tasks.length?`${value}% плана`:'Стратегия пока пуста'}</span><span className="student-card-open-label">Открыть профиль</span></span></button>
}
