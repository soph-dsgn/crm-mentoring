import { useCallback, useEffect, useId, useReducer, useRef, useState } from 'react'
import {
  ArrowClockwiseIcon as ArrowClockwise,
  ArrowsLeftRightIcon as ArrowsLeftRight,
  CheckIcon as Check,
  CopyIcon as Copy,
  CrownIcon as Crown,
  ShieldCheckIcon as ShieldCheck,
  UserPlusIcon as UserPlus,
  UsersThreeIcon as UsersThree,
} from '@phosphor-icons/react'
import type { CurrentUser, CuratorSummary, GroupSummary, SafeUser, TemporaryCredentialResponse } from '../api/contracts'
import { ApiError, usersApi } from '../api/users'
import { copyText } from '../clipboard'
import { ConfirmDialog, Dialog } from '../Dialogs'
import Select from '../Select'
import {
  accountErrorMessage,
  canManageAccounts,
  temporaryCredentialReducer,
  type TemporaryCredential,
} from './accountState'

type LoadState = 'loading' | 'ready' | 'error'

const toSummary = (user: SafeUser): CuratorSummary => ({
  id: user.id,
  login: user.login,
  role: user.role,
  is_owner: user.is_owner,
  is_active: user.is_active,
})

const formatDate = (value: string | null) => value
  ? new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
  : '—'

function AccountPermissionState() {
  return <div className="profile-empty account-permission" role="status">
    <ShieldCheck size={30}/>
    <strong>Нет доступа</strong>
    <p>Управление аккаунтами доступно только владельцу «Кураторской»</p>
  </div>
}

export function TemporaryCredentialDialog({ credential, onClose }: { credential: TemporaryCredential | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')
  useEffect(() => { setCopied(false); setCopyError('') }, [credential])
  const copy = async () => {
    if (!credential) return
    try {
      await copyText(`Логин: ${credential.login}\nВременный пароль: ${credential.temporaryPassword}`)
      setCopied(true); setCopyError('')
    } catch {
      setCopyError('Не удалось скопировать. Выделите данные вручную')
    }
  }
  return <Dialog
    open={Boolean(credential)}
    title="Временные данные для входа"
    description="Пароль показывается только сейчас. После закрытия восстановить его нельзя"
    onClose={onClose}
  >
    {credential&&<div className="credential-content">
      <div><span>Логин</span><code>{credential.login}</code></div>
      <div><span>Временный пароль</span><code>{credential.temporaryPassword}</code></div>
      <p>Передайте данные куратору безопасным способом. При первом входе потребуется создать новый пароль</p>
      {copyError&&<p className="dialog-error" role="alert">{copyError}</p>}
      <div className="dialog-actions">
        <button type="button" className="btn secondary" onClick={() => void copy()}>{copied?<Check size={16}/>:<Copy size={16}/>} {copied?'Скопировано':'Скопировать'}</button>
        <button type="button" className="btn primary" onClick={onClose}>Я сохранила данные</button>
      </div>
    </div>}
  </Dialog>
}

function CreateCuratorDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (response: TemporaryCredentialResponse) => void }) {
  const inputId = useId()
  const [login, setLogin] = useState('')
  const [pending, setPending] = useState(false)
  const pendingRef = useRef(false)
  const [error, setError] = useState('')
  useEffect(() => { if (open) { pendingRef.current=false; setLogin(''); setPending(false); setError('') } }, [open])
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (pendingRef.current) return
    const normalized = login.trim()
    if (!normalized) { setError('Введите логин'); return }
    pendingRef.current=true; setPending(true); setError('')
    try {
      onCreated(await usersApi.createCurator(normalized))
      onClose()
    } catch (caught) {
      setError(accountErrorMessage(caught))
    } finally {
      pendingRef.current=false
      setPending(false)
    }
  }
  return <Dialog open={open} title="Новый куратор" description="Аккаунт получит временный пароль для первого входа" onClose={onClose} dismissible={!pending}>
    <form className="form" onSubmit={event => void submit(event)}>
      <label className="field" htmlFor={inputId}><span>Логин</span><input id={inputId} autoFocus autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" value={login} onChange={event => setLogin(event.target.value)} placeholder="например, curator.name"/></label>
      {error&&<p className="dialog-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="btn secondary" disabled={pending} onClick={onClose}>Отмена</button><button type="submit" className="btn primary" disabled={pending}>{pending?'Создаём…':'Создать аккаунт'}</button></div>
    </form>
  </Dialog>
}

function CuratorSelectionDialog({ open, title, description, confirmLabel, curators, onClose, onConfirm }: { open: boolean; title: string; description: string; confirmLabel: string; curators: CuratorSummary[]; onClose: () => void; onConfirm: (curatorId: string) => Promise<void> }) {
  const [curatorId, setCuratorId] = useState('')
  const [pending, setPending] = useState(false)
  const pendingRef = useRef(false)
  const [error, setError] = useState('')
  useEffect(() => { if (open) { pendingRef.current=false; setCuratorId(curators[0]?.id ?? ''); setPending(false); setError('') } }, [curators, open])
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!curatorId||pendingRef.current) return
    pendingRef.current=true; setPending(true); setError('')
    try { await onConfirm(curatorId); onClose() }
    catch (caught) { setError(accountErrorMessage(caught)) }
    finally { pendingRef.current=false; setPending(false) }
  }
  return <Dialog open={open} title={title} description={description} onClose={onClose} dismissible={!pending}>
    <form className="form" onSubmit={event => void submit(event)}>
      <label className="field"><span>Новый куратор</span><Select aria-label="Новый куратор" value={curatorId} disabled={pending||!curators.length} onChange={event => setCuratorId(event.target.value)}>{curators.map(curator=><option key={curator.id} value={curator.id}>{curator.login}</option>)}</Select></label>
      {!curators.length&&<p className="account-hint">Нет другого активного куратора. Сначала создайте аккаунт</p>}
      {error&&<p className="dialog-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="btn secondary" disabled={pending} onClick={onClose}>Отмена</button><button type="submit" className="btn primary" disabled={pending||!curatorId}>{pending?'Сохраняем…':confirmLabel}</button></div>
    </form>
  </Dialog>
}

function OwnerAccountAdministration({ currentUser, onRefreshUser }: { currentUser: CurrentUser; onRefreshUser: () => Promise<void> }) {
  const [curators, setCurators] = useState<CuratorSummary[]>([])
  const [listState, setListState] = useState<LoadState>('loading')
  const [listError, setListError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SafeUser | null>(null)
  const [groups, setGroups] = useState<GroupSummary[]>([])
  const [detailState, setDetailState] = useState<LoadState>('loading')
  const [detailError, setDetailError] = useState('')
  const [detailVersion, setDetailVersion] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [credential, dispatchCredential] = useReducer(temporaryCredentialReducer, null)
  const [confirmAction, setConfirmAction] = useState<'deactivate' | 'transfer' | null>(null)
  const [offboardOpen, setOffboardOpen] = useState(false)
  const [reassignGroup, setReassignGroup] = useState<GroupSummary | null>(null)

  const loadCurators = useCallback(async (signal?: AbortSignal) => {
    setListState('loading'); setListError('')
    try {
      const result = await usersApi.listCurators(signal)
      setCurators(result)
      setSelectedId(current => current && result.some(item => item.id === current) ? current : result.find(item => item.id === currentUser.id)?.id ?? result[0]?.id ?? null)
      setListState('ready')
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return
      setListError(accountErrorMessage(caught)); setListState('error')
    }
  }, [currentUser.id])

  useEffect(() => {
    const controller = new AbortController()
    void loadCurators(controller.signal)
    return () => controller.abort()
  }, [loadCurators])

  useEffect(() => {
    if (!selectedId) { setDetail(null); setGroups([]); setDetailState('ready'); return }
    const controller = new AbortController()
    setDetailState('loading'); setDetailError('')
    void Promise.all([usersApi.getCurator(selectedId, controller.signal), usersApi.listCuratorGroups(selectedId, controller.signal)])
      .then(([user, assignedGroups]) => { setDetail(user); setGroups(assignedGroups); setDetailState('ready') })
      .catch(caught => {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        setDetailError(accountErrorMessage(caught)); setDetailState('error')
      })
    return () => controller.abort()
  }, [detailVersion, selectedId])

  const refreshDetail = () => setDetailVersion(value => value + 1)
  const updateCurator = (user: SafeUser) => {
    setCurators(current => current.map(item => item.id === user.id ? toSummary(user) : item))
    setDetail(user)
  }
  const activeSuccessors = curators.filter(curator => curator.is_active && curator.id !== detail?.id)

  const handleCreated = (response: TemporaryCredentialResponse) => {
    setCurators(current => [...current, toSummary(response.user)])
    setSelectedId(response.user.id)
    dispatchCredential({ type: 'show', credential: { login: response.user.login, temporaryPassword: response.temporary_password } })
  }

  const deactivate = async () => {
    if (!detail) return
    updateCurator(await usersApi.deactivateCurator(detail.id))
  }

  const transferOwnership = async () => {
    if (!detail) return
    await usersApi.transferOwnership(detail.id)
    try { await onRefreshUser() }
    catch { throw new ApiError(0, 'session_refresh_failed', 'Session refresh failed') }
  }

  const offboard = async (successorId: string) => {
    if (!detail) return
    const response = await usersApi.offboardCurator(detail.id, successorId)
    updateCurator(response.user)
    setGroups([])
  }

  const reassign = async (curatorId: string) => {
    if (!reassignGroup) return
    await usersApi.reassignGroup(reassignGroup.id, curatorId)
    setGroups(current => current.filter(group => group.id !== reassignGroup.id))
  }

  return <div className="accounts-page">
    <div className="page-heading editorial-page-head account-page-head"><div><div className="eyebrow">Доступ и ответственность</div><h1>Аккаунты кураторов</h1><p>Создание аккаунтов, назначение групп и передача прав владельца</p></div><button className="btn dark" onClick={() => setCreateOpen(true)}><UserPlus size={18}/> Новый куратор</button></div>
    {listState==='loading'&&<div className="account-state" role="status"><span className="account-spinner"/>Загружаем аккаунты…</div>}
    {listState==='error'&&<div className="account-state account-state-error" role="alert"><strong>Не удалось загрузить аккаунты</strong><p>{listError}</p><button className="btn secondary" onClick={() => void loadCurators()}><ArrowClockwise size={16}/> Повторить</button></div>}
    {listState==='ready'&&!curators.length&&<div className="profile-empty"><UsersThree size={30}/><strong>Аккаунтов кураторов пока нет</strong><p>Создайте первый аккаунт, чтобы назначить ответственного за группы</p></div>}
    {listState==='ready'&&curators.length>0&&<div className="account-layout">
      <aside className="account-list" aria-label="Кураторы">{curators.map(curator=><button key={curator.id} className={selectedId===curator.id?'selected':''} aria-current={selectedId===curator.id?'true':undefined} onClick={() => setSelectedId(curator.id)}><span className="account-avatar">{curator.login.slice(0,1).toUpperCase()}</span><span><strong>{curator.login}</strong><small>{curator.is_owner?'Владелец':curator.is_active?'Куратор':'Доступ закрыт'}</small></span>{curator.is_owner&&<Crown size={15}/>}<i className={`account-status ${curator.is_active?'active':'inactive'}`} aria-label={curator.is_active?'Активен':'Неактивен'}/></button>)}</aside>
      <section className="account-detail" aria-live="polite">
        {detailState==='loading'&&<div className="account-state" role="status"><span className="account-spinner"/>Загружаем данные…</div>}
        {detailState==='error'&&<div className="account-state account-state-error" role="alert"><strong>Не удалось открыть аккаунт</strong><p>{detailError}</p><button className="btn secondary" onClick={refreshDetail}><ArrowClockwise size={16}/> Повторить</button></div>}
        {detailState==='ready'&&detail&&<>
          <div className="account-detail-head"><div><span className="account-detail-avatar">{detail.login.slice(0,1).toUpperCase()}</span><div><div className="account-detail-badges"><span className={`pill ${detail.is_active?'':'account-inactive'}`}>{detail.is_active?'Активен':'Неактивен'}</span>{detail.is_owner&&<span className="pill owner">Владелец</span>}{detail.must_change_password&&<span className="pill light">Ожидает смены пароля</span>}</div><h2>{detail.login}</h2><p>Создан {formatDate(detail.created_at)}{detail.deactivated_at?` · доступ закрыт ${formatDate(detail.deactivated_at)}`:''}</p></div></div>
            {detail.is_active&&detail.id!==currentUser.id&&<div className="account-detail-actions">{groups.length===0?<button className="btn danger" onClick={() => setConfirmAction('deactivate')}>Деактивировать</button>:<button className="btn secondary" onClick={() => setOffboardOpen(true)}><ArrowsLeftRight size={16}/> Передать группы и отключить</button>}{!detail.is_owner&&<button className="btn dark" onClick={() => setConfirmAction('transfer')}><Crown size={16}/> Передать права владельца</button>}</div>}
          </div>
          <div className="account-facts"><div><span>Роль</span><strong>{detail.is_owner?'Владелец':'Куратор'}</strong></div><div><span>Группы</span><strong>{groups.length}</strong></div><div><span>Доступ</span><strong>{detail.is_active?'Разрешён':'Закрыт'}</strong></div></div>
          <div className="account-groups-head"><div><h3>Назначенные группы</h3><p>Передача меняет ответственного на сервере и не затрагивает учебную историю</p></div></div>
          {groups.length?<div className="account-groups">{groups.map(group=><div key={group.id}><span><strong>{group.name}</strong><small>{group.status==='active'?'Активная':group.status==='backlog'?'Бэклог':group.status==='completed'?'Завершена':'В архиве'}</small></span>{detail.is_active&&activeSuccessors.length>0&&<button className="btn secondary" onClick={() => setReassignGroup(group)}>Передать</button>}</div>)}</div>:<div className="account-empty-groups"><UsersThree size={25}/><strong>Назначенных групп нет</strong><p>Куратор может получить группу при создании или передаче</p></div>}
        </>}
      </section>
    </div>}
    <CreateCuratorDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={handleCreated}/>
    <TemporaryCredentialDialog credential={credential} onClose={() => dispatchCredential({ type: 'dismiss' })}/>
    <ConfirmDialog open={confirmAction==='deactivate'} title="Деактивировать куратора?" description={`Аккаунт ${detail?.login??''} потеряет доступ, а активные сессии будут завершены`} confirmLabel="Деактивировать" danger getErrorMessage={accountErrorMessage} onConfirm={deactivate} onClose={() => setConfirmAction(null)}/>
    <ConfirmDialog open={confirmAction==='transfer'} title="Передать права владельца?" description={`${detail?.login??'Выбранный куратор'} получит полный доступ. Ваш аккаунт останется активным куратором без owner-действий`} confirmLabel="Передать права" getErrorMessage={accountErrorMessage} onConfirm={transferOwnership} onClose={() => setConfirmAction(null)}/>
    <CuratorSelectionDialog open={offboardOpen} title="Передать группы и отключить" description={`Все группы куратора ${detail?.login??''} перейдут выбранному куратору, затем аккаунт будет деактивирован`} confirmLabel="Передать и отключить" curators={activeSuccessors} onClose={() => setOffboardOpen(false)} onConfirm={offboard}/>
    <CuratorSelectionDialog open={Boolean(reassignGroup)} title="Передать группу" description={`Выберите нового ответственного за группу «${reassignGroup?.name??''}»`} confirmLabel="Передать группу" curators={activeSuccessors} onClose={() => setReassignGroup(null)} onConfirm={reassign}/>
  </div>
}

export default function AccountAdminPage({ currentUser, onRefreshUser }: { currentUser: CurrentUser; onRefreshUser: () => Promise<void> }) {
  if (!canManageAccounts(currentUser)) return <AccountPermissionState/>
  return <OwnerAccountAdministration currentUser={currentUser} onRefreshUser={onRefreshUser}/>
}
