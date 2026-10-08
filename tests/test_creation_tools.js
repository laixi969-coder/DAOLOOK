const assert = require('node:assert/strict');
const tools = require('../web/creation-tools.js');
const workspace = {images:[{creation_id:'photo'}], assets:[{id:'product',kind:'图片'}]};
const make = (id, quality, angle, extra={}) => ({id, task_id:'latest', tracking:{status:'draft'}, data:{title:id,body:'正文',quality,angle,...extra}});
const checked = {status:'checked',issues:[]};
const items = [
  make('missing',{status:'needs_input',issues:['缺少事实']},'角度A'),
  make('ready',checked,'角度B'),
  make('photo',checked,'角度C'),
  make('repeat',checked,'角度C'),
  {...make('old',checked,'角度D'),task_id:'old'},
  {...make('published',checked,'角度E'),tracking:{status:'published'}},
];
const picked = tools.shortlist(items,workspace);
assert.equal(picked.main.id,'photo');
assert.equal(picked.alternatives.length,2);
assert.equal(picked.alternatives.some(c=>c.id==='repeat'),false);
assert.equal(picked.alternatives.some(c=>c.id==='old'),false);
assert.equal(new Set([picked.main,...picked.alternatives,...picked.rest].map(c=>c.id)).size,items.length);
assert.equal(picked.reasons.includes('已保存封面，可在下方下载'),true);
assert.equal(tools.shortlist([items.at(-1)],workspace),null);
assert.equal(tools.shortlist([],workspace),null);
assert.equal(tools.shortlist([make('legacy',undefined,'')],workspace).main.id,'legacy');
const onlyOneAngle = tools.shortlist([make('a',checked,'同一角度'),make('b',checked,'同一角度')],workspace);
assert.equal(onlyOneAngle.alternatives.length,0);
assert.equal(onlyOneAngle.rest.length,1);
assert.equal(tools.publicCopy({title:'标题',body:'正文',tags:['咖啡'],hook:'内部镜头',quality:{note:'内部检查'}}),'标题\n\n正文\n\n#咖啡');
const data = new Map();
const storage = {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k),key:i=>[...data.keys()][i],get length(){return data.size;}};
let time=100;
const store = tools.createEditStore(storage,()=>time);
const changes = tools.editable({title:'稿件',body:'未保存的修改',tags:['话题'],comment_layout:{atmosphere:['问题'],knowledge:['说明'],pinned:{text:'置顶'}}});
assert.equal(tools.fingerprint(changes),tools.fingerprint(Object.fromEntries(Object.entries(changes).reverse())));
store.save('alice:project-a:draft',3,{...changes,password:'never-store'});
assert.deepEqual(store.read('alice:project-a:draft').changes,changes);
assert.equal(store.read('alice:project-a:draft').revision,3);
assert.equal(store.read('alice:project-b:draft'),null);
assert.equal(store.read('bob:project-a:draft'),null);
assert.equal(JSON.stringify([...data.values()]).includes('never-store'),false);
time += 86400001;
assert.equal(store.read('alice:project-a:draft'),null);
store.save('alice:project-a:draft',0,changes);store.save('bob:project-a:draft',0,changes);
store.clearUser('alice');
assert.equal(store.read('alice:project-a:draft'),null);
assert.notEqual(store.read('bob:project-a:draft'),null);
assert.equal(tools.createEditStore({setItem(){throw Error('full')}}).save('x',0,changes),false);
console.log('Creation workflow: batch scope, selection diversity, full retention, copy, edit recovery and isolation passed');
