import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'error' })

try {
  const accounts = await server.ssrLoadModule('/src/accounts/accountState.ts')
  const api = await server.ssrLoadModule('/src/api/users.ts')
  const session = await server.ssrLoadModule('/src/auth/session.ts')
  const page = await server.ssrLoadModule('/src/accounts/AccountAdminPage.tsx')

  const curator = { id: 'curator-1', login: 'curator', role: 'admin', is_owner: false, is_active: true, must_change_password: false }
  const owner = { ...curator, id: 'owner-1', login: 'owner', is_owner: true }
  const student = { ...curator, id: 'student-1', login: 'student', role: 'student' }

  assert.equal(accounts.canManageAccounts(owner), true)
  assert.equal(accounts.canManageAccounts(curator), false)
  assert.equal(accounts.canManageAccounts(student), false)

  const credential = { login: 'new.curator', temporaryPassword: 'one-time-secret' }
  const shown = accounts.temporaryCredentialReducer(null, { type: 'show', credential })
  assert.deepEqual(shown, credential)
  assert.equal(accounts.temporaryCredentialReducer(shown, { type: 'dismiss' }), null)

  const secretMarkup = renderToStaticMarkup(React.createElement(page.TemporaryCredentialDialog, { credential, onClose: () => {} }))
  assert.match(secretMarkup, /one-time-secret/)
  assert.match(secretMarkup, /Скопировать/)
  const closedMarkup = renderToStaticMarkup(React.createElement(page.TemporaryCredentialDialog, { credential: null, onClose: () => {} }))
  assert.doesNotMatch(closedMarkup, /one-time-secret/)

  const deniedMarkup = renderToStaticMarkup(React.createElement(page.default, { currentUser: curator, onRefreshUser: async () => {} }))
  assert.match(deniedMarkup, /Нет доступа/)
  assert.doesNotMatch(deniedMarkup, /Новый куратор/)

  assert.equal(accounts.accountErrorMessage(new api.ApiError(409, 'login_conflict', 'Conflict')), 'Этот логин уже используется')
  assert.equal(accounts.accountErrorMessage(new api.ApiError(403, 'forbidden', 'Forbidden')), 'Недостаточно прав для этого действия')
  assert.equal(accounts.accountErrorMessage(new api.ApiError(0, 'connection_error', 'Offline')), 'Не удалось подключиться к серверу')
  assert.equal(accounts.accountErrorMessage(new Error('Internal details')), 'Не удалось выполнить действие')

  const requests = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (input, init) => {
    requests.push([String(input), init])
    if (String(input).includes('/groups?')) return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    return new Response(JSON.stringify({ id: 'ok' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await api.usersApi.createCurator('new.curator')
    await api.usersApi.offboardCurator('curator-1', 'curator-2')
    await api.usersApi.reassignGroup('group-1', 'curator-2')
    await api.usersApi.listCuratorGroups('curator-1')
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.deepEqual(JSON.parse(requests[0][1].body), { login: 'new.curator' })
  assert.deepEqual(JSON.parse(requests[1][1].body), { successor_curator_id: 'curator-2' })
  assert.deepEqual(JSON.parse(requests[2][1].body), { curator_id: 'curator-2' })
  assert.match(requests[3][0], /curator_id=curator-1/)
  assert.equal(requests.every(([, init]) => init.credentials === 'include'), true)

  globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: 'login_conflict', message: 'Duplicate', details: {} } }), { status: 409, headers: { 'Content-Type': 'application/json' } })
  try {
    await assert.rejects(() => api.usersApi.createCurator('duplicate.login'), error => error instanceof api.ApiError && error.status === 409 && error.code === 'login_conflict')
  } finally {
    globalThis.fetch = originalFetch
  }

  const refreshed = await session.refreshSession(async () => ({ ...owner, is_owner: false }))
  assert.equal(refreshed.type, 'AUTHENTICATED')
  assert.equal(refreshed.user.is_owner, false)

  console.log('Account administration verification passed')
} finally {
  await server.close()
}
