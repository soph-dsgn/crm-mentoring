import { useEffect, useRef, useState } from 'react'
import { CaretDownIcon as CaretDown, DatabaseIcon as Database, IdentificationBadgeIcon as IdentificationBadge, SignOutIcon as SignOut, UserCircleIcon as UserCircle } from '@phosphor-icons/react'
import type { CurrentUser } from '../api/contracts'
import { userInitial, userLabel } from './accountState'

export type AccountMenuTarget = 'profile' | 'accounts' | 'migration'

export default function AccountMenu({ user, onOpen, onLogout, logoutPending }: {
  user: CurrentUser
  onOpen: (target: AccountMenuTarget) => void
  onLogout: () => void
  logoutPending: boolean
}) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape' : !root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close) }
  }, [open])
  const choose = (target: AccountMenuTarget) => { setOpen(false); onOpen(target) }
  const role = user.is_owner ? 'Владелец' : 'Куратор'

  return <div className="account-menu" ref={root}>
    <button className="account-menu-trigger" aria-haspopup="menu" aria-expanded={open} aria-label={`Аккаунт: ${userLabel(user)}`} onClick={() => setOpen(value => !value)}>
      <span className="account-menu-avatar" aria-hidden="true">{userInitial(user)}</span>
      <span className="account-menu-name"><strong>{userLabel(user)}</strong><small>{role}</small></span>
      <CaretDown size={14}/>
    </button>
    {open && <div className="account-menu-popover" role="menu">
      <button role="menuitem" onClick={() => choose('profile')}><UserCircle size={18}/> Мой профиль</button>
      {user.is_owner && <>
        <button role="menuitem" onClick={() => choose('accounts')}><IdentificationBadge size={18}/> Аккаунты кураторов</button>
        <button role="menuitem" onClick={() => choose('migration')}><Database size={18}/> Перенос данных</button>
      </>}
      <hr/>
      <button role="menuitem" disabled={logoutPending} onClick={() => { setOpen(false); onLogout() }}><SignOut size={18}/> {logoutPending ? 'Выходим…' : 'Выйти'}</button>
    </div>}
  </div>
}
