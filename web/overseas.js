"use strict";

const OVERSEAS_NAMES = {overseas:"三平台 · 3 个不同创意",tiktok:"TikTok",instagram:"Instagram Reels",youtube:"YouTube Shorts"};
let overseasRefreshTimer;
function platformLabel(p) { return OVERSEAS_NAMES[p] || (p === "douyin" ? "抖音脚本" : "小红书图文"); }
function overseasDefaults() { return {platform:"overseas",goal:"leads",topic:"",market:"United States",language:"en-zh",duration:12,temporary:"",requirements:"",assets:[],reference_id:""}; }
function overseasFormValues() {
  const value={};
  for (const name of ["platform","goal","topic","market","language","temporary","requirements"])
    value[name]=$(`#overseas-${name}`).value;
  value.observation=questionValues("overseas");
  value.duration=Number($("#overseas-duration").value);
  value.assets=selectedAssetIDs("overseas-asset",S.overseasForm?.assets||[]);
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
  return `<section class="overseas-materials"><div class="section-head"><h3>上传创作资料</h3><span class="muted" data-overseas-selected>已选 ${value.assets.length} 份</span></div><label class="overseas-upload"><span>${icon("plus")} ${uploading?"正在读取并保存资料…":"选择文档、图片或海报"}</span><input type="file" id="overseas-material-files" accept=".txt,.md,.csv,.docx,.pdf,image/png,image/jpeg,image/webp" multiple ${uploading||S.busy?"disabled":""}></label>${infoTip("上传格式与资料使用说明", "支持 TXT、MD、CSV、DOCX、PDF、PNG、JPG、WebP；每份最多 2 MB，一次最多 6 份。上传后保存到项目并自动勾选；取消勾选只从本次创作移除。扫描版 PDF 请先转为图片。")}${assets.length?`<div class="overseas-assets">${assets.map(a=>`<label class="overseas-asset"><input type="checkbox" name="overseas-asset" value="${esc(a.id)}" ${value.assets.includes(a.id)?"checked":""}>${a.kind==="图片"?`<img src="${esc(safeImage(a.content))}" alt="${esc(a.name)}预览">`:`<span class="asset-document-icon">${icon("folder")}</span>`}<span class="overseas-asset-name">${esc(a.name)}<small>${a.kind==="图片"?"图片 / 海报":esc(a.kind)}</small></span></label>`).join("")}</div>`:""}</section>`;
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
  return heading("海外创作", "",button("浏览海外灵感","overseas-ideas","secondary","grid"))+
    `<div class="overseas-studio"><section class="panel"><form id="overseas-form"><div class="original-grid"><label class="field"><span>发布平台</span><select id="overseas-platform">${Object.entries(OVERSEAS_NAMES).map(([id,label])=>`<option value="${id}" ${id===value.platform?"selected":""}>${label}</option>`).join("")}</select></label>${goalPicker("overseas-goal",value.goal)}</div><label class="field"><span>产品或创作主题</span><input id="overseas-topic" maxlength="200" required value="${esc(value.topic)}" placeholder="例如：周末咖啡市集、门店上新"></label><div class="original-grid"><label class="field"><span>目标市场</span><input id="overseas-market" maxlength="60" required value="${esc(value.market)}" placeholder="例如：美国 / 德国"></label><label class="field"><span>台词语言 + 中文翻译</span><select id="overseas-language">${Object.entries({"en-zh":"英文 + 中文","es-zh":"西班牙文 + 中文","fr-zh":"法文 + 中文","de-zh":"德文 + 中文"}).map(([id,label])=>`<option value="${id}" ${id===value.language?"selected":""}>${label}</option>`).join("")}</select></label></div><label class="field"><span>目标时长（秒）</span><input id="overseas-duration" type="number" min="5" max="60" step="1" value="${value.duration}" required></label>${value.reference_id?`<div class="notice">已选参考：${esc(S.overseasReferenceTitle||"海外创意")}。<button class="text-btn" type="button" data-action="clear-overseas-reference">取消参考</button></div>`:""}<label class="field"><span>真实卖点、受众和拍摄条件</span><textarea id="overseas-temporary" rows="5" maxlength="100000" placeholder="粘贴产品参数、已证实的卖点、客户疑问、可用的实物与场景。也可以先只写产品名，缺失事实会明确标注。">${esc(value.temporary)}</textarea></label>${overseasMaterials(value,assets)}${questionIntake("overseas",value.observation)}<label class="field"><span>特别要求（可选）</span><textarea id="overseas-requirements" rows="2" maxlength="100000" placeholder="例如：不露脸、一人用手机拍、家居桌面场景">${esc(value.requirements)}</textarea></label><div class="entry-bottom"><span>${S.boot.mode==="demo"?"演示模板 · 不调用模型、不实际翻译":"一次给出 3 个不同创意建议"}</span><span>预计 ${originalCost()} 积分 · 失败退还</span></div><button class="btn primary full" type="submit" ${S.busy||S.overseasUploading===workspaceKey()?"disabled":""}>${icon("spark")}${S.overseasUploading===workspaceKey()?"资料上传中…":S.busy?"正在生成海外创意":"生成 3 个创意建议"}</button></form></section></div>`;
}
function overseasIdeasPage() {
  const lib=S.overseasLibrary, filters=S.overseasFilters||{query:"",platform:"all"};
  const scope=filters.saved?"saved":(filters.scope||"today");
  const today=scope==="today";
  const archive=scope==="archive", playlist=today||archive;
  const tabs={today:"今日推荐",archive:"往期推荐",selected:"易拍片库",candidates:"全部候选",saved:"我的收藏"};
  const updating=S.overseasRefreshing===workspaceKey() || lib?.refresh?.state==="running";
  const navigation=Object.entries(tabs).map(([id,label])=>`<button class="chip ${scope===id?"active":""}" aria-pressed="${scope===id}" data-action="overseas-tab" data-scope="${id}">${label}</button>`).join("");
  const actions=`<div class="actions"><button class="btn secondary" data-action="refresh-overseas-ideas" ${updating?"disabled":""}>${icon("refresh")}${updating?"正在检查…":"检查新片"}</button>${button("收集链接","collect-overseas","secondary","plus")}${button("开始海外创作","overseas","primary","spark")}</div>`;
  const controls=`<section class="${playlist?"overseas-daily-controls":"panel overseas-library-controls"}"><div class="overseas-library-tabs">${navigation}</div>${playlist?"":overseasLibraryFilters(filters,lib)}${S.overseasMessage?`<p class="notice" role="status">${esc(S.overseasMessage)}</p>`:""}</section>`;
  const day=today && lib?.daily?.day;
  const dateLabel=day?`<time class="daily-date" datetime="${esc(day)}">${esc(day)}</time>`:"";
  const issues=lib?.daily?.archive||[];
  const picker=archive && issues.length?`<select class="daily-archive-picker" id="overseas-edition" aria-label="选择往期片单">${issues.map(({key,day})=>`<option value="${esc(key)}" ${key===lib.daily.key?"selected":""}>${esc(day)}${key.endsWith(".0")?"":" · 更新 "+esc(key.split(".")[1])}</option>`).join("")}</select>`:"";
  const header=heading("海外灵感","",playlist?picker||dateLabel:actions)+controls;
  if(!lib) return header+'<div class="loading-line">正在读取海外创意库…</div>';
  const limit=lib.daily?.front_page||10;
  const expanded=filters.expandedDay && filters.expandedDay===lib.daily?.day;
  const visible=today&&!expanded?lib.items.slice(0,limit):lib.items;
  const status=scope==="candidates"?overseasFeedStatus(lib.refresh):"";
  const sectionHead=playlist?"":`<div class="section-head"><h2>${tabs[scope]} <span>${esc(String(lib.total ?? lib.items.length))} 条</span></h2></div>`;
  let body=visible.length?`<div class="${playlist?"overseas-daily-grid":"overseas-idea-grid"}">${visible.map(playlist?overseasDailyCard:overseasIdeaCard).join("")}</div>`:archive?empty("暂无往期推荐","",button("回到今日推荐","overseas-tab","secondary","grid",'data-scope="today"')):empty("暂时没有匹配的创意","可以去易拍片库查看其他拍法。",button("浏览易拍片库","overseas-tab","secondary","grid",'data-scope="selected"'));
  if(today && !expanded && lib.items.length>limit) body+=`<div class="actions overseas-more">${button("再看 "+(lib.items.length-limit)+" 条","overseas-daily-more","secondary","arrow")}</div>`;
  if(lib.previous_offset!=null || lib.next_offset!=null) body+=`<div class="actions">${lib.previous_offset!=null?button("上一页","overseas-idea-page","secondary small","back",`data-offset="${lib.previous_offset}"`):""}${lib.next_offset!=null?button("下一页","overseas-idea-page","secondary small","arrow",`data-offset="${lib.next_offset}"`):""}</div>`;
  return header+sectionHead+status+body;
}
function overseasLibraryFilters(f,lib) {
  const select=(id,label,all,values,selected)=>`<label class="field"><span>${label}</span><select id="${id}"><option value="">${all}</option>${Object.entries(values).map(([v,name])=>`<option value="${esc(v)}" ${selected===v?"selected":""}>${esc(name)}</option>`).join("")}</select></label>`;
  const labels=values=>Object.fromEntries((values||[]).map(v=>[v,v]));
  return `<form id="overseas-filter-form"><label class="field"><span>关键词</span><input id="overseas-query" maxlength="100" value="${esc(f.query)}" placeholder="纸板、擦镜、开业…"></label>
    ${select("overseas-industry","行业","全部行业",labels(lib?.industries),f.industry)}
    ${select("overseas-publisher-type","账号类型","全部类型",labels(lib?.publisher_types),f.publisher_type)}
    ${select("overseas-filter-platform","平台","全部平台",{tiktok:"TikTok",instagram:"Instagram Reels",youtube:"YouTube"},f.platform)}
    ${select("overseas-category","产品品类","全部品类",lib?.categories||{},f.category)}
    <button class="btn secondary" type="submit">筛选</button>${lib?.search_available?`<button class="btn primary" type="button" data-action="search-overseas" ${S.overseasSearching?"disabled":""}>搜索平台内容</button>`:""}</form>${lib?.search_available?infoTip("平台搜索费用",`每次 ${S.boot.rules.search ?? 1} 积分，缓存命中会退回。`):""}`;
}
function overseasFeedStatus(sync) {
  if(!sync) return "";
  const checked=sync.last_checked_at?new Date(sync.last_checked_at).toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}):"";
  const partial=sync.successful_sources===sync.source_count && sync.detail_pending_sources?.length?"部分视频详情待补":"部分来源暂时不可用";
  const status={running:"正在检查新片…",failed:"来源暂时不可用，显示已有片库",partial,idle:"等待首次同步"}[sync.state];
  const latest=checked&&sync.state!=="running"?`最近检查 ${checked}`:"";
  const counts=["succeeded","partial"].includes(sync.state)?`本次新入选 ${sync.new_match_count||0} 条，新增候选 ${sync.added_count||0} 条`:"";
  return `<p class="overseas-feed-status" role="status">${esc(["每天更新",latest,counts,status].filter(Boolean).join(" · "))}</p>`;
}
function overseasPlayerUrl(link) {
  let url;
  try { url=new URL(link); } catch { return ""; }
  if(url.protocol!=="https:" || url.username || url.password || url.port) return "";
  const host=url.hostname.replace(/^www\./,"");
  if(url.hostname==="v.qq.com" && url.pathname==="/txp/iframe/player.html") {
    const id=url.searchParams.get("vid")||"";
    return /^[a-zA-Z0-9]{11}$/.test(id)?`https://v.qq.com/txp/iframe/player.html?vid=${id}`:"";
  }
  if(host==="youtube.com" || host==="youtu.be") {
    const id=host==="youtu.be"?url.pathname.slice(1):url.pathname==="/watch"?url.searchParams.get("v"):url.pathname.match(/^\/shorts\/([^/]+)\/?$/)?.[1];
    return /^[\w-]{11}$/.test(id||"")?`https://www.youtube-nocookie.com/embed/${id}`:"";
  }
  if(host==="instagram.com") {
    const post=url.pathname.match(/^\/(?:reels?|p)\/([\w-]+)\/?$/);
    return post?`https://www.instagram.com/p/${post[1]}/embed/`:"";
  }
  if(host==="tiktok.com") {
    const post=url.pathname.match(/^\/@[^/]+\/video\/(\d+)\/?$/);
    return post?`https://www.tiktok.com/player/v1/${post[1]}?autoplay=0&description=0&music_info=0`:"";
  }
  return "";
}

function overseasFrame(player,label,landscape=false) {
  return `<iframe class="daily-player${landscape?" landscape-player":""}" src="${esc(player)}" title="${esc(label)}" loading="lazy" allow="autoplay; fullscreen; encrypted-media; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
}

function dailyVideoLink(item) {
  return [item?.reference_video?.url,item?.url].find(link=>overseasPlayerUrl(link)) ||
    [item?.reference_video?.url,item?.url].find(link=>/^https:\/\/(?:(?:(?:www|m)\.)?(?:youtube\.com|instagram\.com|tiktok\.com)|youtu\.be|(?:vm|vt)\.tiktok\.com)\//i.test(link||""));
}

function overseasDailyCard(item) {
  const link=dailyVideoLink(item);
  const player=link && overseasPlayerUrl(link);
  const chinese=text=>typeof text==="string" && /[\u3400-\u9fff]/.test(text);
  const payoff=item.mechanism==="实物错觉揭晓" ? "" : (item.idea_zh || item.visual_payoff);
  const idea=[payoff,item.summary_zh,item.summary,item.title_zh,item.mechanism].find(chinese);
  const hook=chinese(item.hook_zh) ? item.hook_zh : "";
  const title=[item.title_zh,item.title,item.mechanism].find(chinese) || "推荐短片";
  const position=item.daily_pick?.position;
  const label=position?`第 ${position} 条原片 · ${title}`:title;
  const image=item.daily_poster || item.reference_video?.thumbnail || "";
  const poster=/^\/art\/overseas\/[\w-]+\.webp$/.test(image) ? image : safeImage(image);
  const source={tiktok:"TikTok",instagram:"Instagram",youtube:"YouTube",tencent:"腾讯视频"}[item.platform]||"原片";
  const cover=poster?`<img src="${esc(poster)}" alt="" loading="${position<=3?"eager":"lazy"}" referrerpolicy="no-referrer">`:"";
  const media=player?`<button type="button" class="daily-poster" data-action="play-overseas-video" data-id="${esc(item.id)}" aria-label="播放：${esc(label)}"><small aria-hidden="true">${source}</small>${cover}<span aria-hidden="true">▶</span></button>`:"";
  const original=link?`<a class="video-watch" href="${esc(link)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(label)}，在原平台观看">在原平台观看 ↗</a>`:"";
  const notes=[["钩子",hook],["创意",idea]].filter(([,value])=>value)
    .map(([label,value])=>`<p><strong>${label}</strong>${esc(value)}</p>`).join("");
  return `<article class="overseas-idea-card"><h2 class="daily-title" lang="zh-CN">${esc(title)}</h2>${media}<div class="daily-notes" lang="zh-CN">${notes}</div>${original}</article>`;
}

function overseasIdeaCard(item) {
  const title=item.title_zh||item.title, summary=item.summary_zh||item.summary;
  const originals=[item.title_zh?item.title:"",item.summary_zh?item.summary:""].filter((text,i,all)=>text&&all.indexOf(text)===i);
  const context=[item.industry,item.publisher_type].filter(Boolean).join(" · ");
  const basis=item.filming_basis && item.filming_basis!=="画面参考" ? item.filming_basis : "";
  const proof=["https://kabo.sh/breakdown/","https://www.sfom.ai/blog/","https://www.webjunction.org/news/","https://www.the-independent.com/life-style/"].some(prefix=>item.review_source?.startsWith(prefix));
  const filming = item.filming ? `<details class="transcript-box"><summary>参考拍法</summary>${item.visual_payoff?`<p>${esc(item.visual_payoff)}</p>`:""}<p>${esc(item.filming)}</p>${basis?`<small class="muted">${esc(item.filming_basis)}</small>`:""}${proof?`<a href="${esc(item.review_source)}" target="_blank" rel="noopener noreferrer">查看参考出处 ↗</a>`:""}</details>` : "";
  return `<article class="overseas-idea-card">${context?`<span class="muted">${esc(context)}</span>`:""}<h3 lang="${item.title_zh?"zh-CN":""}">${esc(title)}</h3><p class="idea-summary">${esc(summary||"尚未补充创意说明")}</p>${originals.length?`<p class="idea-original"><span>原文</span>${originals.map(esc).join("\n\n")}</p>`:""}${overseasReferenceVideo(item)}${filming}<div class="actions">${button(item.saved?"已收藏":"收藏","save-overseas-idea","secondary small",item.saved?"check":"star",`data-id="${item.id}"`)}${button("用这个创意创作","use-overseas-idea","primary small","spark",`data-id="${item.id}"`)}</div></article>`;
}
function overseasReferenceVideo(item) {
  const video=item.reference_video;
  if(video?.url) return `<a class="overseas-reference-video" href="${esc(video.url)}" target="_blank" rel="noopener noreferrer">${video.thumbnail?`<img src="${esc(safeImage(video.thumbnail))}" alt="${esc(video.title_zh||video.title)}" loading="lazy" referrerpolicy="no-referrer">`:""}<span class="video-source">${video.relation==="来源视频"?"来源视频":"同类产品参考"} · ${esc({tiktok:"TikTok",instagram:"Instagram Reels",youtube:"YouTube"}[video.platform]||"YouTube")}</span><strong>${esc(video.title_zh||video.title)}</strong>${video.title_zh?`<span class="video-original">原文：${esc(video.title)}</span>`:""}<span class="video-source">发布者：${esc(video.publisher)}</span>${video.published_at?`<span class="video-source">发布于 ${esc(/^\d{4}-\d{2}-\d{2}$/.test(video.published_at)?video.published_at:date(video.published_at))}</span>`:""}<span class="video-watch">观看参考视频 ↗</span></a>`;
  return item.url?`<a class="video-watch" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">查看原始内容 ↗</a>`:"";
}
async function loadOverseasIdeas(background=false) {
  clearTimeout(overseasRefreshTimer);
  const key=workspaceKey(); const request=++S.overseasLoadToken;
  const f=S.overseasFilters;
  const today=!f.saved && (f.scope||"today")==="today", archive=!f.saved && f.scope==="archive";
  const playlist=today||archive;
  const params=new URLSearchParams({project_id:S.project,query:playlist?"":f.query,category:playlist?"":f.category,
    platform:playlist?"all":f.platform,scope:f.saved?"selected":f.scope||"today",saved:f.saved?"1":"0",offset:String(playlist?0:f.offset||0),
    industry:playlist?"":f.industry||"",publisher_type:playlist?"":f.publisher_type||""});
  if(archive && f.edition) params.set("edition",f.edition);
  let keepPlayers=false;
  try {
    const library=await api("/api/overseas/ideas?"+params);
    if(key!==workspaceKey() || request!==S.overseasLoadToken) return;
    const previous=background && today && S.page==="overseas-ideas" && S.overseasLibrary ? overseasIdeasPage() : "";
    S.overseasLibrary=library;
    keepPlayers=Boolean(previous) && previous===overseasIdeasPage();
    if(!archive && library.refresh?.daily && S.page==="overseas-ideas") {
      overseasRefreshTimer=setTimeout(()=>{
        if(key===workspaceKey() && request===S.overseasLoadToken && S.page==="overseas-ideas") loadOverseasIdeas(true);
      },library.refresh.state==="running"||library.translation_pending?10000:600000);
    }
  } catch(error) { if(key===workspaceKey() && request===S.overseasLoadToken) {S.overseasMessage=error.message;S.overseasLibrary={items:[],categories:{}};} }
  if(!keepPlayers && key===workspaceKey() && S.page==="overseas-ideas") render();
}
async function refreshOverseasIdeas() {
  const key=workspaceKey();
  if(S.overseasRefreshing===key || S.overseasLibrary?.refresh?.state==="running") return;
  readOverseasFilters();S.overseasRefreshing=key;S.overseasMessage="";render();
  try {
    const result=await post("/api/overseas/refresh",body({}));
    if(key!==workspaceKey())return;
    if(result.cached && ["succeeded","partial"].includes(result.state)) S.overseasMessage="刚刚检查过推荐，稍后可再次更新。";
    await loadOverseasIdeas();
  } finally {
    if(S.overseasRefreshing===key)S.overseasRefreshing=null;
    if(key===workspaceKey() && S.page==="overseas-ideas") render();
  }
}
function readOverseasFilters() {
  if(!$("#overseas-filter-form"))return;
  S.overseasFilters={...S.overseasFilters,offset:0,query:$("#overseas-query").value.trim(),category:$("#overseas-category").value,
    platform:$("#overseas-filter-platform").value||"all",industry:$("#overseas-industry").value,publisher_type:$("#overseas-publisher-type").value};
}
async function searchOverseas() {
  if(S.overseasSearching) return;
  clearTimeout(overseasRefreshTimer);
  readOverseasFilters(); const f={...S.overseasFilters},key=workspaceKey();
  if(!f.query || f.platform==="all") throw new Error("请填写关键词，并选择TikTok、Reels或Shorts中的一个平台");
  S.overseasSearching=true; S.overseasMessage=""; render();
  const request=++S.overseasLoadToken;
  try {
    const result=await post("/api/overseas/search",body({query:f.query,platform:f.platform}));
    if(key!==workspaceKey() || request!==S.overseasLoadToken) return;
    S.overseasFilters={...f,saved:false,scope:"candidates"};
    S.overseasMessage='搜索已排队；成功后扣除 '+(S.boot.rules.search??1)+' 积分，缓存命中退回，可在任务记录查看。';
    await poll(result.task_ids,async()=>{
      if(key!==workspaceKey())return;
      await loadOverseasIdeas();
      if(key!==workspaceKey())return;
      S.overseasMessage='平台搜索已完成，候选已加入灵感库，可收藏后用于创作。';render();
    },true);
  } catch(error) {if(key===workspaceKey() && request===S.overseasLoadToken) S.overseasMessage=error.message;}
  finally {if(key===workspaceKey()) {S.overseasSearching=false;if(S.page==="overseas-ideas") render();}}
}
function collectOverseasModal() {
  modal("收集海外社媒内容", `<form id="overseas-collect-form"><label class="field"><span>原始内容链接</span><input id="collect-overseas-url" type="url" maxlength="2000" required placeholder="https://www.tiktok.com/@.../video/..."></label><label class="field"><span>标题 / 内容名称</span><input id="collect-overseas-title" maxlength="200" required></label><label class="field"><span>品类</span><select id="collect-overseas-category"><option value="">待分类</option>${Object.entries(S.overseasLibrary?.categories||{}).map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join("")}</select></label><label class="field"><span>创意说明 / 字幕（可选）</span><textarea id="collect-overseas-summary" rows="4" maxlength="20000"></textarea></label><button class="btn primary full" type="submit">保存到我的收藏</button></form>`);
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
    S.overseasForm.observation={};drafts.save(key+":overseas",S.overseasForm);
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
  return `<article class="draft overseas-card"><div class="draft-top"><span>${number?`<span class="direction-badge">建议 ${number}</span> `:""}${platformLabel(d.overseas.platform)} · ${d.overseas.duration} 秒${d.demo?' · 演示':""}</span><span>${date(c.created_at)}</span></div><h3>${esc(d.title)}</h3>${overseasDetails(c)}${topicBasis(d)}${titles.length?`<section class="overseas-output-section"><h4>标题备选</h4><ul>${titles.map(t=>`<li>${esc(t)}</li>`).join("")}</ul></section>`:""}<section class="overseas-output-section"><h4>发布内容 / Tags</h4><p class="draft-body">${esc(d.body)}</p>${d.tags?.length?`<div class="tags">${d.tags.map(t=>"#"+esc(t)).join(" ")}</div>`:""}</section><details class="transcript-box"><summary>发布与反馈${c.tracking?.status === "published" ? " · 已发布" : ""}</summary>${pipeline(c)}${resultSummary(c)}</details><div class="actions">${button("复制内容","copy","secondary small","copy",`data-id="${c.id}"`)}${d.script?.trim()?button("复制口播","copy-overseas-script","secondary small","copy",`data-id="${c.id}"`):""}${button("下载创意 TXT","download-overseas-plan","secondary small","download",`data-id="${c.id}"`)}${button("编辑标题与内容","edit-draft","secondary small","edit",`data-id="${c.id}"`)}${button(c.saved?"已收藏":"收藏","save-creation","secondary small",c.saved?"check":"star",`data-id="${c.id}"`)}${button("删除","delete-creation","secondary small","trash",`data-id="${c.id}"`)}</div></article>`;
}
function overseasShotCopy(shot) {
  return [shot.line?`口播：${shot.line}`:"",shot.line&&shot.translation_zh?`口播中译：${shot.translation_zh}`:"",shot.screen_text?`屏幕文案：${shot.screen_text}`:"",shot.screen_text&&shot.screen_text_zh?`屏幕文案中译：${shot.screen_text_zh}`:""].filter(Boolean).join("\n");
}
function shootSetupText(setup) {
  if (!setup) return "";
  return [`${setup.people} 人`, setup.locations.join("、"), setup.props.length ? "道具 · " + setup.props.join("、") : "无需额外道具"].join(" / ");
}
function overseasFilmingSteps(d, shots) {
  const steps = [];
  if (d.cost_basis) steps.push(d.cost_basis);
  if ((d.shoot_setup || d.production_method) && Array.isArray(d.shooting_list)) steps.push(...d.shooting_list);
  shots.forEach((shot, index) => {
    const sound = shot.sfx ? "声音 · " + shot.sfx : "";
    const method = [shot.implementation, sound].filter(Boolean).join("\n");
    if (method) steps.push(`镜头 ${index + 1} · ${method}`);
  });
  return steps;
}
function overseasDetails(c) {
  const d=c.data;if(!d.overseas) return "";
  const shots=overseasShots(d);
  const steps = overseasFilmingSteps(d, shots);
  const setup = d.shoot_setup;
  const filming = d.production_method || steps.length ? `<section class="overseas-output-section"><h4>怎么拍</h4>
    ${d.production_method ? `<p>${esc(d.production_method)}</p>` : ""}
    ${setup ? `<div class="muted">${esc(shootSetupText(setup))}</div>` : ""}
    ${setup?.simpler_take ? `<p><strong>简化拍法</strong> ${esc(setup.simpler_take)}</p>` : ""}
    ${steps.length ? `<details class="transcript-box"><summary>实拍步骤</summary><ul>${steps.map(step => `<li>${esc(step)}</li>`).join("")}</ul></details>` : ""}</section>` : "";
  return `<div class="overseas-delivery"><section class="overseas-output-section"><h4>创意</h4><p>${esc(overseasConcept(d))}</p></section>${filming}<section class="overseas-output-section"><h4>画面描述</h4>${shots.map((shot,i)=>`<div class="overseas-shot"><h5>镜头 ${i+1}${Number.isFinite(shot.start)&&Number.isFinite(shot.end)?` · ${shot.start}–${shot.end} 秒`:""}</h5>${shot.camera?`<p>${esc(shot.camera)}</p>`:""}<p>${esc(shot.action)}</p>${shot.line?.trim()?`<div class="overseas-video-copy"><strong>口播</strong><p>${esc(shot.line)}</p>${shot.translation_zh?`<p class="muted">${esc(shot.translation_zh)}</p>`:""}</div>`:""}${shot.screen_text?.trim()?`<div class="overseas-video-copy"><div class="pipeline-head"><strong>屏幕文案</strong>${button("复制屏幕文案","copy-overseas-screen-text","secondary small","copy",`data-id="${c.id}" data-shot="${i}"`)}</div><p>${esc(shot.screen_text)}</p>${shot.screen_text_zh?`<p class="muted">${esc(shot.screen_text_zh)}</p>`:""}</div>`:""}</div>`).join("")}</section>${d.script?.trim()?`<section class="overseas-output-section"><h4>口播文案</h4><p>${esc(d.script)}</p>${d.translation_zh?`<h5>中文翻译</h5><p>${esc(d.translation_zh)}</p>`:""}</section>`:""}<section class="overseas-output-section"><h4>AI 生成提示词</h4>${shots.map((shot,i)=>`<div class="overseas-ai-prompt"><div class="pipeline-head"><h5>镜头 ${i+1}</h5>${button("复制提示词","copy-overseas-prompt","secondary small","copy",`data-id="${c.id}" data-shot="${i}"`)}</div><pre>${esc(overseasAiPrompt(d,shot))}</pre></div>`).join("")}</section></div>`;
}
function overseasPlanText(d) {
  const shots = overseasShots(d);
  const steps = overseasFilmingSteps(d, shots);
  const filming = d.production_method || steps.length ? [
    "怎么拍", d.production_method, shootSetupText(d.shoot_setup),
    ...(d.shoot_setup?.simpler_take ? ["简化拍法", d.shoot_setup.simpler_take] : []),
    ...(steps.length ? ["实拍步骤", ...steps] : []),
  ] : [];
  return [d.title,"创意",overseasConcept(d),...filming,"画面描述",...shots.map((shot,i)=>`镜头 ${i+1}${Number.isFinite(shot.start)&&Number.isFinite(shot.end)?` · ${shot.start}–${shot.end} 秒`:""}\n${shot.camera||""}\n${shot.action}\n${overseasShotCopy(shot)}`),...(d.script?.trim()?["口播文案",d.script,...(d.translation_zh?["中文翻译",d.translation_zh]:[])]:[]),"AI 生成提示词",...shots.map((shot,i)=>`镜头 ${i+1}\n${overseasAiPrompt(d,shot)}`),"标题备选",...(d.titles||[]),"发布内容 / Tags",CreationTools.publicCopy(d)].filter(Boolean).join("\n\n");
}

Object.assign(actions,{
  "focus-overseas-creation":el=>{S.focusCreation=el.dataset.id;render();window.scrollTo({top:0});},
  overseas:()=>navigate("overseas"),"overseas-ideas":()=>navigate("overseas-ideas"),
  "play-overseas-video":el=>{
    const item=S.overseasLibrary?.items.find(i=>i.id===el.dataset.id);
    const link=dailyVideoLink(item);
    const player=link && overseasPlayerUrl(link);
    if(!player)return;
    const src=new URL(player);
    if(src.hostname!=="www.instagram.com")src.searchParams.set("autoplay","1");
    const brand=/^https:\/\/weibo\.com\/\d+\/[a-zA-Z0-9]+$/.test(item.brand_post||"")?`<a class="video-watch" href="${esc(item.brand_post)}" target="_blank" rel="noopener noreferrer">品牌微博 ↗</a>`:"";
    modal("观看原片",overseasFrame(src.href,item.title_zh||item.title||"原片播放器",item.landscape)+`<div class="actions"><a class="video-watch" href="${esc(link)}" target="_blank" rel="noopener noreferrer">在原平台观看 ↗</a>${brand}</div>`,item.landscape);
  },
  "refresh-overseas-ideas":refreshOverseasIdeas,
  "collect-overseas":collectOverseasModal,"search-overseas":searchOverseas,
  "overseas-idea-page":async el=>{S.overseasFilters.offset=Number(el.dataset.offset);await loadOverseasIdeas();},
  "overseas-tab":async el=>{readOverseasFilters();S.overseasFilters.offset=0;S.overseasFilters.saved=el.dataset.scope==="saved";S.overseasFilters.scope=S.overseasFilters.saved?"selected":el.dataset.scope;S.overseasMessage="";await loadOverseasIdeas();},
  "overseas-daily-more":()=>{S.overseasFilters.expandedDay=S.overseasLibrary.daily.day;render();},
  "save-overseas-idea":async el=>{
    const key=workspaceKey(),item=S.overseasLibrary.items.find(i=>i.id===el.dataset.id);
    if(!item) return;
    if(item.id.startsWith("case_")) await post("/api/overseas/ideas",body({case_id:item.id}));
    else if(item.id.startsWith("archetype_")) await post("/api/overseas/ideas",body({archetype_id:item.id}));
    else if(item.id.startsWith("feed_")) await post("/api/overseas/ideas",body({feed_id:item.id}));
    else await api("/api/overseas/ideas/"+item.id,{method:"PATCH",body:JSON.stringify(body({saved:!item.saved}))});
    if(key!==workspaceKey()) return;
    await loadOverseasIdeas();toast(item.saved?"已取消收藏":"创意已收藏");
  },
  "use-overseas-idea":async el=>{
    const item=S.overseasLibrary.items.find(i=>i.id===el.dataset.id);if(!item)return;
    S.overseasForm={...S.overseasForm,reference_id:item.id};S.overseasReferenceTitle=item.title_zh||item.title;
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
  if(e.target.id==="overseas-edition") {
    S.overseasFilters.edition=e.target.value;
    await loadOverseasIdeas();
    return;
  }
  if(e.target.id!=="overseas-material-files") return;
  try {await uploadOverseasMaterials(e.target);} catch(error) {e.target.value="";toast(error.message);}
});

// A signed provider thumbnail can expire between feed refreshes.
document.addEventListener("error",event=>{
  const button=event.target.closest?.("button.daily-poster");
  if(!button || event.target.tagName!=="IMG")return;
  event.target.remove();
},true);
