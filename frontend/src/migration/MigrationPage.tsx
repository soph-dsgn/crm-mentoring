import { useCallback, useEffect, useId, useMemo, useRef, useState, type ChangeEvent } from 'react'
import {
  ArrowClockwiseIcon as ArrowClockwise,
  CheckCircleIcon as CheckCircle,
  DownloadIcon as Download,
  FileArrowUpIcon as FileArrowUp,
  ShieldCheckIcon as ShieldCheck,
  WarningCircleIcon as WarningCircle,
} from '@phosphor-icons/react'
import type { CurrentUser, CuratorSummary, LegacyImportResult, LegacyValidationReport } from '../api/contracts'
import { ApiError } from '../api/http'
import { legacyApi } from '../api/legacy'
import { usersApi } from '../api/users'
import { STORAGE_KEY } from '../data'
import Select from '../Select'
import {
  MAX_LEGACY_IMPORT_BYTES,
  conflictLabel,
  groupConflicts,
  legacyGroups,
  legacySource,
  migrationErrorMessage,
  requestBytes,
  warningLabel,
  type LegacyGroupReference,
} from './migrationState'

type LoadState = 'loading' | 'ready' | 'error'
type FlowState = 'idle' | 'ready' | 'validating' | 'validated' | 'importing' | 'complete' | 'uncertain'

const countLabels: Record<string, string> = {
  groups: 'Группы', students: 'Ученицы', strategies: 'Стратегии', sections: 'Разделы',
  tasks: 'Задачи', meetings: 'Встречи', homeworks: 'Домашние задания',
  homework_items: 'Снимки задач', approvals: 'Согласования с Аней',
}

function downloadJson(value: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function today() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function MigrationPermissionState() {
  return <div className="profile-empty migration-permission" role="status">
    <ShieldCheck size={30}/><strong>Нет доступа</strong>
    <p>Миграция и серверные копии доступны только владельцу «Кураторской»</p>
  </div>
}

export default function MigrationPage({ currentUser, onCutover }: { currentUser: CurrentUser; onCutover: () => void | Promise<void> }) {
  const inputId = useId()
  const fileInput = useRef<HTMLInputElement>(null)
  const requestPending = useRef(false)
  const [curators, setCurators] = useState<CuratorSummary[]>([])
  const [curatorState, setCuratorState] = useState<LoadState>('loading')
  const [curatorError, setCuratorError] = useState('')
  const [source, setSource] = useState<Record<string, unknown> | null>(null)
  const [sourceName, setSourceName] = useState('')
  const [groups, setGroups] = useState<LegacyGroupReference[]>([])
  const [assignments, setAssignments] = useState<Record<string, string>>({})
  const [report, setReport] = useState<LegacyValidationReport | null>(null)
  const [result, setResult] = useState<LegacyImportResult | null>(null)
  const [flow, setFlow] = useState<FlowState>('idle')
  const [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [exportPending, setExportPending] = useState(false)
  const [exportError, setExportError] = useState('')

  const loadCurators = useCallback(async (signal?: AbortSignal) => {
    setCuratorState('loading'); setCuratorError('')
    try {
      const items = await usersApi.listCurators(signal)
      setCurators(items.filter(item => item.is_active && item.role === 'admin'))
      setCuratorState('ready')
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return
      setCuratorError(migrationErrorMessage(caught)); setCuratorState('error')
    }
  }, [])

  useEffect(() => {
    if (!currentUser.is_owner) return
    const controller = new AbortController()
    void loadCurators(controller.signal)
    return () => controller.abort()
  }, [currentUser.is_owner, loadCurators])

  const resetValidation = (nextFlow: FlowState = source ? 'ready' : 'idle') => {
    setReport(null); setResult(null); setConfirmed(false); setError(''); setFlow(nextFlow)
  }

  const loadText = (text: string, name: string) => {
    setError(''); setReport(null); setResult(null); setConfirmed(false)
    try {
      if (new TextEncoder().encode(text).byteLength > MAX_LEGACY_IMPORT_BYTES) throw new Error('too_large')
      const parsed = legacySource(JSON.parse(text))
      if (!parsed) throw new Error('invalid_source')
      const nextGroups = legacyGroups(parsed)
      setSource(parsed); setSourceName(name); setGroups(nextGroups); setAssignments({}); setFlow('ready')
    } catch {
      setSource(null); setSourceName(''); setGroups([]); setAssignments({}); setFlow('idle')
      setError('Не удалось прочитать JSON-копию AppData. Локальные данные не изменены')
    }
  }

  const chooseFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (file.size > MAX_LEGACY_IMPORT_BYTES) {
      setSource(null); setGroups([]); setAssignments({}); setFlow('idle'); setReport(null); setResult(null); setConfirmed(false)
      setError('Файл превышает допустимые 5 МиБ')
      return
    }
    loadText(await file.text(), file.name)
  }

  const browserCopy = (() => { try { return localStorage.getItem(STORAGE_KEY) } catch { return null } })()

  const changeAssignment = (groupId: string, curatorId: string) => {
    setAssignments(current => ({ ...current, [groupId]: curatorId }))
    resetValidation('ready')
  }

  const assignmentsComplete = groups.every(group => Boolean(assignments[group.id]))

  const validate = async () => {
    if (!source || requestPending.current) return
    if (!assignmentsComplete) { setError('Назначьте действующего куратора каждой группе'); return }
    if (requestBytes(source, assignments) > MAX_LEGACY_IMPORT_BYTES) { setError('Файл вместе с назначениями превышает допустимые 5 МиБ'); return }
    requestPending.current = true; setFlow('validating'); setError(''); setReport(null); setResult(null); setConfirmed(false)
    try {
      const next = await legacyApi.validate({ source, curator_assignments: assignments })
      setReport(next); setFlow('validated')
    } catch (caught) {
      setError(migrationErrorMessage(caught)); setFlow('ready')
    } finally { requestPending.current = false }
  }

  const importData = async () => {
    if (!source || !report?.valid || !confirmed || requestPending.current) return
    if (requestBytes(source, assignments, report.checksum) > MAX_LEGACY_IMPORT_BYTES) {
      resetValidation('ready'); setError('Подтверждённый запрос превышает допустимые 5 МиБ'); return
    }
    requestPending.current = true; setFlow('importing'); setError('')
    try {
      const next = await legacyApi.importLegacy({
        source, curator_assignments: assignments, confirmation_checksum: report.checksum, confirm: true,
      })
      setResult(next); setFlow('complete'); setConfirmed(false)
      await onCutover()
    } catch (caught) {
      setConfirmed(false)
      if (caught instanceof ApiError && caught.code === 'connection_error') {
        setFlow('uncertain'); setReport(null)
      } else {
        setFlow('ready'); setReport(null)
      }
      setError(migrationErrorMessage(caught,'import'))
    } finally { requestPending.current = false }
  }

  const exportServerBackup = async () => {
    if (exportPending) return
    setExportPending(true); setExportError('')
    try {
      const backup = await legacyApi.exportBackup()
      downloadJson(backup, `kuratorskaya-server-backup-${today()}.json`)
    } catch (caught) { setExportError(migrationErrorMessage(caught)) }
    finally { setExportPending(false) }
  }

  const conflicts = useMemo(() => groupConflicts(report?.conflicts ?? []), [report])

  if (!currentUser.is_owner) return <MigrationPermissionState/>

  return <div className="migration-page">
    <div className="page-heading migration-heading">
      <div><div className="eyebrow">Данные и восстановление</div><h1>Миграция данных из браузера</h1><p>Сначала сервер проверит копию без записи. Импорт станет доступен только после проверки связей и назначений. Серверная JSON-копия — это логический экспорт, а не операционный backup PostgreSQL</p></div>
      <button className="btn secondary" disabled={exportPending} onClick={() => void exportServerBackup()}><Download size={17}/>{exportPending ? 'Готовим копию…' : 'Скачать логическую JSON-копию'}</button>
    </div>
    {exportError&&<div className="migration-alert error" role="alert">{exportError}<button className="btn small" onClick={() => void exportServerBackup()}>Повторить</button></div>}

    <section className="migration-card" aria-labelledby={`${inputId}-source`}>
      <div className="migration-step"><span>1</span><div><h2 id={`${inputId}-source`}>Выберите локальную копию</h2><p>Поддерживаются AppData v1–v3, не более 5 МиБ. Файл не изменяется и не импортируется автоматически</p></div></div>
      <div className="migration-file-row">
        <button className="btn primary" disabled={flow==='validating'||flow==='importing'} onClick={() => fileInput.current?.click()}><FileArrowUp size={17}/> Выбрать JSON-файл</button>
        {browserCopy&&<button className="btn secondary" disabled={flow==='validating'||flow==='importing'} onClick={() => loadText(browserCopy, 'Копия из этого браузера')}><ShieldCheck size={17}/> Взять копию из этого браузера</button>}
        <span>{sourceName || 'Файл не выбран'}</span>
        <input ref={fileInput} id={inputId} type="file" accept="application/json,.json" disabled={flow==='validating'||flow==='importing'} hidden onChange={event => void chooseFile(event)}/>
      </div>
      {source&&<div className="migration-source-meta"><span>Версия в файле <strong>{typeof source.version === 'number' ? source.version : 'не указана'}</strong></span><span>Групп для назначения <strong>{groups.length}</strong></span><span>Размер запроса <strong>{Math.ceil(requestBytes(source, assignments) / 1024)} КиБ</strong></span></div>}
      {error&&flow!=='uncertain'&&<p className="migration-inline-error" role="alert">{error}</p>}
    </section>

    {source&&<section className="migration-card" aria-labelledby="migration-assignments-title">
      <div className="migration-step"><span>2</span><div><h2 id="migration-assignments-title">Проверьте назначения кураторов</h2><p>Legacy ID не сопоставляются с server ID автоматически. Каждую группу нужно назначить явно</p></div></div>
      {curatorState==='loading'&&<div className="migration-loading" role="status"><span className="account-spinner"/>Загружаем кураторов…</div>}
      {curatorState==='error'&&<div className="migration-alert error" role="alert">{curatorError}<button className="btn small" onClick={() => void loadCurators()}>Повторить</button></div>}
      {curatorState==='ready'&&groups.length===0&&<p className="migration-muted">В файле нет распознанных групп. Сервер проверит структуру коллекции на следующем шаге</p>}
      {curatorState==='ready'&&groups.length>0&&<div className="migration-assignments">{groups.map(group=><label key={group.id}><span><strong>{group.name}</strong><small>Назначение применяется только к этой группе</small></span><Select disabled={flow==='validating'||flow==='importing'} aria-label={`Куратор группы ${group.name}`} value={assignments[group.id] ?? ''} onChange={event => changeAssignment(group.id, event.target.value)}><option value="">Выберите куратора</option>{curators.map(curator=><option key={curator.id} value={curator.id}>{curator.login}{curator.is_owner?' · владелец':''}</option>)}</Select></label>)}</div>}
    </section>}

    {source&&<section className="migration-card" aria-labelledby="migration-validation-title">
      <div className="migration-step"><span>3</span><div><h2 id="migration-validation-title">Проверка без записи</h2><p>Сервер проверит связи, дубликаты, конфликты, статусы и поддерживаемые поля. База данных не изменится</p></div></div>
      <button className="btn dark" disabled={flow==='validating'||flow==='importing'||curatorState!=='ready'||!assignmentsComplete} onClick={() => void validate()}>{flow==='validating'?<span className="account-spinner"/>:<ShieldCheck size={17}/>} {flow==='validating'?'Проверяем…':'Проверить данные'}</button>
      {flow==='uncertain'&&<div className="migration-alert warning" role="alert"><WarningCircle size={20}/><div><strong>Результат импорта неизвестен</strong><p>{error}</p><p>Выберите «Проверить данные» заново. Повторный импорт будет доступен только после новой проверки и подтверждения</p></div></div>}
    </section>}

    {report&&<section className={`migration-card migration-preview ${report.valid?'valid':'invalid'}`} aria-labelledby="migration-preview-title">
      <div className="migration-step"><span>{report.valid?<CheckCircle size={20}/>:<WarningCircle size={20}/>}</span><div><h2 id="migration-preview-title">Результат проверки</h2><p>{report.valid?'Запись в базу ещё не выполнялась. Сверьте состав и подтвердите импорт':'Импорт заблокирован до устранения конфликтов'}</p></div></div>
      <div className="migration-checksum"><span>Контрольная сумма подтверждения</span><code>{report.checksum}</code></div>
      <div className="migration-counts">{Object.entries(report.counts).map(([key,value])=><div key={key}><span>{countLabels[key]??key}</span><strong>{value}</strong></div>)}</div>
      <div className="migration-relationships"><h3>Связи, которые будут перенесены</h3><p>{report.counts.groups??0} групп → {report.counts.students??0} учениц → {report.counts.strategies??0} стратегий</p><p>{report.counts.sections??0} разделов → {report.counts.tasks??0} задач; {report.counts.homeworks??0} ДЗ → {report.counts.homework_items??0} неизменяемых снимков</p></div>
      <div className="migration-reviewed-assignments"><h3>Назначения групп</h3>{groups.map(group=><div key={group.id}><span>{group.name}</span><strong>{curators.find(curator=>curator.id===assignments[group.id])?.login??'Не назначен'}</strong></div>)}</div>
      {conflicts.length>0&&<div className="migration-conflicts" role="alert"><h3>Конфликты и неподдерживаемые записи</h3><ul>{conflicts.map(conflict=><li key={`${conflict.code}:${conflict.entity}`}>{conflictLabel(conflict)}</li>)}</ul></div>}
      {report.warnings.length>0&&<div className="migration-warnings"><h3>Ограничения</h3><ul>{report.warnings.map((warning,index)=><li key={index}>{warningLabel(warning)}</li>)}</ul></div>}
      {report.valid&&<div className="migration-confirmation">
        <label><input type="checkbox" checked={confirmed} disabled={flow==='importing'} onChange={event => setConfirmed(event.target.checked)}/><span>Количество записей, связи и назначения кураторов сверены. Следующий шаг запишет данные на сервер</span></label>
        <button className="btn primary" disabled={!confirmed||flow==='importing'} onClick={() => void importData()}>{flow==='importing'?<span className="account-spinner"/>:<FileArrowUp size={17}/>} {flow==='importing'?'Импортируем…':'Импортировать на сервер'}</button>
      </div>}
    </section>}

    {flow==='complete'&&result&&<section className="migration-card migration-complete" role="status">
      <CheckCircle size={30}/><div><h2>{result.idempotent_replay?'Импорт уже был выполнен':'Миграция завершена'}</h2><p>Серверные данные стали источником истины. Локальные копии из браузера сохранены без изменений</p><small>Импортировано записей: {Object.values(result.counts).reduce((sum,value)=>sum+value,0)}</small></div>
      <button className="btn secondary" onClick={() => void onCutover()}><ArrowClockwise size={17}/> Обновить данные с сервера</button>
    </section>}
  </div>
}
