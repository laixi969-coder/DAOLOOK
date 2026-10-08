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
const context = vm.createContext({createDraftStore, CreationTools, console, localStorage:storage, sessionStorage:storage,
  document:{querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}},
  window:{addEventListener(){}},location:{hash:''},setTimeout(){},clearTimeout(){},assert});
vm.runInContext(source.slice(0,source.lastIndexOf('(async () => {')),context);
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
 })()`,context);
 console.log('Frontend async regressions: stale project response and transcript preservation passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
