import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({ server:{middlewareMode:true,hmr:false}, optimizeDeps:{noDiscovery:true}, appType:'custom', logLevel:'error' })

try {
  const api = await server.ssrLoadModule('/src/api/knowledge.ts')
  const state = await server.ssrLoadModule('/src/knowledge/knowledgeState.ts')
  const http = await server.ssrLoadModule('/src/api/http.ts')
  const requests=[]
  const originalFetch=globalThis.fetch
  globalThis.document={cookie:'kuratorskaya_csrf=synthetic-csrf'}
  globalThis.fetch=async(input,init={})=>{
    requests.push([String(input),init])
    if(String(input).endsWith('/library-state'))return Response.json({status:'active',version:2,activated_at:'2026-01-01T00:00:00Z'})
    if(String(input).includes('/documents?'))return Response.json({items:[],next_cursor:null})
    if(String(input).endsWith('/favorite')||String(input).endsWith('/unfavorite'))return new Response(null,{status:204})
    if(String(input).endsWith('/imports/validate'))return Response.json({valid:true,checksum:'a'.repeat(64),source_version:1,source_format:'knowledge_data_v1',mode:'initial',library_status:'pending',counts:{new_documents:1},items:[],issues:[]})
    if(String(input).endsWith('/imports'))return Response.json({import_run_id:'run-1',checksum:'a'.repeat(64),counts:{new_documents:1},mappings:{},library_status:'active',idempotent_replay:false},{status:201})
    if(String(input).endsWith('/export'))return Response.json({schema_version:1,documents:[]})
    return Response.json({id:'doc-1',kind:'prompt',title:'Синтетический материал',category:'Другие',html:'<p>Текст</p>',plain_text:'Текст',position:0,archived_at:null,created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z',version:1,is_favorite:false})
  }
  try {
    await api.knowledgeApi.libraryState()
    await api.knowledgeApi.list({kind:'prompt',q:'тест',favorite:true,limit:50})
    await api.knowledgeApi.create({kind:'prompt',title:'Синтетический материал',category:'Другие',html:'<p>Текст</p>'})
    await api.knowledgeApi.update('doc/1',{expected_version:1,title:'Обновлено'})
    await api.knowledgeApi.archive('doc/1',2)
    await api.knowledgeApi.restore('doc/1',3)
    await api.knowledgeApi.setFavorite('doc/1',true)
    const source={version:1,prompts:[],chapters:[],importedAt:'2026-01-01T00:00:00Z'}
    const preview=await api.knowledgeApi.validateImport({source,source_format:'knowledge_data_v1',mode:'initial'})
    await api.knowledgeApi.confirmImport({source,source_format:'knowledge_data_v1',mode:'initial',confirmation_checksum:preview.checksum,confirm:true})
    await api.knowledgeApi.exportLibrary()
  } finally { globalThis.fetch=originalFetch;delete globalThis.document }

  assert.equal(requests[1][0],'/api/v1/knowledge/documents?kind=prompt&q=%D1%82%D0%B5%D1%81%D1%82&favorite=true&limit=50')
  assert.equal(requests[2][1].headers.get('X-CSRF-Token'),'synthetic-csrf')
  assert.equal(requests[3][0],'/api/v1/knowledge/documents/doc%2F1')
  assert.deepEqual(JSON.parse(requests[4][1].body),{expected_version:2})
  assert.match(requests[6][0],/\/favorite$/)
  assert.equal(requests[7][0],'/api/v1/knowledge/imports/validate')
  assert.equal(JSON.parse(requests[8][1].body).confirm,true)
  assert.equal(requests[9][0],'/api/v1/knowledge/export')

  assert.equal(state.MAX_KNOWLEDGE_IMPORT_BYTES,5*1024*1024)
  const legacy={version:1,prompts:[{id:'p1',title:'Тест',html:'<p>Текст</p>',text:'Текст',sourceId:'synthetic',sourceRevision:'',sourceHash:'hash',edited:false,deleted:false,favorite:false,updatedAt:'2026-01-01T00:00:00Z'}],chapters:[],importedAt:'2026-01-01T00:00:00Z'}
  const source=state.knowledgeDataSource(legacy)
  assert.deepEqual(source,legacy)
  assert.notEqual(source,legacy)
  assert.equal(state.importRequestBytes({source,source_format:'knowledge_data_v1',mode:'initial'})>0,true)
  const parsed=state.parsedDocumentsSource(legacy.prompts,'prompt','markdown')
  assert.equal(parsed.documents[0].kind,'prompt')
  assert.equal(parsed.documents[0].format,'markdown')
  assert.equal(parsed.documents[0].title,'Тест')
  assert.match(state.knowledgeErrorMessage(new http.ApiError(409,'version_conflict','private raw value')),/другой сессии/)
  assert.doesNotMatch(state.knowledgeErrorMessage(new http.ApiError(422,'validation_error','private raw value')),/private raw value/)
  assert.match(state.knowledgeImportErrorMessage(new http.ApiError(0,'connection_error','private'),'import'),/не повторяйте/)
  assert.equal(state.canManageInitialMigration({role:'admin',is_owner:true,is_active:true,must_change_password:false}),true)
  assert.equal(state.canManageInitialMigration({role:'admin',is_owner:false,is_active:true,must_change_password:false}),false)
  assert.equal(state.canUseKnowledge({role:'student',is_owner:false,is_active:true,must_change_password:false}),false)
  const pageSource=await (await import('node:fs/promises')).readFile(new URL('../src/KnowledgePage.tsx',import.meta.url),'utf8')
  const importSource=await (await import('node:fs/promises')).readFile(new URL('../src/knowledge/KnowledgeImportDialog.tsx',import.meta.url),'utf8')
  assert.match(pageSource,/setImportOpen\(false\);setLibraryStatus\('active'\)/)
  assert.match(pageSource,/readKnowledgeBackup\(\)/)
  assert.doesNotMatch(pageSource,/loadKnowledge\(\)/)
  assert.match(importSource,/confirmation_checksum: report\.checksum, confirm: true/)
  assert.match(importSource,/code === 'connection_error'/)
  assert.match(importSource,/setReport\(null\)/)
  assert.match(importSource,/expected_version: target\.version/)
  assert.doesNotMatch(importSource,/localStorage\.(?:setItem|removeItem)/)
  console.log('Knowledge frontend verification passed')
} finally { await server.close() }
