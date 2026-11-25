import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createServer } from 'vite'

const server = await createServer({ server:{ middlewareMode:true,hmr:false }, optimizeDeps:{noDiscovery:true}, appType:'custom', logLevel:'error' })

try {
  const state = await server.ssrLoadModule('/src/migration/migrationState.ts')
  const api = await server.ssrLoadModule('/src/api/legacy.ts')
  const http = await server.ssrLoadModule('/src/api/http.ts')

  for (const version of [1,2,3]) {
    const source={version,groups:[{id:`group-${version}`,name:`Синтетическая группа ${version}`}],students:[],tasks:[]}
    assert.equal(state.legacySource(source),source)
    assert.deepEqual(state.legacyGroups(source),[{id:`group-${version}`,name:`Синтетическая группа ${version}`}])
  }
  assert.equal(state.legacySource([]),null)
  assert.equal(state.legacyGroups({groups:[null,{id:'',name:'bad'},{id:'group',name:''}]}).length,1)
  assert.deepEqual(state.legacyGroups({groups:[
    {id:'duplicate-group',name:'Первая строка'},
    {id:'duplicate-group',name:'Повтор'},
  ]}),[{id:'duplicate-group',name:'Первая строка'}])
  assert.ok(state.requestBytes({version:3,groups:[]},{})>0)
  assert.equal(state.MAX_LEGACY_IMPORT_BYTES,5*1024*1024)

  const grouped=state.groupConflicts([
    {code:'duplicate_id',entity:'tasks',legacy_id:'one'},
    {code:'duplicate_id',entity:'tasks',legacy_id:'two'},
    {code:'unsupported_field',entity:'students',legacy_id:'three'},
  ])
  assert.deepEqual(grouped,[
    {code:'duplicate_id',entity:'tasks',count:2},
    {code:'unsupported_field',entity:'students',count:1},
  ])
  assert.match(state.conflictLabel(grouped[0]),/Повторяющиеся идентификаторы/)
  assert.doesNotMatch(state.conflictLabel(grouped[0]),/one|two/)
  assert.match(state.migrationErrorMessage(new http.ApiError(0,'connection_error','secret raw message'),'import'),/Результат импорта неизвестен/)
  assert.doesNotMatch(state.migrationErrorMessage(new http.ApiError(0,'connection_error','secret raw message')),/Результат импорта неизвестен/)
  assert.doesNotMatch(state.migrationErrorMessage(new http.ApiError(422,'validation_error','personal payload')),/personal payload/)

  const storageValues=new Map([['crm-mentoring-v1','legacy-backup']])
  const writes=[]
  const storage={getItem:key=>storageValues.get(key)??null,setItem:(key,value)=>{writes.push([key,value]);storageValues.set(key,value)}}
  assert.equal(state.hasServerCutover(storage),false)
  state.markServerCutover(storage)
  assert.equal(state.hasServerCutover(storage),true)
  assert.deepEqual(writes,[[state.SERVER_CUTOVER_KEY,'complete']])
  assert.equal(storageValues.get('crm-mentoring-v1'),'legacy-backup')

  const requests=[]
  const originalFetch=globalThis.fetch
  globalThis.document={cookie:'kuratorskaya_csrf=synthetic-csrf'}
  globalThis.fetch=async(input,init={})=>{
    requests.push([String(input),init])
    if(String(input).endsWith('/validate'))return Response.json({valid:true,checksum:'a'.repeat(64),source_version:3,counts:{groups:1},conflicts:[],warnings:[]})
    if(String(input).endsWith('/legacy'))return Response.json({import_run_id:'run-1',checksum:'a'.repeat(64),counts:{groups:1},mappings:{},idempotent_replay:false},{status:201})
    return Response.json({schema:'kuratorskaya-backup',version:1})
  }
  const source={version:3,groups:[{id:'group-1',name:'Синтетическая группа'}],students:[],tasks:[]}
  try {
    await api.legacyApi.validate({source,curator_assignments:{'group-1':'curator-1'}})
    await api.legacyApi.importLegacy({source,curator_assignments:{'group-1':'curator-1'},confirmation_checksum:'a'.repeat(64),confirm:true})
    await api.legacyApi.exportBackup()
  } finally { globalThis.fetch=originalFetch;delete globalThis.document }
  assert.equal(requests[0][1].headers.get('X-CSRF-Token'),'synthetic-csrf')
  assert.equal(JSON.parse(requests[0][1].body).confirm,undefined)
  assert.deepEqual(JSON.parse(requests[1][1].body),{source,curator_assignments:{'group-1':'curator-1'},confirmation_checksum:'a'.repeat(64),confirm:true})
  assert.equal(requests[2][1].method,undefined)

  const pageSource=await fs.readFile(new URL('../src/migration/MigrationPage.tsx',import.meta.url),'utf8')
  assert.match(pageSource,/if \(!currentUser\.is_owner\) return <MigrationPermissionState\/>/)
  assert.match(pageSource,/file\.size > MAX_LEGACY_IMPORT_BYTES/)
  assert.match(pageSource,/requestBytes\(source, assignments, report\.checksum\) > MAX_LEGACY_IMPORT_BYTES/)
  assert.match(pageSource,/disabled=\{flow==='validating'\|\|flow==='importing'\}/)
  assert.match(pageSource,/disabled=\{flow==='validating'\|\|flow==='importing'\} aria-label=/)
  assert.match(pageSource,/migrationErrorMessage\(caught,'import'\)/)
  assert.match(pageSource,/логическую JSON-копию/)
  assert.match(pageSource,/setReport\(null\); setResult\(null\); setConfirmed\(false\)/)
  assert.match(pageSource,/code === 'connection_error'/)
  assert.match(pageSource,/setFlow\('uncertain'\); setReport\(null\)/)
  assert.match(pageSource,/confirmation_checksum: report\.checksum, confirm: true/)
  assert.doesNotMatch(pageSource,/markServerCutover\(\)/)
  assert.equal(pageSource.includes('localStorage.removeItem'),false)
  assert.equal(pageSource.includes("setItem(STORAGE_KEY"),false)

  const appSource=await fs.readFile(new URL('../src/App.tsx',import.meta.url),'utf8')
  assert.doesNotMatch(appSource,/hasServerCutover|loadData|localStorage\.setItem|openLegacyStudent/)
  assert.match(pageSource,/localStorage\.getItem\(STORAGE_KEY\)/)
  assert.equal(appSource.includes('importBackup'),false)

  console.log('Browser-data migration verification passed')
} finally { await server.close() }
