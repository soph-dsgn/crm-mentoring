import { useCallback, useEffect, useRef, useState } from 'react'
import type { GroupStudentRead, HomeworkRead, StrategyRead } from '../api/contracts'
import { ApiError } from '../api/http'
import { studentApi } from '../api/student'
import { studentFromApi } from '../api/mappers'
import { homeworkFromApi, meetingFromApi } from '../learning/learningState'
import { sectionFromApi, taskFromApi } from '../strategies/strategyState'
import type { Homework, Meeting, StrategySection, StrategyTask, Student } from '../types'
import { studentHomeworkAction } from './studentState'

type LoadStatus='loading'|'ready'|'error'
type ResourceState={status:LoadStatus;error:unknown}
const loadingState:ResourceState={status:'loading',error:null}
const replaceById=<T extends{id:string}>(items:T[],next:T)=>items.some(item=>item.id===next.id)?items.map(item=>item.id===next.id?next:item):[...items,next]
const aborted=(error:unknown)=>error instanceof DOMException&&error.name==='AbortError'

async function allMeetings(studentId:string,signal?:AbortSignal){const items=[] as Awaited<ReturnType<typeof studentApi.listMeetings>>['items'];let cursor:string|undefined;do{const page=await studentApi.listMeetings(studentId,cursor,true,signal);items.push(...page.items);cursor=page.next_cursor??undefined}while(cursor);return items}
async function allHomeworks(strategyId:string,signal?:AbortSignal){const items=[] as HomeworkRead[];let cursor:string|undefined;do{const page=await studentApi.listHomeworks(strategyId,cursor,true,signal);items.push(...page.items);cursor=page.next_cursor??undefined}while(cursor);return items.filter(item=>item.status!=='draft')}

export function useStudentWorkspace(studentId:string){
  const [profile,setProfile]=useState<Student|null>(null)
  const [group,setGroup]=useState<GroupStudentRead|null>(null)
  const [strategy,setStrategy]=useState<StrategyRead|null>(null)
  const [sections,setSections]=useState<StrategySection[]>([])
  const [tasks,setTasks]=useState<StrategyTask[]>([])
  const [meetings,setMeetings]=useState<Meeting[]>([])
  const [homeworks,setHomeworks]=useState<Homework[]>([])
  const [profileState,setProfileState]=useState<ResourceState>(loadingState)
  const [strategyState,setStrategyState]=useState<ResourceState>(loadingState)
  const [meetingState,setMeetingState]=useState<ResourceState>(loadingState)
  const [homeworkState,setHomeworkState]=useState<ResourceState>(loadingState)
  const [pendingHomeworks,setPendingHomeworks]=useState<Set<string>>(()=>new Set())
  const pendingRef=useRef(new Set<string>())

  const loadMeetings=useCallback(async(signal?:AbortSignal)=>{
    setMeetingState(current=>({status:current.status==='ready'?'ready':'loading',error:null}))
    try{const wires=await allMeetings(studentId,signal);if(signal?.aborted)return;setMeetings(wires.map(meetingFromApi));setMeetingState({status:'ready',error:null})}
    catch(error){if(aborted(error))return;setMeetingState({status:'error',error});throw error}
  },[studentId])

  const loadHomeworks=useCallback(async(strategyId:string,signal?:AbortSignal)=>{
    setHomeworkState(current=>({status:current.status==='ready'?'ready':'loading',error:null}))
    try{const wires=await allHomeworks(strategyId,signal);if(signal?.aborted)return;setHomeworks(current=>wires.map(wire=>homeworkFromApi(wire,studentId,current.find(item=>item.id===wire.id)?.history?.map(item=>({id:item.id,homework_id:wire.id,event_type:item.eventType,from_status:item.fromStatus,to_status:item.toStatus,details:{},created_at:item.createdAt}))??[])));setHomeworkState({status:'ready',error:null})}
    catch(error){if(aborted(error))return;setHomeworkState({status:'error',error});throw error}
  },[studentId])

  const loadStrategy=useCallback(async(currentProfile:Student,signal?:AbortSignal)=>{
    setStrategyState(current=>({status:current.status==='ready'?'ready':'loading',error:null}))
    try{
      let nextStrategy:StrategyRead
      try{nextStrategy=await studentApi.getStrategy(studentId,signal)}
      catch(error){if(error instanceof ApiError&&error.status===404){setStrategy(null);setSections([]);setTasks([]);setHomeworks([]);setStrategyState({status:'ready',error:null});setHomeworkState({status:'ready',error:null});return}throw error}
      if(signal?.aborted)return
      setStrategy(nextStrategy)
      const homeworkPromise=loadHomeworks(nextStrategy.id,signal).catch(()=>undefined)
      const sectionWires=await studentApi.listSections(nextStrategy.id,signal)
      const taskPages=await Promise.all(sectionWires.map(section=>studentApi.listTasks(section.id,signal)))
      if(signal?.aborted)return
      setSections(sectionWires.map(section=>sectionFromApi(section,studentId)))
      setTasks(taskPages.flat().map(task=>taskFromApi(task,studentId,null,currentProfile.stage)))
      setStrategyState({status:'ready',error:null})
      await homeworkPromise
    }catch(error){if(aborted(error))return;setStrategyState({status:'error',error});setHomeworkState(current=>current.status==='loading'?{status:'error',error}:current);throw error}
  },[loadHomeworks,studentId])

  const loadProfile=useCallback(async(signal?:AbortSignal)=>{
    setProfileState({status:'loading',error:null});setProfile(null);setGroup(null)
    try{
      const wire=await studentApi.getProfile(studentId,signal)
      const currentProfile=studentFromApi(wire)
      const currentGroup=await studentApi.getGroup(wire.group_id,signal)
      if(signal?.aborted)return
      setProfile(currentProfile);setGroup(currentGroup);setProfileState({status:'ready',error:null})
      await Promise.allSettled([loadStrategy(currentProfile,signal),loadMeetings(signal)])
    }catch(error){if(aborted(error))return;setProfile(null);setGroup(null);setProfileState({status:'error',error});throw error}
  },[loadMeetings,loadStrategy,studentId])

  useEffect(()=>{const controller=new AbortController();void loadProfile(controller.signal).catch(()=>undefined);return()=>controller.abort()},[loadProfile])

  const loadHomeworkHistory=useCallback(async(homeworkId:string)=>{
    const history=[] as Awaited<ReturnType<typeof studentApi.homeworkHistory>>['items'];let cursor:string|undefined
    do{const page=await studentApi.homeworkHistory(homeworkId,cursor);history.push(...page.items);cursor=page.next_cursor??undefined}while(cursor)
    const fresh=await studentApi.getHomework(homeworkId)
    const next=homeworkFromApi(fresh,studentId,history)
    setHomeworks(items=>replaceById(items,next));return next
  },[studentId])

  const submitHomework=useCallback(async(homework:Homework,submissionText:string,workUrl:string)=>{
    if(!studentHomeworkAction(homework)||pendingRef.current.has(homework.id))return null
    pendingRef.current.add(homework.id);setPendingHomeworks(new Set(pendingRef.current))
    try{
      const submissionLinks:Record<string,string>=workUrl.trim()?{work:workUrl.trim()}:{}
      const wire=await studentApi.submitHomework(homework.id,{expected_version:homework.version??1,status:'submitted',submission_text:submissionText.trim(),submission_links:submissionLinks})
      const next=homeworkFromApi(wire,studentId,homework.history?.map(item=>({id:item.id,homework_id:homework.id,event_type:item.eventType,from_status:item.fromStatus,to_status:item.toStatus,details:{},created_at:item.createdAt}))??[])
      setHomeworks(items=>replaceById(items,next))
      await Promise.allSettled([loadHomeworkHistory(homework.id),profile?loadStrategy(profile):Promise.resolve()])
      return next
    }catch(error){
      if(error instanceof ApiError&&error.status===409){try{const fresh=await studentApi.getHomework(homework.id);setHomeworks(items=>replaceById(items,homeworkFromApi(fresh,studentId,homework.history?.map(item=>({id:item.id,homework_id:homework.id,event_type:item.eventType,from_status:item.fromStatus,to_status:item.toStatus,details:{},created_at:item.createdAt}))??[])))}catch{/* The original safe conflict remains visible. */}}
      throw error
    }finally{pendingRef.current.delete(homework.id);setPendingHomeworks(new Set(pendingRef.current))}
  },[loadHomeworkHistory,loadStrategy,profile,studentId])

  return {profile,group,strategy,sections,tasks,meetings,homeworks,profileState,strategyState,meetingState,homeworkState,pendingHomeworks,reload:loadProfile,retryStrategy:()=>profile?loadStrategy(profile):Promise.resolve(),retryMeetings:loadMeetings,retryHomeworks:()=>strategy?loadHomeworks(strategy.id):Promise.resolve(),loadHomeworkHistory,submitHomework}
}
