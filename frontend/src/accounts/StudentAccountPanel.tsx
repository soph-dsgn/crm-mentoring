import { useCallback, useEffect, useId, useReducer, useRef, useState } from 'react'
import { ArrowClockwiseIcon as ArrowClockwise, KeyIcon as Key, ShieldCheckIcon as ShieldCheck, UserPlusIcon as UserPlus } from '@phosphor-icons/react'
import type { StudentAccountResponse } from '../api/contracts'
import { ApiError, usersApi } from '../api/users'
import { ConfirmDialog, Dialog } from '../Dialogs'
import { TemporaryCredentialDialog } from './AccountAdminPage'
import { accountErrorMessage, temporaryCredentialReducer } from './accountState'
import { studentPortalUrl } from '../student/studentState'

function CreateStudentAccountDialog({ open, studentId, onClose, onCreated }: { open: boolean; studentId: string; onClose: () => void; onCreated: (response: Awaited<ReturnType<typeof usersApi.createStudentAccount>>) => void }) {
  const inputId = useId()
  const [login, setLogin] = useState('')
  const [pending, setPending] = useState(false)
  const pendingRef = useRef(false)
  const [error, setError] = useState('')
  useEffect(() => { if (open) { setLogin(''); setPending(false); pendingRef.current=false; setError('') } }, [open])
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const normalized = login.trim()
    if (!normalized) { setError('Введите логин'); return }
    if (pendingRef.current) return
    pendingRef.current=true; setPending(true); setError('')
    try { onCreated(await usersApi.createStudentAccount(studentId, normalized)) }
    catch (caught) { setError(accountErrorMessage(caught)) }
    finally { pendingRef.current=false; setPending(false) }
  }
  return <Dialog open={open} title="Аккаунт ученицы" description="Логин и временный пароль появятся только после создания" onClose={onClose} dismissible={!pending}>
    <form className="form" onSubmit={event=>void submit(event)}>
      <label className="field" htmlFor={inputId}><span>Логин</span><input id={inputId} autoFocus autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" value={login} onChange={event=>setLogin(event.target.value)} placeholder="например, student.name"/></label>
      {error&&<p className="dialog-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="btn secondary" disabled={pending} onClick={onClose}>Отмена</button><button type="submit" className="btn primary" disabled={pending}>{pending?'Создаём…':'Создать аккаунт'}</button></div>
    </form>
  </Dialog>
}

export default function StudentAccountPanel({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const [state, setState] = useState<'loading'|'ready'|'error'>('loading')
  const [account, setAccount] = useState<StudentAccountResponse | null>(null)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [confirm, setConfirm] = useState<'reset'|'deactivate'|'reactivate'|null>(null)
  const [credential, dispatchCredential] = useReducer(temporaryCredentialReducer, null)

  const load = useCallback(async (signal?: AbortSignal) => {
    setState('loading'); setError('')
    try { setAccount(await usersApi.getStudentAccount(studentId, signal)); setState('ready') }
    catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return
      if (caught instanceof ApiError && caught.status === 404) { setAccount(null); setState('ready'); return }
      setError(accountErrorMessage(caught)); setState('error')
    }
  }, [studentId])
  useEffect(() => {
    if (!canManage) return
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [canManage, load])

  if (!canManage) return null
  const created = (response: Awaited<ReturnType<typeof usersApi.createStudentAccount>>) => {
    setAccount({ student_id: response.student_id, user: response.user })
    dispatchCredential({ type:'show', credential:{ login:response.user.login, temporaryPassword:response.temporary_password, entryUrl:studentPortalUrl(studentId,window.location.href) } })
    setCreateOpen(false)
  }
  const reset = async () => {
    if (!account) return
    const response = await usersApi.resetPassword(account.user.id)
    dispatchCredential({ type:'show', credential:{ login:account.user.login, temporaryPassword:response.temporary_password, entryUrl:studentPortalUrl(studentId,window.location.href) } })
    setAccount(current => current ? { ...current, user:{ ...current.user, must_change_password:true } } : current)
  }
  const deactivate = async () => setAccount(await usersApi.deactivateStudentAccount(studentId))
  const reactivate = async () => {
    const response = await usersApi.reactivateStudentAccount(studentId)
    setAccount({ student_id: response.student_id, user: response.user })
    dispatchCredential({ type:'show', credential:{ login:response.user.login, temporaryPassword:response.temporary_password, entryUrl:studentPortalUrl(studentId,window.location.href) } })
  }

  return <section className="surface student-account-panel">
    <div className="section-head"><div><div className="eyebrow">Доступ ученицы</div><h2>Аккаунт</h2></div></div>
    {state==='loading'&&<div className="student-account-state" role="status">Проверяем аккаунт…</div>}
    {state==='error'&&<div className="student-account-state" role="alert"><span>{error}</span><button className="btn secondary" onClick={()=>void load()}><ArrowClockwise size={16}/> Повторить</button></div>}
    {state==='ready'&&!account&&<div className="student-account-empty"><div><UserPlus size={22}/><span><strong>Аккаунт ещё не создан</strong><small>После создания появятся одноразовые данные для первого входа</small></span></div><button className="btn dark" onClick={()=>setCreateOpen(true)}>Создать аккаунт</button></div>}
    {state==='ready'&&account&&<div className="student-account-ready"><div><ShieldCheck size={22}/><span><strong>{account.user.login}</strong><small>{account.user.is_active?(account.user.must_change_password?'Ожидает смены пароля':'Доступ активен'):'Доступ закрыт'}</small></span></div>{account.user.is_active?<div><button className="btn secondary" onClick={()=>setConfirm('reset')}><Key size={16}/> Новый временный пароль</button><button className="btn danger" onClick={()=>setConfirm('deactivate')}>Закрыть доступ</button></div>:<div><button className="btn dark" onClick={()=>setConfirm('reactivate')}>Открыть доступ снова</button></div>}</div>}
    <CreateStudentAccountDialog open={createOpen} studentId={studentId} onClose={()=>setCreateOpen(false)} onCreated={created}/>
    <TemporaryCredentialDialog credential={credential} onClose={()=>dispatchCredential({type:'dismiss'})}/>
    <ConfirmDialog open={confirm==='reset'} title="Выдать новый временный пароль?" description="Все активные сессии ученицы завершатся, при следующем входе потребуется сменить пароль" confirmLabel="Выдать пароль" getErrorMessage={accountErrorMessage} onConfirm={reset} onClose={()=>setConfirm(null)}/>
    <ConfirmDialog open={confirm==='reactivate'} title="Открыть доступ снова?" description="Ученица получит новый временный пароль. Старый пароль больше не подойдёт" confirmLabel="Открыть доступ" getErrorMessage={accountErrorMessage} onConfirm={reactivate} onClose={()=>setConfirm(null)}/>
    <ConfirmDialog open={confirm==='deactivate'} title="Закрыть доступ ученице?" description="Профиль и учебная история сохранятся, активные сессии завершатся. Доступ можно открыть снова" confirmLabel="Закрыть доступ" danger getErrorMessage={accountErrorMessage} onConfirm={deactivate} onClose={()=>setConfirm(null)}/>
  </section>
}
