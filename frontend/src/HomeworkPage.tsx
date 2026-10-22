import { useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowRightIcon as ArrowRight, CheckIcon as Check, ClipboardTextIcon as ClipboardCopy, ArrowSquareOutIcon as ExternalLink } from '@phosphor-icons/react'
import { copyText } from './clipboard'
import { dateLabel, HOMEWORK_STATUS } from './data'
import type { AppData, Homework } from './types'
import { useCalmMotion } from './motion'

export function HomeworkCard({ homework, onUpdate, onTask, taskExists, onDelete, focused=false }: { homework: Homework; onUpdate: (id:string, patch:Partial<Homework>)=>void; onTask:(id:string)=>void; taskExists:(id:string)=>boolean; onDelete:(id:string)=>void; focused?:boolean }) {
  const [copied,setCopied] = useState(false)
  const [copyError,setCopyError] = useState('')
  const copy = async () => { try { await copyText(homework.text); if(homework.status==='draft')onUpdate(homework.id,{status:'issued',issuedAt:new Date().toISOString()}); setCopied(true); setCopyError(''); window.setTimeout(()=>setCopied(false),1800) } catch { setCopyError('Не удалось скопировать. Откройте текст задания и скопируйте его вручную') } }
  const canSubmit=['draft','issued','progress','revision'].includes(homework.status)
  const needsDecision=homework.status==='submitted'
  return <article id={`homework-${homework.id}`} className={`homework-card ${focused?'homework-focused':''}`}>
    <div className="homework-card-head"><div><h3>{homework.title}</h3><p>{HOMEWORK_STATUS[homework.status]}{homework.issuedAt ? ` · выдано ${dateLabel(homework.issuedAt.slice(0,10))}` : ''}{homework.dueAt ? ` · срок ${dateLabel(homework.dueAt)}` : ''}</p></div><button className="btn secondary" onClick={copy}><ClipboardCopy size={17}/>{copied?'Скопировано':'Скопировать ДЗ'}</button></div>
    {copyError&&<p role="alert">{copyError}</p>}
    {homework.workUrl&&<a href={homework.workUrl} target="_blank" rel="noreferrer" className="text-link homework-work-link">Открыть отправленную работу <ExternalLink size={15} weight="regular"/></a>}
    {needsDecision&&<p className="homework-decision-hint">Проверьте работу и примите её или верните с комментарием</p>}
    {(canSubmit||(needsDecision&&!homework.workUrl))&&<div className="homework-review-fields"><label>Ссылка на выполненную работу<input type="url" placeholder="https://…" value={homework.workUrl} onChange={e=>onUpdate(homework.id,{workUrl:e.target.value})}/></label></div>}
    {(needsDecision||homework.status==='revision')&&<div className="homework-review-fields"><label>Комментарий куратора<textarea rows={2} placeholder="Что принять или исправить" value={homework.comment} onChange={e=>onUpdate(homework.id,{comment:e.target.value})}/></label></div>}
    {homework.status==='accepted'&&homework.comment&&<p className="homework-comment">Комментарий к проверке: {homework.comment}</p>}
    <div className="homework-actions">
      {(homework.status==='issued'||homework.status==='revision')&&<button className="btn secondary" onClick={()=>onUpdate(homework.id,{status:'progress'})}>Отметить в работе</button>}
      {canSubmit&&<button className="btn dark" disabled={!homework.workUrl.trim()} title={!homework.workUrl.trim()?'Добавьте ссылку на работу':''} onClick={()=>onUpdate(homework.id,{status:'submitted',submittedAt:new Date().toISOString()})}>Отправить на проверку</button>}
      {needsDecision&&<><button className="btn secondary" onClick={()=>onUpdate(homework.id,{status:'revision'})}>Вернуть на доработку</button><button className="btn dark" onClick={()=>onUpdate(homework.id,{status:'accepted'})}><Check size={17} weight="regular"/> Принять работу</button></>}
    </div>
    <details className="homework-more"><summary>Содержание ДЗ · {homework.items.length} задач</summary><div className="homework-items">{homework.items.map(item=>taskExists(item.taskId)?<button key={item.taskId} onClick={()=>onTask(item.taskId)}>{item.title}<ArrowRight size={16} weight="regular"/></button>:<span key={item.taskId}>{item.title} · исходная задача удалена</span>)}</div><pre>{homework.text}</pre></details>
    {homework.submittedAt&&<p className="homework-submitted">Отправлено {dateLabel(homework.submittedAt.slice(0,10))}{homework.reviewedAt?` · проверено ${dateLabel(homework.reviewedAt.slice(0,10))}`:''}</p>}
    <button className="homework-delete" onClick={()=>onDelete(homework.id)}>Переместить в корзину</button>
  </article>
}

export default function HomeworkPage({data,onStudent,onTask,onUpdate,onDelete,onRestore}:{data:AppData;onStudent:(id:string,homeworkId:string)=>void;onTask:(id:string)=>void;onUpdate:(id:string,patch:Partial<Homework>)=>void;onDelete:(id:string)=>void;onRestore:(id:string)=>void}) {
  const calm=useCalmMotion()
  const [filter,setFilter] = useState<'all'|'submitted'|'open'|'accepted'|'trash'>('submitted')
  const [search,setSearch] = useState('')
  const inFilter=(h:Homework,key:typeof filter)=>key==='trash'?Boolean(h.deletedAt):!h.deletedAt&&(key==='all'||key==='submitted'&&h.status==='submitted'||key==='accepted'&&h.status==='accepted'||key==='open'&&h.status!=='submitted'&&h.status!=='accepted')
  const query=search.trim().toLocaleLowerCase('ru')
  const homeworks = [...data.homeworks].filter(h=>inFilter(h,filter)&&(!query||[data.students.find(s=>s.id===h.studentId)?.name,h.title,h.text].some(value=>value?.toLocaleLowerCase('ru').includes(query)))).sort((a,b)=>(b.submittedAt||b.issuedAt||b.createdAt).localeCompare(a.submittedAt||a.issuedAt||a.createdAt))
  return <div className="homework-page">
    <div className="page-heading"><div><h1>Домашние задания</h1><p>История заданий и очередь проверок</p></div></div>
    <div className="tabs">{(['submitted','open','accepted','all','trash'] as const).map(key=><button key={key} className={filter===key?'selected':''} onClick={()=>setFilter(key)}>{key==='submitted'?'На проверке':key==='open'?'Не завершены':key==='accepted'?'Приняты':key==='trash'?'Корзина':'Все'} <span>{data.homeworks.filter(h=>inFilter(h,key)).length}</span>{filter===key&&<motion.i className="motion-tab-indicator" layoutId="homework-tab-indicator" transition={calm.tab}/>}</button>)}</div>
    <input className="homework-search" type="search" aria-label="Поиск домашнего задания" placeholder="Найти по ученице или содержимому" value={search} onChange={e=>setSearch(e.target.value)}/>
    {homeworks.length?<div className="homework-list">{homeworks.map(h=>{const s=data.students.find(x=>x.id===h.studentId);const g=data.groups.find(x=>x.id===s?.groupId);return <div key={h.id}>{s?<button className="homework-student" onClick={()=>onStudent(h.studentId,h.id)}>{s.name} · {g?.name||'Группа удалена'} <span>Открыть профиль <ArrowRight size={15}/></span></button>:<p className="homework-student">Ученица удалена</p>}{filter==='trash'?<button className="btn secondary" onClick={()=>onRestore(h.id)}>Восстановить «{h.title}»</button>:<HomeworkCard homework={h} onUpdate={onUpdate} onTask={onTask} taskExists={id=>data.tasks.some(task=>task.id===id)} onDelete={onDelete}/>}</div>})}</div>:<div className="profile-empty"><strong>{query?'Ничего не найдено':filter==='submitted'?'Проверок пока нет':'Заданий здесь пока нет'}</strong><p>{query?'Попробуйте другое имя или слово из задания':filter==='submitted'?'Проверок пока нет':'Откройте стратегию ученицы, выберите задачи и сформируйте ДЗ'}</p></div>}
  </div>
}
