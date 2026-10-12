"use strict";

const OVERSEAS_NAMES = {overseas:"三平台 · 3 个不同创意",tiktok:"TikTok",instagram:"Instagram Reels",youtube:"YouTube Shorts"};
function platformLabel(p) { return OVERSEAS_NAMES[p] || (p === "douyin" ? "抖音脚本" : "小红书图文"); }
function overseasDefaults() { return {platform:"overseas",goal:"leads",topic:"",market:"United States",language:"en-zh",duration:24,temporary:"",requirements:"",assets:[],reference_id:""}; }
function overseasFormValues() {
  const value={};
  for (const name of ["platform","goal","topic","market","language","temporary","requirements"])
    value[name]=$(`#overseas-${name}`).value;
  value.duration=Number($("#overseas-duration").value);
  value.assets=$$("input[name=overseas-asset]:checked").map(el=>el.value);
  value.reference_id=S.overseasForm?.reference_id || "";
  return value;
}
function saveOverseasDraft() {
  if (!$("#overseas-form")) return;
  S.overseasForm=overseasFormValues();
  drafts.save(workspaceKey()+":overseas",S.overseasForm);
  const count=$("[data-overseas-selected]");
  if(count) count.textContent=`已选 ${S.overseasForm.assets.length} 份`;
}
function overseasMaterials(value, assets) {
  const uploading=S.overseasUploading===workspaceKey();
  return `<section class="overseas-materials"><div class="section-head"><h3>上传创作资料</h3><span class="muted" data-overseas-selected>已选 ${value.assets.length} 份</span></div><p>产品介绍、品牌文档、产品图或活动海报，都可以作为本次创作依据。</p><label class="overseas-upload"><span>${icon("plus")} ${uploading?"正在读取并保存资料…":"选择文档、图片或海报"}</span><input type="file" id="overseas-material-files" accept=".txt,.md,.csv,.docx,.pdf,image/png,image/jpeg,image/webp" multiple ${uploading||S.busy?"disabled":""}></label><p class="hint">支持 TXT、MD、CSV、Word（.docx）、PDF、PNG、JPG、WebP；每份最多 2 MB，一次最多 6 份。上传后保存到当前项目并自动勾选。文档提取文字，图片交给支持看图的创作模型；扫描版 PDF 请先转成图片。</p>${assets.length?`<div class="overseas-assets">${assets.map(a=>`<label class="overseas-asset"><input type="checkbox" name="overseas-asset" value="${esc(a.id)}" ${value.assets.includes(a.id)?"checked":""}>${a.kind==="图片"?`<img src="${esc(safeImage(a.content))}" alt="${esc(a.name)}预览">`:`<span class="asset-document-icon">${icon("folder")}</span>`}<span class="overseas-asset-name">${esc(a.name)}<small>${a.kind==="图片"?"图片 / 海报":esc(a.kind)}</small></span></label>`).join("")}</div>`:""}<p class="hint">取消勾选即可从本次创作移除，资料仍保留在项目中。</p></section>`;
}
async function uploadOverseasMaterials(input) {
  const files=[...input.files];
  if(!files.length) return;
  const key=workspaceKey(), project=S.project;
  if(S.overseasUploading===key || S.busy) throw new Error("请等待当前上传或生成完成");
  if(files.length>6) throw new Error("一次最多上传 6 份资料");
  for(const file of files) {
    if(file.size>2*1024*1024) throw new Error(`${file.name} 超过 2 MB`);
    if(!["image/png","image/jpeg","image/webp"].includes(file.type) && !/\.(txt|md|csv|docx|pdf)$/i.test(file.name)) throw new Error(`${file.name} 格式不支持，请选择文档或 PNG/JPG/WebP 图片`);
  }
  saveOverseasDraft();
  S.overseasUploading=key;
  render();
  let saved=0;
  try {
    for(const file of files) {
      if(key!==workspaceKey()) break;
      const picture=["image/png","image/jpeg","image/webp"].includes(file.type);
      let content;
      if(picture) {
        content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error("图片读取失败"));reader.readAsDataURL(file);});
        const img=new Image();img.src=content;
        try {await img.decode();} catch {throw new Error(`${file.name} 无法解码，请重新选择图片`);}
      } else {
        content=await fileText(file);
        if(!content.trim()) throw new Error(`${file.name} 没有可读取的文字，扫描文档可转成图片上传`);
        if(content.length>100000) throw new Error(`${file.name} 提取后超过 10 万字，请拆分文件`);
      }
      if(key!==workspaceKey()) break;
      const asset={project_id:project,name:file.name,kind:picture?"图片":"产品信息",content};
      const result=await post("/api/assets",asset);
      if(key!==workspaceKey()) break;
      saveOverseasDraft();
      S.workspace.assets.push({...asset,...result});
      S.overseasForm.assets=[...new Set([...S.overseasForm.assets,result.id])];
      drafts.save(key+":overseas",S.overseasForm);
      saved++;
      if(S.page==="overseas") render();
    }
  } catch(error) {
    if(key===workspaceKey()) throw new Error(`${saved?`已保存 ${saved} 份资料。`:""}${error.message}`);
  } finally {
    input.value="";
    if(S.overseasUploading===key) S.overseasUploading=null;
    if(key===workspaceKey() && S.page==="overseas") render();
  }
  if(key===workspaceKey() && saved) toast(`已上传 ${saved} 份资料，并选入本次创作`);
}
function overseasPage() {
  const value=S.overseasForm || overseasDefaults();
  const assets=S.workspace.assets.filter(a=>a.kind!=="账号");
  return heading("让你的产品，有一个值得看完的故事。", "上传产品资料，选择平台和目标市场，生成视频创意与拍摄脚本。",button("浏览海外灵感","overseas-ideas","secondary","grid"),"OVERSEAS CREATIVE STUDIO")+
    `<div class="overseas-studio"><section class="panel"><form id="overseas-form"><div class="original-grid"><label class="field"><span>发布平台</span><select id="overseas-platform">${Object.entries(OVERSEAS_NAMES).map(([id,label])=>`<option value="${id}" ${id===value.platform?"selected":""}>${label}</option>`).join("")}</select></label>${goalPicker("overseas-goal",value.goal)}</div><label class="field"><span>产品或创作主题</span><input id="overseas-topic" maxlength="200" required value="${esc(value.topic)}" placeholder="例如：三合一折叠无线充电器"></label><div class="original-grid"><label class="field"><span>目标市场</span><input id="overseas-market" maxlength="60" required value="${esc(value.market)}" placeholder="例如：United States / Germany"></label><label class="field"><span>台词语言 + 中文翻译</span><select id="overseas-language">${Object.entries({"en-zh":"英文 + 中文","es-zh":"西班牙文 + 中文","fr-zh":"法文 + 中文","de-zh":"德文 + 中文"}).map(([id,label])=>`<option value="${id}" ${id===value.language?"selected":""}>${label}</option>`).join("")}</select></label></div><label class="field"><span>目标时长（秒）</span><input id="overseas-duration" type="number" min="12" max="60" step="1" value="${value.duration}" required></label>${value.reference_id?`<div class="notice">已选参考：${esc(S.overseasReferenceTitle||"海外创意")}。只借鉴表达机制，产品事实来自你的资料。<button class="text-btn" type="button" data-action="clear-overseas-reference">取消参考</button></div>`:""}<label class="field"><span>真实卖点、受众和拍摄条件</span><textarea id="overseas-temporary" rows="5" maxlength="100000" placeholder="粘贴产品参数、已证实的卖点、客户疑问、可用的实物与场景。也可以先只写产品名，缺失事实会明确标注。">${esc(value.temporary)}</textarea></label>${overseasMaterials(value,assets)}<label class="field"><span>特别要求（可选）</span><textarea id="overseas-requirements" rows="2" maxlength="100000" placeholder="例如：不露脸、一人用手机拍、家居桌面场景">${esc(value.requirements)}</textarea></label><div class="entry-bottom"><span>${S.boot.mode==="demo"?"演示模板 · 不调用模型、不实际翻译":"一次给出 3 个不同创意建议"}</span><span>预计 ${originalCost()} 积分 · 失败退还</span></div><button class="btn primary full" type="submit" ${S.busy||S.overseasUploading===workspaceKey()?"disabled":""}>${icon("spark")}${S.overseasUploading===workspaceKey()?"资料上传中…":S.busy?"正在生成海外创意":"生成 3 个创意建议"}</button></form></section></div>`;
}
function overseasIdeasPage() {
  const lib=S.overseasLibrary;
  const filters=S.overseasFilters || {query:"",category:"",platform:"all",saved:false};
  return heading("把值得借鉴的海外创意，收进来。", "搜索平台内容、收集原始链接，或浏览 60 个旧版案例原型。收藏后可直接带入创作。",`<div class="actions">${button("收集链接","collect-overseas","secondary","plus")}${button("开始海外创作","overseas","primary","spark")}</div>`,"OVERSEAS INSPIRATION")+
    `<section class="panel overseas-library-controls"><div class="overseas-library-tabs"><button class="chip ${!filters.saved?"active":""}" data-action="overseas-tab" data-saved="0">创意推荐</button><button class="chip ${filters.saved?"active":""}" data-action="overseas-tab" data-saved="1">我的收藏</button></div><form id="overseas-filter-form"><label class="field"><span>关键词 / 产品</span><input id="overseas-query" maxlength="100" value="${esc(filters.query)}" placeholder="charger / 收纳 / cleaning"></label><label class="field"><span>品类</span><select id="overseas-category"><option value="">全部品类</option>${Object.entries(lib?.categories||{}).map(([id,label])=>`<option value="${id}" ${filters.category===id?"selected":""}>${esc(label)}</option>`).join("")}</select></label><label class="field"><span>平台</span><select id="overseas-filter-platform"><option value="all">全部平台</option>${Object.entries(OVERSEAS_NAMES).filter(([id])=>id!=="overseas").map(([id,label])=>`<option value="${id}" ${filters.platform===id?"selected":""}>${label}</option>`).join("")}</select></label><button class="btn secondary" type="submit">筛选推荐</button><button class="btn primary" type="button" data-action="search-overseas" ${S.overseasSearching?"disabled":""}>${S.overseasSearching?"正在搜索…":"搜索平台内容"}</button></form><p class="hint">平台搜索请填写关键词并选择一个平台；可能产生数据源费用。${lib?.search_available?"":"当前实时数据源未启用，仍可浏览原型和收集链接。"}</p>${S.overseasMessage?`<p class="notice" role="status">${esc(S.overseasMessage)}</p>`:""}</section>`+
    (lib?`<div class="section-head"><h2>${filters.saved?"收藏的创意":"推荐创意"} <span>${lib.items.length} 条</span></h2><span class="muted">旧版原型仅供启发，未附原视频或核验指标</span></div>${lib.items.length?`<div class="overseas-idea-grid">${lib.items.map(overseasIdeaCard).join("")}</div>`:empty("暂时没有匹配的创意","试试其他关键词、取消筛选，或收集一条你发现的链接。",button("收集链接","collect-overseas","primary","plus"))}`:'<div class="loading-line">正在读取海外创意库…</div>');
}
function overseasIdeaCard(item) {
  return `<article class="overseas-idea-card"><div class="idea-meta"><span class="direction-badge">${item.source_kind==="archetype"?"旧版案例原型":platformLabel(item.platform)}</span><span>${esc(item.category_name||"待分类")}</span></div><h3>${esc(item.title)}</h3><p class="idea-summary">${esc(item.summary||"尚未补充字幕或创意说明")}</p>${item.reflex?`<div class="overseas-methods"><span>${esc(item.reflex)}</span><span>${esc(item.technique)}</span></div>`:""}${item.mechanism?`<p>借鉴点：${esc(item.mechanism)}</p>`:""}${Object.keys(item.metrics||{}).length?`<div class="metrics">${Object.entries(item.metrics).map(([k,v])=>`<span>${{views:"播放",likes:"点赞",comments:"评论",shares:"分享"}[k]||k} ${fmt(v)}</span>`).join("")}</div>`:""}<p class="idea-reason">${esc(item.recommendation||"关键词搜索候选，尚未完成创意拆解")}</p><details class="source-evidence"><summary>来源与推荐依据</summary><p>${esc(item.source||"用户收集")}</p><p>${esc(item.note)}</p>${item.fetched_at?`<p>获取于 ${date(item.fetched_at)}</p>`:""}${item.url?`<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">查看原始内容 ↗</a>`:""}</details><div class="actions">${button(item.saved?"已收藏":"收藏","save-overseas-idea","secondary small",item.saved?"check":"star",`data-id="${item.id}"`)}${button("用这个创意创作","use-overseas-idea","primary small","spark",`data-id="${item.id}"`)}</div></article>`;
}
async function loadOverseasIdeas() {
  const key=workspaceKey(); const request=++S.overseasLoadToken;
  const f=S.overseasFilters;
  const params=new URLSearchParams({project_id:S.project,query:f.query,category:f.category,platform:f.platform,saved:f.saved?"1":"0"});
  try {
    const library=await api("/api/overseas/ideas?"+params);
    if(key!==workspaceKey() || request!==S.overseasLoadToken) return;
    S.overseasLibrary=library;
  } catch(error) { if(key===workspaceKey() && request===S.overseasLoadToken) {S.overseasMessage=error.message;S.overseasLibrary={items:[],categories:{}};} }
  if(key===workspaceKey() && S.page==="overseas-ideas") render();
}
function readOverseasFilters() {
  S.overseasFilters={...S.overseasFilters,query:$("#overseas-query").value.trim(),category:$("#overseas-category").value,platform:$("#overseas-filter-platform").value};
}
async function searchOverseas() {
  if(S.overseasSearching) return;
  readOverseasFilters(); const f={...S.overseasFilters},key=workspaceKey();
  if(!f.query || f.platform==="all") throw new Error("请填写关键词，并选择TikTok、Reels或Shorts中的一个平台");
  S.overseasSearching=true; S.overseasMessage=""; render();
  const request=++S.overseasLoadToken;
  try {
    const result=await post("/api/overseas/search",body({query:f.query,platform:f.platform}));
    if(key!==workspaceKey() || request!==S.overseasLoadToken) return;
    S.overseasFilters={...f,saved:false};
    S.overseasLibrary={...S.overseasLibrary,items:result.items};
    S.overseasMessage=`已取得 ${result.items.length} 条平台候选${result.cached?"，使用15分钟内的缓存":""}，可收藏后用于创作。`;
  } catch(error) {if(key===workspaceKey() && request===S.overseasLoadToken) S.overseasMessage=error.message;}
  finally {if(key===workspaceKey()) {S.overseasSearching=false;if(S.page==="overseas-ideas") render();}}
}
function collectOverseasModal() {
  modal("收集海外社媒内容", `<form id="overseas-collect-form"><p class="subtext">保存原始链接和你看到的创意。不会自动下载视频或声称看过画面。</p><label class="field"><span>原始内容链接</span><input id="collect-overseas-url" type="url" maxlength="2000" required placeholder="https://www.tiktok.com/@.../video/..."></label><label class="field"><span>标题 / 内容名称</span><input id="collect-overseas-title" maxlength="200" required></label><label class="field"><span>品类</span><select id="collect-overseas-category"><option value="">待分类</option>${Object.entries(S.overseasLibrary?.categories||{}).map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join("")}</select></label><label class="field"><span>字幕、内容说明（可选）</span><textarea id="collect-overseas-summary" rows="4" maxlength="20000"></textarea></label><label class="field"><span>最值得借鉴的地方（可选）</span><textarea id="collect-overseas-mechanism" rows="2" maxlength="2000" placeholder="例如：先展示结果，然后切回准备过程"></textarea></label><button class="btn primary full" type="submit">保存到我的收藏</button></form>`);
  S.overseasCollectKey=workspaceKey();
}
async function startOverseas(briefId) {
  if(S.busy) return;
  if(S.overseasUploading===workspaceKey()) throw new Error("资料正在上传，请完成后再生成");
  const key=workspaceKey(); if(!briefId) saveOverseasDraft();
  const value=S.overseasForm;
  if(!briefId && value.topic.trim().length<2) throw new Error("请填写至少2个字的产品或创作主题");
  S.busy=true;render();
  try {
    const result=await post("/api/overseas/create",body(briefId?{brief_id:briefId}:{...value}));
    if(key!==workspaceKey()) return;
    toast("正在生成海外创意，进度可在任务记录查看");
    await poll(result.task_ids,async()=>{
      if(key!==workspaceKey()) return;
      S.onlyFavorites=false;S.stage="all";
      await navigate("creations");S.creationSource=result.brief_id;render();
      toast("3 个创意建议已生成，全部方案可直接查看");
    });
  } finally {if(key===workspaceKey()){S.busy=false;render();}}
}
function overseasDetails(c) {
  const d=c.data;if(!d.overseas) return "";
  const narrative=d.first_second ? `<section class="overseas-story"><h4>故事结构</h4><p><strong>第一秒：</strong>${esc(d.first_second)}</p><p><strong>观众以为：</strong>${esc(d.misread)}</p><p><strong>公平伏笔：</strong>${esc(d.clue)}</p><p><strong>结尾反转：</strong>${esc(d.reveal)}</p><p><strong>产品角色：</strong>${esc(d.product_role)}</p><p><strong>收尾：</strong>${esc(d.ending_type)}</p>${d.casting?`<p><strong>出镜方式：</strong>${esc(d.casting)}</p><p><strong>产品揭晓：</strong>第 ${d.reveal_shot} 镜 · ${esc(d.product_reveal)}</p>`:""}</section>` : `<section class="overseas-story"><h4>旧版创意方法</h4><p>${esc(d.operator||"")}</p><p>${esc(d.innovation||"")}</p></section>`;
  return `<section class="overseas-output"><p class="hint">${platformLabel(d.overseas.platform)} · ${esc(d.overseas.market)} · ${d.overseas.duration} 秒 · ${esc(d.overseas.skill)}</p><div class="actions">${button("复制口播与中译","copy-overseas-script","secondary small","copy",`data-id="${c.id}"`)}${button("下载完整方案","download-overseas-plan","secondary small","download",`data-id="${c.id}"`)}</div>${narrative}<section class="overseas-output-section"><h4>三个 Hook 测试选项</h4>${(d.hooks||[]).map((h,i)=>`<div class="overseas-hook"><strong>Hook ${"ABC"[i]}</strong><p>${esc(h.visual)}</p><p>${esc(h.line)}<br>${esc(h.translation_zh)}</p><small>${esc(h.sfx)}</small></div>`).join("")}</section><section class="overseas-output-section"><h4>完整口播与中文翻译</h4><p><strong>口播</strong><br>${esc(d.script)}</p><p><strong>中文翻译</strong><br>${esc(d.translation_zh)}</p></section><section class="overseas-output-section"><h4>分镜与实现 · ${d.shots?.length||0} 镜</h4><div class="table-wrap overseas-shots"><table><thead><tr><th>秒</th><th>景别 / 画面</th><th>台词 / 中译</th><th>实拍或 AI 实现</th></tr></thead><tbody>${(d.shots||[]).map(s=>`<tr><td>${s.start}–${s.end}</td><td>${esc(s.camera)}<br>${esc(s.action)}</td><td>${esc(s.line)}<br>${esc(s.translation_zh)}</td><td>${esc(s.implementation||"")}<br>${esc(s.screen_text)} / ${esc(s.sfx)}</td></tr>`).join("")}</tbody></table></div></section>${d.production_method?`<section class="overseas-output-section"><h4>制作路径与成本</h4><p>${esc(d.production_method)}</p><p>${esc(d.cost_basis)}</p></section>`:""}<section class="overseas-output-section"><h4>平台适配与讨论问题</h4>${d.loop?`<p>${esc(d.loop)}</p>`:""}<p>${esc(d.adaptation)}</p><ul>${(d.comments||[]).map(t=>`<li>${esc(t)}</li>`).join("")}</ul></section></section>`;
}
function overseasPlanText(d) {
  return [d.title,`平台：${platformLabel(d.overseas.platform)} · 市场：${d.overseas.market} · ${d.overseas.duration} 秒`,"第一秒",d.first_second,"观众以为",d.misread,"公平伏笔",d.clue,"结尾反转",d.reveal,"产品角色",d.product_role,"收尾方式",d.ending_type,"出镜方式",d.casting,"产品揭晓",d.product_reveal,"制作路径",d.production_method,"成本依据",d.cost_basis,"Hook备选",...(d.hooks||[]).map((h,i)=>`${"ABC"[i]}: ${h.visual}\n${h.line}\n${h.translation_zh}\n${h.sfx}`),"完整口播",d.script,"中文翻译",d.translation_zh,"分镜与实现",...(d.storyboard||[]),"拍摄清单",...(d.shooting_list||[]),"平台适配",d.adaptation,"讨论问题",...(d.comments||[]),"发布文案",CreationTools.publicCopy(d),"待核对",...(d.quality?.issues||[]),...(d.missing||[])].filter(v=>v!==undefined&&v!==null).join("\n\n");
}

Object.assign(actions,{
  "focus-overseas-creation":el=>{S.focusCreation=el.dataset.id;render();window.scrollTo({top:0});},
  overseas:()=>navigate("overseas"),"overseas-ideas":()=>navigate("overseas-ideas"),
  "collect-overseas":collectOverseasModal,"search-overseas":searchOverseas,
  "overseas-tab":async el=>{readOverseasFilters();S.overseasFilters.saved=el.dataset.saved==="1";S.overseasMessage="";await loadOverseasIdeas();},
  "save-overseas-idea":async el=>{
    const key=workspaceKey(),item=S.overseasLibrary.items.find(i=>i.id===el.dataset.id);
    if(!item) return;
    if(item.id.startsWith("archetype_")) await post("/api/overseas/ideas",body({archetype_id:item.id}));
    else await api("/api/overseas/ideas/"+item.id,{method:"PATCH",body:JSON.stringify(body({saved:!item.saved}))});
    if(key!==workspaceKey()) return;
    await loadOverseasIdeas();toast(item.saved?"已取消收藏":"创意已收藏");
  },
  "use-overseas-idea":async el=>{
    const item=S.overseasLibrary.items.find(i=>i.id===el.dataset.id);if(!item)return;
    S.overseasForm={...S.overseasForm,reference_id:item.id};S.overseasReferenceTitle=item.title;
    drafts.save(workspaceKey()+":overseas",S.overseasForm);await navigate("overseas");
  },
  "clear-overseas-reference":()=>{saveOverseasDraft();S.overseasForm.reference_id="";S.overseasReferenceTitle="";drafts.save(workspaceKey()+":overseas",S.overseasForm);render();},
  "overseas-again":el=>startOverseas(el.dataset.id),
  "copy-overseas-script":async el=>{const d=S.workspace.creations.find(c=>c.id===el.dataset.id).data;await navigator.clipboard.writeText(d.script+"\n\n"+d.translation_zh);toast("口播与中译已复制，请核对后使用");},
  "download-overseas-plan":el=>{const d=S.workspace.creations.find(c=>c.id===el.dataset.id).data;const url=URL.createObjectURL(new Blob([overseasPlanText(d)],{type:"text/plain;charset=utf-8"}));const link=document.createElement("a");link.href=url;link.download="DAOLOOK-海外创意方案.txt";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},
});
document.addEventListener("input",e=>{if(e.target.closest?.("#overseas-form"))saveOverseasDraft();});
document.addEventListener("change",e=>{if(e.target.closest?.("#overseas-form"))saveOverseasDraft();});
document.addEventListener("change",async e=>{
  if(e.target.id!=="overseas-material-files") return;
  try {await uploadOverseasMaterials(e.target);} catch(error) {e.target.value="";toast(error.message);}
});
