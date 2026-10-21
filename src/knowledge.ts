import DOMPurify from 'dompurify'
import mammoth from 'mammoth'
import { marked } from 'marked'

export type KnowledgeKind = 'prompts' | 'chapters'
export interface KnowledgeRecord {
  id: string
  title: string
  category?: string
  html: string
  text: string
  sourceId: string
  sourceRevision: string
  sourceHash: string
  edited: boolean
  deleted: boolean
  favorite?: boolean
  updatedAt: string
  order?: number
}
export interface KnowledgeData {
  version: 1
  prompts: KnowledgeRecord[]
  chapters: KnowledgeRecord[]
  importedAt: string
}

const DB_NAME = 'crm-mentoring-knowledge'
const STORE_NAME = 'documents'
const DATA_KEY = 'content-v1'
let saveQueue = Promise.resolve()

function db(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function readStored(): Promise<KnowledgeData | undefined> {
  const connection = await db()
  return new Promise((resolve, reject) => {
    const transaction = connection.transaction(STORE_NAME, 'readonly')
    const request = transaction.objectStore(STORE_NAME).get(DATA_KEY)
    request.onsuccess = () => resolve(request.result as KnowledgeData | undefined)
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => connection.close()
  })
}

async function writeStored(data: KnowledgeData): Promise<void> {
  const connection = await db()
  return new Promise((resolve, reject) => {
    const transaction = connection.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).put(data, DATA_KEY)
    transaction.oncomplete = () => { connection.close(); resolve() }
    transaction.onerror = () => { connection.close(); reject(transaction.error) }
  })
}

export function saveKnowledge(data: KnowledgeData): Promise<void> {
  const pending = saveQueue.then(() => writeStored(data))
  saveQueue = pending.catch(() => undefined)
  return pending
}

export async function loadKnowledge(): Promise<KnowledgeData> {
  const stored = await readStored()
  if (stored?.version === 1) return stored
  const response = await fetch('/knowledge-seed.json')
  if (!response.ok) throw new Error('Не удалось загрузить встроенные материалы')
  const seed = await response.json() as KnowledgeData
  await saveKnowledge(seed)
  return seed
}

export function cleanHtml(html: string): string {
  return DOMPurify.sanitize(html, { ADD_ATTR: ['target'], ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|data:image\/(?:png|jpeg|gif|webp);base64,|#|\/)/i })
}

export function htmlToText(html: string): string {
  const holder = document.createElement('div')
  holder.innerHTML = cleanHtml(html)
  holder.querySelectorAll('br').forEach(node => node.replaceWith('\n'))
  holder.querySelectorAll('td, th').forEach(node => node.append('\t'))
  holder.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, tr, blockquote, pre').forEach(node => node.append('\n'))
  return (holder.textContent || '').replace(/\n{3,}/g, '\n\n').trim()
}

export async function copyKnowledge(record: KnowledgeRecord): Promise<void> {
  const html = cleanHtml(record.html)
  const text = htmlToText(html)
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/plain': new Blob([text], { type: 'text/plain' }),
        'text/html': new Blob([html], { type: 'text/html' }),
      })])
      return
    } catch { /* Plain text fallback below. */ }
  }
  await navigator.clipboard.writeText(text)
}

const normalized = (value: string) => value.toLocaleLowerCase('ru').replace(/\s+/g, ' ').trim()
const contentSignature = (value: string) => value.toLocaleLowerCase('ru').replace(/\s+/g, '')
const idFor = (kind: KnowledgeKind, sourceId: string, title: string, index: number) => {
  const key = `${kind}-${sourceId}-${index}-${title}`
  let hash = 2166136261
  for (const char of key) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  return `import-${(hash >>> 0).toString(36)}`
}

export async function parseKnowledgeFile(file: File, kind: KnowledgeKind): Promise<KnowledgeRecord[]> {
  const lower = file.name.toLowerCase()
  const sourcePromptFile = kind === 'prompts' && /^менторинг\.docx$/i.test(file.name)
  const sourceTextbookFile = kind === 'chapters' && /^погружение в it\.docx$/i.test(file.name)
  let html: string
  if (lower.endsWith('.docx')) {
    const result = await mammoth.convertToHtml({ arrayBuffer: await file.arrayBuffer() }, { styleMap: [`p[style-name='Title'] => ${sourcePromptFile ? 'h6' : 'h1'}:fresh`] })
    html = result.value
  } else if (lower.endsWith('.md') || lower.endsWith('.markdown')) {
    html = await marked.parse(await file.text(), { gfm: true })
  } else if (lower.endsWith('.html') || lower.endsWith('.htm')) {
    html = await file.text()
  } else throw new Error('Выберите файл DOCX, HTML или Markdown')
  const holder = document.createElement('div')
  holder.innerHTML = cleanHtml(html)
  const nodes = [...holder.children]
  const numberedBook = kind === 'chapters' && nodes.some(node => node.tagName.toLowerCase() === 'h1' && /^1\.\s/.test(node.textContent?.trim() || ''))
  const sections: { title: string; nodes: Element[] }[] = []
  let current: { title: string; nodes: Element[] } | null = null
  let chapterNumber = 0
  for (const node of nodes) {
    const heading = node.tagName.toLowerCase()
    const title = (node.textContent || '').trim()
    let split = kind === 'prompts' ? (sourcePromptFile ? heading === 'h6' : heading === 'h1' || heading === 'h6') : heading === 'h1'
    if (kind === 'chapters' && split && numberedBook) {
      const match = title.match(/^(\d+)\.\s/)
      if (match) {
        const number = Number(match[1])
        split = number > chapterNumber
        if (split) chapterNumber = number
      } else split = false
    }
    if (split) {
      if (current) sections.push(current)
      current = { title, nodes: [] }
    }
    if (!current) current = { title: file.name.replace(/\.[^.]+$/, ''), nodes: [] }
    if (!(sourcePromptFile && split && heading === 'h6')) current.nodes.push(node)
  }
  if (current) sections.push(current)
  const parts = sourcePromptFile ? sections.flatMap(section => {
    if (/^—+$/.test(section.title)) return []
    if (section.title !== 'НАВЫКИ') return [section]
    const skills: { title: string; nodes: Element[] }[] = []
    let part: { title: string; nodes: Element[] } | null = null
    for (const node of section.nodes) {
      if (node.tagName.toLowerCase() === 'h2') {
        if (part) skills.push(part)
        part = { title: node.textContent?.trim() || 'Навыки', nodes: [] }
      }
      if (part) part.nodes.push(node)
    }
    if (part) skills.push(part)
    return skills
  }) : sections
  const sourceId = sourcePromptFile ? '1Xg7SzmGVX_ZBhCH1fivLwuEVbBPiK9crVt24pCWl4Gg'
    : sourceTextbookFile ? '10k6JRR5HVF2LZSkmppDCeg4gYNNz-t2bHQGsphCUYsc' : `file:${normalized(file.name)}`
  const records = await Promise.all(parts.filter(s => s.nodes.some(n => n.textContent?.trim())).map(async (section, index) => {
    const sectionHtml = cleanHtml(section.nodes.map(n => n.outerHTML).join(''))
    const title = section.title || `Материал ${index + 1}`
    const hashBytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(sectionHtml))
    const sourceHash = [...new Uint8Array(hashBytes)].map(byte => byte.toString(16).padStart(2, '0')).join('')
    const category = sourcePromptFile ? /резюме|навыки|обо мне|пример опыта|зарубеж/i.test(title) ? 'Резюме'
      : /сопровод/i.test(title) ? 'Сопроводительные письма' : /кейс/i.test(title) ? 'Кейсы'
      : /портфолио/i.test(title) ? 'Портфолио' : /собес|hr/i.test(title) ? 'Собеседования' : 'Другие' : 'Другие'
    return { id: sourcePromptFile ? `source-prompt-${index + 1}` : sourceTextbookFile ? `source-chapter-${index + 1}` : idFor(kind, sourceId, title, index), title, category, html: sectionHtml,
      text: htmlToText(sectionHtml), sourceId, sourceRevision: '', sourceHash,
      edited: false, deleted: false, favorite: false, updatedAt: new Date().toISOString(), order: index }
  }))
  if (!records.length) throw new Error('В файле нет читаемого текста')
  return records
}

export function mergeKnowledge(existing: KnowledgeRecord[], incoming: KnowledgeRecord[]) {
  const next = [...existing]
  let added = 0, unchanged = 0, protectedCount = 0, updated = 0
  for (const record of incoming) {
    const index = next.findIndex(item => item.id === record.id)
    if (index < 0) { next.push(record); added++; continue }
    const old = next[index]
    if (old.edited || old.deleted) { protectedCount++; continue }
    if (old.sourceHash === record.sourceHash || contentSignature(old.text) === contentSignature(record.text)) { unchanged++; continue }
    next[index] = { ...record, favorite: old.favorite }
    updated++
  }
  return { records: next, added, unchanged, protectedCount, updated }
}

export function downloadKnowledge(data: KnowledgeData): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `mentoring-knowledge-${new Date().toISOString().slice(0, 10)}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}
