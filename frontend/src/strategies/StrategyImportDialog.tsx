import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { CaretDownIcon as CaretDown, CheckCircleIcon as CheckCircle, FileArrowUpIcon as FileArrowUp, WarningCircleIcon as WarningCircle } from '@phosphor-icons/react'
import type { StrategyImportDraft, StrategyImportResult } from '../api/contracts'
import { strategiesApi } from '../api/strategies'
import { STUDY_STATUS } from '../data'
import { Dialog } from '../Dialogs'
import type { Student } from '../types'
import { buildImportPayload, countLabel, currentProfileValue, defaultProfileSelection, importWarningLabel, MAX_STRATEGY_PDF_BYTES, profileFieldLabels, sourceNameMismatch, statusCounts, strategyImportErrorMessage, taskTotal, type ProfileField, type ProfileSelection } from './strategyImportState'

type Flow = 'idle' | 'reading' | 'preview' | 'importing' | 'complete'
const profileFields: ProfileField[] = ['point_a', 'point_b', 'telegram']

export default function StrategyImportDialog({ open, student, onClose, onImported }: {
  open: boolean
  student: Student
  onClose: () => void
  onImported: (result: StrategyImportResult) => void | Promise<void>
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const pendingRef = useRef(false)
  const [flow, setFlow] = useState<Flow>('idle')
  const [fileName, setFileName] = useState('')
  const [draft, setDraft] = useState<StrategyImportDraft | null>(null)
  const [selection, setSelection] = useState<ProfileSelection>({ point_a: false, point_b: false, telegram: false })
  const [expanded, setExpanded] = useState<number[]>([])
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<StrategyImportResult | null>(null)

  const reset = () => { setFlow('idle'); setFileName(''); setDraft(null); setExpanded([]); setError(''); setResult(null) }
  const close = () => { if (pendingRef.current) return; reset(); onClose() }

  const readFile = async (file: File | undefined) => {
    if (!file || pendingRef.current) return
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') { setError('Выберите PDF, экспортированный из Notion'); return }
    if (file.size > MAX_STRATEGY_PDF_BYTES) { setError('Файл больше 10 МБ. Экспортируйте страницу без вложенных страниц'); return }
    pendingRef.current = true
    setFlow('reading'); setError(''); setDraft(null); setFileName(file.name)
    try {
      const next = await strategiesApi.previewImport(student.id, file)
      setDraft(next); setSelection(defaultProfileSelection(student, next.profile)); setExpanded([]); setFlow('preview')
    } catch (caught) {
      setFlow('idle'); setError(strategyImportErrorMessage(caught))
    } finally { pendingRef.current = false }
  }

  const chooseFile = (event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; event.target.value = ''; void readFile(file) }
  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(false); void readFile(event.dataTransfer.files?.[0]) }

  const confirm = async () => {
    if (!draft || pendingRef.current) return
    pendingRef.current = true
    setFlow('importing'); setError('')
    try {
      const next = await strategiesApi.applyImport(student.id, buildImportPayload(draft, student, selection, fileName))
      setResult(next); setFlow('complete')
      await onImported(next)
    } catch (caught) {
      setFlow('preview'); setError(strategyImportErrorMessage(caught))
    } finally { pendingRef.current = false }
  }

  const busy = flow === 'reading' || flow === 'importing'
  const total = draft ? taskTotal(draft) : 0
  const mismatch = draft ? sourceNameMismatch(draft, student) : null

  return <Dialog open={open} title="Импорт стратегии из Notion" description="Файл только читается. Ничего не запишется, пока вы не подтвердите импорт" onClose={close} wide dismissible={!busy}>
    <div className="knowledge-import-flow strategy-import">
      {flow !== 'complete' && <div className={`strategy-import-drop ${dragging ? 'is-dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        <FileArrowUp size={26}/>
        <div><strong>{fileName || 'Перетащите PDF сюда'}</strong><p>В Notion откройте стратегию, затем ··· → Export → PDF</p></div>
        <button className="btn primary" disabled={busy} onClick={() => fileInput.current?.click()}>{flow === 'reading' ? <><span className="account-spinner"/>Читаем файл…</> : fileName ? 'Выбрать другой файл' : 'Выбрать PDF'}</button>
        <input ref={fileInput} hidden type="file" accept="application/pdf,.pdf" onChange={chooseFile}/>
      </div>}
      {error && <div className="knowledge-alert error" role="alert"><WarningCircle size={18}/><span>{error}</span></div>}
      {draft && flow !== 'complete' && <section className="knowledge-import-preview valid" aria-live="polite">
        <div className="knowledge-import-preview-head"><CheckCircle size={24}/><div><h3>{draft.source_title || 'Стратегия из Notion'}</h3><p>{countLabel(draft.sections.length, 'раздел', 'раздела', 'разделов')} · {countLabel(total, 'задача', 'задачи', 'задач')} · {draft.page_count} стр.</p></div></div>
        {mismatch && <div className="knowledge-alert warning" role="alert"><WarningCircle size={18}/><span>В файле указано имя «{mismatch}», а профиль — «{student.name}». Проверьте, что выбран нужный файл</span></div>}
        <div className="knowledge-import-counts">{statusCounts(draft).map(([status, label, count]) => <div key={status}><span>{label}</span><strong>{count}</strong></div>)}</div>
        <div className="strategy-import-sections">
          <h4>Разделы и задачи</h4>
          {draft.sections.map((section, index) => {
            const open = expanded.includes(index)
            return <div className="strategy-import-section" key={`${index}:${section.title}`}>
              <button type="button" aria-expanded={open} onClick={() => setExpanded(current => open ? current.filter(item => item !== index) : [...current, index])}><span>{section.title}</span><small>{countLabel(section.tasks.length, 'задача', 'задачи', 'задач')}</small><CaretDown size={16} className={open ? 'is-open' : ''}/></button>
              {open && <ol>{section.tasks.map((task, taskIndex) => <li key={taskIndex}><span>{task.title}</span><small className={`strategy-import-status status-${task.study_status}`}>{STUDY_STATUS[task.study_status]}</small></li>)}</ol>}
            </div>
          })}
        </div>
        {profileFields.some(field => draft.profile[field]) && <div className="strategy-import-profile">
          <h4>Заполнить профиль</h4>
          {profileFields.filter(field => draft.profile[field]).map(field => {
            const current = currentProfileValue(student, field).trim()
            return <label key={field}>
              <input type="checkbox" checked={selection[field]} disabled={busy} onChange={event => setSelection(value => ({ ...value, [field]: event.target.checked }))}/>
              <span><strong>{profileFieldLabels[field]}{current ? ' · заменит текущее значение' : ''}</strong><small>{draft.profile[field]}</small></span>
            </label>
          })}
        </div>}
        {draft.warnings.length > 0 && <div className="knowledge-import-issues strategy-import-notes"><h4>Проверьте после импорта</h4><ul>{draft.warnings.map(warning => <li key={warning.code}>{importWarningLabel(warning.code)}{` · ${countLabel(warning.count, 'задача', 'задачи', 'задач')}`}</li>)}</ul></div>}
        <div className="dialog-actions"><button className="btn secondary" disabled={busy} onClick={close}>Отмена</button><button className="btn primary" disabled={busy} onClick={() => void confirm()}>{flow === 'importing' ? <><span className="account-spinner"/>Импортируем…</> : `Импортировать ${countLabel(total, 'задачу', 'задачи', 'задач')}`}</button></div>
      </section>}
      {flow === 'complete' && result && <div className="knowledge-import-complete" role="status"><CheckCircle size={28}/><div><h3>Стратегия заполнена</h3><p>Добавлено разделов: {result.section_count}, задач: {result.task_count}. Названия и статусы можно поправить в стратегии</p></div><button className="btn primary" onClick={close}>Открыть стратегию</button></div>}
    </div>
  </Dialog>
}
