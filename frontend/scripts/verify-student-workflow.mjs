import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createServer } from 'vite'

const server = await createServer({ server:{ middlewareMode:true, hmr:false }, optimizeDeps:{ noDiscovery:true }, appType:'custom', logLevel:'error' })

try {
  const state = await server.ssrLoadModule('/src/student/studentState.ts')
  const api = await server.ssrLoadModule('/src/api/student.ts')
  const http = await server.ssrLoadModule('/src/api/http.ts')

  assert.equal(state.studentProfileIdFromUrl('https://crm.test/?student=student-1'), 'student-1')
  assert.equal(state.studentProfileIdFromUrl('https://crm.test/'), null)
  assert.equal(state.studentPortalUrl('student / 1', 'https://crm.test/current'), 'https://crm.test/?student=student+%2F+1')
  assert.equal(state.studentHomeworkAction({ status:'issued', archivedAt:'' }), 'submit')
  assert.equal(state.studentHomeworkAction({ status:'revision', archivedAt:'' }), 'resubmit')
  assert.equal(state.studentHomeworkAction({ status:'submitted', archivedAt:'' }), null)
  assert.equal(state.studentHomeworkAction({ status:'revision', archivedAt:'2026-11-20T10:00:00Z' }), null)
  assert.equal(state.studentErrorMessage(new http.ApiError(404,'not_found','missing')), 'Профиль недоступен или ссылка устарела')
  assert.equal(state.studentErrorMessage(new http.ApiError(409,'version_conflict','stale')), 'Домашнее задание изменилось. Мы загрузили актуальную версию — проверьте её и отправьте работу снова')

  const requests=[]
  const originalFetch=globalThis.fetch
  globalThis.document={cookie:'kuratorskaya_csrf=student-csrf'}
  globalThis.fetch=async(input,init)=>{
    const url=String(input);requests.push([url,init])
    if(url.includes('/transitions'))return Response.json({id:'homework-1',strategy_id:'strategy-1',title:'ДЗ',description:'',links:{},submission_text:'Готово',submission_links:{},curator_feedback:'',due_at:null,status:'submitted',issued_at:'2026-11-20T10:00:00Z',submitted_at:'2026-11-20T11:00:00Z',reviewed_at:null,archived_at:null,created_at:'2026-11-20T09:00:00Z',updated_at:'2026-11-20T11:00:00Z',version:3,items:[]})
    return Response.json({items:[],next_cursor:null})
  }
  try {
    await api.studentApi.listHomeworks('strategy-1',undefined,true)
    await api.studentApi.submitHomework('homework-1',{expected_version:2,status:'submitted',submission_text:'Готово',submission_links:{}})
  } finally {
    globalThis.fetch=originalFetch
    delete globalThis.document
  }
  assert.equal(requests[0][0].includes('include_archived=true'),true)
  assert.equal(requests[1][1].headers.get('X-CSRF-Token'),'student-csrf')
  assert.deepEqual(JSON.parse(requests[1][1].body),{expected_version:2,status:'submitted',submission_text:'Готово',submission_links:{}})

  const source = await fs.readFile(new URL('../src/student/useStudentWorkspace.ts', import.meta.url),'utf8')
  assert.equal(source.includes('localStorage'),false)
  assert.equal(source.includes('listAll('),false)
  assert.equal(source.includes('/students?'),false)
  assert.match(source, /pendingRef\.current\.has\(homework\.id\)/)
  assert.match(source, /pendingRef\.current\.add\(homework\.id\)/)
  assert.match(source, /pendingRef\.current\.delete\(homework\.id\)/)
  assert.match(source, /error instanceof ApiError&&error\.status===409/)
  assert.match(source, /studentApi\.getHomework\(homework\.id\)/)

  const styles = await fs.readFile(new URL('../src/student/student.css', import.meta.url),'utf8')
  assert.match(styles, /@media\(max-width:640px\).*\.student-nav\{[^}]*display:grid[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/s)
  assert.match(styles, /@media\(max-width:640px\).*\.student-nav button\{[^}]*min-width:0[^}]*width:100%/s)

  const appSource = await fs.readFile(new URL('../src/student/StudentApp.tsx', import.meta.url),'utf8')
  assert.match(appSource, /historyStatus==='loading'/)
  assert.match(appSource, /historyStatus==='error'/)
  assert.match(appSource, /historyStatus==='loaded'/)
  assert.match(appSource, /История пока пуста/)
  assert.match(appSource, /onClick=\{\(\)=>void loadHistory\(\)\}/)

  console.log('Student-facing workflow verification passed')
} finally {
  await server.close()
}
