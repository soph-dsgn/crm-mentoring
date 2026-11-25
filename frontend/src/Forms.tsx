import { cloneElement, isValidElement, useId, useRef, useState } from 'react'
import DateField from './DateField'
import { CameraIcon as Camera, TrashIcon as Trash2 } from '@phosphor-icons/react'
import Select from './Select'
import Avatar, { imageFromFile } from './Avatar'
import { addCalendarMonths, GROUP_STATUS, STAGES } from './data'
import type { Group, GroupStatus, Stage, Student } from './types'

export function Field({label,children}:{label:string;children:React.ReactNode}){const id=useId();return <div className="field"><label htmlFor={id}>{label}</label>{isValidElement(children)?cloneElement(children as React.ReactElement<{id?:string}>,{id}):children}</div>}

export function GroupForm({draft,setDraft,onSave,onCancel,pending=false,error=''}:{draft:Group;setDraft:(v:Group)=>void;onSave:()=>void;onCancel:()=>void;pending?:boolean;error?:string}){
  return <form className="form" onSubmit={e=>{e.preventDefault();onSave()}}><Field label="Название группы"><input required autoFocus disabled={pending} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder="Например, Группа 5"/></Field><div className="form-grid"><Field label="Статус"><Select disabled={pending} value={draft.status} onChange={e=>{const status=e.target.value as GroupStatus;setDraft({...draft,status})}}>{Object.entries(GROUP_STATUS).filter(([id])=>id!=='archived').map(([id,label])=><option key={id} value={id}>{label}</option>)}</Select></Field><Field label="Дата начала"><DateField disabled={pending} value={draft.startsAt} onChange={value=>setDraft({...draft,startsAt:value,endsAt:draft.durationMonths?addCalendarMonths(value,draft.durationMonths):draft.endsAt})}/></Field><Field label="Продолжительность, месяцев"><input disabled={pending} type="number" min="0.5" step="0.5" value={draft.durationMonths??''} onChange={e=>{const durationMonths=e.target.value?Number(e.target.value):undefined;setDraft({...draft,durationMonths,endsAt:durationMonths&&draft.startsAt?addCalendarMonths(draft.startsAt,durationMonths):draft.endsAt})}} placeholder="Необязательно"/></Field><Field label="Планируемое окончание"><DateField disabled={pending} value={draft.endsAt} onChange={value=>setDraft({...draft,endsAt:value,durationMonths:undefined})}/></Field><Field label="Фактическое завершение"><DateField disabled={pending} value={draft.actualEndsAt} onChange={value=>setDraft({...draft,actualEndsAt:value})}/></Field></div><Field label="Заметки куратора"><textarea disabled={pending} rows={4} value={draft.notes} onChange={e=>setDraft({...draft,notes:e.target.value})} placeholder="Фокус группы, договорённости, важный контекст"/></Field><div className="form-helper">Плановая дата не меняет статус автоматически. Запуск и завершение подтверждаются вручную</div>{error&&<p className="form-error" role="alert">{error}</p>}<div className="dialog-actions"><button type="button" className="btn secondary" disabled={pending} onClick={onCancel}>Отмена</button><button className="btn primary" disabled={pending} type="submit">{pending?'Сохраняем…':'Сохранить группу'}</button></div></form>
}

export function StudentForm({draft,setDraft,groups,onSave,onCancel,pending=false,error='',groupLocked=false,photoUploadEnabled=true}:{draft:Student;setDraft:(v:Student)=>void;groups:Group[];onSave:()=>void;onCancel:()=>void;pending?:boolean;error?:string;groupLocked?:boolean;photoUploadEnabled?:boolean}){
  const [photoError,setPhotoError]=useState('')
  const [photoPending,setPhotoPending]=useState(false)
  const latestDraft=useRef(draft)
  latestDraft.current=draft
  const update=(patch:Partial<Student>)=>setDraft({...draft,...patch})
  const upload = async (file?: File) => {
    if (!file || photoPending) return
    setPhotoPending(true)
    setPhotoError('')
    try {
      const photo = await imageFromFile(file)
      setDraft({ ...latestDraft.current, photo })
    } catch (error) {
      setPhotoError(error instanceof Error ? error.message : 'Не удалось загрузить фото')
    } finally {
      setPhotoPending(false)
    }
  }
  const aboutFields=([['background','Бэкграунд'],['experience','Опыт работы и проекты'],['strengths','Сильные стороны'],['growthAreas','Зоны роста'],['difficulties','Текущие сложности'],['expectations','Карьерные ожидания'],['personalNotes','Особенности и важные заметки']] as const)
  const linkFields=([['telegram','Telegram'],['resume','Резюме'],['portfolio','Портфолио'],['figma','Figma'],['notion','Notion']] as const)
  const aboutCount=aboutFields.filter(([key])=>draft[key].trim()).length
  const linksCount=linkFields.filter(([key])=>draft.links[key].trim()).length
  return <form className="form" onSubmit={e=>{e.preventDefault();if(!photoPending)onSave()}}><div className="photo-editor"><Avatar student={draft} size="lg"/><div><strong>Фотография ученицы</strong><p>{photoUploadEnabled?'JPG или PNG до 12 МБ. Изображение уменьшится перед сохранением':'Просмотр фотографии ученицы'}</p>{photoUploadEnabled&&<div><label className="btn secondary photo-upload"><Camera size={16}/> {draft.photo?'Заменить фото':'Загрузить фото'}<input type="file" accept="image/jpeg,image/png" disabled={pending||photoPending} hidden onChange={e=>{void upload(e.target.files?.[0]);e.target.value=''}}/></label>{draft.photo&&<button type="button" className="btn danger" disabled={pending||photoPending} onClick={()=>update({photo:''})}><Trash2 size={15}/> Удалить</button>}</div>}{photoError&&<small className="text-red">{photoError}</small>}</div></div>
    <div className="form-section-title">Основная информация</div><div className="form-grid"><Field label="Имя и фамилия"><input required autoFocus disabled={pending} value={draft.name} onChange={e=>update({name:e.target.value})} placeholder="Имя и фамилия"/></Field><Field label="Возраст (необязательно)"><input disabled={pending} type="number" min="0" max="150" value={draft.age??''} onChange={e=>update({age:e.target.value?Number(e.target.value):null})} placeholder="—"/></Field><Field label="Группа"><Select disabled={pending||groupLocked} value={draft.groupId} onChange={e=>update({groupId:e.target.value})}>{groups.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</Select></Field><Field label="Дата начала"><DateField disabled={pending} value={draft.startsAt} onChange={value=>update({startsAt:value})}/></Field><Field label="Этап обучения"><Select disabled={pending} value={draft.stageKnown===false?'':draft.stage} onChange={e=>update(e.target.value?{stage:e.target.value as Stage,stageKnown:true}:{stageKnown:false})}><option value="">Не указан</option>{STAGES.map(s=><option key={s.id} value={s.id}>{s.number}. {s.label}</option>)}</Select></Field><Field label="Профессиональный уровень"><input disabled={pending} value={draft.level} onChange={e=>update({level:e.target.value})} placeholder="Junior"/></Field><Field label="Желаемая позиция"><input disabled={pending} value={draft.desiredPosition} onChange={e=>update({desiredPosition:e.target.value})} placeholder="Product Designer"/></Field><Field label="Карьерная цель"><input disabled={pending} value={draft.careerGoal} onChange={e=>update({careerGoal:e.target.value})} placeholder="Какого результата хочет достичь"/></Field></div>
    <details className="form-more"><summary>Об ученице{aboutCount?` · заполнено ${aboutCount} из ${aboutFields.length}`:''}</summary><div className="form-grid">{aboutFields.map(([key,label])=><Field key={key} label={label}><textarea disabled={pending} rows={3} value={draft[key]} onChange={e=>update({[key]:e.target.value})}/></Field>)}</div></details>
    <details className="form-more"><summary>Точка А и точка Б{draft.pointA||draft.pointB?' · заполнено':''}</summary><div className="form-grid"><Field label="Точка А"><textarea disabled={pending} rows={3} value={draft.pointA} onChange={e=>update({pointA:e.target.value})} placeholder="Исходная ситуация"/></Field><Field label="Точка Б"><textarea disabled={pending} rows={3} value={draft.pointB} onChange={e=>update({pointB:e.target.value})} placeholder="Целевой или достигнутый результат"/></Field></div></details>
    <details className="form-more"><summary>Ссылки{linksCount?` · добавлено ${linksCount}`:''}</summary><div className="form-grid">{linkFields.map(([key,label])=><Field key={key} label={label}><input disabled={pending} type="url" value={draft.links[key]} onChange={e=>update({links:{...draft.links,[key]:e.target.value}})} placeholder="https://"/></Field>)}</div></details>
    {error&&<p className="form-error" role="alert">{error}</p>}<div className="dialog-actions"><button type="button" className="btn secondary" disabled={pending} onClick={onCancel}>Отмена</button><button className="btn primary" disabled={pending||photoPending} type="submit">{pending?'Сохраняем…':'Сохранить профиль'}</button></div>
  </form>
}
