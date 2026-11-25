import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const securePassword = () => `Qa1!${randomUUID()}`
const button = (page, name) => page.getByRole('button', { name, exact: true })
const tab = (page, name) => page.getByRole('tab', { name: new RegExp(`^${name}( |$)`) })
const heading = (page, name) => page.getByRole('heading', { name, exact: true })
const searchName = 'Поиск группы или ученицы'
const accountMenu = page => page.getByRole('button', { name: /^Аккаунт:/ })
const menuItem = (page, name) => page.getByRole('menuitem', { name, exact: true })
async function openMenu(page, item) {
  await accountMenu(page).click()
  await menuItem(page, item).click()
}

function bootstrapOwner() {
  const args = [
    'python', '-m', 'app.cli.bootstrap_owner', '--login', 'acceptance.owner',
    '--confirm-database', 'acceptance', '--confirm-first-owner',
  ]
  const code = `import os, pty, sys; sys.exit(os.waitstatus_to_exitcode(pty.spawn(${JSON.stringify(args)})))`
  const output = execFileSync('docker', [
    'compose', '-f', '../deploy/compose.acceptance.yml', 'exec', '-T',
    'backend', 'python', '-c', code,
  ], { encoding: 'utf-8' })
  const password = output.match(/^Temporary password \(shown once\): ([^\r\n]+)/m)?.[1]
  if (!password) throw new Error('Bootstrap did not present a temporary credential')
  return password
}

async function login(page, loginName, password) {
  await page.getByLabel('Логин', { exact: true }).fill(loginName)
  await page.getByLabel('Пароль', { exact: true }).fill(password)
  await button(page, 'Войти').click()
}

async function changeTemporaryPassword(page, next) {
  await expect(heading(page, 'Создайте новый пароль')).toBeVisible()
  await expect(page.getByLabel('Временный пароль', { exact: true })).toBeHidden()
  await page.getByLabel('Новый пароль', { exact: true }).fill(next)
  await page.getByLabel('Повторите новый пароль', { exact: true }).fill(next)
  const changed = page.waitForResponse(response =>
    response.url().endsWith('/api/v1/auth/change-password') && response.request().method() === 'POST')
  await button(page, 'Сохранить новый пароль').click()
  expect((await changed).status()).toBe(200)
  await expect(heading(page, 'Создайте новый пароль')).toBeHidden()
  const session = await page.request.get(new URL('/api/v1/auth/me', page.url()).href)
  expect(session.status()).toBe(200)
  expect(await session.json()).toMatchObject({ must_change_password: false })
}

async function createCurator(owner, name) {
  await button(owner, 'Новый куратор').click()
  const dialog = owner.getByRole('dialog', { name: 'Новый куратор' })
  await dialog.getByLabel('Логин', { exact: true }).fill(name)
  await button(dialog, 'Создать аккаунт').click()
  const credentials = owner.getByRole('dialog', { name: 'Временные данные для входа' })
  await expect(credentials).toBeVisible()
  const password = await credentials.locator('code').nth(1).textContent()
  await button(credentials, 'Данные сохранены').click()
  return password
}

async function createGroup(page, name, checkInvalidDate = false) {
  await button(page, 'Стратегии').click()
  await button(page, 'Новая группа').click()
  await page.getByLabel('Название группы').fill(name)
  if (checkInvalidDate) {
    const start = page.getByLabel('Дата начала', { exact: true })
    await start.fill('01.02.2026')
    await start.fill('31.02.2026')
    await start.blur()
    await expect(start).toHaveAttribute('aria-invalid', 'true')
    await button(page, 'Сохранить группу').click()
    await expect(start).toBeFocused()
    await expect(start).toHaveValue('31.02.2026')
    await start.fill('02.02.2026')
    await expect(start).not.toHaveAttribute('aria-invalid', 'true')
  }
  const response = page.waitForResponse(resp =>
    resp.url().endsWith('/api/v1/groups') && resp.request().method() === 'POST')
  await button(page, 'Сохранить группу').click()
  const saved = await response
  expect(saved.status()).toBe(201)
  await expect(heading(page, name)).toBeVisible()
  const group = await saved.json()
  if (checkInvalidDate) expect(group.starts_at).toBe('2026-02-02')
  return group.id
}

async function findProfile(page, name) {
  await button(page, searchName).click()
  await page.getByRole('textbox', { name: searchName }).fill(name)
  await page.locator('.toolbar-search-results').getByRole('button', { name }).click()
  await expect(heading(page, name)).toBeVisible()
}

async function importKnowledge(page, fixture, title) {
  await button(page, 'Импорт').click()
  const dialog = page.getByRole('dialog', { name: 'Импортировать материалы' })
  await dialog.locator('input[type=file]').setInputFiles(fixture)
  const validation = page.waitForResponse(response => response.url().endsWith('/knowledge/imports/validate'))
  await button(dialog, 'Проверить без записи').click()
  const report = await (await validation).json()
  expect(report.valid, JSON.stringify(report.issues || report.error)).toBe(true)
  await dialog.getByRole('checkbox').check()
  await button(dialog, 'Импортировать').click()
  await expect(page.locator('.knowledge-index').getByText(title, { exact: true })).toBeVisible()
}

test('HTTPS release supports curator learning and independent sessions', async ({ browser, request }) => {
  for (const path of ['/strategies/strategy-seed.json', '/strategies/old.pdf', '/knowledge-seed.json', '/assets/missing.js.map', '/api/missing']) {
    const response = await request.get(path)
    expect(response.status(), path).toBe(404)
  }
  expect((await request.get('/health/ready')).ok()).toBe(true)
  const denied = await request.get('/api/v1/groups')
  expect(denied.status()).toBe(401)
  expect(denied.headers()['cache-control']).toBe('no-store')

  const ownerContext = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } })
  const curatorContext = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  const secondContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const studentContext = await browser.newContext({ ignoreHTTPSErrors: true })
  try {
    await ownerContext.addInitScript(() => {
      if (!localStorage.getItem('crm-mentoring-v1')) {
        localStorage.setItem('crm-mentoring-v1', JSON.stringify({ version: 3, groups: [{ id: 'local-only', name: 'Локальная запись' }], students: [], tasks: [], sections: [], meetings: [], homeworks: [] }))
      }
    })
    const owner = await ownerContext.newPage()
    const temporary = process.env.CRM_ACCEPTANCE_OWNER_TEMPORARY || bootstrapOwner()
    const password = securePassword()
    await owner.goto('https://localhost:8443')
    await login(owner, 'acceptance.owner', temporary)
    await changeTemporaryPassword(owner, password)
    await expect(heading(owner, 'Обзор')).toBeVisible()
    await button(owner, searchName).click()
    await owner.getByRole('textbox', { name: searchName }).fill('Локальная запись')
    await expect(owner.getByText('Ничего не найдено', { exact: true })).toBeVisible()
    await button(owner, searchName).click()
    const cookies = await ownerContext.cookies()
    expect(cookies.filter(cookie => cookie.name.startsWith('kuratorskaya_')).map(
      ({ name, secure, httpOnly }) => ({ name, secure, httpOnly }),
    )).toEqual(expect.arrayContaining([
      { name: 'kuratorskaya_session', secure: true, httpOnly: true },
      { name: 'kuratorskaya_csrf', secure: true, httpOnly: false },
    ]))

    await openMenu(owner, 'Аккаунты кураторов')
    const firstTemporary = await createCurator(owner, 'acceptance.first')
    const secondTemporary = await createCurator(owner, 'acceptance.second')
    await openMenu(owner, 'Перенос данных')
    const source = {
      version: 3, demo: false,
      groups: [
        { id: 'legacy-first', name: 'Импортированная группа', startsAt: '2026-01-10', status: 'active' },
        { id: 'legacy-archive', name: 'Импортированный архив', startsAt: '2026-01-10', status: 'archived', statusBeforeArchive: 'completed' },
      ],
      students: [{ id: 'legacy-student', groupId: 'legacy-first', name: 'Импортированная Ученица', stage: 'start' }],
      sections: [{ id: 'legacy-section', studentId: 'legacy-student', title: 'Начало', order: 0 }],
      tasks: [{ id: 'legacy-task', studentId: 'legacy-student', sectionId: 'legacy-section', title: 'Импортированная задача', studyStatus: 'not_started', order: 0 }],
      meetings: [],
      homeworks: [{ id: 'legacy-homework', studentId: 'legacy-student', title: 'Импортированное ДЗ', status: 'draft', text: 'Текст ДЗ', items: [{ taskId: 'legacy-task', title: 'Исторический снимок', description: 'Синтетический текст' }] }],
    }
    for (let index = 2; index <= 20; index++) {
      const studentId = `legacy-student-${index}`
      const sectionId = `legacy-section-${index}`
      source.students.push({ id: studentId, groupId: 'legacy-first', name: `Учебный профиль ${index}`, stage: 'start' })
      source.sections.push({ id: sectionId, studentId, title: 'Задачи', order: 0 })
      source.tasks.push(...Array.from({ length: 30 }, (_, order) => ({
        id: `legacy-task-${index}-${order}`, studentId, sectionId,
        title: `Задача ${order + 1}`, studyStatus: 'not_started', order,
      })))
    }
    const approvalReads = new Set()
    let individualApprovalReads = 0
    owner.on('request', request => {
      if (request.method() !== 'GET') return
      const path = new URL(request.url()).pathname
      if (/^\/api\/v1\/strategies\/[^/]+\/approvals$/.test(path)) approvalReads.add(path)
      if (/^\/api\/v1\/strategy-tasks\/[^/]+\/approval$/.test(path)) individualApprovalReads++
    })

    await owner.locator('input[type=file]').setInputFiles({
      name: 'appdata-v3.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(source)),
    })
    for (const [name, curatorName] of [
      ['Импортированная группа', 'acceptance.first'],
      ['Импортированный архив', 'acceptance.second'],
    ]) {
      await owner.getByRole('combobox', { name: `Куратор группы ${name}` }).click()
      await owner.getByRole('option', { name: curatorName, exact: true }).click()
    }
    const validation = owner.waitForResponse(response => response.url().endsWith('/imports/legacy/validate'))
    await button(owner, 'Проверить данные').click()
    const report = await (await validation).json()
    expect(report.valid, JSON.stringify(report.conflicts || report.error)).toBe(true)
    await owner.getByRole('checkbox').check()
    await button(owner, 'Импортировать на сервер').click()
    await expect(heading(owner, 'Миграция завершена')).toBeVisible()
    await findProfile(owner, 'Импортированная Ученица')
    await tab(owner, 'Домашние задания').click()
    await expect(heading(owner, 'Импортированное ДЗ')).toBeVisible()
    await owner.getByText(/^Содержание ДЗ/).click()
    await expect(owner.getByText('Исторический снимок', { exact: true })).toBeVisible()
    await expect.poll(() => approvalReads.size, { timeout: 30_000 }).toBeGreaterThanOrEqual(20)
    expect(individualApprovalReads).toBe(0)

    const curator = await curatorContext.newPage()
    const second = await secondContext.newPage()
    await Promise.all([curator.goto('https://localhost:8443'), second.goto('https://localhost:8443')])
    const passwords = [securePassword(), securePassword()]
    for (const [page, loginName, initial, final] of [
      [curator, 'acceptance.first', firstTemporary, passwords[0]],
      [second, 'acceptance.second', secondTemporary, passwords[1]],
    ]) {
      await login(page, loginName, initial)
      await changeTemporaryPassword(page, final)
      await expect(heading(page, 'Обзор')).toBeVisible()
    }

    const sourceId = await createGroup(curator, 'Приёмочная группа 1', true)
    const targetId = await createGroup(second, 'Приёмочная группа 2')
    await button(second, 'Добавить ученицу').click()
    await second.getByLabel('Имя и фамилия').fill('Вторая тестовая ученица')
    await button(second, 'Сохранить профиль').click()
    await expect(heading(second, 'Вторая тестовая ученица')).toBeVisible()
    const foreignGroup = await second.request.get(`https://localhost:8443/api/v1/groups/${sourceId}`)
    const group = await foreignGroup.json()
    const csrf = (await secondContext.cookies()).find(cookie => cookie.name === 'kuratorskaya_csrf').value
    const foreignEdit = await second.request.patch(`https://localhost:8443/api/v1/groups/${sourceId}`, {
      headers: { Origin: 'https://localhost:8443', 'X-CSRF-Token': csrf },
      data: { expected_version: group.version, name: 'Запрещённое изменение' },
    })
    expect(foreignEdit.status()).toBe(403)
    expect((await second.request.patch(`https://localhost:8443/api/v1/groups/${targetId}`, {
      headers: { Origin: 'https://localhost:8443' },
      data: { expected_version: 1, name: 'Без CSRF' },
    })).status()).toBe(403)

    const learner = 'Приёмочная Ученица'
    await button(curator, 'Добавить ученицу').click()
    await curator.getByLabel('Имя и фамилия').fill(learner)
    await button(curator, 'Сохранить профиль').click()
    await expect(heading(curator, learner)).toBeVisible()
    expect(await curator.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.innerWidth)).toBe(true)

    await tab(curator, 'Стратегия').click()
    await button(curator, 'Создать пустую').click()
    for (const section of ['Первый раздел', 'Второй раздел']) {
      await curator.getByRole('textbox', { name: 'Название нового раздела' }).fill(section)
      await button(curator, 'Добавить раздел').click()
      await expect(curator.getByRole('button', { name: new RegExp(section) }).first()).toBeVisible()
    }
    await button(curator, 'Переместить раздел выше: Второй раздел').click()
    await expect(curator.locator('.study-section-toggle').first()).toContainText('Второй раздел')
    const first = curator.locator('.study-section').filter({ hasText: 'Первый раздел' })
    await button(first, 'Добавить задачу').click()
    await curator.getByLabel('Название задачи').fill('Синтетическая задача')
    await button(curator, 'Сохранить задачу').click()
    await curator.getByRole('combobox', { name: 'Раздел задачи: Синтетическая задача' }).click()
    await curator.getByRole('option', { name: 'Второй раздел' }).click()
    const destination = curator.locator('.study-section').filter({ hasText: 'Второй раздел' })
    await expect(destination.getByText('Синтетическая задача', { exact: true })).toBeVisible()
    await button(destination, 'Добавить задачу').click()
    await curator.getByLabel('Название задачи').fill('Дополнительная задача')
    await button(curator, 'Сохранить задачу').click()
    await button(destination, 'Переместить выше: Дополнительная задача').click()
    await expect(destination.locator('.task-card-open').first()).toHaveAccessibleName('Открыть задачу: Дополнительная задача')
    await button(first, 'Удалить').click()
    await button(curator.getByRole('dialog', { name: 'Удалить раздел?' }), 'Удалить раздел').click()
    await expect(first).toHaveCount(0)

    await tab(curator, 'Встречи').click()
    await button(curator, 'Добавить встречу').click()
    await curator.getByLabel('Тема встречи').fill('Приёмочная встреча')
    await curator.getByLabel('Итоги и договорённости').fill('Согласовали следующий шаг')
    await button(curator, 'Сохранить встречу').click()
    await expect(heading(curator, 'Приёмочная встреча')).toBeVisible()
    await button(curator, 'Редактировать встречу: Приёмочная встреча').click()
    await curator.getByLabel('Заметки куратора').fill('Внутренняя заметка встречи')
    await button(curator, 'Сохранить встречу').click()
    await expect(curator.getByText('Внутренняя заметка встречи', { exact: true })).toBeVisible()
    await button(curator, 'Переместить встречу в архив: Приёмочная встреча').click()
    await button(curator.getByRole('dialog', { name: 'Переместить встречу в архив?' }), 'Переместить в архив').click()
    await expect(heading(curator, 'Приёмочная встреча')).toHaveCount(0)
    await button(curator, 'Показать архив').click()
    await button(curator, 'Восстановить').click()
    await expect(heading(curator, 'Приёмочная встреча')).toBeVisible()

    await tab(curator, 'Стратегия').click()
    await button(curator, 'Открыть задачу: Синтетическая задача').click()
    await button(curator, 'Передать Ане').click()
    const taskDialog = curator.getByRole('dialog', { name: 'Синтетическая задача' })
    await taskDialog.getByLabel('Что проверить Ане').fill('Проверь структуру задачи')
    const handoff = curator.waitForResponse(response => response.url().endsWith('/approval') && response.request().method() === 'POST')
    await button(taskDialog, 'Передать').click()
    expect((await handoff).status()).toBe(201)
    await expect(taskDialog.getByText('Ждёт Аню', { exact: true })).toBeVisible()
    await taskDialog.getByLabel('Закрыть').click()

    const transition = page => page.waitForResponse(response =>
      response.url().endsWith('/approval/transition') && response.request().method() === 'POST')
    await button(owner, 'Обзор').click()
    await button(owner, 'Задачи Ани').click()
    await button(owner, 'Вернуть на доработку').click()
    await owner.getByLabel('Что нужно поправить').fill('Добавь пример')
    let response = transition(owner)
    await owner.locator('.approval-reply').getByRole('button', { name: 'Вернуть на доработку' }).click()
    expect((await response).status()).toBe(200)

    await button(curator, 'Задачи Ани').click()
    await expect(curator.getByText('Добавь пример')).toBeVisible()
    await curator.getByLabel('Что исправлено').fill('Пример добавлен')
    response = transition(curator)
    await button(curator, 'Отправить Ане повторно').click()
    expect((await response).status()).toBe(200)
    await expect(button(curator, 'Согласовать')).toHaveCount(0)

    await button(owner, 'Обзор').click()
    await button(owner, 'Задачи Ани').click()
    response = transition(owner)
    await button(owner, 'Согласовать').click()
    expect((await response).status()).toBe(200)
    await findProfile(curator, learner)
    await tab(curator, 'Стратегия').click()

    await curator.getByRole('checkbox', { name: 'Выбрать для ДЗ: Синтетическая задача' }).check()
    await curator.getByRole('button', { name: /^Сформировать ДЗ/ }).click()
    await curator.getByRole('dialog', { name: 'Домашнее задание' }).locator('.dialog-actions').getByRole('button', { name: 'Закрыть' }).click()
    await tab(curator, 'Домашние задания').click()
    await button(curator, 'Выдать ДЗ').click()
    await button(curator, 'Отметить в работе').click()
    await curator.getByLabel('Комментарий к отправке').fill('Синтетическая работа')
    await button(curator, 'Зафиксировать сдачу').click()
    await button(curator, 'Вернуть на доработку').click()
    await curator.getByLabel('Комментарий к отправке').fill('Синтетическая доработка')
    await button(curator, 'Зафиксировать сдачу').click()
    await button(curator, 'Принять работу').click()
    await expect(curator.getByText(/^Принято/)).toBeVisible()

    await owner.reload()
    await findProfile(owner, learner)
    await button(owner, 'Перевести в другую группу').click()
    await owner.getByRole('combobox', { name: 'Группа назначения' }).click()
    await owner.getByRole('option', { name: 'Приёмочная группа 2' }).click()
    await button(owner, 'Перевести').click()
    await expect(owner.locator('.profile-identity')).toContainText('Приёмочная группа 2')

    await second.reload()
    await findProfile(second, learner)
    await tab(second, 'Домашние задания').click()
    await expect(second.getByText(/^Принято/)).toBeVisible()

    await tab(second, 'Обзор').click()
    await button(second.locator('.student-account-panel'), 'Создать аккаунт').click()
    const studentForm = second.getByRole('dialog', { name: 'Аккаунт ученицы' })
    await studentForm.getByLabel('Логин').fill('acceptance.learner')
    await button(studentForm, 'Создать аккаунт').click()
    const studentCredentials = second.getByRole('dialog', { name: 'Временные данные для входа' })
    await expect(studentCredentials).toBeVisible()
    const studentTemporary = await studentCredentials.locator('code').nth(1).textContent()
    const studentUrl = await studentCredentials.locator('code').nth(2).textContent()
    await button(studentCredentials, 'Данные сохранены').click()
    const learnerPage = await studentContext.newPage()
    await learnerPage.goto(studentUrl)
    await login(learnerPage, 'acceptance.learner', studentTemporary)
    const learnerPassword = securePassword()
    await changeTemporaryPassword(learnerPage, learnerPassword)
    await expect(heading(learnerPage, learner)).toBeVisible()
    await button(learnerPage, 'Встречи').click()
    await expect(heading(learnerPage, 'Приёмочная встреча')).toBeVisible()
    await expect(learnerPage.getByText('Внутренняя заметка встречи')).toHaveCount(0)

    const target = 'Приёмочная группа 2'
    for (const page of [owner, second]) {
      await button(page.getByRole('navigation', { name: 'Путь к ученице' }), target).click()
      await button(page, 'Редактировать группу').click()
      await expect(page.getByRole('dialog', { name: 'Редактировать группу' })).toBeVisible()
    }
    await owner.getByLabel('Заметки куратора').fill('Первая версия заметки')
    await button(owner, 'Сохранить группу').click()
    await expect(owner.getByRole('dialog', { name: 'Редактировать группу' })).toHaveCount(0)
    await second.getByLabel('Заметки куратора').fill('Конфликтующая версия заметки')
    await button(second, 'Сохранить группу').click()
    await expect(second.getByRole('alert')).toContainText('Данные изменились в другой сессии')
    await expect(second.getByLabel('Заметки куратора')).toHaveValue('Конфликтующая версия заметки')
    await button(second, 'Отмена').click()

    await button(owner, 'Промпты').click()
    await button(owner, 'Загрузить промпты').click()
    await button(owner, 'Начать с пустой библиотеки').click()
    await button(owner, 'Проверить без записи').click()
    await owner.getByRole('checkbox').check()
    await button(owner, 'Импортировать и активировать').click()
    await expect(heading(owner, 'Промпты')).toBeVisible()
    await button(owner, 'Промпт').click()
    const editor = owner.getByRole('dialog', { name: 'Новый материал' })
    await editor.getByLabel('Название').fill('Приёмочный материал')
    await editor.locator('[contenteditable]').fill('Общий синтетический текст')
    await button(editor, 'Сохранить').click()
    await expect(heading(owner, 'Приёмочный материал')).toBeVisible()
    await button(owner, 'В избранное').click()
    await expect(button(owner, 'Убрать из избранного')).toBeVisible()
    await button(second, 'Промпты').click()
    await expect(heading(second, 'Приёмочный материал')).toBeVisible()
    await expect(button(second, 'В избранное')).toBeVisible()
    await expect(button(second, 'Локальная копия')).toHaveCount(0)
    await expect(button(second, 'Серверная копия')).toHaveCount(0)
    await button(owner, 'Редактировать').click()
    const edit = owner.getByRole('dialog', { name: 'Редактировать' })
    await edit.getByLabel('Название').fill('Обновлённый материал')
    await button(edit, 'Сохранить').click()
    await expect(heading(owner, 'Обновлённый материал')).toBeVisible()
    await button(owner, 'В архив').click()
    await button(owner.getByRole('dialog', { name: 'Переместить материал в архив?' }), 'В архив').click()
    await expect(heading(owner, 'Обновлённый материал')).toHaveCount(0)
    await button(owner, 'Показать архив').click()
    await owner.getByRole('button', { name: /Обновлённый материал/ }).click()
    await button(owner, 'Восстановить').click()
    await button(owner.getByRole('dialog', { name: 'Восстановить материал?' }), 'Восстановить').click()
    await expect(owner.getByText('Материал восстановлен', { exact: true })).toBeVisible()

    await importKnowledge(owner, {
      name: 'sample.md', mimeType: 'text/markdown', buffer: Buffer.from('# Учебный Markdown\n\nПроверка импорта'),
    }, 'Учебный Markdown')
    await importKnowledge(owner, {
      name: 'sample.html', mimeType: 'text/html', buffer: Buffer.from('<h1>Учебный HTML</h1><p>Проверка импорта</p>'),
    }, 'Учебный HTML')
    await importKnowledge(owner, fileURLToPath(new URL('./fixtures/Учебный DOCX.docx', import.meta.url)), 'Учебный DOCX')
    await importKnowledge(owner, {
      name: 'knowledge-v1.json', mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({
        version: 1, importedAt: '2026-01-01T00:00:00Z', chapters: [],
        prompts: [{ id: 'qa-legacy', title: 'Учебная копия знаний', category: 'Другие',
          html: '<p>Содержание локальной копии</p>', text: 'Содержание локальной копии',
          sourceId: 'qa-legacy-library', sourceRevision: '', sourceHash: 'synthetic',
          edited: false, deleted: false, favorite: false, updatedAt: '2026-01-01T00:00:00Z',
        }],
      })),
    }, 'Учебная копия знаний')
    await owner.getByRole('textbox', { name: 'Поиск по базе знаний' }).fill('Содержание локальной копии')
    await expect(owner.locator('.knowledge-index button').filter({ hasText: 'Учебная копия знаний' })).toBeVisible()
    await expect(owner.locator('.knowledge-index button').filter({ hasText: 'Учебный DOCX' })).toHaveCount(0)

    await openMenu(owner, 'Аккаунты кураторов')
    await owner.getByRole('button', { name: /acceptance.first Куратор/ }).click()
    await button(owner, 'Новый временный пароль').click()
    await button(owner.getByRole('dialog', { name: 'Выдать новый временный пароль?' }), 'Выдать пароль').click()
    const resetData = owner.getByRole('dialog', { name: 'Временные данные для входа' })
    await expect(resetData).toBeVisible()
    await button(resetData, 'Данные сохранены').click()
    await curator.reload()
    await expect(heading(curator, 'Вход в Кураторскую')).toBeVisible()

    await button(owner, 'Передать группы и отключить').click()
    const offboard = owner.getByRole('dialog', { name: 'Передать группы и отключить' })
    await offboard.getByRole('combobox', { name: 'Новый куратор' }).click()
    await owner.getByRole('option', { name: 'acceptance.second', exact: true }).click()
    await button(offboard, 'Передать и отключить').click()
    await expect(owner.locator('.account-detail-head')).toContainText('Неактивен')

    await openMenu(owner, 'Мой профиль')
    await button(owner, 'Сменить пароль').click()
    await owner.getByLabel('Текущий пароль', { exact: true }).fill(password)
    const replacement = securePassword()
    await owner.getByLabel('Новый пароль', { exact: true }).fill(replacement)
    await owner.getByLabel('Повторите новый пароль', { exact: true }).fill(replacement)
    await button(owner, 'Сохранить новый пароль').click()
    await expect(owner.getByText('Пароль изменён', { exact: true })).toBeVisible()
    await button(owner, 'Понятно').click()
    await openMenu(owner, 'Выйти')
    await login(owner, 'acceptance.owner', replacement)
    await expect(heading(owner, 'Обзор')).toBeVisible()

    await openMenu(owner, 'Аккаунты кураторов')
    await owner.getByRole('button', { name: /acceptance.second Куратор/ }).click()
    await button(owner, 'Передать права владельца').click()
    await button(owner.getByRole('dialog', { name: 'Передать права владельца?' }), 'Передать права').click()
    await accountMenu(owner).click()
    await expect(menuItem(owner, 'Аккаунты кураторов')).toHaveCount(0)
    await second.reload()
    await accountMenu(second).click()
    await expect(menuItem(second, 'Аккаунты кураторов')).toBeVisible()
  } finally {
    await Promise.all([ownerContext.close(), curatorContext.close(), secondContext.close(), studentContext.close()])
  }
})
