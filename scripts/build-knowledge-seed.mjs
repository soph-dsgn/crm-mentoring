import fs from 'node:fs/promises'
import crypto from 'node:crypto'
import mammoth from 'mammoth'
import * as cheerio from 'cheerio'

const [promptsFile, textbookFile] = process.argv.slice(2)
if (!promptsFile || !textbookFile) throw new Error('Pass the prompts and textbook DOCX paths')

const source = {
  prompts: '1Xg7SzmGVX_ZBhCH1fivLwuEVbBPiK9crVt24pCWl4Gg',
  textbook: '10k6JRR5HVF2LZSkmppDCeg4gYNNz-t2bHQGsphCUYsc',
}

async function convert(file, options = {}) {
  const result = await mammoth.convertToHtml({ path: file }, options)
  const $ = cheerio.load(`<main>${result.value}</main>`, { decodeEntities: false })
  return { $, nodes: $('main').children().toArray(), warnings: result.messages }
}

const textOf = ($, nodes) => nodes.map(node => $(node).text()).join('\n').trim()
const htmlOf = ($, nodes) => nodes.map(node => $.html(node)).join('')
const hash = value => crypto.createHash('sha256').update(value).digest('hex')
const now = '2026-10-20T00:00:00.000Z'
const categoryOf = title => {
  if (/резюме|навыки|обо мне|пример опыта|зарубеж/i.test(title)) return 'Резюме'
  if (/сопровод/i.test(title)) return 'Сопроводительные письма'
  if (/кейс/i.test(title)) return 'Кейсы'
  if (/портфолио/i.test(title)) return 'Портфолио'
  if (/собес|hr/i.test(title)) return 'Собеседования'
  return 'Другие'
}

const promptDoc = await convert(promptsFile, { styleMap: ["p[style-name='Title'] => h6:fresh"] })
const promptGroups = []
let current = null
for (const node of promptDoc.nodes) {
  if (node.tagName === 'h6') {
    if (current) promptGroups.push(current)
    current = { tabTitle: promptDoc.$(node).text().trim(), nodes: [] }
  } else if (current) current.nodes.push(node)
}
if (current) promptGroups.push(current)

const prompts = []
for (const group of promptGroups) {
  if (/^—+$/.test(group.tabTitle) || !textOf(promptDoc.$, group.nodes)) continue
  const pieces = []
  if (group.tabTitle === 'НАВЫКИ') {
    let part = null
    for (const node of group.nodes) {
      if (node.tagName === 'h2') {
        if (part) pieces.push(part)
        part = { title: promptDoc.$(node).text().trim(), nodes: [node] }
      } else if (part) part.nodes.push(node)
    }
    if (part) pieces.push(part)
  } else {
    pieces.push({ title: group.tabTitle, nodes: group.nodes })
  }
  for (const piece of pieces) {
    const text = textOf(promptDoc.$, piece.nodes)
    const html = htmlOf(promptDoc.$, piece.nodes)
    const id = `source-prompt-${prompts.length + 1}`
    prompts.push({ id, title: piece.title, category: categoryOf(group.tabTitle), html, text,
      sourceId: source.prompts, sourceRevision: '2026-10-19T18:24:01.411Z', sourceHash: hash(html), edited: false,
      deleted: false, favorite: false, updatedAt: now })
  }
}

const textbookDoc = await convert(textbookFile)
const textbookGroups = []
current = null
let lastNumber = 0
for (const node of textbookDoc.nodes) {
  const heading = node.tagName === 'h1' ? textbookDoc.$(node).text().trim() : ''
  const match = heading.match(/^(\d+)\.\s+(.+)/)
  const number = match ? Number(match[1]) : 0
  // The source uses Heading 1 for many nested questions. Its chapter numbers
  // progress through the book; nested lists restart at 1 and stay in the chapter.
  if (number > lastNumber && number <= 30) {
    if (current) textbookGroups.push(current)
    current = { title: heading, nodes: [] }
    lastNumber = number
  }
  if (!current) current = { title: 'Введение', nodes: [] }
  current.nodes.push(node)
}
if (current) textbookGroups.push(current)
const chapters = textbookGroups.map((group, index) => {
  const html = htmlOf(textbookDoc.$, group.nodes)
  return { id: `source-chapter-${index + 1}`, title: group.title, html, text: textOf(textbookDoc.$, group.nodes),
    sourceId: source.textbook, sourceRevision: '2026-10-19T16:16:07.828Z', sourceHash: hash(html), edited: false,
    deleted: false, updatedAt: now, order: index }
})

const seed = { version: 1, source, prompts, chapters, importedAt: now }
await fs.writeFile('public/knowledge-seed.json', JSON.stringify(seed))
console.log(JSON.stringify({
  prompts: prompts.length, chapters: chapters.length,
  promptChars: prompts.reduce((n, x) => n + x.text.length, 0),
  textbookChars: chapters.reduce((n, x) => n + x.text.length, 0),
  promptHtmlChars: prompts.reduce((n, x) => n + x.html.length, 0),
  textbookHtmlChars: chapters.reduce((n, x) => n + x.html.length, 0),
  warnings: { prompts: promptDoc.warnings.slice(0, 5), textbook: textbookDoc.warnings.slice(0, 5) },
  titles: { prompts: prompts.map(x => x.title), chapters: chapters.map(x => x.title) },
}, null, 2))
