import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ArrowClockwiseIcon, CheckCircleIcon, EyeIcon, EyeSlashIcon, SignOutIcon, SpinnerGapIcon, WarningCircleIcon } from '@phosphor-icons/react'
import { FlowBackground } from '../FlowBackground'
import { ApiError } from '../api/http'
import type { AnonymousReason } from './authState'
import { validateLogin, validatePasswordChange, type FieldErrors } from './formValidation'

function authErrorMessage(error: unknown, context: 'login' | 'password'): string {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить действие. Попробуйте ещё раз'
  if (error.code === 'connection_error') return 'Нет соединения с сервером. Проверьте интернет и повторите попытку'
  if (error.code === 'rate_limited') return 'Слишком много попыток. Подождите немного и попробуйте снова'
  if (error.code === 'invalid_credentials') return context === 'login' ? 'Логин или пароль не подходят' : 'Временный пароль введён неверно'
  if (error.code === 'password_too_short' || error.status === 422) return 'Проверьте поля и попробуйте снова'
  return 'Сервер не смог выполнить запрос. Попробуйте ещё раз'
}

function AuthLayout({ title, description, children, compact = false }: { title: string; description: string; children: ReactNode; compact?: boolean }) {
  return <main className="auth-shell">
    <FlowBackground className="auth-flow-background"/>
    <section className={`auth-panel ${compact ? 'auth-panel-compact' : ''}`} aria-labelledby="auth-title">
      <div className="auth-brand"><img src="/brand-star.svg" width="30" height="30" alt=""/><span>Кураторская</span></div>
      <div className="auth-heading"><h1 id="auth-title">{title}</h1><p>{description}</p></div>
      {children}
    </section>
  </main>
}

function PasswordField({ id, label, value, onChange, autoComplete, error, autoFocus = false }: { id: string; label: string; value: string; onChange: (value: string) => void; autoComplete: string; error?: string; autoFocus?: boolean }) {
  const [visible, setVisible] = useState(false)
  const errorId = `${id}-error`
  return <div className={`auth-field ${error ? 'has-error' : ''}`}>
    <label htmlFor={id}>{label}</label>
    <span className="auth-input-wrap">
      <input id={id} type={visible ? 'text' : 'password'} value={value} autoFocus={autoFocus} autoComplete={autoComplete} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} onChange={event => onChange(event.target.value)}/>
      <button type="button" className="auth-password-toggle" aria-label={visible ? `Скрыть поле «${label}»` : `Показать поле «${label}»`} aria-pressed={visible} onClick={() => setVisible(current => !current)}>{visible ? <EyeSlashIcon size={19} weight="regular"/> : <EyeIcon size={19} weight="regular"/>}</button>
    </span>
    {error ? <small id={errorId} className="auth-field-error">{error}</small> : null}
  </div>
}

function LogoutAction({ onLogout, disabled = false }: { onLogout: () => Promise<void>; disabled?: boolean }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const logout = async () => {
    setPending(true)
    setError('')
    try {
      await onLogout()
    } catch {
      setError('Не удалось завершить сессию. Проверьте соединение и повторите попытку')
    } finally {
      setPending(false)
    }
  }

  return <>
    <button className="auth-secondary-action" type="button" disabled={pending || disabled} onClick={() => void logout()}><SignOutIcon size={17} weight="regular"/>{pending ? 'Выходим…' : 'Выйти'}</button>
    <div className="auth-form-status" aria-live="polite">{error ? <p className="auth-form-error" role="alert">{error}</p> : null}</div>
  </>
}

export function LoginScreen({ reason, notice, onSubmit }: { reason: AnonymousReason; notice: string | null; onSubmit: (payload: { login: string; password: string }) => Promise<void> }) {
  const loginId = useId()
  const passwordId = useId()
  const pendingRef = useRef(false)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState('')
  const [pending, setPending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (pendingRef.current) return
    const nextErrors = validateLogin(login, password)
    setErrors(nextErrors)
    setFormError('')
    if (Object.keys(nextErrors).length) return
    pendingRef.current = true
    setPending(true)
    try {
      await onSubmit({ login: login.trim(), password })
    } catch (error) {
      setPassword('')
      setFormError(authErrorMessage(error, 'login'))
    } finally {
      pendingRef.current = false
      setPending(false)
    }
  }

  return <AuthLayout title="Вход в Кураторскую" description="Продолжите работу с группами, стратегиями и домашними заданиями">
    {reason === 'expired' ? <div className="auth-message auth-message-warning" role="status"><WarningCircleIcon size={20}/><div><strong>Сессия завершилась</strong><span>Войдите снова, чтобы продолжить работу</span></div></div> : null}
    {reason === 'password_changed' || notice ? <div className="auth-message auth-message-success" role="status"><CheckCircleIcon size={20}/><div><strong>Пароль изменён</strong><span>{notice ?? 'Войдите с новым паролем'}</span></div></div> : null}
    <form className="auth-form" noValidate onSubmit={event => void submit(event)}>
      <label className={`auth-field ${errors.login ? 'has-error' : ''}`} htmlFor={loginId}>
        <span>Логин</span>
        <input id={loginId} value={login} autoFocus autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="username" aria-invalid={Boolean(errors.login)} aria-describedby={errors.login ? `${loginId}-error` : undefined} onChange={event => { setLogin(event.target.value); if (errors.login) setErrors(current => ({ ...current, login: '' })) }}/>
        {errors.login ? <small id={`${loginId}-error`} className="auth-field-error">{errors.login}</small> : null}
      </label>
      <PasswordField id={passwordId} label="Пароль" value={password} onChange={value => { setPassword(value); if (errors.password) setErrors(current => ({ ...current, password: '' })) }} autoComplete="current-password" error={errors.password}/>
      <div className="auth-form-status" aria-live="polite">{formError ? <p className="auth-form-error" role="alert">{formError}</p> : null}</div>
      <button className="btn primary auth-submit" type="submit" disabled={pending}>{pending ? <><SpinnerGapIcon className="auth-spinner" size={18}/>Входим…</> : 'Войти'}</button>
    </form>
  </AuthLayout>
}

export function ChangePasswordScreen({ login, onSubmit, onLogout }: { login: string; onSubmit: (payload: { current_password: string; new_password: string }) => Promise<void>; onLogout: () => Promise<void> }) {
  const currentId = useId()
  const newId = useId()
  const confirmationId = useId()
  const pendingRef = useRef(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState('')
  const [pending, setPending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (pendingRef.current) return
    const nextErrors = validatePasswordChange(currentPassword, newPassword, confirmation)
    setErrors(nextErrors)
    setFormError('')
    if (Object.keys(nextErrors).length) return
    pendingRef.current = true
    setPending(true)
    try {
      await onSubmit({ current_password: currentPassword, new_password: newPassword })
    } catch (error) {
      setCurrentPassword('')
      setFormError(authErrorMessage(error, 'password'))
    } finally {
      pendingRef.current = false
      setPending(false)
    }
  }

  return <AuthLayout title="Создайте новый пароль" description={`Аккаунт ${login} использует временный пароль. Смените его перед началом работы`}>
    <div className="auth-requirements" aria-label="Требования к паролю"><strong>Новый пароль</strong><span className={newPassword.length >= 12 ? 'is-met' : ''}>{newPassword.length >= 12 ? <CheckCircleIcon size={17}/> : <span className="auth-requirement-dot"/>}Минимум 12 символов</span><span className={confirmation && newPassword === confirmation ? 'is-met' : ''}>{confirmation && newPassword === confirmation ? <CheckCircleIcon size={17}/> : <span className="auth-requirement-dot"/>}Одинаковый в обоих полях</span></div>
    <form className="auth-form" noValidate onSubmit={event => void submit(event)}>
      <PasswordField id={currentId} label="Временный пароль" value={currentPassword} onChange={value => { setCurrentPassword(value); if (errors.currentPassword) setErrors(current => ({ ...current, currentPassword: '' })) }} autoComplete="current-password" error={errors.currentPassword} autoFocus/>
      <PasswordField id={newId} label="Новый пароль" value={newPassword} onChange={value => { setNewPassword(value); if (errors.newPassword) setErrors(current => ({ ...current, newPassword: '' })) }} autoComplete="new-password" error={errors.newPassword}/>
      <PasswordField id={confirmationId} label="Повторите новый пароль" value={confirmation} onChange={value => { setConfirmation(value); if (errors.confirmation) setErrors(current => ({ ...current, confirmation: '' })) }} autoComplete="new-password" error={errors.confirmation}/>
      <div className="auth-form-status" aria-live="polite">{formError ? <p className="auth-form-error" role="alert">{formError}</p> : null}</div>
      <button className="btn primary auth-submit" type="submit" disabled={pending}>{pending ? <><SpinnerGapIcon className="auth-spinner" size={18}/>Сохраняем…</> : 'Сохранить новый пароль'}</button>
      <LogoutAction onLogout={onLogout} disabled={pending}/>
    </form>
  </AuthLayout>
}

export function SessionLoadingScreen() {
  return <AuthLayout compact title="Проверяем сессию" description="Подготавливаем рабочее пространство"><div className="auth-loading" role="status" aria-live="polite"><SpinnerGapIcon className="auth-spinner" size={22}/><span>Проверяем сессию…</span></div></AuthLayout>
}

export function SessionErrorScreen({ onRetry }: { onRetry: () => void | Promise<void> }) {
  return <AuthLayout compact title="Не удалось подключиться" description="Кураторская не может проверить текущую сессию. Защищённые данные не будут показаны без подтверждения"><div className="auth-connection-error"><WarningCircleIcon size={24}/><p>Проверьте соединение с сервером и повторите попытку</p></div><button className="btn primary auth-submit" type="button" onClick={() => void onRetry()}><ArrowClockwiseIcon size={18} weight="regular"/>Повторить</button></AuthLayout>
}

export function StudentAccessScreen({ onLogout }: { onLogout: () => Promise<void> }) {
  return <AuthLayout compact title="Личный кабинет пока не подключён" description="Этот этап открывает рабочее пространство кураторов. Доступ ученицы появится после подключения её стратегии и домашних заданий к серверу"><LogoutAction onLogout={onLogout}/></AuthLayout>
}
