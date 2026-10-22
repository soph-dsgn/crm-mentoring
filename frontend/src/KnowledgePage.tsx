import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeftIcon as ArrowLeft, BookOpenIcon as BookOpen, CheckIcon as Check, CaretRightIcon as ChevronRight, CopyIcon as Copy, DownloadIcon as Download, FilePlusIcon as FilePlus2, PencilIcon as Pencil, PlusIcon as Plus, MagnifyingGlassIcon as Search, StarIcon as Star, TrashIcon as Trash2, UploadIcon as Upload, XIcon as X } from '@phosphor-icons/react'
import Select from './Select'
import { cleanHtml, copyKnowledge, downloadKnowledge, htmlToText, loadKnowledge, mergeKnowledge, parseKnowledgeFile, saveKnowledge } from './knowledge'
import type { KnowledgeData, KnowledgeKind, KnowledgeRecord } from './knowledge'
import { useCalmMotion } from './motion'
import { useDialogA11y } from './dialogA11y'

const CATEGORIES = ['Все', 'Резюме', 'Сопроводительные письма', 'Кейсы', 'Портфолио', 'Собеседования', 'Другие']
const empty = (kind: KnowledgeKind): KnowledgeRecord => ({
  id: `custom-${crypto.randomUUID()}`, title: '', category: kind === 'prompts' ? 'Другие' : undefined,
  html: '<p></p>', text: '', sourceId: 'user', sourceRevision: '', sourceHash: '', edited: true,
  deleted: false, favorite: false, updatedAt: new Date().toISOString(),
})

export default function KnowledgePage({ kind }: { kind: KnowledgeKind }) {
  const calm=useCalmMotion()
  const [data, setData] = useState<KnowledgeData | null>(null)
  const dataRef = useRef<KnowledgeData | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('Все')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editor, setEditor] = useState<KnowledgeRecord | null>(null)
  const editorDialogRef=useDialogA11y(Boolean(editor),()=>setEditor(null))
  const [copied, setCopied] = useState(false)
  const [headings, setHeadings] = useState<{ id: string; text: string; level: number }[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const editorRef = useRef<HTMLDivElement>(null)
  const articleRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    loadKnowledge().then(value => { if (!cancelled) { dataRef.current = value; setData(value) } })
      .catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : 'Не удалось открыть базу знаний') })
    return () => { cancelled = true }
  }, [])

  const records = useMemo(() => (data?.[kind] || []).filter(record => !record.deleted)
    .sort((a, b) => kind === 'chapters' ? (a.order ?? 0) - (b.order ?? 0) : a.title.localeCompare(b.title, 'ru')), [data, kind])
  const filtered = useMemo(() => records.filter(record => {
    const match = !query.trim() || `${record.title} ${record.text}`.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru').trim())
    return match && (kind === 'chapters' || category === 'Все' || record.category === category) && (!favoritesOnly || record.favorite)
  }), [records, query, category, favoritesOnly, kind])
  const selected = filtered.find(record => record.id === selectedId) || filtered[0] || null

  useEffect(() => {
    if (kind !== 'chapters' || !articleRef.current) { setHeadings([]); return }
    const found = [...articleRef.current.querySelectorAll('h1, h2, h3')].map((node, index) => {
      const id = `knowledge-heading-${index}`
      node.id = id
      return { id, text: node.textContent?.trim() || '', level: Number(node.tagName.slice(1)) }
    }).filter(item => item.text)
    setHeadings(found)
  }, [selected?.id, selected?.html, kind])

  const commit = async (update: (old: KnowledgeData) => KnowledgeData) => {
    const old = dataRef.current
    if (!old) return
    const next = update(old)
    dataRef.current = next
    setData(next)
    try { await saveKnowledge(next); setError('') } catch { setError('Не удалось сохранить изменения. Экспортируйте данные и проверьте свободное место браузера') }
  }
  const patchRecord = (id: string, patch: Partial<KnowledgeRecord>) => commit(old => ({ ...old,
    [kind]: old[kind].map(record => record.id === id ? { ...record, ...patch, updatedAt: new Date().toISOString() } : record),
  }))
  const saveEditor = async () => {
    if (!editor?.title.trim()) { setError('Укажите название материала'); return }
    const html = cleanHtml(editorRef.current?.innerHTML || editor.html)
    if (!htmlToText(html)) { setError('Добавьте текст материала'); return }
    const record = { ...editor, html, text: htmlToText(html), edited: true, updatedAt: new Date().toISOString() }
    await commit(old => ({ ...old, [kind]: old[kind].some(item => item.id === record.id)
      ? old[kind].map(item => item.id === record.id ? record : item)
      : [...old[kind], { ...record, order: kind === 'chapters' ? old.chapters.length : undefined }],
    }))
    setSelectedId(record.id)
    setEditor(null)
    setNotice('Материал сохранён')
  }
  const remove = async (record: KnowledgeRecord) => {
    if (!confirm(`Удалить «${record.title}»? Материал останется в резервной копии`)) return
    await patchRecord(record.id, { deleted: true, edited: true })
    setSelectedId(null)
    setNotice('Материал удалён')
  }
  const onImport = async (file?: File) => {
    if (!file || !dataRef.current) return
    setError('')
    try {
      if (file.name.toLowerCase().endsWith('.json')) {
        const backup = JSON.parse(await file.text()) as KnowledgeData
        if (backup.version !== 1 || !Array.isArray(backup.prompts) || !Array.isArray(backup.chapters)) throw new Error('Файл не похож на резервную копию базы знаний')
        const p = mergeKnowledge(dataRef.current.prompts, backup.prompts)
        const c = mergeKnowledge(dataRef.current.chapters, backup.chapters)
        if (!confirm(`Восстановить данные? Новых: ${p.added + c.added}, обновлений: ${p.updated + c.updated}. Изменённые и удалённые материалы защищены: ${p.protectedCount + c.protectedCount}`)) return
        await commit(old => ({ ...old, prompts: p.records, chapters: c.records }))
        setNotice(`Добавлено ${p.added + c.added}, обновлено ${p.updated + c.updated}, сохранено без изменений ${p.protectedCount + c.protectedCount}`)
      } else {
        const parsed = await parseKnowledgeFile(file, kind)
        const result = mergeKnowledge(dataRef.current[kind], parsed)
        if (!confirm(`Импортировать ${parsed.length} материалов из «${file.name}»? Новых: ${result.added}, обновлений: ${result.updated}, защищённых пользовательских правок: ${result.protectedCount}`)) return
        await commit(old => ({ ...old, [kind]: result.records }))
        setNotice(`Добавлено ${result.added}, обновлено ${result.updated}, без дубликатов ${result.unchanged}; правки защищены: ${result.protectedCount}`)
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Импорт не удался') }
  }
  const copy = async (record: KnowledgeRecord) => {
    try { await copyKnowledge(record); setCopied(true); setTimeout(() => setCopied(false), 1800) }
    catch { setError('Копирование не удалось. Проверьте разрешение браузера на буфер обмена') }
  }

  return <div className="knowledge-page">
    <header className="knowledge-head">
      <div><h1>{kind === 'prompts' ? 'Промпты' : 'Учебник'}</h1><p>{kind === 'prompts' ? `${records.length} записей · исходный документ «МЕНТОРИНГ»` : `${records.length} разделов · исходный документ «Погружение в IT»`}</p></div>
      <div className="knowledge-head-actions">
        <button className="btn secondary" onClick={() => inputRef.current?.click()}><Upload size={16}/> Импорт</button>
        <button className="btn secondary" onClick={() => data && downloadKnowledge(data)} disabled={!data}><Download size={16}/> Экспорт</button>
        <button className="btn primary" onClick={() => setEditor(empty(kind))}><Plus size={16}/> {kind === 'prompts' ? 'Промпт' : 'Раздел'}</button>
        <input ref={inputRef} hidden type="file" accept=".docx,.html,.htm,.md,.markdown,.json" onChange={event => { void onImport(event.target.files?.[0]); event.target.value = '' }}/>
      </div>
    </header>
    {error && <div className="knowledge-alert error" role="alert">{error}</div>}
    {notice && <div className="knowledge-alert">{notice}<button onClick={() => setNotice('')} aria-label="Закрыть"><X size={14}/></button></div>}
    {!data ? <div className="knowledge-loading">Загружаем материалы…</div> : <div className="knowledge-layout">
      <aside className="knowledge-index">
        <label className="knowledge-search"><Search size={17}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Поиск по содержимому"/></label>
        {kind === 'prompts' && <><div className="knowledge-categories">{CATEGORIES.map(item => <button key={item} className={category === item ? 'active' : ''} onClick={() => setCategory(item)}>{item}</button>)}</div><button className={`knowledge-favorites ${favoritesOnly ? 'active' : ''}`} onClick={() => setFavoritesOnly(!favoritesOnly)}><Star size={15} fill={favoritesOnly ? 'currentColor' : 'none'}/> Избранное</button></>}
        <div className="knowledge-index-count">{filtered.length} {kind === 'prompts' ? 'записей' : 'разделов'}</div>
        <div className="knowledge-index-list">
          {filtered.map(record => <button key={record.id} className={`knowledge-index-item ${selected?.id === record.id ? 'active' : ''}`} onClick={() => setSelectedId(record.id)}><span><strong>{record.title}</strong>{kind === 'prompts' && <small>{record.category}</small>}</span><ChevronRight size={16}/></button>)}
          {!filtered.length && <div className="knowledge-no-results">Ничего не найдено. Попробуйте другой запрос</div>}
        </div>
      </aside>
      <section className="knowledge-reader">
        {selected ? <>
          <div className="knowledge-reader-head"><div><span>{kind === 'prompts' ? selected.category : 'Раздел учебника'}</span><h2>{selected.title}</h2></div><div className="knowledge-reader-actions">
            {kind === 'prompts' && <button aria-label={selected.favorite ? 'Убрать из избранного' : 'В избранное'} title="Избранное" onClick={() => patchRecord(selected.id, { favorite: !selected.favorite })}><Star size={17} fill={selected.favorite ? 'currentColor' : 'none'}/></button>}
            <button title="Редактировать" aria-label="Редактировать" onClick={() => setEditor({ ...selected })}><Pencil size={17}/></button>
            <button title="Удалить" aria-label="Удалить" onClick={() => remove(selected)}><Trash2 size={17}/></button>
          </div></div>
          <div className="knowledge-source">{selected.sourceId === 'user' ? 'Мой материал' : selected.sourceId.startsWith('file:') ? `Импорт: ${selected.sourceId.slice(5)}` : 'Исходный документ Google Docs'}{selected.edited && ' · изменён'}</div>
          {kind === 'chapters' && headings.length > 1 && <nav className="knowledge-toc" aria-label="В этом разделе"><strong>В этом разделе</strong><div>{headings.slice(1).map(heading => <button key={heading.id} className={heading.level === 3 ? 'nested' : ''} onClick={() => document.getElementById(heading.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{heading.text}</button>)}</div></nav>}
          <article key={selected.id} ref={articleRef} className="knowledge-article" dangerouslySetInnerHTML={{ __html: cleanHtml(selected.html) }}/>
          <div className="knowledge-reader-foot"><button className="btn primary" onClick={() => copy(selected)}>{copied ? <Check size={16}/> : <Copy size={16}/>} {copied ? 'Скопировано' : kind === 'prompts' ? 'Скопировать промпт' : 'Скопировать раздел'}</button></div>
        </> : <div className="knowledge-empty"><BookOpen size={28}/><h2>Пока здесь пусто</h2><p>Добавьте материал или импортируйте DOCX, HTML или Markdown</p><button className="btn primary" onClick={() => inputRef.current?.click()}><FilePlus2 size={16}/> Импортировать</button></div>}
      </section>
    </div>}
    <AnimatePresence initial={false}>{editor && <motion.div key="knowledge-editor" className="modal-backdrop" {...calm.backdrop} onMouseDown={event => { if (event.target === event.currentTarget) setEditor(null) }}><motion.div ref={editorDialogRef} tabIndex={-1} className="dialog knowledge-editor-dialog" role="dialog" aria-modal="true" aria-label="Редактировать материал" {...calm.modal}><div className="dialog-head"><h2>{data?.[kind].some(item => item.id === editor.id) ? 'Редактировать' : 'Новый материал'}</h2><button className="icon-btn" onClick={() => setEditor(null)} aria-label="Закрыть"><X size={20}/></button></div><div className="knowledge-editor-form"><label className="field"><span>Название</span><input value={editor.title} onChange={event => setEditor({ ...editor, title: event.target.value })} autoFocus/></label>{kind === 'prompts' && <div className="field"><span>Категория</span><Select aria-label="Категория" value={editor.category} onChange={event => setEditor({ ...editor, category: event.target.value })}>{CATEGORIES.slice(1).map(item => <option key={item}>{item}</option>)}</Select></div>}<label className="field"><span>Содержание</span><div ref={editorRef} className="knowledge-rich-editor" contentEditable suppressContentEditableWarning dangerouslySetInnerHTML={{ __html: cleanHtml(editor.html) }}/></label><p className="knowledge-editor-help">Можно редактировать текст прямо здесь, вставлять списки, таблицы и ссылки. Исходная версия защищена резервным экспортом</p><div className="dialog-actions"><button className="btn secondary" onClick={() => setEditor(null)}><ArrowLeft size={15}/> Отмена</button><button className="btn primary" onClick={saveEditor}>Сохранить</button></div></div></motion.div></motion.div>}</AnimatePresence>
  </div>
}
