import { useEffect, useState } from 'react'
import { KeyIcon as Key, SignOutIcon as SignOut } from '@phosphor-icons/react'
import type { CurrentUser } from '../api/contracts'
import { authApi } from '../api/auth'
import { accountErrorMessage, userInitial, userLabel } from './accountState'

export default function MyAccountPage({ user, groupCount, onSaved, onChangePassword, onLogout }: {
  user: CurrentUser
  groupCount: number
  onSaved: () => Promise<void>
  onChangePassword: () => void
  onLogout: () => void
}) {
  const [name, setName] = useState(user.display_name ?? '')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  useEffect(() => setName(user.display_name ?? ''), [user.display_name])
  const unchanged = name.trim() === (user.display_name ?? '')

  const save = async () => {
    if (pending || unchanged) return
    setPending(true); setMessage(null)
    try { await authApi.updateMe(name.trim()); await onSaved(); setMessage({ kind: 'success', text: 'Имя сохранено' }) }
    catch (error) { setMessage({ kind: 'error', text: accountErrorMessage(error) }) }
    finally { setPending(false) }
  }

  return <div className="my-account">
    <div className="page-heading"><div><h1>Мой профиль</h1><p>Как вас видят коллеги и как вы входите в «Кураторскую»</p></div></div>
    <section className="surface my-account-card">
      <div className="my-account-identity"><span className="account-detail-avatar">{userInitial(user)}</span><div><h2>{userLabel(user)}</h2><p>{user.is_owner ? 'Владелец' : 'Куратор'} · логин {user.login}</p></div></div>
      <form className="my-account-form" onSubmit={event => { event.preventDefault(); void save() }}>
        <label className="field"><span>Имя</span><input maxLength={120} value={name} onChange={event => { setName(event.target.value); setMessage(null) }} placeholder="Имя или имя и фамилия"/><small>Показывается в шапке и в списке кураторов. Можно оставить пустым — тогда будет виден логин</small></label>
        <button className="btn dark" disabled={pending || unchanged}>{pending ? 'Сохраняем…' : 'Сохранить'}</button>
        {message && <p className={message.kind === 'error' ? 'dialog-error' : 'my-account-success'} role={message.kind === 'error' ? 'alert' : 'status'}>{message.text}</p>}
      </form>
      <div className="account-facts"><div><span>Роль</span><strong>{user.is_owner ? 'Владелец' : 'Куратор'}</strong></div><div><span>Мои группы</span><strong>{groupCount}</strong></div><div><span>Логин</span><strong>{user.login}</strong></div></div>
      <div className="my-account-actions"><button className="btn secondary" onClick={onChangePassword}><Key size={16}/> Сменить пароль</button><button className="btn secondary" onClick={onLogout}><SignOut size={16}/> Выйти</button></div>
    </section>
  </div>
}
