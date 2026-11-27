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
  await test('production board renders full-project stats with today output and direction mix',`
    S.workspace={stats:{today:7,total:9,published:2,directions:{xhs:{'测评':4,'钓鱼帖':2},douyin:{'建立信任':6}},results:{recorded:2,views:300,leads:5,orders:1}},sources:[],briefs:[],assets:[],creations:[],images:[]};
    const card=productionBoard([
      {id:'1',created_at:new Date().toISOString(),data:{demo:true,direction:'测评'},tracking:{status:'draft'},results:{}},
      {id:'2',created_at:'2026-01-01T00:00:00+00:00',data:{},tracking:{status:'published',published_at:new Date().toISOString()},results:{}}
    ]);
    assert.ok(card.includes('今日产出'));
    assert.ok(card.includes('<strong>7'));
    assert.ok(card.includes('小红书图文 测评 4 · 钓鱼帖 2'));
    assert.ok(card.includes('抖音脚本 建立信任 6'));
    assert.ok(card.includes('提醒：不要整批只做一种岗位'));
    assert.ok(card.includes('<strong>2<small> / 9'));
    assert.ok(card.includes('<strong>300</strong>'));
    assert.ok(card.includes('不受列表分页影响'));
    // 旧响应没有 stats 时回退到已加载稿件口径，不抛错
    S.workspace={sources:[],briefs:[],assets:[],creations:[],images:[]};
    const fallback=productionBoard([{id:'3',created_at:new Date().toISOString(),data:{demo:false,direction:'测评'},tracking:{status:'draft'},results:{}}]);
    assert.ok(fallback.includes('今日产出'));
    assert.ok(fallback.includes('<strong>1'));
  `);
  await test('submitWithIntake asks once, merges answer and never loops',`
    S.intakeSkipped={};let calls=[];
    const submit=async d=>{calls.push(d);
      if(!d.answer&&!d.skip_question)return {ask:{id:'leads_missing',question:'q'}};
      if(d.answer)return {ask:{id:'price_conflict',question:'q2'}};  // 回答后仍命中，应自动跳过而不是再问
      return {task_ids:['t']};};
    modal=(t,h)=>{};close=()=>{};
    const pending=submitWithIntake({temporary:'x'},submit);
    await Promise.resolve();await Promise.resolve();await Promise.resolve();
    assert.ok(S.intakeResolve);
    document.querySelector=()=>({value:'私信我'});
    await actions['intake-answer']();
    const r=await pending;
    assert.equal(r.task_ids[0],'t');
    assert.equal(calls.length,3);
    assert.equal(calls[1].answer,'私信我');
    assert.equal(calls[2].skip_question,true);
  `);
  await test('skipping the question remembers dismissal per workspace',`
    S.intakeSkipped={};
    const submit=async d=>d.skip_question?{task_ids:['t2']}:{ask:{id:'sales_missing',question:'q'}};
    modal=()=>{};close=()=>{};
    const pending=submitWithIntake({},submit);
    await Promise.resolve();await Promise.resolve();await Promise.resolve();
    await actions['intake-skip']();
    const r=await pending;
    assert.equal(r.task_ids[0],'t2');
    assert.equal(S.intakeSkipped['user:project:sales_missing'],true);
    // 已跳过的问题不再弹窗
    let asked=0;modal=()=>{asked++;};
    const r2=await submitWithIntake({},async d=>d.skip_question?{task_ids:['t3']}:{ask:{id:'sales_missing',question:'q'}});
    assert.equal(r2.task_ids[0],'t3');
    assert.equal(asked,0);
  `);
  await test('optional observation form captures source and persists per project',`
    const fields={'#original-goal':'leads','#original-platform':'xhs','#original-topic':'写真', '#original-keyword':'', '#original-requirements':'', '#original-temporary':'业务资料',
      '#original-question-text':'底片全部给吗？','#original-question-source':'customer_quote', '#original-question-context':'首次拍摄','#original-question-reference':'咨询记录','#original-question-occurred_on':'2026-11-06'};
    document.querySelector=s=>({value:fields[s]});let submitted;
    api=async(path,options)=>{submitted=JSON.parse(options.body);throw Error('stop after capture');};
    await startOriginal();
    assert.equal(submitted.observation.text,'底片全部给吗？');assert.equal(submitted.observation.source,'customer_quote');
    assert.equal(drafts.read(workspaceKey()).observation.context,'首次拍摄');
    assert.equal(drafts.read('user:another'),null);
  `);
  await test('topic provenance escapes user content and never enters public copy',`
    S.workspace.assets=[];
    const data={title:'标题',body:'正文',tags:[],topic_plan:{problem:'<script>bad</script>',relevance:'人群',answer:'回答',takeaway:'收获',approach:'答疑'},topic_basis:{status:'sourced',sources:[{source_label:'客户原话',quote:'<img src=x>',reference:'javascript:alert(1)'}],answer_sources:[]}};
    const html=topicBasis(data);
    assert.equal(html.includes('<script>'),false);assert.equal(html.includes('<img src=x>'),false);
    assert.equal(html.includes('href="javascript:'),false);assert.equal(html.includes('来源证明记录存在'),true);
    assert.equal(CreationTools.publicCopy(data),'标题\\n\\n正文');
    assert.equal(topicBasis({...data,topic_basis:{...data.topic_basis,status:'hypothesis'}}).includes('待验证'),true);
    assert.equal(topicBasis({...data,topic_basis:{...data.topic_basis,status:'clue'}}).includes('市场线索'),true);
    assert.equal(topicBasis({...data,topic_basis:{...data.topic_basis,review_required:true}}).includes('稿件已修改'),true);
  `);
  await test('draft cards expose existing publish and result workflows',`
    S.workspace={sources:[{id:'s',platform:'xhs'}],assets:[],images:[]};
    const html=draftCard({id:'c',source_id:'s',created_at:'2026-11-07',data:{title:'标题',body:'正文',tags:[]}});
    assert.equal(html.includes('data-action="publish"'),true);
    assert.equal(html.includes('data-action="record-results"'),true);
    assert.equal(html.includes('发布与反馈'),true);
  `);
  await test('question library discards late responses after switching projects',`
    let finish,shown=false;api=()=>new Promise(resolve=>finish=resolve);modal=()=>{shown=true;};
    const pending=questionLibrary();S.project='different';finish({items:[{text:'private'}],feedback:[]});await pending;
    assert.equal(shown,false);assert.equal(S.questionLibrary,undefined);
  `);
  await test('reference creation submits observation separately from business facts',`
    S.detail='source';S.selectedAssets=[];
    const fields={'#requirements':'语气自然','#temporary':'业务事实','#create-question-text':'真实问题','#create-question-source':'field_observation'};
    document.querySelector=s=>({value:fields[s]});let submitted;
    api=async(path,options)=>{submitted=JSON.parse(options.body);throw Error('stop after capture');};
    await startCreate();assert.equal(submitted.observation.source,'field_observation');
    assert.equal(submitted.temporary,'业务事实');
  `);
  await test('accepted creation clears submitted observation without clearing business draft',`
    const fields={'#original-goal':'leads','#original-platform':'xhs','#original-topic':'写真', '#original-keyword':'', '#original-requirements':'', '#original-temporary':'真实资料', '#original-question-text':'底片给吗？','#original-question-source':'customer_quote'};
    document.querySelector=s=>({value:fields[s]});api=async()=>({task_ids:['task'],brief_id:'brief'});poll=async()=>{};
    await startOriginal();assert.equal(S.original.temporary,'真实资料');
    assert.equal(JSON.stringify(S.original.observation),'{}');
    assert.equal(JSON.stringify(drafts.read(workspaceKey()).observation),'{}');
  `);
  await test('overseas shares optional evidence and published feedback without changing creative format',`
    S.overseasForm={...overseasDefaults(),topic:'charger',observation:{text:'Too many cables',source:'field_observation'}};
    S.workspace={assets:[],images:[],sources:[]};
    const html=overseasPage();assert.equal(html.includes('overseas-question-text'),true);
    assert.equal(html.includes('Too many cables'),true);
    const card=overseasCard({id:'c',data:{title:'Story',body:'Copy',tags:[],overseas:{platform:'tiktok'}}});
    assert.equal(card.includes('data-action="publish"'),true);
    assert.equal(card.includes('data-action="record-results"'),true);
  `);
  await test('closing the question dialog settles as skip',`
    S.intakeSkipped={};
    const submit=async d=>d.skip_question?{task_ids:['t']}:{ask:{id:'leads_missing',question:'q'}};
    modal=()=>{};close=()=>{};
    const pending=submitWithIntake({},submit);
    await Promise.resolve();await Promise.resolve();await Promise.resolve();
    actions.close();
    const r=await pending;
    assert.equal(r.task_ids[0],'t');
    assert.equal(S.intakeSkipped['user:project:leads_missing'],true);
  `);
  await test('result list restores the domestic shortlist and preserves every card',`
    S.workspace={sources:[{id:"s",platform:"xhs"}],assets:[],images:[],briefs:[]};
    const draft=(id,angle,status)=>({id,source_id:"s",task_id:"batch",data:{title:id,body:"真实正文",angle,quality:{status,issues:status==="needs_input"?["请核对价格"]:[]},shooting_list:["手机"],image_suggestions:["实物图"],comment_layout:{knowledge:["回复顾客"]}}});
    const items=[draft("未核对稿","展示","needs_input"),draft("优先稿","对比","checked"),draft("另一种说法","解答","checked"),draft("同切角稿","对比","checked")];
    const html=creationSelection(items);
    assert.match(html,/draft-featured/);assert.ok(html.indexOf("<h3>优先稿")<html.indexOf("<h3>未核对稿"));
    assert.equal((html.match(/<article /g)||[]).length,4);
    assert.match(html,/备选稿/);assert.match(html,/拍摄清单/);assert.match(html,/可用的评论回复/);
    assert.match(html,/发布前需核对/);assert.match(html,/复制待核对稿/);assert.match(html,/确认可发布/);
    items[0].ready_at="2026-01-01";assert.ok(creationSelection(items).includes("这版稿件已由你确认可发布"));
    const calls=[];api=async(path,opt)=>{if(!opt)return {...items[0]};calls.push([path,JSON.parse(opt.body)]);return {};};refresh=async()=>{};
    items[0].source_digest="reviewed-source-version";
    S.workspace.creations=items;await actions["confirm-ready"]({dataset:{id:items[0].id}});
    assert.equal(calls[0][0],"/api/creations/未核对稿/ready");assert.equal(calls[0][1].revision,0);
    assert.equal(calls[0][1].source_digest,items[0].source_digest);
    const newer={...items[0],source_digest:"changed-price"};
    api=async(path,opt)=>{assert.equal(opt,undefined);return newer;};
    await actions["confirm-ready"]({dataset:{id:items[0].id}});
    assert.equal(items[0].source_digest,"changed-price");
  `);
  await test('board shows an explicit zero only for a measured metric and uses matched views',`
    S.workspace={sources:[],briefs:[],assets:[{kind:"账号",id:"acc",name:"总店"}],images:[],stats:{
      results:{recorded:1,views:0,leads:0,orders:0},metric_counts:{views:1,leads:0,orders:0},account_published:{acc:25},
      delivery:{formal:4,published:1,confirmed_batches:2,first_ready_seconds:120},
      goal_windows:[{platform:"instagram",goal:"leads",window:"7d",total:8,posts:3,paired_posts:2,paired_views:400,paired_actions:2}]
    }};
    const html=productionBoard([{data:{},tracking:{status:"draft"}}]);
    assert.ok(html.includes("浏览次数</p><strong>0</strong>"));assert.ok(html.includes("订单数</p><strong>—</strong>"));
    assert.ok(html.includes("25%"));assert.ok(html.includes("2 分钟"));assert.ok(html.includes("5.0 咨询/千次浏览（2 篇）"));
    assert.ok(html.includes("已发 25"));
  `);
  await test('mature release cohorts and comparable accounts display their denominators',`
    const c={batches:4,published_batches:1,confirmed_batches:2,confirmed_drafts:3,
      seven_day_posts:2,seven_day_filled:0,manual_revisions:2,timed_revisions:1,median_edit_minutes:0,
      unknown_batches:1,model:{calls:2,retries:1,input_tokens:25,output_tokens:10,
      usage_calls:1,metered_tasks:3,tasks:4,per_confirmed_microusd:null}};
    const html=cohortOverview(c);
    assert.ok(html.includes("25%（1/4）") && html.includes("0%（0/2）") && html.includes("0 分钟"));
    assert.ok(html.includes("估算模型费</p><strong>—"));
    const group={account_id:"account",account_name:"分店<一>",platform:"xhs",goal:"sales",window:"7d",
      traffic_type:"paid",posts:2,total:2,paired_views:90,paired_actions:2,paired_posts:1};
    const table=goalWindowTable([group],true);
    assert.ok(table.includes("分店&lt;一&gt;") && table.includes("含付费流量"));
  `);
  await test('results editor preserves unknowns, prevents accidental loss and saves the selected window',`
    const pub="2020-01-01T12:00:00Z";const draft={id:"c",tracking:{status:"published",published_at:pub},
      results:{views:100,note:"记录",recorded_at:"v1",windows:{"24h":{views:30,leads:0}}}};
    S.workspace={creations:[draft]};let form, payload;modal=(title,html)=>{form=html;};close=()=>{};refresh=async()=>{};
    actions["record-results"]({dataset:{id:"c"}});assert.match(form,/统计截至/);
    const inputs={};for (const [k,v] of Object.entries({views:"100",leads:"",orders:"",spend:"",note:"记录"}))inputs["#result-"+k]={value:v};
    document.querySelector=id=>inputs[id];const select={id:"result-window",value:"24h",dataset:{}};
    const change=()=>document.handlers.change[0]({target:select});
    await change();assert.equal(inputs["#result-leads"].value,0);assert.equal(inputs["#result-orders"].value,"");
    for (const inp of Object.values(inputs))inp.value=String(inp.value);
    inputs["#result-views"].value="31";select.value="7d";await change();assert.equal(select.value,"24h");
    api=async(path,opt)=>{payload=JSON.parse(opt.body);return {};};
    await document.handlers.submit[0]({preventDefault(){},target:{id:"results-form",querySelector:()=>({disabled:false})}});
    assert.equal(payload.window,"24h");assert.equal(payload.results.leads,0);assert.equal(payload.results.views,31);
    assert.equal("orders" in payload.results,false);assert.equal(payload.expected_updated_at,"v1");assert.equal(payload.expected_published_at,pub);
  `);
  await test('daily and archived players carry the displayed reference to a free, recoverable project draft',`
    let dialog, closed=false, posted;
    modal=(title,html)=>{dialog=html;}; close=()=>{closed=true;};
    S.workspace=page(); S.overseasForm={...overseasDefaults(),topic:'柜台活动',goal:'sales',assets:['photo']};
    for (const edition of ['today','archive']) {
      S.page='overseas-ideas';
      const ref='edition_'+edition, item={id:'same-video',creation_reference_id:ref,title_zh:'柜台翻牌',url:'https://www.youtube.com/shorts/E8rFu6YYzsw'};
      S.overseasLibrary={items:[item]};
      assert.ok(!overseasDailyCard(item).includes('用这条拍法创作'));
      actions['play-overseas-video']({dataset:{id:item.id,reference:ref}});
      assert.ok(dialog.includes('用这条拍法创作') && dialog.includes('data-reference="'+ref+'"'));
      // A subsequent library refresh must not change the reference in an already open player.
      S.overseasLibrary.items=[];
      await actions['use-overseas-idea']({dataset:{reference:ref,title:item.title_zh,workspace:workspaceKey()},closest:()=>true});
      assert.equal(closed,true);assert.equal(S.page,'overseas');
      const saved=drafts.read(workspaceKey()+':overseas');
      assert.equal(saved.reference_id,ref);assert.equal(saved.reference_title,'柜台翻牌');
      assert.equal(saved.goal,'sales');assert.deepEqual(Array.from(saved.assets),['photo']);
      assert.ok(overseasPage().includes('柜台翻牌'));
    }
    assert.ok(overseasDailyCard({id:'old',creation_reference_id:'legacy-ref',title:'往期短片'}).includes('data-reference="legacy-ref"'));
    await actions['use-overseas-idea']({dataset:{reference:'wrong',title:'别的项目',workspace:'other:project'}});
    assert.equal(S.overseasForm.reference_id,'edition_archive');
    api=async(path,opts)=>{posted=JSON.parse(opts.body);return {task_ids:[]};};poll=async()=>{};
    await startOverseas();
    assert.equal(posted.reference_id,'edition_archive');assert.equal(posted.reference_title,undefined);
    actions['clear-overseas-reference']();assert.equal(drafts.read(workspaceKey()+':overseas').reference_id,'');
  `);
  await test('editor shows fact conflicts beside source text and escapes both',`
    S.workspace=page();S.workspace.assets=[{id:'a',name:'门店价目表'}];
    const html=editorFactChecks({claim_checks:[{status:'review',value:'99元',sentence:'现价99元<x>',reason:'价格不符',source:{asset_id:'a',quote:'售价199元<y>'}}]});
    assert.ok(html.includes('1 项待核对') && html.includes('99元&lt;x&gt;') && html.includes('售价199元&lt;y&gt;'));
    assert.ok(html.includes('门店价目表') && html.includes('价格不符'));
    assert.equal(editorFactChecks({}), '');
  `);
  await test('candidate with no metrics opens manual analysis with its exact link and no charge',`
    S.workspace=page();S.transcript='上一条字幕';S.entry='keyword';
    let html,visits=[],payments=0;const url='https://www.xiaohongshu.com/explore/test';
    modal=(title,body)=>{html=body;};close=()=>{};navigate=async view=>visits.push(view);
    api=async()=>{payments++;};
    await actions['prepare-reference']({dataset:{url,workspace:'another-project'}});
    assert.equal(S.entry,'keyword');
    showReferenceCandidates([],[{title:'原片<x>',url},{title:'假的',url:'https://example.org/video/x'}]);
    assert.ok(html.includes('待核实') && html.includes('带入单条拆解') && html.includes('原片&lt;x&gt;') && !html.includes('假的'));
    await actions['prepare-reference']({dataset:{url,workspace:workspaceKey()}});
    assert.equal(S.entry,'single');assert.equal(S.entryText,url);assert.equal(S.transcript,'');
    assert.deepEqual(visits,['discover']);assert.equal(payments,0);
  `);
  await test('redteam review renders escaped scores and issues without entering public copy',`
    const review={version:'2.0',scores:{hook:6,emotion:8,meme:5,sharpness:9,fit:8},fatal_issues:['开头偏平<script>'],summary:'已重构<img src=x>',note:'仅作自审',edited_after:true};
    const html=redteamReviewBox(review,true);
    assert.ok(html.includes('红队爆款精修') && html.includes('redteam-score low') && html.includes('6/10') && html.includes('此后有新修改'));
    assert.equal(html.includes('<script>'),false);assert.equal(html.includes('<img src=x>'),false);
    assert.equal(CreationTools.publicCopy({title:'标题',body:'正文',tags:[],redteam_review:review}),'标题\\n\\n正文');
    S.workspace={sources:[{id:'s',platform:'xhs'}],assets:[],images:[],briefs:[]};
    const card=draftCard({id:'c',source_id:'s',created_at:'2026-11-27',data:{title:'标题',body:'正文',tags:[],redteam_review:review}});
    assert.ok(card.includes('红队爆款精修'));
    S.editSession={id:'c',revision:1,readonly:false,dirty:false};
    document.querySelector=()=>({value:''});
    let sent;api=async(path,opts)=>{sent={path,body:JSON.parse(opts.body)};return {task_ids:['t']};};
    poll=async()=>{};
    await actions['redteam-draft']();
    assert.equal(sent.path,'/api/creations/c/rewrite');
    assert.equal(sent.body.mode,'redteam');assert.equal(sent.body.revision,1);assert.equal(sent.body.instruction,'');
  `);
  console.log('Frontend review regressions passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
