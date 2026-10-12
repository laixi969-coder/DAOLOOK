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
    `<div class="overseas-studio"><section class="panel"><form id="overseas-form"><div class="original-grid"><label class="field"><span>发布平台</span><select id="overseas-platform">${Object.entries(OVERSEAS_NAMES).map(([id,label])=>`<option value="${id}" ${id===value.platform?"selected":""}>${label}</option>`).join("")}</select></label>${goalPicker("overseas-goal",value.goal)}</div><label class="field"><span>产品或创作主题</span><input id="overseas-topic" maxlength="200" required value="${esc(value.topic)}" placeholder="例如：三合一折叠无线充电器"></label><div class="original-grid"><label class="field"><span>目标市场</span><input id="overseas-market" maxlength="60" required value="${esc(value.market)}" placeholder="例如：United States / Germany"></label><label class="field"><span>台词语言 + 中文翻译</span><select id="overseas-language">${Object.entries({"en-zh":"英文 + 中文","es-zh":"西班牙文 + 中文","fr-zh":"法文 + 中文","de-zh":"德文 + 中文"}).map(([id,label])=>`<option value="${id}" ${id===value.language?"selected":""}>${label}</option>`).join("")}</select></label></div><label class="field"><span>目标时长（秒）</span><input id="overseas-duration" type="number" min="12" max="60" step="1" value="${value.duration}" required></label>${value.reference_id?`<div class="notice">已选参考：${esc(S.overseasReferenceTitle||"海外创意")}。<button class="text-btn" type="button" data-action="clear-overseas-reference">取消参考</button></div>`:""}<label class="field"><span>真实卖点、受众和拍摄条件</span><textarea id="overseas-temporary" rows="5" maxlength="100000" placeholder="粘贴产品参数、已证实的卖点、客户疑问、可用的实物与场景。也可以先只写产品名，缺失事实会明确标注。">${esc(value.temporary)}</textarea></label>${overseasMaterials(value,assets)}<label class="field"><span>特别要求（可选）</span><textarea id="overseas-requirements" rows="2" maxlength="100000" placeholder="例如：不露脸、一人用手机拍、家居桌面场景">${esc(value.requirements)}</textarea></label><div class="entry-bottom"><span>${S.boot.mode==="demo"?"演示模板 · 不调用模型、不实际翻译":"一次给出 3 个不同创意建议"}</span><span>预计 ${originalCost()} 积分 · 失败退还</span></div><button class="btn primary full" type="submit" ${S.busy||S.overseasUploading===workspaceKey()?"disabled":""}>${icon("spark")}${S.overseasUploading===workspaceKey()?"资料上传中…":S.busy?"正在生成海外创意":"生成 3 个创意建议"}</button></form></section></div>`;
}
function overseasIdeasPage() {
  const lib=S.overseasLibrary;
  const filters=S.overseasFilters || {query:"",category:"",platform:"all",saved:false};
  return heading("把值得借鉴的海外创意，收进来。", "搜索平台内容、收集原始链接，或浏览 60 条创意说明与真实参考视频。收藏后可直接带入创作。",`<div class="actions">${button("收集链接","collect-overseas","secondary","plus")}${button("开始海外创作","overseas","primary","spark")}</div>`,"OVERSEAS INSPIRATION")+
    `<section class="panel overseas-library-controls"><div class="overseas-library-tabs"><button class="chip ${!filters.saved?"active":""}" data-action="overseas-tab" data-saved="0">创意推荐</button><button class="chip ${filters.saved?"active":""}" data-action="overseas-tab" data-saved="1">我的收藏</button></div><form id="overseas-filter-form"><label class="field"><span>关键词 / 产品</span><input id="overseas-query" maxlength="100" value="${esc(filters.query)}" placeholder="charger / 收纳 / cleaning"></label><label class="field"><span>品类</span><select id="overseas-category"><option value="">全部品类</option>${Object.entries(lib?.categories||{}).map(([id,label])=>`<option value="${id}" ${filters.category===id?"selected":""}>${esc(label)}</option>`).join("")}</select></label><label class="field"><span>平台</span><select id="overseas-filter-platform"><option value="all">全部平台</option>${Object.entries(OVERSEAS_NAMES).filter(([id])=>id!=="overseas").map(([id,label])=>`<option value="${id}" ${filters.platform===id?"selected":""}>${label}</option>`).join("")}</select></label><button class="btn secondary" type="submit">筛选推荐</button><button class="btn primary" type="button" data-action="search-overseas" ${S.overseasSearching?"disabled":""}>${S.overseasSearching?"正在搜索…":"搜索平台内容"}</button></form><p class="hint">平台搜索请填写关键词并选择一个平台；可能产生数据源费用。${lib?.search_available?"":"当前实时数据源未启用，仍可浏览创意和收集链接。"}</p>${S.overseasMessage?`<p class="notice" role="status">${esc(S.overseasMessage)}</p>`:""}</section>`+
    (lib?`<div class="section-head"><h2>${filters.saved?"收藏的创意":"推荐创意"} <span>${lib.items.length} 条</span></h2><span class="muted">已附视频 ${lib.items.filter(i=>i.reference_video?.url||i.url).length} / ${lib.items.length} 条</span></div>${lib.items.length?`<div class="overseas-idea-grid">${lib.items.map(overseasIdeaCard).join("")}</div>`:empty("暂时没有匹配的创意","试试其他关键词、取消筛选，或收集一条你发现的链接。",button("收集链接","collect-overseas","primary","plus"))}`:'<div class="loading-line">正在读取海外创意库…</div>');
}
function overseasIdeaCard(item) {
  return `<article class="overseas-idea-card"><h3>${esc(item.title)}</h3><p class="idea-summary">${esc(item.summary||"尚未补充创意说明")}</p>${overseasReferenceVideo(item)}<div class="actions">${button(item.saved?"已收藏":"收藏","save-overseas-idea","secondary small",item.saved?"check":"star",`data-id="${item.id}"`)}${button("用这个创意创作","use-overseas-idea","primary small","spark",`data-id="${item.id}"`)}</div></article>`;
}
function overseasReferenceVideo(item) {
  const video=item.reference_video;
  if(video?.url) return `<a class="overseas-reference-video" href="${esc(video.url)}" target="_blank" rel="noopener noreferrer">${video.thumbnail?`<img src="${esc(safeImage(video.thumbnail))}" alt="${esc(video.title)}" loading="lazy" referrerpolicy="no-referrer">`:""}<span class="video-source">同类产品参考 · YouTube</span><strong>${esc(video.title)}</strong><span class="video-source">发布者：${esc(video.publisher)}</span><span class="video-watch">观看参考视频 ↗</span></a>`;
  return item.url?`<a class="video-watch" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">查看原始内容 ↗</a>`:"";
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
  modal("收集海外社媒内容", `<form id="overseas-collect-form"><p class="subtext">保存参考视频链接和创意说明。</p><label class="field"><span>原始内容链接</span><input id="collect-overseas-url" type="url" maxlength="2000" required placeholder="https://www.tiktok.com/@.../video/..."></label><label class="field"><span>标题 / 内容名称</span><input id="collect-overseas-title" maxlength="200" required></label><label class="field"><span>品类</span><select id="collect-overseas-category"><option value="">待分类</option>${Object.entries(S.overseasLibrary?.categories||{}).map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join("")}</select></label><label class="field"><span>创意说明 / 字幕（可选）</span><textarea id="collect-overseas-summary" rows="4" maxlength="20000"></textarea></label><button class="btn primary full" type="submit">保存到我的收藏</button></form>`);
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
function overseasShots(d) {
  return d.shots?.length ? d.shots : (d.storyboard||[]).map(action=>({camera:"",action}));
}
function overseasAiPrompt(d,shot) {
  if(shot.ai_prompt) return shot.ai_prompt;
  return ["9:16竖屏，真实摄影质感。",shot.camera,shot.action,"沿用相同场景和参考素材，产品外观、比例与材质保持一致。",d.casting==="无人"?"画面中没有人物、手部、身体或人物倒影。":"","不生成字幕或品牌标识，文字在后期添加。"].filter(Boolean).join("\n");
}
function overseasConcept(d) {
  if(d.concept) return d.concept;
  return [d.first_second,d.reveal].filter(Boolean).join(" ").replace(/(?:这是结构占位|演示占位|演示模板|具体故事需用实际产品)[^。]*。?/g,"") || d.hook || "";
}
function overseasCard(c,number=0) {
  const d=c.data;
  const titles=[...new Set(d.titles||[])].filter(t=>t&&t!==d.title);
  return `<article class="draft overseas-card"><div class="draft-top"><span>${number?`<span class="direction-badge">建议 ${number}</span> `:""}${platformLabel(d.overseas.platform)} · ${d.overseas.duration} 秒${d.demo?' · 演示':""}</span><span>${date(c.created_at)}</span></div><h3>${esc(d.title)}</h3>${overseasDetails(c)}${titles.length?`<section class="overseas-output-section"><h4>标题备选</h4><ul>${titles.map(t=>`<li>${esc(t)}</li>`).join("")}</ul></section>`:""}<section class="overseas-output-section"><h4>发布内容 / Tags</h4><p class="draft-body">${esc(d.body)}</p>${d.tags?.length?`<div class="tags">${d.tags.map(t=>"#"+esc(t)).join(" ")}</div>`:""}</section><div class="actions">${button("复制内容","copy","secondary small","copy",`data-id="${c.id}"`)}${d.script?.trim()?button("复制口播","copy-overseas-script","secondary small","copy",`data-id="${c.id}"`):""}${button("下载创意 TXT","download-overseas-plan","secondary small","download",`data-id="${c.id}"`)}${button("编辑标题与内容","edit-draft","secondary small","edit",`data-id="${c.id}"`)}${button(c.saved?"已收藏":"收藏","save-creation","secondary small",c.saved?"check":"star",`data-id="${c.id}"`)}${button("删除","delete-creation","secondary small","trash",`data-id="${c.id}"`)}</div></article>`;
}
function overseasShotCopy(shot) {
  return [shot.line?`口播：${shot.line}`:"",shot.line&&shot.translation_zh?`口播中译：${shot.translation_zh}`:"",shot.screen_text?`屏幕文案：${shot.screen_text}`:"",shot.screen_text&&shot.screen_text_zh?`屏幕文案中译：${shot.screen_text_zh}`:""].filter(Boolean).join("\n");
}
function overseasDetails(c) {
  const d=c.data;if(!d.overseas) return "";
  const shots=overseasShots(d);
  return `<div class="overseas-delivery"><section class="overseas-output-section"><h4>创意</h4><p>${esc(overseasConcept(d))}</p></section><section class="overseas-output-section"><h4>画面描述</h4>${shots.map((shot,i)=>`<div class="overseas-shot"><h5>镜头 ${i+1}${Number.isFinite(shot.start)&&Number.isFinite(shot.end)?` · ${shot.start}–${shot.end} 秒`:""}</h5>${shot.camera?`<p>${esc(shot.camera)}</p>`:""}<p>${esc(shot.action)}</p>${shot.line?.trim()?`<div class="overseas-video-copy"><strong>口播</strong><p>${esc(shot.line)}</p>${shot.translation_zh?`<p class="muted">${esc(shot.translation_zh)}</p>`:""}</div>`:""}${shot.screen_text?.trim()?`<div class="overseas-video-copy"><div class="pipeline-head"><strong>屏幕文案</strong>${button("复制屏幕文案","copy-overseas-screen-text","secondary small","copy",`data-id="${c.id}" data-shot="${i}"`)}</div><p>${esc(shot.screen_text)}</p>${shot.screen_text_zh?`<p class="muted">${esc(shot.screen_text_zh)}</p>`:""}</div>`:""}</div>`).join("")}</section>${d.script?.trim()?`<section class="overseas-output-section"><h4>口播文案</h4><p>${esc(d.script)}</p>${d.translation_zh?`<h5>中文翻译</h5><p>${esc(d.translation_zh)}</p>`:""}</section>`:""}<section class="overseas-output-section"><h4>AI 生成提示词</h4>${shots.map((shot,i)=>`<div class="overseas-ai-prompt"><div class="pipeline-head"><h5>镜头 ${i+1}</h5>${button("复制提示词","copy-overseas-prompt","secondary small","copy",`data-id="${c.id}" data-shot="${i}"`)}</div><pre>${esc(overseasAiPrompt(d,shot))}</pre></div>`).join("")}</section></div>`;
}
function overseasPlanText(d) {
  return [d.title,"创意",overseasConcept(d),"画面描述",...overseasShots(d).map((shot,i)=>`镜头 ${i+1}${Number.isFinite(shot.start)&&Number.isFinite(shot.end)?` · ${shot.start}–${shot.end} 秒`:""}\n${shot.camera||""}\n${shot.action}\n${overseasShotCopy(shot)}`),...(d.script?.trim()?["口播文案",d.script,...(d.translation_zh?["中文翻译",d.translation_zh]:[])]:[]),"AI 生成提示词",...overseasShots(d).map((shot,i)=>`镜头 ${i+1}\n${overseasAiPrompt(d,shot)}`),"标题备选",...(d.titles||[]),"发布内容 / Tags",CreationTools.publicCopy(d)].filter(Boolean).join("\n\n");
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
  "copy-overseas-screen-text":async el=>{const d=S.workspace.creations.find(c=>c.id===el.dataset.id)?.data;if(!d)return;const shot=overseasShots(d)[Number(el.dataset.shot)];if(!shot?.screen_text?.trim())return;await navigator.clipboard.writeText(shot.screen_text);toast("屏幕文案已复制");},
  "copy-overseas-prompt":async el=>{const d=S.workspace.creations.find(c=>c.id===el.dataset.id)?.data;if(!d)return;const shot=overseasShots(d)[Number(el.dataset.shot)];if(!shot)return;await navigator.clipboard.writeText(overseasAiPrompt(d,shot));toast("提示词已复制");},
  "copy-overseas-script":async el=>{const d=S.workspace.creations.find(c=>c.id===el.dataset.id).data;await navigator.clipboard.writeText([d.script,d.translation_zh].filter(Boolean).join("\n\n"));toast("口播已复制");},
  "download-overseas-plan":el=>{const d=S.workspace.creations.find(c=>c.id===el.dataset.id).data;const url=URL.createObjectURL(new Blob([overseasPlanText(d)],{type:"text/plain;charset=utf-8"}));const link=document.createElement("a");link.href=url;link.download="DAOLOOK-海外创意方案.txt";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},
});
document.addEventListener("input",e=>{if(e.target.closest?.("#overseas-form"))saveOverseasDraft();});
document.addEventListener("change",e=>{if(e.target.closest?.("#overseas-form"))saveOverseasDraft();});
document.addEventListener("change",async e=>{
  if(e.target.id!=="overseas-material-files") return;
  try {await uploadOverseasMaterials(e.target);} catch(error) {e.target.value="";toast(error.message);}
});
