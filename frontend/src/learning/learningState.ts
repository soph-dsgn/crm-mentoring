import type { HomeworkHistoryRead, HomeworkRead, MeetingRead } from '../api/contracts'
import { ApiError } from '../api/http'
import type { AppData, Homework, HomeworkHistory, Meeting } from '../types'

export function meetingFromApi(meeting:MeetingRead):Meeting{return {id:meeting.id,studentId:meeting.student_id,date:meeting.date,title:meeting.title,summary:meeting.summary,notes:meeting.notes??'',archivedAt:meeting.archived_at??'',createdAt:meeting.created_at,updatedAt:meeting.updated_at,version:meeting.version,serverBacked:true}}
export function homeworkHistoryFromApi(item:HomeworkHistoryRead):HomeworkHistory{return {id:item.id,eventType:item.event_type,fromStatus:item.from_status,toStatus:item.to_status,createdAt:item.created_at}}
export function homeworkFromApi(homework:HomeworkRead,studentId:string,history:HomeworkHistoryRead[]=[]):Homework{
  const submissionLinks={...homework.submission_links}
  return {id:homework.id,studentId,strategyId:homework.strategy_id,title:homework.title,text:homework.description,links:{...homework.links},items:homework.items.map(item=>({id:item.id,taskId:item.task_id,title:item.title,description:item.description,url:Object.values(item.links)[0]??'',materials:[...item.materials],links:{...item.links},period:item.period_text,dueAt:item.due_at??''})),status:homework.status,issuedAt:homework.issued_at??'',submittedAt:homework.submitted_at??'',reviewedAt:homework.reviewed_at??'',workUrl:Object.values(submissionLinks)[0]??'',submissionText:homework.submission_text,submissionLinks,comment:homework.curator_feedback,dueAt:homework.due_at??'',archivedAt:homework.archived_at??'',deletedAt:homework.archived_at??'',createdAt:homework.created_at,updatedAt:homework.updated_at,version:homework.version,serverBacked:true,history:history.map(homeworkHistoryFromApi)}
}

export type HomeworkAction='issue'|'progress'|'submit'|'revision'|'accept'|'archive'|'restore'
export function homeworkActions(homework:Homework,canWrite:boolean):HomeworkAction[]{
  if(!canWrite)return []
  if(homework.archivedAt)return ['restore']
  switch(homework.status){case'draft':return['issue','archive'];case'issued':return['progress','submit','archive'];case'progress':return['submit'];case'submitted':return['revision','accept'];case'revision':return['progress','submit'];case'accepted':return['archive']}
}

export function withServerLearning(base:AppData,meetings:Meeting[],homeworks:Homework[]):AppData{
  const studentIds=new Set(base.students.filter(student=>student.serverBacked).map(student=>student.id))
  return {...base,meetings:meetings.filter(meeting=>studentIds.has(meeting.studentId)),homeworks:homeworks.filter(homework=>studentIds.has(homework.studentId))}
}

export function learningErrorMessage(error:unknown):string{
  if(error instanceof Error&&error.message==='strategy_refresh_failed')return'Домашнее задание обновлено, но статусы задач не удалось синхронизировать. Повторите обновление'
  if(!(error instanceof ApiError))return'Не удалось выполнить действие'
  switch(error.code){
    case'connection_error':return'Не удалось подключиться к серверу'
    case'forbidden':return'У вас нет прав изменять встречу или домашнее задание'
    case'not_found':return'Запись больше недоступна'
    case'version_conflict':return'Данные изменились в другой сессии. Мы загрузили актуальную версию — проверьте изменения и повторите действие'
    case'curator_assignment_changed':return'Назначение куратора изменилось. Доступ и данные обновлены'
    case'homework_immutable':return'Выданное домашнее задание нельзя редактировать'
    case'homework_review_active':return'Завершите активную проверку перед архивированием'
    case'task_review_conflict':return'Одна из задач уже проверяется в другом домашнем задании'
    case'invalid_homework_transition':return'Это действие больше недоступно. Мы загрузили актуальное состояние'
    case'invalid_meeting_transition':return'Состояние встречи уже изменилось. Обновите данные'
    case'homework_archived':return'Сначала восстановите домашнее задание'
    case'submission_required':return'Добавьте текст или ссылку на выполненную работу'
    case'invalid_task_selection':return'Выберите уникальные неархивные задачи из стратегии этой ученицы'
    default:return error.status===422?'Проверьте заполненные поля':'Не удалось выполнить действие'
  }
}
