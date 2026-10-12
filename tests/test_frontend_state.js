const assert = require('node:assert/strict');
const { createDraftStore } = require('../web/draft-store.js');
const data = new Map();
const storage = { getItem:k=>data.get(k)??null, setItem:(k,v)=>data.set(k,v), removeItem:k=>data.delete(k), key:i=>[...data.keys()][i], get length(){return data.size;} };
let now = 100;
const store = createDraftStore(storage, ()=>now);
store.save('alice:project-a', {topic:'咖啡',temporary:'业务资料',goal:'sales',assets:['one'],password:'secret'});
assert.equal(store.read('alice:project-a').temporary,'业务资料');
assert.equal(store.read('alice:project-a').goal,'sales');
assert.equal(store.read('alice:project-b'),null);
assert.equal(store.read('bob:project-a'),null);
assert.equal(JSON.stringify([...data.values()]).includes('secret'),false);
now += 86400001;
assert.equal(store.read('alice:project-a'),null);
store.save('alice:a',{topic:'A'}); store.save('alice:b',{topic:'B'});store.save('bob:b',{topic:'C'});
store.clearUser('alice');assert.equal(store.read('alice:a'),null);assert.equal(store.read('alice:b'),null);assert.equal(store.read('bob:b').topic,'C');
const broken=createDraftStore({getItem(){throw Error('denied')},setItem(){throw Error('full')}},()=>now);
assert.equal(broken.read('x'),null);assert.equal(broken.save('x',{}),false);
console.log('Draft persistence: isolation, expiry, logout, storage failure passed');

// Run application functions against controlled dependencies, without a browser or backend.
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require.resolve('../web/app.js'),'utf8');
const CreationTools = require('../web/creation-tools.js');
const context = vm.createContext({createDraftStore, CreationTools, URLSearchParams, console, localStorage:storage, sessionStorage:storage,
  document:{querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}},
  window:{addEventListener(){}},location:{hash:''},setTimeout(){},clearTimeout(){},assert});
vm.runInContext(source.slice(0,source.lastIndexOf('(async () => {')),context);
vm.runInContext(fs.readFileSync(require.resolve('../web/overseas.js'),'utf8'),context);
(async()=>{
 await vm.runInContext(`(async()=>{
   S.boot={user:{id:'alice'}};S.project='a';S.workspaceKey='alice:a';
   let resolveA;
   api=path => path.startsWith('/api/workspace') ? new Promise(r=>resolveA=r) : Promise.resolve(path==='/api/tasks'?[]:S.boot);
   const old=refresh();
   S.project='b';
   api=async path => path.startsWith('/api/workspace') ? {assets:[],sources:[{id:'b'}],creations:[],images:[]} : path==='/api/tasks'?[]:S.boot;
   await refresh();
   resolveA({assets:[],sources:[{id:'a'}],creations:[],images:[]});await old;
   assert.equal(S.workspace.sources[0].id,'b');
   const fields={'#reference':{value:'https://www.douyin.com/video/123'},'#transcript':{value:'用户输入的真实口播'}};
   document.querySelector=key=>fields[key]||null;
   let submitted;
   render=()=>{fields['#transcript'].value='';};
   api=async(path,options)=>{submitted=JSON.parse(options.body);return {task_ids:['task']};};
   poll=async()=>{};toast=()=>{};
   await startAnalyze();assert.equal(submitted.transcript,'用户输入的真实口播');
   // A delayed overseas library response must not leak into a new project.
   S.project='a';S.page='overseas-ideas';S.overseasLoadToken=0;
   S.overseasFilters={query:'charger',category:'',platform:'all',saved:false};
   api=()=>new Promise(resolve=>{resolveA=resolve;});
   render=()=>{};
   const oldLibrary=loadOverseasIdeas();
   S.project='b';
   api=async()=>({items:[{id:'project-b'}]});
   await loadOverseasIdeas();
   resolveA({items:[{id:'project-a'}]});await oldLibrary;
   assert.equal(S.overseasLibrary.items[0].id,'project-b');
   drafts.save('alice:b:overseas',{platform:'overseas',topic:'Charger',market:'Germany',language:'de-zh',duration:32,reference_id:'one',temporary:'facts',password:'secret'});
   const recovered=drafts.read('alice:b:overseas');
   assert.equal(recovered.language,'de-zh');assert.equal(recovered.duration,32);assert.equal(recovered.password,undefined);
   // Mixed uploads persist and select both documents and image posters.
   S.page='overseas';S.busy=false;S.workspace={assets:[]};S.overseasForm=overseasDefaults();
   saveOverseasDraft=()=>{};
   fileText=async file=>file.text();
   globalThis.FileReader=class {readAsDataURL(file){this.result=file.data;this.onload();}};
   globalThis.Image=class {async decode(){}};
   const uploads=[];
   api=async(path,options)=>{uploads.push({path,value:JSON.parse(options.body)});return {id:'asset-'+uploads.length};};
   const textFile={name:'品牌介绍.txt',type:'text/plain',size:20,text:async()=> '品牌与产品的真实资料'};
   const posterFile={name:'产品海报.png',type:'image/png',size:100,data:'data:image/png;base64,test'};
   await uploadOverseasMaterials({files:[textFile,posterFile],value:'chosen'});
   assert.equal(uploads.length,2);
   assert.equal(uploads[1].value.kind,'图片');
   assert.equal(uploads[1].value.content,posterFile.data);
   assert.equal(S.overseasForm.assets.join(','),'asset-1,asset-2');
   assert.equal(drafts.read('alice:b:overseas').assets.length,2);
   assert.equal(S.overseasUploading,null);
   await assert.rejects(uploadOverseasMaterials({files:[{...textFile,size:3000000}]}),/2 MB/);
   await assert.rejects(uploadOverseasMaterials({files:[{...textFile,name:'file.exe',type:''}]}),/格式不支持/);
   // A later failure keeps earlier successful uploads selected.
   let calls=0;
   api=async()=>{if(++calls===2)throw Error('保存失败');return {id:'partial'};};
   await assert.rejects(uploadOverseasMaterials({files:[textFile,posterFile]}),/已保存 1 份/);
   assert.equal(S.overseasForm.assets.includes('partial'),true);
   // Do not start generation or send delayed files into another workspace.
   let finishRead;
   fileText=()=>new Promise(resolve=>{finishRead=resolve;});
   api=async()=>{throw Error('跨项目上传');};
   const pendingUpload=uploadOverseasMaterials({files:[textFile]});
   await assert.rejects(startOverseas(),/资料正在上传/);
   S.project='c';S.workspace={assets:[]};S.overseasForm=overseasDefaults();
   finishRead('old project document');await pendingUpload;
   assert.equal(S.workspace.assets.length,0);
   assert.equal(S.overseasForm.assets.length,0);
   // A new batch must show every suggestion even after earlier filtering.
   S.overseasForm.topic='Charger';S.onlyFavorites=true;S.stage='published';
   api=async()=>({task_ids:['new-task'],brief_id:'new-brief'});
   poll=async(ids,done)=>done();navigate=async()=>{};
   await startOverseas();
   assert.equal(S.onlyFavorites,false);assert.equal(S.stage,'all');
   assert.equal(S.creationSource,'new-brief');
   S.workspace={assets:[],sources:[],briefs:[],images:[],creations:[]};
   const suggestions=[1,2,3].map(n=>({id:'suggestion-'+n,created_at:'2026-10-12',data:{title:'Idea '+n,body:'Full script '+n,overseas:{platform:'tiktok',market:'US',duration:24,skill:'hiccai-pop'}}}));
   const displayed=creationSelection(suggestions);
   for(let n=1;n<=3;n++) {assert.equal(displayed.includes('建议 '+n),true);assert.equal(displayed.includes('Full script '+n),true);}
   assert.equal(displayed.includes('<details'),false);
   // Only useful deliverables appear, including copyable prompts for old/new records.
   const full={id:'lean-plan',created_at:'2026-10-12',data:{title:'Title',body:'Caption',tags:['product'],concept:'A concrete idea',script:'Spoken script',translation_zh:'中文口播',overseas:{platform:'tiktok',duration:24},shots:[{start:0,end:24,camera:'Close-up',action:'A light moves across the table',ai_prompt:'A scene with <sample>'}],quality:{status:'needs_input',issues:['发布前还需补充']},role:'岗位',shooting_list:['拍摄清单'],missing:['素材缺口'],value:'内容价值',cta:'行动引导'}};
   const lean=overseasCard(full,1),planText=overseasPlanText(full.data);
   for(const ignored of ['发布前还需补充','拍摄清单','素材缺口','岗位','内容价值','行动引导']) {assert.equal(lean.includes(ignored),false);assert.equal(planText.includes(ignored),false);}
   for(const included of ['A concrete idea','Spoken script','Caption','AI 生成提示词']) assert.equal(lean.includes(included),true);
   assert.equal(lean.includes('&lt;sample&gt;'),true);
   assert.equal(overseasAiPrompt(full.data,{camera:'Fixed shot',action:'Old scene'}).includes('Old scene'),true);
   let copiedPrompt;
   globalThis.navigator={clipboard:{writeText:async value=>{copiedPrompt=value;}}};
   S.workspace.creations=[full];
   await actions['copy-overseas-prompt']({dataset:{id:'lean-plan',shot:'0'}});
   assert.equal(copiedPrompt,'A scene with <sample>');
 })()`,context);
 console.log('Frontend async regressions: project isolation, transcript preservation and overseas draft recovery passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
