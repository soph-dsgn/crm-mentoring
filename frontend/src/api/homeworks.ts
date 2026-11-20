import { apiRequest } from './http'
import type { HomeworkCreateRequest, HomeworkHistoryList, HomeworkList, HomeworkRead, HomeworkTransitionRequest, HomeworkUpdateRequest } from './contracts'

const encoded=(value:string)=>encodeURIComponent(value)

export const homeworksApi={
  list(strategyId:string,cursor?:string,includeArchived=false,signal?:AbortSignal){const params=new URLSearchParams({limit:'100'});if(cursor)params.set('cursor',cursor);if(includeArchived)params.set('include_archived','true');return apiRequest<HomeworkList>(`/api/v1/strategies/${encoded(strategyId)}/homeworks?${params}`,{signal})},
  create(strategyId:string,payload:HomeworkCreateRequest,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/strategies/${encoded(strategyId)}/homeworks`,{method:'POST',body:payload,signal})},
  get(homeworkId:string,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}`,{signal})},
  update(homeworkId:string,payload:HomeworkUpdateRequest,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}`,{method:'PATCH',body:payload,signal})},
  transition(homeworkId:string,payload:HomeworkTransitionRequest,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}/transitions`,{method:'POST',body:payload,signal})},
  archive(homeworkId:string,expectedVersion:number,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}/archive`,{method:'POST',body:{expected_version:expectedVersion},signal})},
  restore(homeworkId:string,expectedVersion:number,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}/restore`,{method:'POST',body:{expected_version:expectedVersion},signal})},
  history(homeworkId:string,cursor?:string,signal?:AbortSignal){const params=new URLSearchParams({limit:'100'});if(cursor)params.set('cursor',cursor);return apiRequest<HomeworkHistoryList>(`/api/v1/homeworks/${encoded(homeworkId)}/history?${params}`,{signal})},
}
