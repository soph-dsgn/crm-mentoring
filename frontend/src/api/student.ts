import type {
  GroupStudentRead,
  HomeworkHistoryList,
  HomeworkList,
  HomeworkRead,
  HomeworkTransitionRequest,
  MeetingList,
  StrategyRead,
  StrategySectionRead,
  StrategyTaskRead,
  StudentSelfRead,
} from './contracts'
import { apiRequest } from './http'

const encoded = (value:string) => encodeURIComponent(value)

export const studentApi = {
  getProfile(studentId:string,signal?:AbortSignal){return apiRequest<StudentSelfRead>(`/api/v1/students/${encoded(studentId)}`,{signal})},
  getGroup(groupId:string,signal?:AbortSignal){return apiRequest<GroupStudentRead>(`/api/v1/groups/${encoded(groupId)}`,{signal})},
  getStrategy(studentId:string,signal?:AbortSignal){return apiRequest<StrategyRead>(`/api/v1/students/${encoded(studentId)}/strategy`,{signal})},
  listSections(strategyId:string,signal?:AbortSignal){return apiRequest<StrategySectionRead[]>(`/api/v1/strategies/${encoded(strategyId)}/sections`,{signal})},
  listTasks(sectionId:string,signal?:AbortSignal){return apiRequest<StrategyTaskRead[]>(`/api/v1/strategy-sections/${encoded(sectionId)}/tasks?include_archived=true`,{signal})},
  listMeetings(studentId:string,cursor?:string,includeArchived=false,signal?:AbortSignal){const params=new URLSearchParams({limit:'100'});if(cursor)params.set('cursor',cursor);if(includeArchived)params.set('include_archived','true');return apiRequest<MeetingList>(`/api/v1/students/${encoded(studentId)}/meetings?${params}`,{signal})},
  listHomeworks(strategyId:string,cursor?:string,includeArchived=false,signal?:AbortSignal){const params=new URLSearchParams({limit:'100'});if(cursor)params.set('cursor',cursor);if(includeArchived)params.set('include_archived','true');return apiRequest<HomeworkList>(`/api/v1/strategies/${encoded(strategyId)}/homeworks?${params}`,{signal})},
  getHomework(homeworkId:string,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}`,{signal})},
  homeworkHistory(homeworkId:string,cursor?:string,signal?:AbortSignal){const params=new URLSearchParams({limit:'100'});if(cursor)params.set('cursor',cursor);return apiRequest<HomeworkHistoryList>(`/api/v1/homeworks/${encoded(homeworkId)}/history?${params}`,{signal})},
  submitHomework(homeworkId:string,payload:HomeworkTransitionRequest,signal?:AbortSignal){return apiRequest<HomeworkRead>(`/api/v1/homeworks/${encoded(homeworkId)}/transitions`,{method:'POST',body:payload,signal})},
}
