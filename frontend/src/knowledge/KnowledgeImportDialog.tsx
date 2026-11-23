import { useId, useRef, useState, type ChangeEvent } from 'react'
import { CheckCircleIcon as CheckCircle, FileArrowUpIcon as FileArrowUp, ShieldCheckIcon as ShieldCheck, WarningCircleIcon as WarningCircle } from '@phosphor-icons/react'
import type { KnowledgeConflictAction, KnowledgeConflictResolution, KnowledgeImportRequest, KnowledgeImportResult, KnowledgeImportValidation, KnowledgeKind } from '../api/contracts'
import { knowledgeApi } from '../api/knowledge'
import { ApiError } from '../api/http'
import { Dialog } from '../Dialogs'
import { parseKnowledgeFile, readKnowledgeBackup } from '../knowledge'
import Select from '../Select'
import { importRequestBytes, knowledgeDataSource, knowledgeImportErrorMessage, MAX_KNOWLEDGE_IMPORT_BYTES, parsedDocumentsSource } from './knowledgeState'

type ImportSource = Pick<KnowledgeImportRequest, 'source' | 'source_format' | 'mode'>
type Flow = 'idle' | 'ready' | 'validating' | 'validated' | 'importing' | 'uncertain' | 'complete'

const countLabels: Record<string, string> = {
  new_documents: 'Новые материалы', exact_duplicates: 'Точные дубликаты', conflicts: 'Конфликты',
  resolved_conflicts: 'Решённые конфликты', archived_records: 'Архивные записи', skipped_records: 'Пропущенные записи',
  imported_documents: 'Импортированные материалы', overwritten_documents: 'Обновлённые материалы', created_copies: 'Созданные копии',
  skipped_conflicts: 'Пропущенные конфликты', unsupported_records: 'Неподдерживаемые записи',
}

const issueLabels: Record<string, string> = {
  unsupported_version: 'Неподдерживаемая версия копии', unsupported_field: 'Есть неподдерживаемые поля',
  invalid_collection: 'Некорректная коллекция материалов', invalid_record: 'Некорректная запись',
  invalid_source_identity: 'Не удалось определить исходную запись', invalid_title: 'Не указано название',
  invalid_content: 'Материал не содержит допустимого текста', invalid_category: 'Некорректная категория',
  invalid_position: 'Некорректный порядок', invalid_flag: 'Некорректный признак записи',
  unsupported_document_format: 'Неподдерживаемый формат документа', duplicate_source_key: 'Повторяется идентификатор исходной записи',
  content_conflict: 'Материал уже изменён на сервере', version_conflict: 'Версия материала изменилась',
  resolution_without_conflict: 'Решение больше не относится к конфликту',
}

function fileFormat(file: File): 'docx' | 'html' | 'markdown' {
  const name = file.name.toLowerCase()
  if (name.endsWith('.docx')) return 'docx'
  if (name.endsWith('.html') || name.endsWith('.htm')) return 'html'
  return 'markdown'
}

export default function KnowledgeImportDialog({ open, initial, kind, onClose, onComplete }: {
  open: boolean
  initial: boolean
  kind: KnowledgeKind
  onClose: () => void
  onComplete: (result: KnowledgeImportResult) => void | Promise<void>
}) {
  const inputId = useId()
  const fileInput = useRef<HTMLInputElement>(null)
  const pendingRef = useRef(false)
  const [flow, setFlow] = useState<Flow>('idle')
  const [prepared, setPrepared] = useState<ImportSource | null>(null)
  const [sourceName, setSourceName] = useState('')
  const [report, setReport] = useState<KnowledgeImportValidation | null>(null)
  const [resolutions, setResolutions] = useState<Record<string, KnowledgeConflictResolution>>({})
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<KnowledgeImportResult | null>(null)

  const resetPreview = (next: ImportSource, name: string) => {
    setPrepared(next); setSourceName(name); setReport(null); setResolutions({}); setConfirmed(false); setResult(null); setError(''); setFlow('ready')
  }

  const loadLocalCopy = async () => {
    try {
      const data = await readKnowledgeBackup()
      if (!data) { setError('На этом устройстве нет сохранённой копии KnowledgeData v1'); return }
      resetPreview({ source: knowledgeDataSource(data), source_format: 'knowledge_data_v1', mode: 'initial' }, 'Копия KnowledgeData v1 из этого браузера')
    } catch { setError('Не удалось прочитать локальную копию. Она не изменена') }
  }

  const chooseFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (file.size > MAX_KNOWLEDGE_IMPORT_BYTES) { setError('Файл превышает допустимые 5 МиБ'); return }
    try {
      if (file.name.toLowerCase().endsWith('.json')) {
        const raw = JSON.parse(await file.text()) as unknown
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('invalid')
        resetPreview({ source: raw as Record<string, unknown>, source_format: 'knowledge_data_v1', mode: initial ? 'initial' : 'additional' }, file.name)
      } else {
        if (initial) throw new Error('initial_requires_backup')
        const uiKind = kind === 'prompt' ? 'prompts' : 'chapters'
        const records = await parseKnowledgeFile(file, uiKind)
        resetPreview({ source: parsedDocumentsSource(records, kind, fileFormat(file)), source_format: 'parsed_documents', mode: 'additional' }, file.name)
      }
    } catch (caught) {
      setError(caught instanceof Error && caught.message === 'initial_requires_backup'
        ? 'Для первой активации выберите JSON-копию KnowledgeData v1'
        : 'Не удалось прочитать файл. Локальная копия не изменена')
    }
  }

  const request = (): KnowledgeImportRequest | null => prepared ? { ...prepared, resolutions } : null

  const validate = async () => {
    const payload = request()
    if (!payload || pendingRef.current) return
    if (importRequestBytes(payload) > MAX_KNOWLEDGE_IMPORT_BYTES) { setError('Запрос превышает допустимые 5 МиБ'); return }
    pendingRef.current = true; setFlow('validating'); setError(''); setConfirmed(false)
    try { setReport(await knowledgeApi.validateImport(payload)); setFlow('validated') }
    catch (caught) { setReport(null); setFlow('ready'); setError(knowledgeImportErrorMessage(caught)) }
    finally { pendingRef.current = false }
  }

  const setResolution = async (sourceKey: string, action: KnowledgeConflictAction, targetId: string | null) => {
    setError(''); setConfirmed(false); setReport(current => current ? { ...current, valid: false } : current)
    if (action !== 'overwrite') { setResolutions(current => ({ ...current, [sourceKey]: { action } })); return }
    if (!targetId) { setError('Сервер не указал материал для обновления. Выберите пропуск или создание копии'); return }
    try {
      const target = await knowledgeApi.get(targetId)
      setResolutions(current => ({ ...current, [sourceKey]: { action, expected_version: target.version } }))
    } catch (caught) { setError(knowledgeImportErrorMessage(caught)) }
  }

  const confirmImport = async () => {
    const payload = request()
    if (!payload || !report?.valid || !confirmed || pendingRef.current) return
    const confirmedRequest = { ...payload, confirmation_checksum: report.checksum, confirm: true }
    if (importRequestBytes(confirmedRequest) > MAX_KNOWLEDGE_IMPORT_BYTES) { setError('Подтверждённый запрос превышает допустимые 5 МиБ'); return }
    pendingRef.current = true; setFlow('importing'); setError('')
    try {
      const next = await knowledgeApi.confirmImport(confirmedRequest)
      setResult(next); setFlow('complete'); setConfirmed(false); await onComplete(next)
    } catch (caught) {
      setConfirmed(false); setReport(null)
      setFlow(caught instanceof ApiError && caught.code === 'connection_error' ? 'uncertain' : 'ready')
      setError(knowledgeImportErrorMessage(caught, 'import'))
    } finally { pendingRef.current = false }
  }

  const close = () => { if (!pendingRef.current) { setFlow('idle'); setPrepared(null); setSourceName(''); setReport(null); setResolutions({}); setConfirmed(false); setResult(null); setError(''); onClose() } }
  const conflicts = report?.items.filter(item => item.classification === 'conflict') ?? []

  return <Dialog open={open} title={initial ? 'Перенести локальную базу знаний' : 'Импортировать материалы'} description={initial ? 'Проверка не записывает данные. Активация выполняется только после отдельного подтверждения' : 'Сначала сервер покажет новые записи, дубликаты и конфликты без записи'} onClose={close} wide dismissible={!pendingRef.current}>
    <div className="knowledge-import-flow">
      <div className="knowledge-import-source">
        {initial && <button className="btn secondary" disabled={flow==='validating'||flow==='importing'} onClick={() => void loadLocalCopy()}><ShieldCheck size={17}/> Использовать копию этого браузера</button>}
        <button className="btn primary" disabled={flow==='validating'||flow==='importing'} onClick={() => fileInput.current?.click()}><FileArrowUp size={17}/> Выбрать файл</button>
        <input ref={fileInput} id={inputId} hidden type="file" accept={initial ? 'application/json,.json' : '.docx,.html,.htm,.md,.markdown,.json'} onChange={event => void chooseFile(event)}/>
        <span>{sourceName || (initial ? 'KnowledgeData v1 не выбрана' : 'Файл не выбран')}</span>
      </div>
      {prepared && <div className="knowledge-import-meta"><span>Источник <strong>{prepared.source_format === 'knowledge_data_v1' ? 'KnowledgeData v1' : 'разобранные документы'}</strong></span><span>Режим <strong>{initial ? 'первая активация' : 'добавление'}</strong></span><span>Размер <strong>{Math.ceil(importRequestBytes(request()!) / 1024)} КиБ</strong></span></div>}
      {error && <div className={`knowledge-alert error ${flow==='uncertain'?'warning':''}`} role="alert"><WarningCircle size={18}/><span>{error}</span>{flow==='uncertain'&&<button className="btn small" onClick={() => void validate()}>Проверить заново</button>}</div>}
      {prepared && flow !== 'complete' && <button className="btn dark" disabled={flow==='validating'||flow==='importing'} onClick={() => void validate()}>{flow==='validating'?<span className="account-spinner"/>:<ShieldCheck size={17}/>} {report ? 'Проверить решения заново' : 'Проверить без записи'}</button>}
      {report && <section className={`knowledge-import-preview ${report.valid?'valid':'invalid'}`} aria-live="polite">
        <div className="knowledge-import-preview-head">{report.valid?<CheckCircle size={24}/>:<WarningCircle size={24}/>}<div><h3>{report.valid ? 'Проверка пройдена' : 'Нужно решить конфликты'}</h3><p>{report.valid ? 'На сервер ещё ничего не записано' : 'Импорт остаётся заблокированным'}</p></div></div>
        <div className="knowledge-import-counts">{Object.entries(report.counts).map(([key,value])=><div key={key}><span>{countLabels[key] ?? key}</span><strong>{value}</strong></div>)}</div>
        {report.issues.length>0&&<div className="knowledge-import-issues" role="alert"><h4>Ограничения</h4><ul>{report.issues.map((issue,index)=><li key={`${issue.code}:${issue.source_key}:${index}`}>{issueLabels[issue.code] ?? 'Запись требует проверки'}{issue.fields.length ? `: ${issue.fields.join(', ')}` : ''}</li>)}</ul></div>}
        {conflicts.length>0&&<div className="knowledge-import-conflicts"><h4>Решения по конфликтам</h4>{conflicts.map((item,index)=><label key={item.source_key}><span>Конфликт {index+1}<small>{item.conflict_code ? issueLabels[item.conflict_code] ?? 'Материал отличается от серверной версии' : 'Материал отличается от серверной версии'}</small></span><Select aria-label={`Решение конфликта ${index+1}`} value={resolutions[item.source_key]?.action ?? ''} onChange={event => void setResolution(item.source_key,event.target.value as KnowledgeConflictAction,item.target_id)}><option value="">Выберите действие</option><option value="skip">Пропустить</option><option value="create_copy">Создать отдельную копию</option><option value="overwrite">Обновить серверную версию</option></Select></label>)}</div>}
        {report.valid&&<div className="knowledge-import-confirm"><code title="Контрольная сумма">{report.checksum}</code><label><input type="checkbox" checked={confirmed} disabled={flow==='importing'} onChange={event=>setConfirmed(event.target.checked)}/><span>Я сверила результат проверки и подтверждаю запись на сервер. Локальная копия останется без изменений</span></label><button className="btn primary" disabled={!confirmed||flow==='importing'} onClick={() => void confirmImport()}>{flow==='importing'?<span className="account-spinner"/>:<FileArrowUp size={17}/>} {flow==='importing'?'Импортируем…':initial?'Импортировать и активировать':'Импортировать'}</button></div>}
      </section>}
      {flow==='complete'&&result&&<div className="knowledge-import-complete" role="status"><CheckCircle size={28}/><div><h3>{result.idempotent_replay?'Импорт уже был выполнен':'Импорт завершён'}</h3><p>{initial?'Серверная база знаний активирована':'Материалы доступны всем авторизованным кураторам'}. Исходные данные браузера не изменены</p></div><button className="btn secondary" onClick={close}>Готово</button></div>}
    </div>
  </Dialog>
}
