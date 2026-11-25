import { useCallback, useEffect, useRef, useState } from 'react'
import { ArchiveIcon as Archive, ArrowClockwiseIcon as ArrowClockwise, ArrowLeftIcon as ArrowLeft, BookOpenIcon as BookOpen, CheckIcon as Check, CaretRightIcon as ChevronRight, CopyIcon as Copy, DownloadIcon as Download, FilePlusIcon as FilePlus2, PencilIcon as Pencil, PlusIcon as Plus, MagnifyingGlassIcon as Search, StarIcon as Star, UploadIcon as Upload, XIcon as X } from '@phosphor-icons/react'
import type { KnowledgeDocumentRead, KnowledgeDocumentSummary, KnowledgeKind } from './api/contracts'
import { knowledgeApi } from './api/knowledge'
import { ApiError } from './api/http'
import { useCurrentUser } from './auth/authContext'
import { ConfirmDialog, Dialog } from './Dialogs'
import { cleanHtml, copyKnowledge, downloadKnowledge, htmlToText, readKnowledgeBackup, type KnowledgeRecord } from './knowledge'
import KnowledgeImportDialog from './knowledge/KnowledgeImportDialog'
import { canManageInitialMigration, canUseKnowledge, knowledgeErrorMessage, summaryFromDocument } from './knowledge/knowledgeState'
import { motionScrollBehavior } from './motion'
import Select from './Select'

type UiKind = 'prompts' | 'chapters'
type LoadState = 'loading' | 'ready' | 'error'
type EditorDraft = Pick<KnowledgeDocumentRead, 'id' | 'title' | 'category' | 'html' | 'position' | 'version'> & { isNew: boolean }

const CATEGORIES = ['Все', 'Резюме', 'Сопроводительные письма', 'Кейсы', 'Портфолио', 'Собеседования', 'Другие']
const serverKind = (kind: UiKind): KnowledgeKind => kind === 'prompts' ? 'prompt' : 'chapter'

function today() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
}

function downloadJson(value: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(value,null,2)],{type:'application/json'})
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href=url;link.download=filename;link.click();URL.revokeObjectURL(url)
}

export default function KnowledgePage({ kind }: { kind: UiKind }) {
  const currentUser = useCurrentUser()
  const kindValue = serverKind(kind)
  const [libraryState,setLibraryState]=useState<LoadState>('loading')
  const [libraryStatus,setLibraryStatus]=useState<'pending'|'active'|null>(null)
  const [items,setItems]=useState<KnowledgeDocumentSummary[]>([])
  const [listState,setListState]=useState<LoadState>('loading')
  const [listError,setListError]=useState('')
  const [nextCursor,setNextCursor]=useState<string|null>(null)
  const [loadingMore,setLoadingMore]=useState(false)
  const [query,setQuery]=useState('')
  const [debouncedQuery,setDebouncedQuery]=useState('')
  const [category,setCategory]=useState('Все')
  const [favoritesOnly,setFavoritesOnly]=useState(false)
  const [showArchived,setShowArchived]=useState(false)
  const [selectedId,setSelectedId]=useState<string|null>(null)
  const [selected,setSelected]=useState<KnowledgeDocumentRead|null>(null)
  const [detailState,setDetailState]=useState<LoadState>('ready')
  const [detailError,setDetailError]=useState('')
  const [editor,setEditor]=useState<EditorDraft|null>(null)
  const [editorError,setEditorError]=useState('')
  const [conflict,setConflict]=useState(false)
  const [importOpen,setImportOpen]=useState(false)
  const [confirmation,setConfirmation]=useState<{title:string;description:string;label:string;action:()=>Promise<void>}|null>(null)
  const [notice,setNotice]=useState('')
  const [pageError,setPageError]=useState('')
  const [copied,setCopied]=useState(false)
  const [headings,setHeadings]=useState<{id:string;text:string;level:number}[]>([])
  const editorRef=useRef<HTMLDivElement>(null)
  const articleRef=useRef<HTMLDivElement>(null)
  const mutationPending=useRef(false)

  const loadLibraryState=useCallback(async(signal?:AbortSignal)=>{
    setLibraryState('loading');setPageError('')
    try {const state=await knowledgeApi.libraryState(signal);setLibraryStatus(state.status);setLibraryState('ready')}
    catch(caught){if(caught instanceof DOMException&&caught.name==='AbortError')return;setPageError(knowledgeErrorMessage(caught));setLibraryState('error')}
  },[])

  useEffect(()=>{const controller=new AbortController();void loadLibraryState(controller.signal);return()=>controller.abort()},[loadLibraryState])
  useEffect(()=>{const timeout=setTimeout(()=>setDebouncedQuery(query.trim()),300);return()=>clearTimeout(timeout)},[query])

  const loadList=useCallback(async({append=false,cursor,signal}:{append?:boolean;cursor?:string|null;signal?:AbortSignal}={})=>{
    if(!append)setListState('loading');else setLoadingMore(true)
    setListError('')
    try {
      const page=await knowledgeApi.list({kind:kindValue,category:kind==='prompts'&&category!=='Все'?category:undefined,q:debouncedQuery||undefined,favorite:favoritesOnly?true:undefined,includeArchived:showArchived,cursor:cursor??undefined,limit:50},signal)
      setItems(current=>append?[...new Map([...current,...page.items].map(item=>[item.id,item])).values()]:page.items)
      setNextCursor(page.next_cursor);setListState('ready')
      if(!append)setSelectedId(current=>page.items.some(item=>item.id===current)?current:page.items[0]?.id??null)
    } catch(caught) {
      if(caught instanceof DOMException&&caught.name==='AbortError')return
      setListError(knowledgeErrorMessage(caught));setListState('error')
    } finally {setLoadingMore(false)}
  },[category,debouncedQuery,favoritesOnly,kind,kindValue,showArchived])

  useEffect(()=>{
    if(libraryStatus!=='active')return
    const controller=new AbortController();void loadList({signal:controller.signal});return()=>controller.abort()
  },[libraryStatus,loadList])

  const loadDetail=useCallback(async(id:string,signal?:AbortSignal)=>{
    setDetailState('loading');setDetailError('')
    try {const document=await knowledgeApi.get(id,signal);setSelected(document);setDetailState('ready');return document}
    catch(caught){if(caught instanceof DOMException&&caught.name==='AbortError')return;setDetailError(knowledgeErrorMessage(caught));setDetailState('error');return undefined}
  },[])

  useEffect(()=>{
    if(!selectedId){setSelected(null);setDetailState('ready');return}
    const controller=new AbortController();void loadDetail(selectedId,controller.signal);return()=>controller.abort()
  },[loadDetail,selectedId])
  useEffect(()=>{
    if(libraryStatus!=='active')return
    const refresh=()=>{void loadList();if(selectedId)void loadDetail(selectedId)}
    window.addEventListener('focus',refresh);return()=>window.removeEventListener('focus',refresh)
  },[libraryStatus,loadDetail,loadList,selectedId])

  useEffect(()=>{
    if(kind!=='chapters'||!articleRef.current){setHeadings([]);return}
    const found=[...articleRef.current.querySelectorAll('h1,h2,h3')].map((node,index)=>{const id=`knowledge-heading-${index}`;node.id=id;return{id,text:node.textContent?.trim()||'',level:Number(node.tagName.slice(1))}}).filter(item=>item.text)
    setHeadings(found)
  },[kind,selected?.html,selected?.id])

  const reconcileDocument=(document:KnowledgeDocumentRead)=>{
    setSelected(document);setSelectedId(document.id)
    setItems(current=>{const summary=summaryFromDocument(document);return current.some(item=>item.id===document.id)?current.map(item=>item.id===document.id?summary:item):[summary,...current]})
  }
  const runMutation=async(action:()=>Promise<KnowledgeDocumentRead>)=>{
    if(mutationPending.current)return undefined
    mutationPending.current=true;setPageError('')
    try {const document=await action();reconcileDocument(document);return document}
    catch(caught){
      setPageError(knowledgeErrorMessage(caught))
      if(caught instanceof ApiError&&caught.status===409){setConflict(true);if(selectedId)void loadDetail(selectedId)}
      if(caught instanceof ApiError&&[403,404].includes(caught.status))void loadList()
      throw caught
    } finally {mutationPending.current=false}
  }

  const openNew=()=>{setEditorError('');setConflict(false);setEditor({id:'',title:'',category:kind==='prompts'?'Другие':null,html:'<p></p>',position:items.length,version:1,isNew:true})}
  const openEdit=()=>{if(!selected)return;setEditorError('');setConflict(false);setEditor({id:selected.id,title:selected.title,category:selected.category,html:selected.html,position:selected.position,version:selected.version,isNew:false})}
  const saveEditor=async()=>{
    if(!editor||mutationPending.current)return
    const title=editor.title.trim();const html=cleanHtml(editorRef.current?.innerHTML||editor.html)
    if(!title){setEditorError('Укажите название материала');return}
    if(!htmlToText(html)){setEditorError('Добавьте текст материала');return}
    setEditorError('')
    try {
      const saved=await runMutation(()=>editor.isNew
        ?knowledgeApi.create({kind:kindValue,title,category:kind==='prompts'?editor.category:null,html,position:editor.position})
        :knowledgeApi.update(editor.id,{expected_version:editor.version,title,category:kind==='prompts'?editor.category:null,html,position:editor.position}))
      if(saved){setEditor(null);setNotice('Материал сохранён');void loadList()}
    } catch(caught) {setEditorError(knowledgeErrorMessage(caught))}
  }
  const reloadEditor=async()=>{if(!editor||editor.isNew)return;const current=await loadDetail(editor.id);if(current){setEditor({id:current.id,title:current.title,category:current.category,html:current.html,position:current.position,version:current.version,isNew:false});setConflict(false);setEditorError('')}}

  const toggleFavorite=async()=>{if(!selected||mutationPending.current)return;const next=!selected.is_favorite;mutationPending.current=true;setPageError('');try{await knowledgeApi.setFavorite(selected.id,next);reconcileDocument({...selected,is_favorite:next})}catch(caught){setPageError(knowledgeErrorMessage(caught))}finally{mutationPending.current=false}}
  const requestArchive=()=>{if(!selected)return;const archived=Boolean(selected.archived_at);setConfirmation({title:archived?'Восстановить материал?':'Переместить материал в архив?',description:archived?`«${selected.title}» снова появится в рабочем списке`:`«${selected.title}» останется на сервере и будет доступен в архиве`,label:archived?'Восстановить':'В архив',action:async()=>{await runMutation(()=>archived?knowledgeApi.restore(selected.id,selected.version):knowledgeApi.archive(selected.id,selected.version));setNotice(archived?'Материал восстановлен':'Материал перемещён в архив');await loadList()}})}
  const copy=async()=>{if(!selected)return;const record:KnowledgeRecord={id:selected.id,title:selected.title,category:selected.category??undefined,html:selected.html,text:selected.plain_text,sourceId:'server',sourceRevision:String(selected.version),sourceHash:'',edited:true,deleted:Boolean(selected.archived_at),favorite:selected.is_favorite,updatedAt:selected.updated_at,order:selected.position};try{await copyKnowledge(record);setCopied(true);setTimeout(()=>setCopied(false),1800)}catch{setPageError('Не удалось скопировать. Проверьте доступ браузера к буферу обмена')}}
  const exportLocal=async()=>{try{const local=await readKnowledgeBackup();if(!local){setPageError('На этом устройстве нет локальной копии KnowledgeData v1');return}downloadKnowledge(local)}catch{setPageError('Не удалось прочитать локальную копию. Она не изменена')}}
  const exportServer=async()=>{try{downloadJson(await knowledgeApi.exportLibrary(),`kuratorskaya-knowledge-server-${today()}.json`)}catch(caught){setPageError(knowledgeErrorMessage(caught))}}
  const importComplete=async()=>{setImportOpen(false);setLibraryStatus('active');await loadList();setNotice('Серверная база знаний обновлена')}

  if(!canUseKnowledge(currentUser))return <div className="knowledge-state" role="alert"><BookOpen size={30}/><h2>Нет доступа к базе знаний</h2><p>Раздел доступен только активным кураторам и владельцу</p></div>
  if(libraryState==='loading')return <div className="knowledge-loading" role="status"><span className="account-spinner"/>Проверяем состояние базы знаний…</div>
  if(libraryState==='error')return <div className="knowledge-state error" role="alert"><h2>Не удалось открыть базу знаний</h2><p>{pageError}</p><button className="btn secondary" onClick={()=>void loadLibraryState()}>Повторить</button></div>
  if(libraryStatus==='pending')return <div className="knowledge-page"><div className="knowledge-state pending"><BookOpen size={32}/><h1>Промпты ещё не загружены</h1><p>{canManageInitialMigration(currentUser)?'Промпты хранятся на сервере и общие для всех кураторов и учениц. Загрузите файл с промптами один раз — например, knowledge-seed.json из материалов переноса':'Промпты появятся, когда владелец загрузит их на сервер'}</p>{canManageInitialMigration(currentUser)&&<button className="btn primary" onClick={()=>setImportOpen(true)}><Upload size={17}/> Загрузить промпты</button>}<button className="btn secondary" onClick={()=>void loadLibraryState()}><ArrowClockwise size={17}/> Обновить состояние</button></div><KnowledgeImportDialog open={importOpen} initial kind={kindValue} onClose={()=>setImportOpen(false)} onComplete={importComplete}/></div>

  return <div className="knowledge-page">
    <header className="knowledge-head"><div><h1>{kind==='prompts'?'Промпты':'Учебник'}</h1><p>Общая серверная база · изменения доступны на всех устройствах</p></div><div className="knowledge-head-actions"><button className="btn secondary" onClick={()=>setImportOpen(true)}><Upload size={16}/> Импорт</button>{currentUser.is_owner&&<button className="btn secondary" onClick={()=>void exportLocal()}><Download size={16}/> Локальная копия</button>}{currentUser.is_owner&&<button className="btn secondary" onClick={()=>void exportServer()}><Download size={16}/> Серверная копия</button>}<button className="btn primary" onClick={openNew}><Plus size={16}/> {kind==='prompts'?'Промпт':'Раздел'}</button></div></header>
    {pageError&&<div className="knowledge-alert error" role="alert">{pageError}<button onClick={()=>setPageError('')} aria-label="Закрыть"><X size={14}/></button></div>}
    {notice&&<div className="knowledge-alert" role="status">{notice}<button onClick={()=>setNotice('')} aria-label="Закрыть"><X size={14}/></button></div>}
    <div className="knowledge-layout"><aside className="knowledge-index"><label className="knowledge-search"><Search size={17}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Поиск по содержимому" aria-label="Поиск по базе знаний"/></label>{kind==='prompts'&&<><div className="knowledge-categories">{CATEGORIES.map(item=><button key={item} className={category===item?'active':''} aria-pressed={category===item} onClick={()=>setCategory(item)}>{item}</button>)}</div><button className={`knowledge-favorites ${favoritesOnly?'active':''}`} aria-pressed={favoritesOnly} onClick={()=>setFavoritesOnly(value=>!value)}><Star size={15} weight={favoritesOnly?'fill':'regular'}/> Избранное</button></>}<button className={`knowledge-favorites ${showArchived?'active':''}`} aria-pressed={showArchived} onClick={()=>setShowArchived(value=>!value)}><Archive size={15}/> {showArchived?'Скрыть архив':'Показать архив'}</button><div className="knowledge-index-count">{items.length} {kind==='prompts'?'записей':'разделов'}</div><div className="knowledge-index-list">{listState==='loading'&&items.length===0&&<div className="knowledge-inline-state" role="status"><span className="account-spinner"/>Загружаем…</div>}{items.map(record=><button key={record.id} className={`knowledge-index-item ${selectedId===record.id?'active':''} ${record.archived_at?'archived':''}`} onClick={()=>setSelectedId(record.id)}><span><strong>{record.title}</strong><small>{record.archived_at?'В архиве':kind==='prompts'?record.category:'Раздел учебника'}</small></span><ChevronRight size={16}/></button>)}{listState==='ready'&&items.length===0&&<div className="knowledge-no-results">Ничего не найдено. Попробуйте другой запрос</div>}{listState==='error'&&<div className="knowledge-inline-error" role="alert"><p>{listError}</p><button className="btn small" onClick={()=>void loadList()}>Повторить</button></div>}{nextCursor&&<button className="btn secondary knowledge-more" disabled={loadingMore} onClick={()=>void loadList({append:true,cursor:nextCursor})}>{loadingMore?'Загружаем…':'Показать ещё'}</button>}</div></aside>
      <section className="knowledge-reader">{detailState==='loading'&&selected?.id!==selectedId&&<div className="knowledge-empty" role="status"><span className="account-spinner"/>Загружаем материал…</div>}{detailState==='error'&&<div className="knowledge-empty error" role="alert"><h2>Не удалось загрузить материал</h2><p>{detailError}</p>{selectedId&&<button className="btn secondary" onClick={()=>void loadDetail(selectedId)}>Повторить</button>}</div>}{selected?.id===selectedId&&<><div className="knowledge-reader-head"><div><span>{selected.archived_at?'В архиве':kind==='prompts'?selected.category:'Раздел учебника'}</span><h2>{selected.title}</h2></div><div className="knowledge-reader-actions">{kind==='prompts'&&<button aria-label={selected.is_favorite?'Убрать из избранного':'В избранное'} aria-pressed={selected.is_favorite} title="Избранное" onClick={()=>void toggleFavorite()}><Star size={18} weight={selected.is_favorite?'fill':'regular'}/></button>}<button title="Редактировать" aria-label="Редактировать" onClick={openEdit}><Pencil size={17}/></button><button title={selected.archived_at?'Восстановить':'В архив'} aria-label={selected.archived_at?'Восстановить':'В архив'} onClick={requestArchive}><Archive size={17}/></button></div></div><div className="knowledge-source">Серверный материал · версия {selected.version}</div>{kind==='chapters'&&headings.length>1&&<nav className="knowledge-toc" aria-label="В этом разделе"><strong>В этом разделе</strong><div>{headings.slice(1).map(heading=><button key={heading.id} className={heading.level===3?'nested':''} onClick={()=>document.getElementById(heading.id)?.scrollIntoView({behavior:motionScrollBehavior(window.matchMedia('(prefers-reduced-motion: reduce)').matches),block:'start'})}>{heading.text}</button>)}</div></nav>}<article key={`${selected.id}-${selected.version}`} ref={articleRef} className="knowledge-article" dangerouslySetInnerHTML={{__html:cleanHtml(selected.html)}}/><div className="knowledge-reader-foot"><button className="btn primary" onClick={()=>void copy()}>{copied?<Check size={16}/>:<Copy size={16}/>} {copied?'Скопировано':kind==='prompts'?'Скопировать промпт':'Скопировать раздел'}</button></div></>}{!selectedId&&detailState==='ready'&&<div className="knowledge-empty"><BookOpen size={28}/><h2>Пока здесь пусто</h2><p>Добавьте материал или импортируйте DOCX, HTML, Markdown или KnowledgeData v1</p><button className="btn primary" onClick={()=>setImportOpen(true)}><FilePlus2 size={16}/> Импортировать</button></div>}</section>
    </div>
    <Dialog open={Boolean(editor)} title={editor?.isNew?'Новый материал':'Редактировать'} onClose={()=>{if(!mutationPending.current)setEditor(null)}} wide dismissible={!mutationPending.current}>{editor&&<div className="knowledge-editor-form"><label className="field"><span>Название</span><input value={editor.title} onChange={event=>setEditor({...editor,title:event.target.value})} autoFocus/></label>{kind==='prompts'&&<div className="field"><span>Категория</span><Select aria-label="Категория" value={editor.category??'Другие'} onChange={event=>setEditor({...editor,category:event.target.value})}>{CATEGORIES.slice(1).map(item=><option key={item}>{item}</option>)}</Select></div>}<label className="field"><span>Содержание</span><div ref={editorRef} className="knowledge-rich-editor" contentEditable role="textbox" aria-multiline="true" suppressContentEditableWarning dangerouslySetInnerHTML={{__html:cleanHtml(editor.html)}}/></label><p className="knowledge-editor-help">Сервер очистит HTML и безопасные ссылки перед сохранением</p>{editorError&&<p className="dialog-error" role="alert">{editorError}</p>}{conflict&&<div className="knowledge-conflict" role="alert"><p>Черновик сохранён только в этом окне. Можно закрыть его или явно загрузить актуальную серверную версию</p><button className="btn secondary" onClick={()=>void reloadEditor()}>Загрузить серверную версию</button></div>}<div className="dialog-actions"><button className="btn secondary" disabled={mutationPending.current} onClick={()=>setEditor(null)}><ArrowLeft size={15}/> Отмена</button><button className="btn primary" disabled={mutationPending.current} onClick={()=>void saveEditor()}>{mutationPending.current?'Сохраняем…':'Сохранить'}</button></div></div>}</Dialog>
    <KnowledgeImportDialog open={importOpen} initial={false} kind={kindValue} onClose={()=>setImportOpen(false)} onComplete={importComplete}/>
    <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title??''} description={confirmation?.description??''} confirmLabel={confirmation?.label} danger={confirmation?.label==='В архив'} getErrorMessage={knowledgeErrorMessage} onConfirm={confirmation?.action??(()=>{})} onClose={()=>setConfirmation(null)}/>
  </div>
}
