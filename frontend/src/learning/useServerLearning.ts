import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { HomeworkCreateRequest, HomeworkRead, HomeworkTransitionRequest, HomeworkUpdateRequest, MeetingCreateRequest, MeetingUpdateRequest, StrategyRead } from '../api/contracts'
import { homeworksApi } from '../api/homeworks'
import { ApiError } from '../api/http'
import { meetingsApi } from '../api/meetings'
import type { Homework, Meeting, Student } from '../types'
import { homeworkFromApi, meetingFromApi } from './learningState'

type LoadStatus='loading'|'ready'|'error'
type ResourceState={status:LoadStatus;error:unknown;errorsByStudent:Map<string,unknown>}
const loadingState=():ResourceState=>({status:'loading',error:null,errorsByStudent:new Map()})

const replaceById=<T extends{id:string}>(items:T[],next:T)=>items.some(item=>item.id===next.id)?items.map(item=>item.id===next.id?next:item):[...items,next]

export function mergeLearningRecords<T extends{studentId:string}>(current:T[],activeStudentIds:Set<string>,updates:Map<string,T[]>):T[]{
  const retained=current.filter(item=>activeStudentIds.has(item.studentId)&&!updates.has(item.studentId))
  return [...updates.values()].reduce((records,items)=>records.concat(items),retained)
}

export function shouldEvictLearningRecords(error:unknown):boolean{return error instanceof ApiError&&(error.status===403||error.status===404)}

async function allMeetings(studentId:string,signal?:AbortSignal){const items=[] as Awaited<ReturnType<typeof meetingsApi.list>>['items'];let cursor: string|undefined;do{const page=await meetingsApi.list(studentId,cursor,true,signal);items.push(...page.items);cursor=page.next_cursor??undefined}while(cursor);return items}
async function allHomeworks(strategyId:string,signal?:AbortSignal){const items=[] as HomeworkRead[];let cursor:string|undefined;do{const page=await homeworksApi.list(strategyId,cursor,true,signal);items.push(...page.items);cursor=page.next_cursor??undefined}while(cursor);return items}

function loadState(errorsByStudent:Map<string,unknown>,studentCount:number):ResourceState{
  const allFailed=studentCount>0&&errorsByStudent.size===studentCount
  return {status:allFailed?'error':'ready',error:allFailed?errorsByStudent.values().next().value:null,errorsByStudent}
}

export function useServerLearning(identityKey:string,students:Student[],strategies:Record<string,StrategyRead|null>,refreshStrategyStudent:(studentId:string)=>Promise<unknown>){
  const [meetings,setMeetings]=useState<Meeting[]>([])
  const [homeworks,setHomeworks]=useState<Homework[]>([])
  const [meetingState,setMeetingState]=useState<ResourceState>(loadingState)
  const [homeworkState,setHomeworkState]=useState<ResourceState>(loadingState)
  const sourcesRef=useRef({students,strategies});sourcesRef.current={students,strategies}
  const sourceKey=useMemo(()=>students.map(student=>`${student.id}:${student.version??0}:${strategies[student.id]?.id??''}`).sort().join('|'),[students,strategies])

  const applyMeetings=useCallback((studentId:string,next:Meeting[])=>setMeetings(items=>[...items.filter(item=>item.studentId!==studentId),...next]),[])
  const applyHomeworks=useCallback((studentId:string,next:Homework[])=>setHomeworks(items=>[...items.filter(item=>item.studentId!==studentId),...next]),[])
  const evictStudent=useCallback((studentId:string)=>{setMeetings(items=>items.filter(item=>item.studentId!==studentId));setHomeworks(items=>items.filter(item=>item.studentId!==studentId))},[])

  const loadMeetings=useCallback(async(signal?:AbortSignal)=>{
    setMeetingState(current=>current.status==='ready'?current:loadingState())
    const current=sourcesRef.current
    const results=await Promise.allSettled(current.students.map(student=>allMeetings(student.id,signal)))
    if(signal?.aborted)return
    const updates=new Map<string,Meeting[]>();const errors=new Map<string,unknown>()
    results.forEach((result,index)=>{const studentId=current.students[index].id;if(result.status==='fulfilled')updates.set(studentId,result.value.map(meetingFromApi));else{errors.set(studentId,result.reason);if(shouldEvictLearningRecords(result.reason))updates.set(studentId,[])}})
    setMeetings(items=>mergeLearningRecords(items,new Set(current.students.map(student=>student.id)),updates))
    setMeetingState(loadState(errors,current.students.length))
  },[])

  const loadHomeworks=useCallback(async(signal?:AbortSignal)=>{
    setHomeworkState(current=>current.status==='ready'?current:loadingState())
    const current=sourcesRef.current
    const results=await Promise.allSettled(current.students.map(async student=>{const strategy=current.strategies[student.id];return strategy?(await allHomeworks(strategy.id,signal)).map(item=>homeworkFromApi(item,student.id)):[]}))
    if(signal?.aborted)return
    const updates=new Map<string,Homework[]>();const errors=new Map<string,unknown>()
    results.forEach((result,index)=>{const studentId=current.students[index].id;if(result.status==='fulfilled')updates.set(studentId,result.value);else{errors.set(studentId,result.reason);if(shouldEvictLearningRecords(result.reason))updates.set(studentId,[])}})
    setHomeworks(items=>mergeLearningRecords(items,new Set(current.students.map(student=>student.id)),updates))
    setHomeworkState(loadState(errors,current.students.length))
  },[])

  const load=useCallback(async(signal?:AbortSignal)=>{await Promise.all([loadMeetings(signal),loadHomeworks(signal)])},[loadHomeworks,loadMeetings])
  useEffect(()=>{const controller=new AbortController();void load(controller.signal);return()=>controller.abort()},[identityKey,sourceKey,load])

  const updateResourceState=useCallback((resource:'meetings'|'homeworks',studentId:string,error?:unknown)=>{
    const setter=resource==='meetings'?setMeetingState:setHomeworkState
    setter(current=>{const errors=new Map(current.errorsByStudent);if(error)errors.set(studentId,error);else errors.delete(studentId);return loadState(errors,students.length)})
  },[students.length])

  const refreshMeetings=useCallback(async(studentId:string,signal?:AbortSignal)=>{const student=students.find(item=>item.id===studentId);if(!student)return null;try{const next=(await allMeetings(student.id,signal)).map(meetingFromApi);applyMeetings(studentId,next);updateResourceState('meetings',studentId);return next}catch(requestError){if(shouldEvictLearningRecords(requestError))applyMeetings(studentId,[]);updateResourceState('meetings',studentId,requestError);throw requestError}},[applyMeetings,students,updateResourceState])
  const refreshHomeworks=useCallback(async(studentId:string,signal?:AbortSignal)=>{const student=students.find(item=>item.id===studentId);if(!student)return null;try{const strategy=strategies[studentId];const next=strategy?(await allHomeworks(strategy.id,signal)).map(item=>homeworkFromApi(item,studentId)):[];applyHomeworks(studentId,next);updateResourceState('homeworks',studentId);return next}catch(requestError){if(shouldEvictLearningRecords(requestError))applyHomeworks(studentId,[]);updateResourceState('homeworks',studentId,requestError);throw requestError}},[applyHomeworks,strategies,students,updateResourceState])
  const refreshStudent=useCallback(async(studentId:string,signal?:AbortSignal)=>{const results=await Promise.allSettled([refreshMeetings(studentId,signal),refreshHomeworks(studentId,signal)]);if(results.every(result=>result.status==='rejected'))throw (results[0] as PromiseRejectedResult).reason;return results},[refreshHomeworks,refreshMeetings])
  const conflictRefresh=useCallback(async<T,>(studentId:string,request:()=>Promise<T>,refresh:(studentId:string)=>Promise<unknown>)=>{try{return await request()}catch(requestError){if(requestError instanceof ApiError&&[403,404,409].includes(requestError.status))await refresh(studentId).catch(()=>undefined);throw requestError}},[])

  const createMeeting=useCallback(async(studentId:string,payload:MeetingCreateRequest)=>{const next=meetingFromApi(await meetingsApi.create(studentId,payload));setMeetings(items=>replaceById(items,next));return next},[])
  const updateMeeting=useCallback(async(meeting:Meeting,payload:Omit<MeetingUpdateRequest,'expected_version'>)=>{const next=meetingFromApi(await conflictRefresh(meeting.studentId,()=>meetingsApi.update(meeting.id,{...payload,expected_version:meeting.version??1}),refreshMeetings));setMeetings(items=>replaceById(items,next));return next},[conflictRefresh,refreshMeetings])
  const setMeetingArchived=useCallback(async(meeting:Meeting,archived:boolean)=>{const wire=await conflictRefresh(meeting.studentId,()=>archived?meetingsApi.archive(meeting.id,meeting.version??1):meetingsApi.restore(meeting.id,meeting.version??1),refreshMeetings);const next=meetingFromApi(wire);setMeetings(items=>replaceById(items,next));return next},[conflictRefresh,refreshMeetings])

  const createHomework=useCallback(async(studentId:string,payload:HomeworkCreateRequest)=>{const strategy=strategies[studentId];if(!strategy)throw new ApiError(422,'strategy_required','Strategy is required');const next=homeworkFromApi(await homeworksApi.create(strategy.id,payload),studentId);setHomeworks(items=>replaceById(items,next));return next},[strategies])
  const updateHomework=useCallback(async(homework:Homework,payload:Omit<HomeworkUpdateRequest,'expected_version'>)=>{const next=homeworkFromApi(await conflictRefresh(homework.studentId,()=>homeworksApi.update(homework.id,{...payload,expected_version:homework.version??1}),refreshHomeworks),homework.studentId,[]);setHomeworks(items=>replaceById(items,next));return next},[conflictRefresh,refreshHomeworks])
  const transitionHomework=useCallback(async(homework:Homework,payload:Omit<HomeworkTransitionRequest,'expected_version'>)=>{let wire:HomeworkRead;try{wire=await conflictRefresh(homework.studentId,()=>homeworksApi.transition(homework.id,{...payload,expected_version:homework.version??1}),refreshHomeworks)}catch(requestError){if(requestError instanceof ApiError&&requestError.status===409)await refreshStrategyStudent(homework.studentId).catch(()=>undefined);throw requestError}const next=homeworkFromApi(wire,homework.studentId,[]);setHomeworks(items=>replaceById(items,next));try{await refreshStrategyStudent(homework.studentId);updateResourceState('homeworks',homework.studentId)}catch{updateResourceState('homeworks',homework.studentId,new Error('strategy_refresh_failed'))}return next},[conflictRefresh,refreshHomeworks,refreshStrategyStudent,updateResourceState])
  const setHomeworkArchived=useCallback(async(homework:Homework,archived:boolean)=>{const wire=await conflictRefresh(homework.studentId,()=>archived?homeworksApi.archive(homework.id,homework.version??1):homeworksApi.restore(homework.id,homework.version??1),refreshHomeworks);const next=homeworkFromApi(wire,homework.studentId,homework.history?.map(item=>({id:item.id,homework_id:homework.id,event_type:item.eventType,from_status:item.fromStatus,to_status:item.toStatus,details:{},created_at:item.createdAt}))??[]);setHomeworks(items=>replaceById(items,next));return next},[conflictRefresh,refreshHomeworks])
  const loadHomeworkHistory=useCallback(async(homework:Homework)=>{const history=[] as Awaited<ReturnType<typeof homeworksApi.history>>['items'];let cursor:string|undefined;do{const page=await homeworksApi.history(homework.id,cursor);history.push(...page.items);cursor=page.next_cursor??undefined}while(cursor);const fresh=await homeworksApi.get(homework.id);const next=homeworkFromApi(fresh,homework.studentId,history);setHomeworks(items=>replaceById(items,next));return next},[])

  return {meetings,homeworks,meetingStatus:meetingState.status,meetingError:meetingState.error,meetingErrorsByStudent:meetingState.errorsByStudent,meetingPartialErrorCount:meetingState.errorsByStudent.size,homeworkStatus:homeworkState.status,homeworkError:homeworkState.error,homeworkErrorsByStudent:homeworkState.errorsByStudent,homeworkPartialErrorCount:homeworkState.errorsByStudent.size,load,loadMeetings,loadHomeworks,refreshMeetings,refreshHomeworks,refreshStudent,evictStudent,createMeeting,updateMeeting,setMeetingArchived,createHomework,updateHomework,transitionHomework,setHomeworkArchived,loadHomeworkHistory}
}
