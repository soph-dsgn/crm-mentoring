import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'error' })

try {
  const http = await server.ssrLoadModule('/src/api/http.ts')
  const state = await server.ssrLoadModule('/src/auth/authState.ts')
  const session = await server.ssrLoadModule('/src/auth/session.ts')
  const access = await server.ssrLoadModule('/src/auth/access.ts')
  const screens = await server.ssrLoadModule('/src/auth/AuthScreens.tsx')
  const validation = await server.ssrLoadModule('/src/auth/formValidation.ts')

  assert.equal(http.readCookie('first=1; kuratorskaya_csrf=token%20value; last=3', 'kuratorskaya_csrf'), 'token value')
  assert.equal(http.readCookie('first=1', 'kuratorskaya_csrf'), null)

  const requests = []
  const fetchOk = async (input, init) => {
    requests.push([input, init])
    return new Response(JSON.stringify({ id: 'user-1' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  await http.apiRequest('/api/v1/auth/change-password', {
    method: 'POST',
    body: { current_password: 'temporary password', new_password: 'new secure password' },
  }, { fetchImpl: fetchOk, cookie: 'kuratorskaya_csrf=csrf-value' })
  assert.equal(requests[0][1].credentials, 'include')
  assert.equal(requests[0][1].headers.get('X-CSRF-Token'), 'csrf-value')
  assert.equal(requests[0][1].headers.get('Content-Type'), 'application/json')

  await http.apiRequest('/api/v1/auth/me', {}, { fetchImpl: fetchOk, cookie: 'kuratorskaya_csrf=csrf-value' })
  assert.equal(requests[1][1].headers.has('X-CSRF-Token'), false)

  await assert.rejects(
    () => http.apiRequest('/api/v1/auth/login', {}, { fetchImpl: async () => { throw new TypeError('Failed to fetch') } }),
    error => error instanceof http.ApiError && error.code === 'connection_error' && error.status === 0,
  )
  for (const status of [403, 409, 422]) {
    await assert.rejects(
      () => http.apiRequest('/api/v1/auth/change-password', { method: 'POST' }, { fetchImpl: async () => new Response(JSON.stringify({ error: { code: `error_${status}`, message: 'Backend message', details: { field: 'password' } } }), { status, headers: { 'Content-Type': 'application/json' } }) }),
      error => error instanceof http.ApiError && error.status === status && error.code === `error_${status}` && error.details.field === 'password',
    )
  }
  await assert.rejects(
    () => http.apiRequest('/api/v1/auth/login', {}, { fetchImpl: async () => new Response(JSON.stringify({ error: { code: 'invalid_credentials', message: 'Invalid credentials', details: {} } }), { status: 401, headers: { 'Content-Type': 'application/json' } }) }),
    error => error instanceof http.ApiError && error.code === 'invalid_credentials' && error.status === 401,
  )
  let expiredCount = 0
  http.setSessionExpiredHandler(() => { expiredCount += 1 })
  await assert.rejects(() => http.apiRequest('/api/v1/groups', {}, { fetchImpl: async () => new Response(null, { status: 401 }) }))
  assert.equal(expiredCount, 1)
  await assert.rejects(() => http.apiRequest('/api/v1/auth/me', {}, { fetchImpl: async () => new Response(null, { status: 401 }), notifyUnauthorized: false }))
  assert.equal(expiredCount, 1)
  http.setSessionExpiredHandler(null)

  const user = { id: 'user-1', login: 'curator', role: 'admin', is_owner: false, must_change_password: false, is_active: true }
  const owner = { ...user, is_owner: true }
  const student = { ...user, role: 'student', login: 'student' }
  assert.deepEqual(access.getAccessProfile(owner), { kind: 'owner', canUseCrm: true, canManageUsers: true })
  assert.deepEqual(access.getAccessProfile(user), { kind: 'curator', canUseCrm: true, canManageUsers: false })
  assert.deepEqual(access.getAccessProfile(student), { kind: 'student', canUseCrm: false, canManageUsers: false })

  assert.deepEqual(await session.restoreSession(async () => user), { type: 'AUTHENTICATED', user })
  assert.deepEqual(await session.restoreSession(async () => { throw new http.ApiError(401, 'not_authenticated', 'Not authenticated') }), { type: 'BOOTSTRAP_ANONYMOUS' })
  assert.deepEqual(await session.restoreSession(async () => { throw new http.ApiError(0, 'connection_error', 'Connection failed') }), { type: 'BOOTSTRAP_ERROR', message: 'Не удалось подключиться к серверу. Проверьте соединение и повторите попытку' })
  assert.equal(await session.restoreSession(async () => { throw new DOMException('Aborted', 'AbortError') }), null)
  assert.deepEqual(await session.closeSession(async () => {}), { type: 'SIGNED_OUT' })
  await assert.rejects(
    () => session.closeSession(async () => { throw new http.ApiError(403, 'invalid_csrf_token', 'Invalid CSRF token') }),
    error => error instanceof http.ApiError && error.code === 'invalid_csrf_token',
  )
  assert.deepEqual(state.authReducer(state.initialAuthState, { type: 'BOOTSTRAP_ANONYMOUS' }), { status: 'anonymous', user: null, reason: null, message: null })
  assert.equal(state.authReducer(state.initialAuthState, { type: 'AUTHENTICATED', user: { ...user, must_change_password: true } }).status, 'password_change')
  assert.deepEqual(state.authReducer({ status: 'authenticated', user, reason: null, message: null }, { type: 'SESSION_EXPIRED' }), { status: 'anonymous', user: null, reason: 'expired', message: null })
  assert.equal(state.authReducer(state.initialAuthState, { type: 'BOOTSTRAP_ERROR', message: 'Нет соединения' }).status, 'error')

  assert.deepEqual(validation.validateLogin('', ''), { login: 'Введите логин', password: 'Введите пароль' })
  assert.deepEqual(validation.validatePasswordChange('temporary', 'short', 'different'), { newPassword: 'Минимум 12 символов', confirmation: 'Пароли не совпадают' })
  assert.deepEqual(validation.validatePasswordChange('temporary', 'long password value', 'long password value'), {})

  const noop = async () => {}
  const loginMarkup = renderToStaticMarkup(React.createElement(screens.LoginScreen, { reason: 'expired', notice: null, onSubmit: noop }))
  assert.match(loginMarkup, /Сессия завершилась/)
  assert.match(loginMarkup, /autoComplete="username"/)
  assert.match(loginMarkup, /autoComplete="current-password"/)
  assert.match(loginMarkup, /aria-live="polite"/)
  assert.match(loginMarkup, /Войти/)

  const changeMarkup = renderToStaticMarkup(React.createElement(screens.ChangePasswordScreen, { login: 'curator', onSubmit: noop, onLogout: noop }))
  assert.match(changeMarkup, /Создайте новый пароль/)
  assert.match(changeMarkup, /Минимум 12 символов/)
  assert.match(changeMarkup, /autoComplete="new-password"/)
  assert.match(changeMarkup, /Выйти/)

  const loadingMarkup = renderToStaticMarkup(React.createElement(screens.SessionLoadingScreen))
  assert.match(loadingMarkup, /Проверяем сессию/)
  assert.match(loadingMarkup, /role="status"/)

  const errorMarkup = renderToStaticMarkup(React.createElement(screens.SessionErrorScreen, { onRetry: noop }))
  assert.match(errorMarkup, /Не удалось подключиться/)
  assert.match(errorMarkup, /Повторить/)

  const studentMarkup = renderToStaticMarkup(React.createElement(screens.StudentAccessScreen, { onLogout: noop }))
  assert.match(studentMarkup, /Личный кабинет пока не подключён/)
  assert.match(studentMarkup, /Выйти/)

  console.log('Auth/session verification passed')
} finally {
  await server.close()
}
