'use strict';
// Deterministic application-level regressions; no server, provider, or browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDraftStore} = require('../web/draft-store.js');
const CreationTools = require('../web/creation-tools.js');
function context() {
  const values=new Map();
  const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k),key:i=>[...values.keys()][i],get length(){return values.size;}};
  const ctx=vm.createContext({assert,console,createDraftStore,CreationTools,URL,URLSearchParams,structuredClone,
    localStorage:storage,sessionStorage:storage,setTimeout(){},clearTimeout(){},
    document:{handlers:{},querySelector:()=>null,querySelectorAll:()=>[],addEventListener(type,handler){(this.handlers[type]||=[]).push(handler);}},
    window:{addEventListener(){},scrollTo(){}},location:{hash:''}});
  const app=fs.readFileSync(require.resolve('../web/app.js'),'utf8');
  vm.runInContext(app.slice(0,app.lastIndexOf('(async () => {')),ctx);
  vm.runInContext(fs.readFileSync(require.resolve('../web/overseas.js'),'utf8'),ctx);
  vm.runInContext(`
    S.boot={user:{id:'user'},projects:[{id:'project'}],rules:{},credits:{}};
    S.project='project';S.workspaceKey='user:project';S.workspacePages=1;
    S.original.assets=[];S.overseasForm=overseasDefaults();
    render=()=>{};toast=()=>{};
    globalThis.page=(sources=[],cursor=null)=>({sources,briefs:[],assets:[],creations:[],images:[],pagination:{more:!!cursor,cursor,limit:25}});
  `,ctx);
  return ctx;
}
async function test(name,code) {
  await vm.runInContext(`(async()=>{${code}})()`,context());
  console.log('PASS '+name);
}
(async()=>{
  await test('initial workspace stays bounded; refresh replays only loaded pages',`
    let requests=[];let changed=false;
    api=async path=>{
      requests.push(path);
      if(path==='/api/tasks')return [];
      if(path==='/api/bootstrap')return S.boot;
      if(path.includes('cursor=second'))return page([{id:'older',saved:changed?1:0}],'third');
      return page([{id:'newer',saved:0}],'second');
    };
    await refresh();assert.equal(requests.filter(p=>p.startsWith('/api/workspace')).length,1);
    await loadMoreWorkspace();assert.equal(S.workspacePages,2);
    changed=true;requests=[];await refresh();
    assert.equal(S.workspace.sources.length,2);
    assert.equal(S.workspace.sources.find(r=>r.id==='older').saved,1);
    assert.equal(requests.filter(p=>p.startsWith('/api/workspace')).length,2);
    assert.equal(S.workspace.pagination.cursor,'third');
  `);
  await test('active historical source survives mutation refresh outside loaded pages',`
    S.page='detail';S.detail='older';
    api=async path=>path.startsWith('/api/workspace')?page([{id:'newer'}],'second'):
      path==='/api/tasks'?[]:path==='/api/bootstrap'?S.boot:
      {id:'older',saved:1,data:{kind:'source'}};
    await refresh();assert.equal(S.workspace.sources.find(r=>r.id==='older').saved,1);
    assert.equal(S.workspacePages,1);
  `);
  await test('stale load-more cannot overwrite refreshed data or cursor',`
    S.workspace=page([{id:'before'}],'old');let finish;
    api=()=>new Promise(resolve=>finish=resolve);
    const pending=loadMoreWorkspace();
    api=async path=>path.startsWith('/api/workspace')?page([{id:'fresh'}],'current'):path==='/api/tasks'?[]:S.boot;
    await refresh();finish(page([{id:'stale'}],'wrong'));await pending;
    assert.equal(JSON.stringify(S.workspace.sources.map(r=>r.id)),JSON.stringify(['fresh']));
    assert.equal(S.workspace.pagination.cursor,'current');assert.equal(S.loadingWorkspace,false);
  `);
  await test('slower same-project refresh cannot replace newest refresh',`
    let finish;
    api=path=>path.startsWith('/api/workspace')?new Promise(resolve=>finish=resolve):Promise.resolve(path==='/api/tasks'?[]:S.boot);
    const pending=refresh();
    api=async path=>path.startsWith('/api/workspace')?page([{id:'latest'}]):path==='/api/tasks'?[]:S.boot;
    await refresh();finish(page([{id:'obsolete'}]));await pending;
    assert.equal(S.workspace.sources[0].id,'latest');
  `);
  await test('off-page assets survive changes while visible unchecked assets are removed',`
    document.querySelectorAll=()=>[{value:'visible-on',checked:true},{value:'visible-off',checked:false}];
    assert.equal(JSON.stringify(selectedAssetIDs('original-asset',['off-page','visible-off'])),JSON.stringify(['off-page','visible-on']));
    const fields={'#original-goal':'leads','#original-platform':'xhs','#original-topic':'product','#original-keyword':'','#original-requirements':'','#original-temporary':'real facts'};
    document.querySelector=s=>({value:fields[s]});
    S.original.assets=['off-page','visible-off'];let submitted;
    api=async(path,options)=>{submitted=JSON.parse(options.body);throw Error('stop after capture');};
    await startOriginal();assert.equal(JSON.stringify(submitted.assets),JSON.stringify(['off-page','visible-on']));
    for(const key of ['platform','goal','topic','market','language','temporary','requirements','duration'])fields['#overseas-'+key]=key==='duration'?'24':'value';
    S.overseasForm={assets:['off-page','visible-off']};
    assert.equal(JSON.stringify(overseasFormValues().assets),JSON.stringify(['off-page','visible-on']));
  `);
  await test('creation context hydrates its source and compact images on demand',`
    let requests=[];
    api=async path=>{
      requests.push(path);
      if(path.includes('/creations/old/images'))return [{id:'cover',creation_id:'old',data:{url:'/api/media/images/cover?project_id=project'}}];
      if(path.includes('/creations/old'))return {id:'old',source_id:'brief',data:{}};
      return {id:'brief',data:{kind:'brief'}};
    };
    const creation=await ensureCreationContext('old',true);
    assert.equal(creation.id,'old');assert.equal(S.workspace.briefs[0].id,'brief');assert.equal(S.workspace.images[0].id,'cover');
    assert.equal(requests.length,3);assert.equal(requests.some(p=>p.startsWith('/api/workspace')),false);
  `);
  await test('stale creation detail cannot enter a different project',`
    let finish;api=()=>new Promise(resolve=>finish=resolve);
    const pending=ensureCreationContext('old',true);S.project='another';
    finish({id:'old',source_id:'brief',data:{}});await pending;
    assert.equal(S.workspace.creations.length,0);assert.equal(S.workspace.images.length,0);
  `);
  await test('cover plan hydrates its off-page photo before building selector',`
    S.workspace.creations=[{id:'draft',source_id:'source',data:{}}];S.workspace.sources=[{id:'source',data:{}}];
    api=async path=>path.includes('/images?')?[]:{id:'old-photo',kind:'图片',name:'Old photo',content:'data:image/png;base64,AAAA'};
    const contextApi=api;api=async(path,options)=>path==='/api/cover/plan'?{brief:{asset_id:'old-photo',style:'brand',title:'Title',points:[],subtitle:'',brand:''},styles:[],recommended:'brand'}:contextApi(path,options);
    let markup='';modal=(title,html)=>{markup=html;};document.querySelector=()=>({classList:{add(){}}});previewCover=async()=>{};
    await coverStudio('draft');
    assert.equal(markup.includes('value="old-photo" selected'),true);
    assert.equal(S.workspace.assets[0].content,'/api/media/assets/old-photo?project_id=project');
  `);
  await test('historical remote covers open directly without cross-origin fetch',`
    S.workspace.images=[{id:'image',data:{url:'https://provider.example/private.png'}}];let opened;
    fetch=async()=>{throw Error('cross-origin fetch must not run');};
    window.open=(url)=>{opened=url;};await exportCover('image','png');
    assert.equal(opened,'https://provider.example/private.png');
  `);
  await test('private lazy cover export fetches on demand and produces canvas output',`
    S.workspace.images=[{id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',data:{url:'/api/media/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?project_id=bbbb'}}];
    let fetched,drawn=false,downloaded=false;
    fetch=async url=>{fetched=url;return {ok:true,blob:async()=>({})};};
    FileReader=class {readAsDataURL(){this.result='data:image/png;base64,AAAA';this.onload();}};
    Image=class {async decode(){}};document.fonts={ready:Promise.resolve()};
    URL.createObjectURL=()=> 'blob:export';URL.revokeObjectURL=()=>{};
    document.createElement=tag=>tag==='canvas'?{getContext:()=>({fillRect(){},drawImage(){drawn=true;}}),toBlob:fn=>fn({})}:{click(){downloaded=true;}};
    await exportCover('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','png');
    assert.equal(fetched,'/api/media/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?project_id=bbbb');assert.equal(drawn,true);assert.equal(downloaded,true);
  `);
  await test('background search polling preserves foreground generation watcher and busy state',`
    const timers=[];setTimeout=fn=>timers.push(fn);
    S.busy=true;const foreground=['generation'];S.watching=foreground;
    api=async()=>[{id:'search',state:'SUCCEEDED',result:'{}'}];refresh=async()=>{};
    let completed=false;const pending=poll(['search'],async()=>{completed=true;},true);
    assert.equal(S.watching,foreground);await timers.shift()();await pending;
    assert.equal(completed,true);assert.equal(S.watching,foreground);assert.equal(S.busy,true);
  `);
  await test('older task and audit responses are ignored after list replacement',`
    let finish;S.tasks=[{id:'old',created_at:'2026'}];api=()=>new Promise(resolve=>finish=resolve);
    const pending=actions['older-tasks']();S.tasks=[{id:'fresh'}];finish([{id:'stale'}]);await pending;
    assert.equal(S.tasks.length,1);assert.equal(S.tasks[0].id,'fresh');
    S.admin={audit:[{id:'old',created_at:'2026'}]};const audit=actions['older-audit']();
    S.admin={audit:[{id:'fresh'}]};finish([{id:'stale'}]);await audit;
    assert.equal(S.admin.audit.length,1);assert.equal(S.admin.audit[0].id,'fresh');
  `);
  await test('live account controls exclude demo identities and default to clearing old balance',`
    let markup='';modal=(title,html)=>{markup=html;};
    S.boot.user={id:'user',email:'real@example.com',live_access:false,demo_account:false};S.mail=true;
    actions.account();assert.equal(markup.includes('verify-access-form'),true);
    assert.equal(markup.includes('清零'),true);
    S.boot.user.demo_account=true;actions.account();assert.equal(markup.includes('verify-access-form'),false);
    assert.equal(markup.includes('演示身份不能开通'),true);
    S.admin={users:[{id:'target',email:'target@example.com',balance:100,live_access:0,demo_account:0}]};
    actions['activate-access']({dataset:{id:'target'}});
    assert.equal(markup.includes('preserve-live-balance'),true);
    assert.equal(markup.includes('type="checkbox" checked'),false);
    let sent;
    api=async(path,options)=>{
      if(path==='/api/admin/access'){sent=JSON.parse(options.body);return {ok:true};}
      if(path==='/api/admin')return S.admin;
      if(path==='/api/tasks')return [];
      if(path.startsWith('/api/workspace'))return page();
      return S.boot;
    };
    document.querySelector=()=>({checked:false,innerHTML:''});close=()=>{};
    await document.handlers.submit[0]({preventDefault(){},target:{id:'admin-access-form',querySelector:()=>({disabled:false})}});
    assert.equal(sent.user_id,'target');assert.equal(sent.preserve_balance,false);
  `);
  await test('mailbox ownership activation uses verify purpose and authenticated code endpoint',`
    S.boot.user={id:'user',email:'real@example.com',live_access:false};let calls=[];
    api=async(path,options)=>{
      if(options)calls.push({path,body:JSON.parse(options.body)});
      if(path==='/api/tasks')return [];
      if(path.startsWith('/api/workspace'))return page();
      return S.boot;
    };
    await actions['send-access-code']({disabled:false});
    assert.equal(calls[0].path,'/api/auth/code');assert.equal(calls[0].body.purpose,'verify');assert.equal(calls[0].body.email,'real@example.com');
    document.querySelector=()=>({value:'123456'});close=()=>{};
    await document.handlers.submit[0]({preventDefault(){},target:{id:'verify-access-form',querySelector:()=>({disabled:false})}});
    assert.equal(calls[1].path,'/api/auth/verify');assert.equal(calls[1].body.code,'123456');
  `);
  console.log('Frontend review regressions passed (14 cases).');
})().catch(error=>{console.error(error);process.exitCode=1;});
