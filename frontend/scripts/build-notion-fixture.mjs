// Builds a synthetic Notion-like strategy PDF for backend parser tests.
// The page mimics the Notion "Export as PDF" layout: a large page title, "Точка А/Б" tables
// and bordered strategy tables with narrow columns. «Часть 2» deliberately has no repeated
// header row after the page break. All names and texts are fictional.
// Usage from frontend/: node scripts/build-notion-fixture.mjs
import { chromium } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const output = fileURLToPath(new URL('../../backend/tests/fixtures/notion-strategy-synthetic.pdf', import.meta.url))

const longComment = Array.from({ length: 70 }, (_, index) => `Шаг ${index + 1} синтетического плана`).join('<br>')
const fillerRows = Array.from({ length: 6 }, (_, index) => `<tr><td></td><td>Запасная задача ${index + 1}</td><td></td><td>Описание запасной задачи</td><td></td><td>Not started</td></tr>`).join('')

const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
  body { font-family: Arial, sans-serif; font-size: 14px; margin: 0; }
  h1 { font-size: 40px; margin: 0 0 24px; }
  h3 { font-size: 14px; font-weight: 700; margin: 24px 0 8px; }
  table { border-collapse: collapse; table-layout: fixed; width: 640px; }
  th, td { border: 1px solid #999; padding: 6px 8px; vertical-align: top; text-align: left; font-weight: 400; overflow-wrap: break-word; word-break: break-word; }
  col.property { width: 24px; } col.title { width: 120px; } col.period { width: 80px; } col.comment { width: 200px; } col.material { width: 110px; } col.status { width: 106px; }
</style></head><body>
  <h1>Тестовая | Стратегия действий</h1>
  <h3>Точка А</h3>
  <table><tr><th>Ссылка на тг</th><th>Опыт работы</th><th>Цель</th></tr>
    <tr><td>@test_handle</td><td>Синтетический опыт в графическом дизайне</td><td>Стать продуктовым дизайнером</td></tr></table>
  <h3>Точка Б</h3>
  <table><tr><th>Цель</th><th>Резюме</th></tr><tr><td>Untitled</td><td>Готово к отправке</td></tr></table>
  <h3>Часть 1</h3>
  <table><colgroup><col class="property"><col class="title"><col class="period"><col class="comment"><col class="material"><col class="status"></colgroup>
    <thead><tr><th>P</th><th>Этап</th><th>Период</th><th>Комментарии</th><th>Материалы</th><th>Статус</th></tr></thead>
    <tr><td></td><td>Зарегистрироваться в Notion</td><td></td><td>Проверить, что доступ открыт</td><td><a href="https://example.com/guide">Гайд</a></td><td>Done</td></tr>
    <tr><td></td><td>Пройти диагностику</td><td>1-2 недели</td><td>Записать выводы<br>1) Сравнить с целью</td><td></td><td>In progress</td></tr>
    <tr><td></td><td>Подготовить резюме</td><td></td><td><b>Промпт для кейса</b> внутри ячейки</td><td></td><td>Hold</td></tr>
    <tr><td></td><td>Задача без статуса</td><td></td><td></td><td></td><td></td></tr>
  </table>
  <h3>Часть 2</h3>
  <table><colgroup><col class="property"><col class="title"><col class="period"><col class="comment"><col class="material"><col class="status"></colgroup>
    <tr><th>P</th><th>Этап</th><th>Период</th><th>Комментарии</th><th>Материалы</th><th>Статус</th></tr>
    ${fillerRows}
    <tr><td></td><td>Длинная задача через разрыв страницы</td><td></td><td>${longComment}</td><td></td><td>Not started</td></tr>
    <tr><td></td><td>Финальная задача</td><td></td><td>После разрыва</td><td></td><td>Done</td></tr>
  </table>
</body></html>`

const browser = await chromium.launch(process.env.CRM_ACCEPTANCE_BROWSER ? { channel: process.env.CRM_ACCEPTANCE_BROWSER } : {})
try {
  const page = await browser.newPage()
  await page.setContent(html, { waitUntil: 'load' })
  await page.pdf({ path: output, format: 'A4', margin: { top: '20mm', bottom: '20mm', left: '20mm', right: '20mm' } })
  console.log(`Wrote ${output}`)
} finally {
  await browser.close()
}
