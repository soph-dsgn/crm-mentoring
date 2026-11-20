import { apiRequest } from './http'
import type { MeetingCreateRequest, MeetingList, MeetingRead, MeetingUpdateRequest } from './contracts'

const encoded = (value:string) => encodeURIComponent(value)

export const meetingsApi = {
  list(studentId:string, cursor?:string, includeArchived=false, signal?:AbortSignal) {
    const params=new URLSearchParams({limit:'100'})
    if(cursor)params.set('cursor',cursor)
    if(includeArchived)params.set('include_archived','true')
    return apiRequest<MeetingList>(`/api/v1/students/${encoded(studentId)}/meetings?${params}`,{signal})
  },
  create(studentId:string,payload:MeetingCreateRequest,signal?:AbortSignal){return apiRequest<MeetingRead>(`/api/v1/students/${encoded(studentId)}/meetings`,{method:'POST',body:payload,signal})},
  get(meetingId:string,signal?:AbortSignal){return apiRequest<MeetingRead>(`/api/v1/meetings/${encoded(meetingId)}`,{signal})},
  update(meetingId:string,payload:MeetingUpdateRequest,signal?:AbortSignal){return apiRequest<MeetingRead>(`/api/v1/meetings/${encoded(meetingId)}`,{method:'PATCH',body:payload,signal})},
  archive(meetingId:string,expectedVersion:number,signal?:AbortSignal){return apiRequest<MeetingRead>(`/api/v1/meetings/${encoded(meetingId)}/archive`,{method:'POST',body:{expected_version:expectedVersion},signal})},
  restore(meetingId:string,expectedVersion:number,signal?:AbortSignal){return apiRequest<MeetingRead>(`/api/v1/meetings/${encoded(meetingId)}/restore`,{method:'POST',body:{expected_version:expectedVersion},signal})},
}
