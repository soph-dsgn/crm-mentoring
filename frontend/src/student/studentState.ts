import { ApiError } from '../api/http'
import type { Homework } from '../types'

export type StudentHomeworkAction = 'submit' | 'resubmit' | null

export function studentProfileIdFromUrl(value:string):string|null{
  try{return new URL(value).searchParams.get('student')?.trim()||null}catch{return null}
}

export function studentPortalUrl(studentId:string,currentUrl:string):string{
  const url=new URL(currentUrl)
  url.pathname='/'
  url.search=''
  url.hash=''
  url.searchParams.set('student',studentId)
  return url.toString()
}

export function studentHomeworkAction(homework:Pick<Homework,'status'|'archivedAt'>):StudentHomeworkAction{
  if(homework.archivedAt)return null
  if(homework.status==='revision')return'resubmit'
  return homework.status==='issued'||homework.status==='progress'?'submit':null
}

export function studentErrorMessage(error:unknown):string{
  if(!(error instanceof ApiError))return'Не удалось загрузить данные. Проверьте соединение и повторите попытку'
  switch(error.code){
    case'connection_error':return'Не удалось подключиться к серверу. Проверьте соединение и повторите попытку'
    case'not_found':return'Профиль недоступен или ссылка устарела'
    case'forbidden':return'У этого аккаунта нет доступа к запрошенным данным'
    case'version_conflict':return'Домашнее задание изменилось. Мы загрузили актуальную версию — проверьте её и отправьте работу снова'
    case'task_review_conflict':return'Одна из задач уже находится на проверке в другом домашнем задании'
    case'invalid_homework_transition':return'Статус задания уже изменился. Мы загрузили актуальную версию'
    case'submission_required':return'Добавьте текст или ссылку на выполненную работу'
    default:return error.status===422?'Проверьте текст и ссылки перед отправкой':'Не удалось выполнить действие'
  }
}
