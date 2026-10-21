import { useState } from 'react'
import { ArrowRightIcon as ArrowRight, PlusIcon as Plus } from '@phosphor-icons/react'
import { APPROVAL_STATUS, approvalState, dateLabel, groupProgress, isOverdue, needsAnyaApproval, taskColumn } from './data'
import type { AppData, Group, StrategyTask, Student } from './types'

type Attention = { student: Student; overdue: number; blockers: number; stale: boolean }
type Props = { data:AppData; activeGroups:Group[]; tasks:StrategyTask[]; attention:Attention[]; upcoming:StrategyTask[]; onGroup:(id:string)=>void; onStudent:(id:string)=>void; onTask:(id:string)=>void; onReview:(id:string)=>void; onNewGroup:()=>void; onStrategies:()=>void; onAnya:()=>void; onHomework:()=>void }
type Row = {id:string; title:string; detail:string; actionLabel:string; action:()=>void}

function Panel({title,subtitle,rows,empty,action,limit=4}:{title:string;subtitle:string;rows:Row[];empty:string;action?:{label:string;run:()=>void};limit?:number}) {
  const [expanded,setExpanded]=useState(false)
  const visible=expanded?rows:rows.slice(0,limit)
  return <section className="overview-panel"><div className="overview-panel-head"><div><h2>{title}</h2><p>{subtitle}</p></div>{action&&<button onClick={action.run}>{action.label} <ArrowRight size={16}/></button>}</div>
    {visible.length?<div className="overview-list">{visible.map(row=><button key={row.id} onClick={row.action}><span><strong>{row.title}</strong><small>{row.detail}</small></span><span className="overview-row-action">{row.actionLabel} <ArrowRight size={16}/></span></button>)}</div>:<p className="overview-empty">{empty}</p>}
    {rows.length>limit&&<button className="overview-expand" onClick={()=>setExpanded(!expanded)}>{expanded?'Свернуть':`Показать все · ${rows.length}`}</button>}
  </section>
}

const studentCount=(count:number)=>`${count} ${count%10===1&&count%100!==11?'ученица':count%10>=2&&count%10<=4&&(count%100<12||count%100>14)?'ученицы':'учениц'}`

export default function PlanOverview({data,activeGroups,tasks,attention,upcoming,onGroup,onStudent,onTask,onReview,onNewGroup,onStrategies,onAnya,onHomework}:Props) {
  const activeStudents = new Set(data.students.filter(s=>activeGroups.some(g=>g.id===s.groupId)).map(s=>s.id))
  const overdue = tasks.filter(t=>taskColumn(t)!=='done'&&isOverdue(t.dueAt)).sort((a,b)=>a.dueAt.localeCompare(b.dueAt))
  const reviews = data.homeworks.filter(h=>!h.deletedAt&&h.status==='submitted'&&activeStudents.has(h.studentId)).sort((a,b)=>b.submittedAt.localeCompare(a.submittedAt))
  const anyaToSend = tasks.filter(t=>needsAnyaApproval(t)&&approvalState(t)==='to_send')
  const anyaWaiting = tasks.filter(t=>needsAnyaApproval(t)&&['sent','reviewing'].includes(approvalState(t)))
  const person = (id:string) => data.students.find(s=>s.id===id)?.name||'Ученица удалена'
  return <div className="workspace-board overview-workspace"><div className="board-heading"><h1>Обзор</h1><p>Рабочая очередь по активным группам</p></div><div className="overview-grid">
    <Panel title={`Активные группы · ${activeGroups.length}`} subtitle="Группы и ученицы текущего обучения" rows={activeGroups.map(g=>({id:g.id,title:g.name,detail:`${studentCount(data.students.filter(s=>s.groupId===g.id).length)} · ${groupProgress(data,g)}% плана`,actionLabel:'Открыть группу',action:()=>onGroup(g.id)}))} empty="Активных групп пока нет. Создайте группу или запустите группу из бэклога" action={{label:'Все группы',run:onStrategies}} limit={6}/>
    <Panel title={`На проверке · ${reviews.length}`} subtitle="Работы, ожидающие решения куратора" rows={reviews.map(h=>({id:h.id,title:h.title,detail:`${person(h.studentId)} · отправлено ${dateLabel(h.submittedAt.slice(0,10))}`,actionLabel:'Проверить работу',action:()=>onReview(h.id)}))} empty="Работ на проверке нет" action={{label:'Вся очередь',run:onHomework}}/>
    <Panel title={`Просрочено · ${overdue.length}`} subtitle="Задачи с указанным сроком" rows={overdue.map(t=>({id:t.id,title:t.title,detail:`${person(t.studentId)} · срок ${dateLabel(t.dueAt)}`,actionLabel:'Открыть задачу',action:()=>onTask(t.id)}))} empty="Просроченных задач нет"/>
    <Panel title="Ближайшие действия" subtitle="Сроки и задачи в работе" rows={upcoming.map(t=>({id:t.id,title:t.title,detail:`${person(t.studentId)} · ${t.dueAt?dateLabel(t.dueAt):'в процессе'}`,actionLabel:'Открыть задачу',action:()=>onTask(t.id)}))} empty="Задач в работе пока нет"/>
    <Panel title={`Требуют внимания · ${attention.length}`} subtitle="Просрочки, блокировки и давно не обновлённые стратегии" rows={attention.map(x=>({id:x.student.id,title:x.student.name,detail:[x.overdue&&`${x.overdue} просрочено`,x.blockers&&`${x.blockers} блокируют`,x.stale&&'стратегия давно не обновлялась'].filter(Boolean).join(' · '),actionLabel:'Открыть профиль',action:()=>onStudent(x.student.id)}))} empty="По текущим признакам нет задач, требующих внимания"/>
    <Panel title="Согласования с Аней" subtitle={`${anyaToSend.length} нужно передать · ${anyaWaiting.length} ждут ответа`} rows={[...anyaToSend,...anyaWaiting].map(t=>({id:t.id,title:t.title,detail:`${person(t.studentId)} · ${APPROVAL_STATUS[approvalState(t)]}`,actionLabel:'Открыть задачу',action:()=>onTask(t.id)}))} empty="Открытых согласований нет" action={{label:'Вся очередь',run:onAnya}}/>
  </div>{activeGroups.length===0&&<div className="board-footer"><button onClick={onNewGroup}>Создать группу <Plus size={17}/></button></div>}</div>
}
