"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const paths = {
  home: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  folder:
    "M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  edit: "m15 4 5 5M4 16 16 4a2 2 0 0 1 4 4L8 20H4z",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  coin: "M12 7v10M15 8h-4a2 2 0 0 0 0 4h2a2 2 0 0 1 0 4H9M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  link: "m10 13 4-4M8 15l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 9l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0",
  layers: "m12 3 10 5-10 5L2 8zm-9 9 9 5 9-5M3 16l9 5 9-5",
  user: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2",
  search: "M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0m-2 5 6 6",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  back: "M20 12H4m6-6-6 6 6 6",
  heart: "M20 5c-3-3-6-1-8 1-2-2-5-4-8-1-5 5 3 11 8 15 5-4 13-10 8-15",
  star: "m12 2 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z",
  chat: "M21 11a9 9 0 0 1-9 9H3l2-5a9 9 0 1 1 16-4",
  trend: "m3 17 6-6 4 4 8-10m-6 0h6v6",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  plus: "M12 5v14M5 12h14",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12M6 18 18 6",
  copy: "M9 9h12v12H9zM15 5V2H2v13h3",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7",
  image: "M3 3h18v18H3zM3 17l6-6 4 4 3-3 5 5M16 7h.01",
  help: "M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5M12 17h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  settings:
    "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2",
  logout: "M10 4H4v16h6M10 12h12m-4-4 4 4-4 4",
  menu: "M3 6h18M3 12h18M3 18h18",
  shield: "M12 2 3 6v6q0 6 9 10 9-4 9-10V6zm-5 10 3 3 7-7",
  refresh: "M20 8a8 8 0 1 0 0 8M20 3v5h-5",
};
const icon = (n) =>
  `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[n] || paths.spark}"/></svg>`;
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const S = {
  boot: null,
  project: localStorage.getItem("daolook-project"),
  page: "discover",
  entry: "original",
  filter: "全部",
  contentFormat: "全部",
  sourceKind: "all",
  platform: "all",
  sort: "recent",
  search: "",
  workspace: { sources: [], creations: [], assets: [], images: [] },
  tasks: [],
  detail: null,
  adminTab: "config",
  busy: false,
  entryText: "",
  requirements: "",
  goal: "leads",
  temporary: "",
  original: {
    goal: "leads",
    platform: "xhs",
    topic: "",
    keyword: "",
    assets: [],
    requirements: "",
    temporary: "",
  },
  selectedAssets: [],
};
const drafts = createDraftStore({
  getItem: key => sessionStorage.getItem(key), setItem: (key,value) => sessionStorage.setItem(key,value),
  removeItem: key => sessionStorage.removeItem(key), key: i => sessionStorage.key(i),
  get length() { return sessionStorage.length; },
});
const workspaceKey = () => S.boot ? `${S.boot.user.id}:${S.project}` : '';
const editStore = CreationTools.createEditStore({
  getItem: key => sessionStorage.getItem(key), setItem: (key, value) => sessionStorage.setItem(key, value),
  removeItem: key => sessionStorage.removeItem(key), key: i => sessionStorage.key(i),
  get length() { return sessionStorage.length; },
});
function saveDraft() { if (S.workspaceKey && S.workspaceKey === workspaceKey()) S.draftSaved = drafts.save(S.workspaceKey, S.original); }
function showFormError(form, message) {
  let error = form?.querySelector('.form-error');
  if (!error && form) { error=document.createElement('p');error.className='inline-error form-error';error.setAttribute('role','alert');form.prepend(error); }
  if(error) {error.textContent=message;error.tabIndex=-1;error.focus();} else toast(message);
}
const pageNames = {
  discover: "开始创作",
  saved: "参考收藏",
  creations: "我的创作",
  assets: "项目资料",
  tasks: "任务记录",
  credits: "积分账本",
  admin: "管理后台",
  detail: "内容拆解",
};
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  let result;
  try { result = await response.json(); } catch { throw new Error(response.status === 429 ? '操作太频繁，请稍后再试' : '服务暂时未响应，请稍后重试；已提交任务可在任务记录查看'); }
  if (!response.ok) throw new Error(result.error || (response.status === 429 ? '操作太频繁，请稍后再试' : '请求失败，请稍后重试'));
  return result;
}
const post = (path, data) =>
  api(path, { method: "POST", body: JSON.stringify(data) });
const body = (d) => ({ ...d, project_id: S.project });
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("show");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(
    () => { $("#toast").classList.remove("show"); $("#toast").textContent = ""; },
    3600,
  );
}
function fmt(n) {
  return Number(n) >= 10000
    ? (Number(n) / 10000).toFixed(1) + "w"
    : Number(n) >= 1000
      ? (Number(n) / 1000).toFixed(1) + "k"
      : String(n ?? "—");
}
function date(d) {
  return new Date(d).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
function art(s) {
  if (safeImage(s.data.cover_url)) return esc(s.data.cover_url);
  return `/art/${["slow", "home", "coffee", "travel", "food", "book"].includes(s.data.theme) ? s.data.theme : "book"}.svg`;
}
function empty(title, text, action = "") {
  return `<div class="empty">${icon("spark")}<h3>${title}</h3><p>${text}</p>${action}</div>`;
}
function button(label, action, style = "secondary", ic = "", attrs = "") {
  return `<button class="btn ${style}" data-action="${action}" ${attrs}>${ic ? icon(ic) : ""}${label}</button>`;
}
async function bootstrap() {
  S.boot = await api("/api/bootstrap");
  if (!S.boot.projects.some((p) => p.id === S.project))
    S.project = S.boot.projects[0]?.id;
  localStorage.setItem("daolook-project", S.project);
  await refresh();
}
async function refresh() {
  const key = workspaceKey();
  if (S.workspaceKey !== key) {
    S.original = { goal: "leads", platform: "xhs", topic: "", keyword: "", assets: [], requirements: "", temporary: "", ...(drafts.read(key) || {}) };
    S.selectedAssets = [];
    S.requirements = S.temporary = S.entryText = S.transcript = "";
    S.creationSource = null;
    S.goal = "leads";
    S.busy = false;
    S.watching = null;
    S.workspace = { sources: [], creations: [], assets: [], images: [] };
  }
  S.workspaceKey = key;
  const [workspace, tasks, boot] = await Promise.all([
    api("/api/workspace?project_id=" + S.project), api("/api/tasks"), api("/api/bootstrap"),
  ]);
  if (workspaceKey() !== key) return;
  S.workspace = workspace; S.tasks = tasks; S.boot = boot;
  S.original.assets = S.original.assets.filter(id => workspace.assets.some(a => a.id === id));
}
function shell() {
  const project = S.boot.projects.find((p) => p.id === S.project);
  const user = S.boot.user;
  return `<div class="shell"><aside class="sidebar"><button class="close sidebar-mobile-close" data-action="menu" aria-label="关闭菜单">${icon("close")}</button><a class="brand" href="#discover">DAOLOOK<span class="brand-dot">✳</span></a><div class="brand-sub">有依据 · 有灵感 · 有表达</div><button class="project-switch" data-action="projects"><span class="project-symbol">${icon("folder")}</span><span>${esc(project?.name || "选择项目")}<small>个人工作空间</small></span><span class="chevron">⌄</span></button><div class="nav-label">WORKSPACE</div><nav class="nav" aria-label="工作空间">${[
    ["discover", "spark", "开始创作"],
    ["saved", "grid", "参考收藏"],
    ["creations", "edit", "我的创作"],
    ["assets", "folder", "项目资料"],
  ]
    .map(
      ([id, ic, label]) =>
        `<button class="${S.page === id || (S.page === "detail" && id === "discover") ? "active" : ""}" data-page="${id}">${icon(ic)}${label}${id === "creations" ? `<span class="count">${S.workspace.creations.length}</span>` : ""}</button>`,
    )
    .join(
      "",
    )}</nav><div class="nav-label">MANAGE</div><nav class="nav">${[["tasks", "clock", "任务记录"], ["credits", "coin", "积分账本"], ...(user.role === "admin" ? [["admin", "settings", "管理后台"]] : [])].map(([id, ic, label]) => `<button class="${S.page === id ? "active" : ""}" data-page="${id}">${icon(ic)}${label}</button>`).join("")}</nav><div class="sidebar-bottom"><div class="credit-mini"><div class="top">${icon("coin")}创作积分</div><div class="balance">${S.boot.credits.balance.toLocaleString()}<small>可用积分</small></div><div class="credit-track"><span style="width:${Math.min(100, S.boot.credits.balance / 3)}%"></span></div><button data-page="credits">查看积分与消耗 ${icon("arrow")}</button></div><button class="profile" data-action="account"><span class="avatar">${user.email.startsWith("demo-") ? "D" : esc(user.email[0].toUpperCase())}</span><span>${user.email.startsWith("demo-") ? "登录 / 注册" : "账号与项目"}<small>${user.role === "admin" ? "超级管理员" : user.email.startsWith("demo-") ? "演示工作空间" : "个人创作者"}</small></span>${icon("settings")}</button></div></aside><main class="main"><header class="topbar"><div class="breadcrumb"><button class="mobile-menu" data-action="menu" aria-label="展开菜单">${icon("menu")}</button>${icon("home")}<span>/</span><span class="crumb-name">${esc(project?.name)}</span><span>/</span><strong>${pageNames[S.page]}</strong></div><div class="top-actions"><span class="mode">${S.boot.mode === "demo" ? "演示模式 · 仅体验模板" : "已连接服务"}</span><button class="text-btn" data-action="help">${icon("help")}使用指南</button><span class="avatar">${user.email.startsWith("demo-") ? "D" : esc(user.email[0].toUpperCase())}</span></div></header><div class="content" id="content">${pageContent()}</div></main></div>`;
}
function heading(
  title,
  description,
  right = "",
  eyebrow = "YOUR NEXT GREAT IDEA STARTS HERE",
) {
  return `<div class="heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div>${right}</div>`;
}
function pageContent() {
  switch (S.page) {
    case "discover":
      return discover();
    case "saved":
      return saved();
    case "detail":
      return detail();
    case "creations":
      return creations();
    case "assets":
      return assets();
    case "tasks":
      return tasks();
    case "credits":
      return credits();
    case "admin":
      return admin();
    default:
      return discover();
  }
}
function shellKey() {
  const project = S.boot.projects.find((p) => p.id === S.project);
  return [
    S.project,
    project?.name,
    S.boot.user.email,
    S.boot.user.role,
    S.boot.mode,
    S.boot.credits.balance,
    S.boot.credits.frozen,
    S.workspace.creations.length,
    S.page,
  ].join("|");
}
function render() {
  const active = document.activeElement;
  const id = active?.id;
  const start = active?.selectionStart;
  const app = $("#app");
  const key = shellKey();
  if (app.dataset.shellKey === key && $("#content")) {
    $("#content").innerHTML = pageContent();
  } else {
    app.dataset.shellKey = key;
    app.innerHTML = shell();
  }
  if (id && $("#" + id)) {
    $("#" + id).focus();
    if (start !== null && start !== undefined)
      try {
        $("#" + id).setSelectionRange(start, start);
      } catch {}
  }
}
function discover() {
  return (
    heading(
      '把你的生意，讲给<span class="serif">对的人。</span>',
      "给一份业务资料，选一个目标，拿到能用的文案。",
      `<div class="step-note"><span>01 选目标</span><i>→</i><span>02 给资料</span><i>→</i><span>03 拿文案</span></div>`,
    ) +
    entryPanel() +
    `${S.entry === "original" ? '<details class="optional-references"><summary>想找一些写法参考？（可选）</summary>' : ""}<section><div class="section-head"><div><h2>${S.workspace.sources.length && S.workspace.sources.every((s) => s.data.demo) ? "拆解体验样本" : "项目参考内容"} <span>${S.workspace.sources.length} 条</span></h2><p>你提交并完成拆解的内容会保留在这里。示例有明确标识，不是实时爆款推荐。</p></div><button class="text-btn" data-action="refresh">${icon("refresh")}刷新列表</button></div>${filters()}<div class="cards" id="source-cards">${sourceCards(false)}</div><div class="bottom-note">${icon("shield")}${S.boot.mode === "demo" ? "示例内容与互动数据仅供体验，不代表真实平台数据" : "仅分析公开内容，不长期保存完整原视频"}</div></section>${S.entry === "original" ? "</details>" : ""}`
  );
}
function entryPanel() {
  const tabs = [
    ["original", "spark", "用我的资料创作"],
    ["single", "link", S.entry === "original" ? "参考内容改写（可选）" : "单条链接"],
    ["batch", "layers", "批量链接"],
    ["creator", "user", "博主主页"],
    ["keyword", "search", "关键词 / 品类"],
  ];
  const placeholder = {
    single: "粘贴小红书 / 抖音分享链接，让灵感有迹可循…",
    batch: "每行粘贴一条小红书或抖音链接，支持混合平台",
    creator: "粘贴博主主页分享链接，发现值得参考的内容…",
    keyword: "输入关键词或品类，如：咖啡、家居、生活方式…",
  }[S.entry];
  return `<section class="entry-panel"><div class="entry-tabs" role="tablist" aria-label="参考入口">${tabs.filter(([id]) => S.entry !== "original" || ["original", "single"].includes(id)).map(([id, ic, label]) => `<button role="tab" aria-selected="${S.entry === id}" tabindex="${S.entry === id ? 0 : -1}" class="${S.entry === id ? "active" : ""}" data-entry="${id}">${icon(ic)}${label}</button>`).join("")}<span class="entry-help">${S.entry === "original" ? "把你的产品和服务讲清楚" : "好创作，从一个好参考开始"}</span></div>${S.entry === "original" ? originalForm() : `<form id="analyze-form"><div class="input-row"><div class="reference-input">${icon(S.entry === "keyword" ? "search" : "link")}${S.entry === "batch" ? `<textarea id="reference" aria-label="参考内容" placeholder="${placeholder}">${esc(S.entryText)}</textarea>` : `<input id="reference" aria-label="参考内容" value="${esc(S.entryText)}" placeholder="${placeholder}" autocomplete="off">`}</div>${S.entry === "keyword" ? `<select id="keyword-platform" aria-label="搜索平台"><option value="xhs">小红书</option><option value="douyin">抖音</option></select>` : ""}<button type="submit" class="btn primary" ${S.busy ? "disabled" : ""}>${S.busy ? '<span class="spinner"></span>' : icon("spark")}${S.busy ? "正在提交" : "开始拆解"} ${!S.busy ? icon("arrow") : ""}</button></div>${S.entry === "single" ? `<details class="transcript-box"><summary>视频内容？可补充口播或字幕文字（可选）</summary><textarea id="transcript" rows="4" maxlength="20000" aria-label="视频口播或字幕文字" placeholder="粘贴这条视频的口播或字幕。没有时系统会尝试自动转写；都没有时，口播、镜头、节奏会标注无法判断。">${esc(S.transcript || "")}</textarea></details>` : ""}<div class="entry-bottom"><span class="platform-marks"><span class="xhs-mark">小红书</span><span class="dy-mark">♪</span>${S.entry === "keyword" ? (S.boot.mode === "demo" ? "演示搜索仅返回预置样本，不执行真实检索" : "按所选平台搜索，以结果中位数为赛道基线，按相对表现精选；评分未经校准，不保证为爆款") : "自动识别平台 · 使用对应平台的拆解方式"}</span><span id="entry-cost">${analyzeEstimate()}</span></div></form>`}</section>`;
}
function catalogItems() {
  return S.workspace.sources.filter(
    (s) =>
      (S.page !== "saved" || s.saved) &&
      (S.sourceKind === "all" ||
        (S.sourceKind === "demo" ? s.data.demo : !s.data.demo)) &&
      (S.platform === "all" || s.platform === S.platform),
  );
}
function filters() {
  const pool = catalogItems();
  const industries = [
    "全部",
    ...new Set(pool.map((s) => s.classification?.industry || "待分类")),
  ];
  const formats = [
    "全部",
    ...new Set(pool.map((s) => s.classification?.format || "待判断")),
  ];
  if (!industries.includes(S.filter)) S.filter = "全部";
  if (!formats.includes(S.contentFormat)) S.contentFormat = "全部";
  return `<div class="catalog-controls"><div class="filters"><div class="filter-group"><span class="muted">行业</span>${industries.map((f) => `<button class="chip ${S.filter === f ? "active" : ""}" data-filter="${esc(f)}">${esc(f)} · ${f === "全部" ? pool.length : pool.filter((s) => (s.classification?.industry || "待分类") === f).length}</button>`).join("")}</div></div><div class="filter-right catalog-selects"><label>内容来源<select id="source-kind-filter"><option value="all" ${S.sourceKind === "all" ? "selected" : ""}>全部来源</option><option value="real" ${S.sourceKind === "real" ? "selected" : ""}>真实参考</option><option value="demo" ${S.sourceKind === "demo" ? "selected" : ""}>演示样本</option></select></label><label>表达形式<select id="format-filter">${formats.map((f) => `<option ${S.contentFormat === f ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></label><label>平台<select id="platform-filter" aria-label="筛选平台"><option value="all" ${S.platform === "all" ? "selected" : ""}>全部平台</option><option value="xhs" ${S.platform === "xhs" ? "selected" : ""}>小红书</option><option value="douyin" ${S.platform === "douyin" ? "selected" : ""}>抖音</option></select></label><label>排序<select id="sort-filter" aria-label="内容排序">${[
    ["recent", "最近拆解"],
    ["engagement", "点赞最多"],
    ["relative", "相对表现（未校准）"],
    ["efficiency", "粉丝效率"],
  ]
    .map(
      ([k, v]) =>
        `<option value="${k}" ${S.sort === k ? "selected" : ""}>${v}</option>`,
    )
    .join(
      "",
    )}</select></label></div><p class="catalog-explanation">${{ recent: "按加入项目的时间排序，没有自动评选“好内容”。", engagement: "按点赞数从高到低排序；缺少数据的内容排在最后。", relative: "按已有指标加权排序，缺失项不参与。演示与真实内容分组，不混合比较；不同数据完整度的分数不可直接视为优劣。", efficiency: "粉丝效率 =（点赞＋收藏）÷ 粉丝数，不是曝光互动率；缺少任一数据时不计算。" }[S.sort]} 分类为关键词建议，可在卡片查看依据。</p></div>`;
}
function sourceMetric(s, kind) {
  const d = s.data;
  if (kind === "relative") return s.ranking?.score ?? null;
  const numeric = (value) =>
    value !== null &&
    value !== undefined &&
    value !== "" &&
    Number.isFinite(Number(value)) &&
    Number(value) >= 0
      ? Number(value)
      : null;
  if (kind === "engagement") return numeric(d.likes);
  const likes = numeric(d.likes),
    saves = numeric(d.saves),
    followers = numeric(d.followers);
  return likes !== null && saves !== null && followers > 0
    ? (likes + saves) / followers
    : null;
}
function sourceCards(savedOnly) {
  let items = S.workspace.sources.filter(
    (s) =>
      (!savedOnly || s.saved) &&
      (S.filter === "全部" ||
        (s.classification?.industry || "待分类") === S.filter) &&
      (S.contentFormat === "全部" ||
        (s.classification?.format || "待判断") === S.contentFormat) &&
      (S.sourceKind === "all" ||
        (S.sourceKind === "demo" ? s.data.demo : !s.data.demo)) &&
      (S.platform === "all" || s.platform === S.platform) &&
      (!S.search || s.data.title.includes(S.search)),
  );
  if (S.sort !== "recent")
    items.sort((a, b) => {
      if (Boolean(a.data.demo) !== Boolean(b.data.demo))
        return a.data.demo ? 1 : -1;
      const av = sourceMetric(a, S.sort),
        bv = sourceMetric(b, S.sort);
      return av === null ? (bv === null ? 0 : 1) : bv === null ? -1 : bv - av;
    });
  if (!items.length)
    return `<div style="grid-column:1/-1">${empty(S.sourceKind === "real" ? "当前筛选下没有真实参考" : "这里还没有参考内容", S.sourceKind === "real" && S.boot.mode === "demo" ? "当前为演示模式。配置数据源与模型并启用真实服务后，才能获取真实参考。" : "粘贴一条链接开始拆解，或试试其他筛选条件。")}</div>`;
  return items
    .map(
      (s, i) =>
        `<article class="source-card" style="animation-delay:${Math.min(i, 5) * 40}ms"><button class="art" data-source="${s.id}" aria-label="拆解 ${esc(s.data.title)}"><img src="${art(s)}" alt="${esc(s.data.category || "参考内容")}主题插画" loading="lazy"><span class="platform-badge ${s.platform === "douyin" ? "dy" : ""}">${s.platform === "xhs" ? "小红书" : "♪ 抖音"}</span>${s.data.demo ? '<span class="demo-stamp">示例</span>' : ""}<span class="outlier">${icon("trend")}${sourceMetric(s, "efficiency") !== null ? `${sourceMetric(s, "efficiency").toFixed(1)}× 粉丝效率${s.data.demo ? " · 示例" : ""}` : "效率数据不完整"}</span></button><div class="source-body"><h3>${esc(s.data.title)}</h3><div class="author"><span class="author-avatar">${esc((s.data.author || "作")[0])}</span><span class="author-name">${esc(s.data.author || "未知作者")}</span><span class="author-followers">${fmt(s.data.followers)} 粉丝</span></div><div class="metrics"><span>${icon("heart")}${fmt(s.data.likes)}</span><span>${icon("star")}${fmt(s.data.saves)}</span><span>${icon("chat")}${fmt(s.data.comments)}</span></div><p class="source-format">形式 · ${esc(s.classification?.format || "待判断")} <span>建议分类</span></p><details class="source-evidence"><summary>来源与排序依据</summary><p>${esc(s.classification?.basis || "分类依据待补充")}</p>${(s.selection_reasons || []).map((r) => `<p>${esc(r)}</p>`).join("")}${s.data.url && /^https?:\/\//.test(s.data.url) && !s.data.demo ? `<a href="${esc(s.data.url)}" target="_blank" rel="noopener noreferrer">查看原始内容 ↗</a>` : ""}</details><div class="card-footer"><span class="category">行业 · ${esc(s.classification?.industry || "待分类")}</span><button data-source="${s.id}">拆解内容 ${icon("arrow")}</button></div></div></article>`,
    )
    .join("");
}
function saved() {
  return (
    heading(
      "收藏值得反复看的内容",
      "每一条保存的参考，都是下一次创作的起点。",
      button("寻找新灵感", "discover", "primary", "plus"),
    ) +
    filters() +
    `<div class="cards">${sourceCards(true)}</div>`
  );
}
function detail() {
  const s = S.workspace.sources.find((x) => x.id === S.detail);
  if (!s)
    return empty(
      "参考内容不存在",
      "请返回发现灵感页面重新选择。",
      button("返回", "discover", "primary"),
    );
  return `<button class="back" data-page="discover">${icon("back")}返回发现灵感</button>${heading(esc(s.data.title), "先理解内容为什么有效，再找到属于自己的表达。", button(s.saved ? "已保存参考" : "保存参考", "save-source", s.saved ? "secondary" : "primary", s.saved ? "check" : "plus", `data-id="${s.id}"`), "CONTENT BREAKDOWN / " + (s.platform === "xhs" ? "小红书" : "抖音"))}<div class="two-col"><section class="panel"><div class="detail-cover"><img src="${art(s)}" alt="参考主题插画"></div><div class="source-meta"><span>${esc(s.data.author || "未知作者")}</span><span>${fmt(s.data.likes)} 赞</span><span>${fmt(s.data.saves)} 收藏</span>${s.url && /^https?:/.test(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>` : ""}</div>${s.data.demo ? '<div class="notice">演示拆解：以下内容用于体验产品流程，不是真实平台抓取或模型分析。</div>' : ""}${s.data.transcript_source ? `<div class="hint">口播与字幕依据：${esc(s.data.transcript_source)}</div>` : s.data.transcript_note ? `<div class="notice">${esc(s.data.transcript_note)}；口播、镜头、节奏相关判断仅供参考。</div>` : ""}<h2>把好内容拆开看</h2>${(s.analysis.sections || []).map((a, i) => `<div class="analysis-section"><span class="num">${String(i + 1).padStart(2, "0")}</span><div><h3>${esc(a.name)}</h3><p>${esc(a.text)}</p></div></div>`).join("")}</section><section class="panel composer"><h2>${icon("spark")} 创作我的版本</h2><p class="intro">借鉴这条内容的创作思路，结合你的品牌与本次要求，一次获得 6 到 8 条不同角度的文案。</p><form id="create-form">${goalPicker("create-goal", S.goal)}<label class="field"><span>本次创作要求 <small style="display:inline;font-weight:400">可选</small></span><textarea id="requirements" rows="5" placeholder="比如：改成适合独立咖啡店的日常分享，语气轻松，面向刚接触手冲的年轻人…">${esc(S.requirements)}</textarea></label><div class="field"><span>选择项目资料 <small style="display:inline;font-weight:400">可选，不会自动使用</small></span>${S.workspace.assets.length ? S.workspace.assets.map((a) => `<label class="check-row"><input type="checkbox" name="asset" value="${esc(a.id)}" ${S.selectedAssets.includes(a.id) ? "checked" : ""}>${a.kind === "图片" ? `<img class="asset-choice-thumb" src="${esc(safeImage(a.content))}" alt="">` : icon("folder")}${esc(a.name)}</label>`).join("") : '<p class="muted">还没有长期资料，去「项目资料」添加品牌或产品信息。</p>'}</div><div class="inline-photo-upload"><label class="field"><span>上传产品图 / 个人 IP 形象图</span><input type="file" id="creation-photo-file" accept="image/png,image/jpeg,image/webp" multiple><small>每张最多 2 MB，一次最多 6 张。上传后保存到当前项目并自动勾选，用于本次创作；封面默认带入一张，可重新选择。</small></label></div><label class="field"><span>本次临时资料 <small style="display:inline;font-weight:400">可选</small></span><textarea id="temporary" rows="3" placeholder="补充本次需要的真实信息，不会自动存入项目">${esc(S.temporary)}</textarea></label><label class="text-btn" style="cursor:pointer">${icon("plus")}上传文本资料<input type="file" id="temporary-file" accept=".txt,.md,.csv,.docx,.pdf" hidden></label><div class="hint">每次生成 6 到 8 条独立稿件 · 新结果追加保留<br>预计消耗 ${S.boot.rules.create} 积分，失败自动退还</div><button class="btn primary full" type="submit" ${S.busy ? "disabled" : ""}>${S.busy ? '<span class="spinner"></span>' : icon("spark")}生成 6 到 8 条我的版本 ${icon("arrow")}</button></form><div class="actions" style="margin-top:16px">${button(`查看已有稿件 (${S.workspace.creations.filter((c) => c.source_id === s.id).length})`, "source-creations", "secondary small", "edit")}</div></section></div>`;
}
function creations() {
  let items = S.workspace.creations.filter(
    (c) => !S.creationSource || c.source_id === S.creationSource,
  );
  if (S.onlyFavorites) items = items.filter((c) => c.saved);
  const scoped = items;
  if (S.stage && S.stage !== "all")
    items = items.filter(
      (c) =>
        stageOf(c) === S.stage ||
        (S.stage === "published" && stageOf(c) === "firsthour"),
    );
  return (
    heading(
      "把今天这篇，准备好。",
      "先选一篇，直接修改并预览，再复制发布。编辑免费，已保存的版本随时可恢复。",
      `<div class="actions">${button("Excel 导出", "export-xlsx", "secondary", "download")}${button("CSV 导出", "export-csv", "secondary", "download")}${button("开始新创作", "discover", "primary", "plus")}</div>`,
      "MADE BY YOU, INSPIRED BY THE WORLD",
    ) +
    (briefOf(S.creationSource)
      ? briefPanel(briefOf(S.creationSource))
      : sourceOf(S.creationSource)
        ? sourcePanel(sourceOf(S.creationSource))
        : "") +
    productionBoard(scoped) +
    `<div class="section-head"><h2>${S.onlyFavorites ? "收藏稿件" : "全部稿件"} <span>${items.length} 条</span></h2><button class="chip ${S.onlyFavorites ? "active" : ""}" data-action="filter-favorites">${S.onlyFavorites ? "查看全部" : "仅看收藏"}</button>${S.creationSource ? button("查看全部稿件", "all-creations", "secondary small") : ""}</div>${items.length ? creationSelection(items) : empty("从你的业务资料开始", "选一个目标，粘贴或上传产品与服务资料，就能开始创作。", button("开始创作", "discover", "primary", "spark"))}`
  );
}
function creationSelection(items) {
  const selection = CreationTools.shortlist(items, S.workspace);
  if (!selection) return `<div class="creation-grid">${items.map(c => draftCard(c)).join("")}</div>`;
  return `<section class="creation-picks"><div class="pick-intro"><p class="eyebrow">先完成一篇</p><h2>建议从这篇开始</h2><p>${selection.reasons.map(esc).join("；")}。</p><small>按本批稿件的待补项与现有图片排序，不预测流量。全部稿件均保留。</small></div><div class="pick-layout">${draftCard(selection.main, true)}${selection.alternatives.length ? `<aside class="pick-alternatives"><h3>也可以试试这些方向</h3>${selection.alternatives.map(c => `<article><p class="muted">${esc(c.data.angle || c.data.direction || "另一种表达")}</p><h4>${esc(c.data.title)}</h4><p>${esc((c.data.body || "").slice(0, 100))}${(c.data.body || "").length > 100 ? "…" : ""}</p>${button("打开并编辑", "edit-draft", "secondary small", "edit", `data-id="${c.id}"`)}</article>`).join("")}</aside>` : ""}</div></section>${selection.rest.length ? `<details class="other-creations"><summary>展开其他稿件与历史内容（${selection.rest.length} 条）</summary><div class="creation-grid">${selection.rest.map(c => draftCard(c)).join("")}</div></details>` : ""}`;
}
function draftCard(c, featured = false) {
  const d = c.data;
  const source =
    S.workspace.sources.find((s) => s.id === c.source_id) ||
    briefOf(c.source_id);
  const images = S.workspace.images.filter((i) => i.creation_id === c.id);
  return `<article class="draft ${featured ? "draft-featured" : ""}"><div class="draft-top"><span>${source?.data?.kind === "brief" ? "自主创作 · " : ""}${source?.platform === "douyin" ? "♪ 抖音脚本" : "小红书图文"}${d.angle ? " · " + esc(d.angle) : ""}</span><span>${date(c.created_at)}</span></div>${d.goal ? `<div class="draft-direction"><span class="direction-badge">${esc(GOAL_LABELS[d.goal] || "业务内容")}</span>${d.audience ? `<span>${esc(d.audience)}</span>` : ""}</div>` : ""}<h3>${esc(d.title)}</h3><div class="draft-start">${button("编辑与发布准备", "edit-draft", "primary small", "edit", `data-id="${c.id}"`)}</div>${deliveryStatus(d)}${d.quality?.status === "needs_input" ? button("补充资料再写", "improve-draft", "secondary small", "edit", `data-id="${c.id}"`) : ""}${d.demo ? '<div class="notice">演示稿件 · 模板示例，未调用 AI 模型</div>' : ""}${d.hook ? `<div class="hint"><strong>开头怎么说</strong><br>${esc(d.hook)}</div>` : ""}<div class="draft-body">${esc(d.body)}</div><div class="tags">${(d.tags || []).map((t) => "#" + esc(t)).join(" ")}</div><details><summary>标题备选、配图与素材提示</summary><p>${(d.titles || []).map(esc).join("<br>")}</p><p style="margin-top:8px">封面：${esc(d.cover_text)}</p><p>${(d.image_suggestions || []).map(esc).join(" / ")}</p><p>${(d.storyboard || []).map(esc).join("<br>")}</p><p>${(d.shooting_list || []).map(esc).join(" / ")}</p><p class="inline-error">${(d.missing || []).map(esc).join("<br>")}</p></details>${commentLayout(d.comment_layout)}${images.map(coverCard).join("")}${pipeline(c, source)}${resultSummary(c)}<div class="actions"><button data-action="copy" data-id="${c.id}">${icon("copy")} ${d.quality?.status === "needs_input" || d.demo ? "复制待完善稿" : "复制正文"}</button><button data-action="save-creation" data-id="${c.id}" class="${c.saved ? "saved-icon" : ""}">${icon(c.saved ? "check" : "star")} ${c.saved ? "已收藏" : "收藏"}</button><button data-action="cover" data-id="${c.id}">${icon("image")} 封面</button><button data-action="delete-creation" data-id="${c.id}" style="margin-left:auto;color:#a3a892" aria-label="删除此稿件">${icon("trash")}</button></div></article>`;
}
const DIRECTION_TONE = { 测评: "trust", 建立信任: "trust", 钓鱼帖: "hook", 截流: "hook" };
function commentLines(layout) {
  if (!layout) return [];
  const p = layout.pinned || {};
  return [
    ...(layout.atmosphere || []).map((t) => "【气氛】" + t),
    ...(layout.knowledge || []).map((t) => "【知识】" + t),
    p.text ? "【置顶】" + p.text : "",
    p.goal ? "置顶目标：" + p.goal : "",
    p.keep_on_top ? "保持置顶：" + p.keep_on_top : "",
    layout.first_hour ? "发布后一小时：" + layout.first_hour : "",
  ].filter(Boolean);
}
function commentLayout(layout) {
  if (!layout) return "";
  const p = layout.pinned || {};
  const list = (label, items) =>
    items && items.length
      ? `<div class="comment-row"><strong>${label}</strong><ul>${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>`
      : "";
  return `<details class="comment-layout"><summary>可用的评论回复</summary>${list("引导讨论", layout.atmosphere)}${list("补充说明", layout.knowledge)}${p.text ? `<div class="comment-row"><strong>置顶</strong><ul><li>${esc(p.text)}</li></ul><small>目标：${esc(p.goal || "")}<br>保持置顶：${esc(p.keep_on_top || "")}</small></div>` : ""}${layout.first_hour ? `<div class="comment-row"><strong>发布后一小时</strong><p>${esc(layout.first_hour)}</p></div>` : ""}</details>`;
}
function originalCost() {
  return S.boot.rules.original ?? S.boot.rules.create;
}
const GOAL_LABELS = { reach: "更多人看到", leads: "更多人咨询", sales: "更多人下单" };
function goalPicker(id, value) {
  return `<label class="field"><span>这次最想要什么？</span><select id="${id}">${Object.entries(GOAL_LABELS).map(([v, label]) => `<option value="${v}" ${value === v ? "selected" : ""}>${label}</option>`).join("")}</select></label>`;
}
function originalForm() {
  const o = S.original;
  const assets = S.workspace.assets.filter((a) => a.kind !== "账号");
  return `<form id="original-form" class="original-form">
    <div class="original-grid">${goalPicker("original-goal", o.goal)}
    <label class="field"><span>发到哪里？</span><select id="original-platform">${[["xhs", "小红书图文"], ["douyin", "抖音脚本"]].map(([v, l]) => `<option value="${v}" ${o.platform === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label class="field original-topic"><span>想介绍什么？</span><input id="original-topic" maxlength="200" value="${esc(o.topic)}" placeholder="例如：店里的冷萃挂耳咖啡" autocomplete="off" required></label></div>
    <label class="field"><span>把业务资料给我</span><textarea id="original-temporary" rows="4" maxlength="100000" placeholder="直接粘贴产品介绍、客户常问的问题或服务说明。比如：卖给谁、能解决什么、有什么真实特点、怎么咨询或购买。">${esc(o.temporary)}</textarea><small>已有资料可在下方勾选。输入会在当前标签页保留 24 小时，退出账号后清除。</small></label>
    <div class="actions"><label class="text-btn upload-label">${icon("plus")}上传业务文档<input type="file" id="original-file" accept=".txt,.md,.csv,.docx,.pdf" hidden></label><label class="text-btn upload-label">${icon("image")}添加产品 / 人物照片<input type="file" id="original-photo-file" accept="image/png,image/jpeg,image/webp" multiple hidden></label></div>
    ${assets.length ? `<details class="transcript-box" ${o.assets.length || !o.temporary.trim() ? "open" : ""}><summary>使用已保存的资料（共 ${assets.length} 份，已选 ${o.assets.length} 份）</summary><div class="original-assets">${assets.map((a) => `<label class="check-row"><input type="checkbox" name="original-asset" value="${esc(a.id)}" ${o.assets.includes(a.id) ? "checked" : ""}>${a.kind === "图片" ? `<img class="asset-choice-thumb" src="${esc(safeImage(a.content))}" alt="">` : icon("folder")}${esc(a.name)}</label>`).join("")}</div></details>` : ""}
    <details class="transcript-box"><summary>还有想补充的？（可选）</summary><label class="field"><span>语气或特别要求</span><textarea id="original-requirements" rows="2" placeholder="比如：面向第一次买挂耳的上班族，语气轻松">${esc(o.requirements)}</textarea></label><label class="field"><span>参考内容的搜索词</span><input id="original-keyword" maxlength="60" value="${esc(o.keyword)}" placeholder="不用填，系统会根据主题查找"></label></details>
    <div class="entry-bottom"><span class="platform-marks">${S.boot.mode === "demo" ? "当前为演示模式，生成的是体验模板" : "生成标题、正文、配图建议和评论回复"}</span><span>预计 ${originalCost()} 积分 · 失败自动退还</span></div>
    <button type="submit" class="btn primary" ${S.busy || S.imageUploading ? "disabled" : ""}>${S.busy ? '<span class="spinner"></span>' : icon("spark")}${S.busy ? "正在准备内容" : "帮我写好"} ${icon("arrow")}</button>
  </form>`;
}
function deliveryStatus(d) {
  const q = d.quality;
  if (!q) return '<p class="hint">历史稿件，请在发布前核对业务信息。</p>';
  return `<div class="delivery-status ${q.status === "checked" ? "checked" : ""}"><strong>${q.status === "checked" ? "基础检查通过，请核对后发布" : q.status === "review" ? "已编辑，请核对后发布" : "发布前还需补充"}</strong>${q.issues?.length ? `<ul>${q.issues.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}<p>${esc(q.note || "")}</p></div>`;
}

function editorValues() {
  const result = {};
  $$("#draft-editor [data-edit-field]").forEach(el => {
    const key = el.dataset.editField;
    if (key === "tags") result.tags = el.value.split(/[\s#,，]+/).filter(Boolean);
    else if (key.startsWith("comment-")) (result.comments ||= {})[key.slice(8)] = el.value;
    else result[key] = el.value;
  });
  return result;
}
function editorPreview(values, imageURL = "") {
  return `<div class="post-preview">${imageURL ? `<img src="${esc(safeImage(imageURL))}" alt="已保存封面，文字修改后请核对图片">` : `<div class="preview-placeholder">${icon("image")}<span>正文准备好后，可用产品照片制作封面</span></div>`}<div class="post-preview-copy"><h3>${esc(values.title)}</h3><p>${esc(values.body)}</p><div class="tags">${(values.tags || []).map(t => "#" + esc(t)).join(" ")}</div></div></div>`;
}
function updateEditorPreview() {
  const session = S.editSession;
  if (!session || session.key !== workspaceKey() || !$("#draft-editor")) return;
  const values = editorValues();
  session.dirty = CreationTools.fingerprint(values) !== session.baseline;
  $("#editor-feedback").innerHTML = session.dirty
    ? '<div class="notice">当前修改尚未保存，旧的检查结果不适用于这份改稿。保存后会重新检查占位内容和标题等基础问题，业务事实仍需你核对。</div>'
    : session.savedFeedback;
  $("#draft-live-preview").innerHTML = editorPreview(values, session.imageURL);
  $("#editor-length").textContent = `标题 ${[...values.title].length} 字 · 正文 ${[...values.body].length} 字`;
  const saved = session.readonly || !session.dirty || editStore.save(session.storageKey, session.revision, values);
  if (!session.dirty) editStore.remove(session.storageKey);
  $("#editor-save-status").textContent = session.readonly ? "已发布或已记录效果，原文只读" : session.dirty ? (saved ? "修改暂存在当前标签页，保存后同步到项目" : "浏览器无法暂存，请及时保存修改") : "当前显示已保存内容";
  $$("[data-action=restore-draft]").forEach(el => { el.disabled = session.readonly || session.dirty; });
}
async function openDraftEditor(id) {
  const c = S.workspace.creations.find(x => x.id === id);
  if (!c) throw new Error("稿件不存在，请刷新后再试");
  const key = workspaceKey();
  const storageKey = `${key}:${id}`;
  const readonly = c.tracking?.status === "published" || !!c.results?.recorded_at;
  const local = readonly ? null : editStore.read(storageKey);
  const values = local?.changes || CreationTools.editable(c.data);
  const image = S.workspace.images.filter(i => i.creation_id === id).sort((a,b) => b.created_at.localeCompare(a.created_at))[0];
  const input = (key, label, rows, max) => `<label class="field"><span>${label}</span><${rows ? "textarea" : "input"} id="edit-${key}" data-edit-field="${key}" maxlength="${max}" ${rows ? `rows="${rows}"` : `value="${esc(values[key] || "")}"`} ${["title", "body"].includes(key) ? "required" : ""}>${rows ? esc(values[key] || "") + "</textarea>" : ""}</label>`;
  const comments = values.comments;
  modal("编辑与发布准备", `<p class="subtext">直接修改这篇，同步查看正文效果。保存和恢复版本不消耗积分。</p>${local ? `<div class="notice">已找回本标签页未保存的修改。${local.revision !== (c.revision || 0) ? "服务器已有更新；请先复制备份，再打开最新稿。" : ""}</div>` : ""}${readonly ? '<div class="notice">已发布或已记录效果的稿件保留原文，可复制与查看历史。</div>' : ""}<div class="draft-editor-layout"><form id="draft-editor"><div id="editor-feedback">${deliveryStatus(c.data)}</div><fieldset ${readonly ? "disabled" : ""}>${input("title", "标题", 0, 300)}${input("body", "正文", 12, 30000)}<label class="field"><span>话题（用空格分隔）</span><input id="edit-tags" data-edit-field="tags" maxlength="1220" value="${esc((values.tags || []).join(" "))}"></label><details class="editor-extra"><summary>封面文字、开头与评论</summary>${input("cover_text", "封面文字", 2, 300)}${input("hook", "开头 / 口播钩子", 3, 2000)}${input("cta", "正文中的下一步行动", 2, 2000)}${comments ? Object.entries({atmosphere:"互动提问",knowledge:"补充说明",pinned:"置顶评论"}).map(([k,label])=>`<label class="field"><span>${label}</span><textarea id="edit-comment-${k}" data-edit-field="comment-${k}" rows="3" maxlength="4000">${esc(comments[k])}</textarea></label>`).join("") : ""}</details></fieldset><p class="hint" id="editor-save-status" aria-live="polite"></p><div class="editor-actions">${!readonly ? '<button class="btn primary" type="submit">保存修改</button>' : ""}<button class="btn secondary" type="button" data-action="copy-editor">复制当前正文</button><button class="text-btn" type="button" data-action="download-editor">下载正文 TXT</button></div><button class="text-btn editor-reload" type="button" data-action="latest-draft" ${local ? "" : "hidden"}>放弃本地修改，打开最新稿</button></form><aside class="draft-preview"><div class="preview-label"><span>正文预览</span><small id="editor-length"></small></div><div id="draft-live-preview"></div><p class="hint">预览用于检查内容与阅读顺序，实际排版以发布平台为准。${image ? "已保存封面不会随改稿自动更新。" : ""}</p>${image ? coverCard(image) : button("制作封面", "editor-cover", "secondary small", "image")}<details class="editor-history"><summary>已保存的历史版本</summary><p class="hint">恢复会新增一个版本。请先保存当前修改。</p><div id="editor-history-list">正在读取…</div></details></aside></div>`, true);
  $(".dialog").classList.add("draft-editor-dialog");
  const session = {id, key, project: S.project, storageKey, revision: local?.revision ?? c.revision ?? 0, readonly, imageURL: image?.data.url || "", savedFeedback: deliveryStatus(c.data), baseline: CreationTools.fingerprint(CreationTools.editable(c.data)), dirty: false};
  S.editSession = session;
  updateEditorPreview();
  try {
    const history = await api(`/api/creations/${id}/revisions?project_id=${session.project}`);
    if (S.editSession !== session || key !== workspaceKey()) return;
    $("#editor-history-list").innerHTML = history.map(v => `<details class="revision-item"><summary>版本 ${v.revision} · ${esc(v.reason)} · ${date(v.created_at)}</summary><h4>${esc(v.data.title)}</h4><p>${esc(v.data.body)}</p>${!readonly && v.revision !== session.revision ? `<button class="btn secondary small" type="button" data-action="restore-draft" data-revision="${v.revision}" ${session.dirty ? "disabled" : ""}>恢复此版本</button>` : ""}</details>`).join("");
  } catch (error) {
    if (S.editSession === session) $("#editor-history-list").textContent = error.message;
  }
}
async function saveDraftEdit(restoreRevision) {
  const session = S.editSession;
  if (!session || session.key !== workspaceKey() || session.saving) return;
  if (restoreRevision !== undefined && session.dirty) throw new Error("请先保存当前修改，再恢复历史版本");
  const form = $("#draft-editor");
  const changes = editorValues();
  session.saving = true;
  form.querySelector("fieldset").disabled = true;
  $$(".draft-editor-dialog button").forEach(el => { el.disabled = true; });
  try {
    const result = await post(`/api/creations/${session.id}/${restoreRevision === undefined ? "edit" : "restore"}`, {project_id: session.project, revision: session.revision, ...(restoreRevision === undefined ? {changes} : {restore_revision: restoreRevision})});
    const cached = editStore.read(session.storageKey);
    if (!cached || (cached.revision === session.revision && CreationTools.fingerprint(cached.changes) === CreationTools.fingerprint(changes))) editStore.remove(session.storageKey);
    if (session.key !== workspaceKey()) return;
    const c = S.workspace.creations.find(x => x.id === session.id);
    if (c) { c.data = result.data; c.revision = result.revision; }
    render();
    if (S.editSession === session) await openDraftEditor(session.id);
    toast(restoreRevision === undefined ? "修改已保存，可继续复制或制作封面" : "历史版本已恢复，原有版本仍保留");
  } catch (error) {
    if (S.editSession === session) {
      showFormError(form, error.message);
      form.querySelector(".editor-reload").hidden = false;
    }
  } finally {
    session.saving = false;
    if (S.editSession === session) {
      form.querySelector("fieldset").disabled = session.readonly;
      $$(".draft-editor-dialog button").forEach(el => { el.disabled = false; });
      updateEditorPreview();
    }
  }
}

function resultSummary(c) {
  const r = c.results || {};
  const metrics = [["views", "浏览"], ["leads", "有效咨询"], ["orders", "订单"]];
  return `<div class="result-summary"><span>${metrics.map(([key, label]) => `${label} ${r[key] ?? "—"}`).join(" · ")}</span><button class="text-btn" data-action="record-results" data-id="${c.id}">记录效果</button></div>`;
}

function accounts() {
  return S.workspace.assets.filter((a) => a.kind === "账号");
}
function firstHourLeft(t) {
  if (t.status !== "published" || !t.published_at) return null;
  return 60 - Math.floor((Date.now() - new Date(t.published_at).getTime()) / 60000);
}
function checklistDone(t) {
  const k = t.checklist || {};
  return k.pinned && k.knowledge && k.atmosphere;
}
function stageOf(c) {
  const t = c.tracking || {};
  if (t.status !== "published") return "draft";
  const left = firstHourLeft(t);
  if (c.data.comment_layout && left !== null && left > 0 && !checklistDone(t))
    return "firsthour";
  return "published";
}
function productionBoard(items) {
  if (!items.length) return "";
  const count = (st) => items.filter((c) => stageOf(c) === st).length;
  const published = items.length - count("draft");
  const real = items.filter((c) => !c.data.demo);
  const recorded = real.filter((c) => ["views", "leads", "orders"].some((key) => c.results?.[key] != null));
  const total = (key) => {
    const known = recorded.filter((c) => c.results?.[key] != null);
    return known.length ? known.reduce((n, c) => n + c.results[key], 0) : "—";
  };
  const accs = accounts();
  const chips = [
    ["all", "全部", items.length],
    ["draft", "待发布", count("draft")],
    ["published", "已发布", published],
    ["firsthour", "第一小时进行中", count("firsthour")],
  ];
  const stage = S.stage || "all";
  return `<section class="panel board"><details class="board-overview"><summary>发布与效果 · 已发布 ${published} 条 · ${recorded.length} 条已记录效果</summary><div class="board-stats"><div><p>已发布内容</p><strong>${published}<small> / ${items.length}</small></strong></div><div><p>浏览次数</p><strong>${total("views")}</strong></div><div><p>有效咨询</p><strong>${total("leads")}</strong></div><div><p>订单数</p><strong>${total("orders")}</strong></div></div><p class="board-hint">${recorded.length} 条正式内容已记录效果 · 手动累计数据，未记录显示 —，演示内容不计入效果。</p>${accs.length ? `<div class="board-accounts"><span>账号矩阵</span>${accs.map((a) => { const mine = items.filter((c) => c.tracking?.account_id === a.id); return `<span class="acc">${esc(a.name)}<small>已发 ${mine.filter((c) => c.tracking.status === "published").length}</small></span>`; }).join("")}</div>` : `<p class="board-hint">在「项目资料」里添加类型为「账号」的资料，就能区分不同账号发布的内容。</p>`}</details><div class="stage-chips">${chips.map(([id, label, n]) => `<button class="chip ${stage === id ? "active" : ""}" data-action="stage" data-stage="${id}">${label} ${n}</button>`).join("")}</div></section>`;
}
function pipeline(c, source) {
  const t = c.tracking || { status: "draft" };
  const acc = accounts().find((a) => a.id === t.account_id);
  if (t.status !== "published")
    return `<div class="pipeline"><div class="pipeline-head"><span class="stage-pill">待发布</span><button class="text-btn" data-action="publish" data-id="${c.id}">${icon("check")} 已在平台发布</button></div></div>`;
  const left = firstHourLeft(t);
  const k = t.checklist || {};
  const items = [
    ["pinned", "重要说明已置顶"],
    ["knowledge", "常见问题已回复"],
    ["atmosphere", "互动提问已回复"],
  ];
  return `<div class="pipeline"><div class="pipeline-head"><span class="stage-pill live">已发布${acc ? " · " + esc(acc.name) : ""} · ${date(t.published_at)}</span><span class="pipeline-actions"><button class="text-btn muted-btn" data-action="unpublish" data-id="${c.id}">撤回</button></span></div>${c.data.comment_layout ? `<div class="first-hour"><p><strong>第一小时评论</strong> ${left > 0 ? `还剩 ${left} 分钟` : "已过第一小时"}${checklistDone(t) ? " · 已完成" : ""}</p>${items.map(([key, label]) => `<label class="check-row"><input type="checkbox" data-action="check-item" data-id="${c.id}" data-key="${key}" ${k[key] ? "checked" : ""}>${label}</label>`).join("")}</div>` : ""}</div>`;
}
async function track(id, data) {
  const r = await post("/api/tracking/" + id, body(data));
  const c = S.workspace.creations.find((x) => x.id === id);
  if (c) c.tracking = r;
  render();
  return r;
}
function briefOf(id) {
  return (S.workspace.briefs || []).find((b) => b.id === id);
}
function sourceOf(id) {
  return id ? S.workspace.sources.find((s) => s.id === id) : null;
}
function sourcePanel(s) {
  return `<section class="panel brief-panel"><div class="brief-head"><div><p class="eyebrow">再创作 · ${s.platform === "douyin" ? "抖音" : "小红书"}</p><h2>${esc(s.data.title || "参考内容")}</h2></div><div class="actions">${button("再来一批", "create-again", "primary small", "spark", `data-id="${s.id}"`)}${button("回到拆解", "open-source", "secondary small", "back", `data-id="${s.id}"`)}</div></div><p class="muted">再来一批沿用上次的目标、资料与尚未过期的临时资料；想换资料或要求，回到拆解页填写。预计消耗 ${S.boot.rules.create} 积分，失败自动退还。</p></section>`;
}
function briefPanel(b) {
  const bm = b.data.benchmark || {};
  const examples = (bm.examples || [])
    .map((e) => `<li>${esc(e.title || "（无标题）")}<small>${fmt(e.likes)} 赞 · ${fmt(e.saves)} 收藏</small></li>`)
    .join("");
  return `<section class="panel brief-panel"><div class="brief-head"><div><p class="eyebrow">自主创作 · ${b.platform === "douyin" ? "抖音" : "小红书"}</p><h2>${esc(b.data.topic)}</h2></div>${button("再来一批", "original-again", "primary small", "spark", `data-id="${b.id}"`)}</div><p class="muted">使用了本次提供的业务资料（其中 ${(b.data.assets || []).length} 份来自已保存资料）${b.data.requirements ? " · 有本次要求" : ""}。再来一批沿用目标、资料及尚未过期的临时资料。资料已过期时，请重新补充。</p>${bm.note ? `<div class="notice">${esc(bm.note)}</div>` : ""}${examples ? `<details class="brief-bench"><summary>赛道参考：「${esc(bm.keyword || "")}」候选 ${bm.pool} 条，互动中位数 ${bm.baseline != null ? fmt(Math.round(bm.baseline)) : "—"}；只用来看写法</summary><ul>${examples}</ul></details>` : ""}</section>`;
}
async function startOriginal(briefId) {
  const operationKey = workspaceKey();
  if (S.busy) return;
  if (S.imageUploading) throw new Error("图片正在上传，请完成后再生成");
  const again = !!briefId;
  if (!again) {
    S.original = {
      goal: $("#original-goal").value,
      platform: $("#original-platform").value,
      topic: $("#original-topic").value.trim(),
      keyword: $("#original-keyword").value.trim(),
      assets: $$("input[name=original-asset]:checked").map((x) => x.value),
      requirements: $("#original-requirements").value,
      temporary: $("#original-temporary").value,
    };
    saveDraft();
    if (S.original.topic.length < 2) throw new Error("请填写创作主题");
    if (!S.original.assets.length && !S.original.temporary.trim())
      throw new Error("请粘贴业务资料，或勾选一份已保存的资料");
  }
  S.busy = true;
  render();
  try {
    const r = await post(
      "/api/original",
      body(
        again
          ? { brief_id: briefId }
          : {
              goal: S.original.goal,
              platform: S.original.platform,
              topic: S.original.topic,
              keyword: S.original.keyword,
              assets: S.original.assets,
              requirements: S.original.requirements,
              temporary: S.original.temporary,
            },
      ),
    );
    toast("正在根据你的资料写内容，可在任务记录查看进度…");
    if (operationKey !== workspaceKey()) return;
    await poll(r.task_ids, async (success) => {
      S.creationSource = r.brief_id;
      S.page = "creations";
      location.hash = "creations";
      render();
      let count = "6 到 8";
      try {
        count = JSON.parse(success[0].result).creation_ids.length;
      } catch (err) {}
      toast(`${count} 条自主创作稿件已生成`);
      saveDraft();
    });
  } catch (e) {
    if (operationKey !== workspaceKey()) return;
    S.busy = false;
    render();
    toast(e.message);
  }
}
function analyzeEstimate() {
  const unit = S.boot.rules.analyze;
  if (S.entry === "batch") {
    const n = Math.max(1, S.entryText.split("\n").filter((x) => x.trim()).length);
    return `预计 ${unit * n} 积分 · 逐条结算 · 失败自动退还`;
  }
  if (S.entry === "creator" || S.entry === "keyword") {
    const n = S.boot.discover_pick || 3;
    return `最多 ${unit * n} 积分 · 按相对表现精选 ${n} 条，逐条结算，未完成的退还`;
  }
  return `预计 ${unit} 积分 · 失败自动退还`;
}
function safeImage(url) {
  return /^(https:\/\/|data:image\/(png|jpeg|webp|svg\+xml);base64,)/.test(
    url || "",
  )
    ? url
    : "";
}
function assets() {
  return (
    heading(
      "让 AI 更了解你的品牌",
      "沉淀品牌、产品和受众信息。创作时按需选择，让表达有据可依。",
      button("添加资料", "new-asset", "primary", "plus"),
      "YOUR BRAND, IN CONTEXT",
    ) +
    (S.workspace.assets.length
      ? `<div class="asset-grid">${S.workspace.assets.map((a) => `<article class="asset-card"><span class="status">${esc(a.kind)}</span><h3>${esc(a.name)}</h3>${a.kind === "图片" ? `<img src="${esc(safeImage(a.content))}" alt="${esc(a.name)}">` : `<p>${esc(a.content)}</p>`}<div class="actions">${button("编辑 / 替换", "edit-asset", "secondary small", "edit", `data-id="${a.id}"`)}${button("删除", "delete-asset", "small", "trash", `data-id="${a.id}"`)}</div></article>`).join("")}</div>`
      : empty(
          "把品牌资料放进来",
          "添加品牌介绍、产品卖点、受众画像或禁用词，<br>创作时选择使用，资料不会自动全选。",
          button("添加第一份资料", "new-asset", "primary", "plus"),
        ))
  );
}
const states = {
  PENDING: "排队中",
  FETCHING: "获取内容",
  PROCESSING: "处理中",
  ANALYZING: "拆解中",
  GENERATING: "生成中",
  SUCCEEDED: "已完成",
  FAILED: "失败 · 已退款",
  PARTIAL: "部分完成",
  CANCELLED: "已取消",
};
const skillStates = {
  Draft: "草稿",
  Test: "测试中",
  Published: "生效中",
  Archived: "已归档",
};
function tasks() {
  const items = S.tasks.filter((t) => t.project_id === S.project);
  return (
    heading(
      "每一份灵感，都有迹可循",
      "查看任务进度、处理结果与消耗。失败任务会自动退回积分。",
      button("刷新", "refresh", "secondary", "refresh"),
      "TASK HISTORY",
    ) +
    (items.length
      ? `<div class="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>积分</th><th>时间</th><th>结果</th></tr></thead><tbody>${items.map((t) => `<tr><td>${{ analyze: "参考内容拆解", create: "再创作 · 6 到 8 条稿件", original: "自主创作 · 6 到 8 条稿件", cover: "封面生成" }[t.kind]}</td><td><span class="status ${t.state === "FAILED" ? "failed" : ["SUCCEEDED", "PARTIAL"].includes(t.state) ? "" : "pending"}" title="${esc(t.state === "PARTIAL" ? t.error || "" : "")}">${states[t.state] || t.state}</span></td><td>${t.cost}</td><td>${date(t.created_at)}</td><td>${t.error && t.state !== "PARTIAL" ? `<span title="${esc(t.error)}">${esc(t.error.slice(0, 40))}</span>` : ["SUCCEEDED", "PARTIAL"].includes(t.state) ? `<button class="text-btn" data-action="task-result" data-id="${t.id}">查看结果 ${icon("arrow")}</button>` : t.state === "CANCELLED" ? "—" : button("取消任务", "cancel-task", "secondary small", "close", `data-id="${t.id}"`)}</td></tr>`).join("")}</tbody></table></div>`
      : empty("还没有任务", "从一条参考链接开始，任务进度会显示在这里。"))
  );
}
function credits() {
  return (
    heading(
      "积分与使用记录",
      "生成前可查看费用；成功后扣除，失败或取消会退回。",
      "",
      "CREDIT ACCOUNT",
    ) +
    `<div class="summary-strip"><div><p>当前可用积分</p><strong>${S.boot.credits.balance}</strong></div><div><p>正在冻结</p><strong>${S.boot.credits.frozen}</strong></div><div><p>创作一批内容</p><strong>${originalCost()}<small style="font-size:12px"> 积分</small></strong></div></div><div class="notice">暂不支持在线充值，积分由管理员发放。已完成稿件的主动删除不会退还积分；封面生成单独计费，每次 ${S.boot.rules.cover} 积分。</div><p class="hint">提交时预留积分，成功后确认扣除；结算行显示 0 表示没有再次扣款。</p><div id="ledger">${S.ledger ? ledgerTable() : '<div class="loading-line"><span class="spinner"></span>读取积分流水…</div>'}</div>`
  );
}
function ledgerTable() {
  return `<div class="table-wrap"><table><thead><tr><th>流水说明</th><th>类型</th><th>可用积分变动</th><th>时间</th></tr></thead><tbody>${S.ledger.map((l) => `<tr><td>${esc(l.description.replace(/\b(original|create|analyze|cover)\b/g, key => ({original:"内容创作",create:"参考改写",analyze:"内容拆解",cover:"封面生成"})[key]))}</td><td>${{ GRANT: "发放", DEDUCT: "扣减", FREEZE: "冻结", REFUND: "退回", SETTLE: "结算" }[l.kind] || l.kind}</td><td style="color:${l.amount > 0 ? "#718d42" : "inherit"}">${l.amount > 0 ? "+" : ""}${l.amount}</td><td>${date(l.created_at)}</td></tr>`).join("")}</tbody></table></div>`;
}
function admin() {
  if (S.boot.user.role !== "admin")
    return empty("无管理权限", "请使用管理员邮箱登录。");
  if (!S.admin)
    return '<div class="loading-line"><span class="spinner"></span>加载管理配置…</div>';
  return (
    heading(
      "DAOLOOK 管理后台",
      "管理服务配置、用户积分、任务与创作规则。",
      "",
      "SYSTEM ADMINISTRATION",
    ) +
    `<div class="admin-tabs">${[
      ["config", "服务配置"],
      ["models", "模型路由"],
      ["users", "用户与积分"],
      ["tasks", "任务管理"],
      ["skills", "Skill 版本"],
    ]
      .map(
        ([id, label]) =>
          `<button class="chip ${S.adminTab === id ? "active" : ""}" data-admin-tab="${id}">${label}</button>`,
      )
      .join("")}</div>` +
    adminBody()
  );
}
function adminBody() {
  const a = S.admin,
    c = a.config;
  if (S.adminTab === "models")
    return `<div class="admin-grid"><section class="panel"><h2>模型供应商</h2><p class="muted">默认供应商在服务配置中维护；可添加其他供应商作为主模型或备用。</p><div class="actions" style="margin:20px 0">${button("添加供应商", "new-provider", "primary small", "plus")}</div>${a.providers.map((p) => `<div class="asset-card" style="margin-top:12px"><span class="status">${p.enabled ? "已启用" : "已停用"}</span><h3>${esc(p.name)}</h3><p>${esc(p.base_url)}</p><div class="actions">${button("编辑", "edit-provider", "secondary small", "edit", `data-id="${p.id}"`)}${button("测试 / 同步", "test-provider", "secondary small", "refresh", `data-id="${p.id}"`)}</div></div>`).join("")}</section><section class="panel"><h2>按任务配置主备模型</h2><form id="routes-form">${["analyze", "create", "cover"].map((kind) => `<h3 style="font-size:14px;margin:18px 0">${{ analyze: "内容拆解", create: "再创作", cover: "封面生成" }[kind]}</h3>${["primary", "backup"].map((pos) => `<label class="field"><span>${pos === "primary" ? "主" : "备用"}供应商</span><select id="route-${kind}-${pos}-provider">${[{ id: "default", name: "默认供应商" }, ...a.providers].map((p) => `<option value="${p.id}" ${a.routes[kind][pos].provider === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>${field("模型 ID（留空继承默认配置）", `route-${kind}-${pos}-model`, a.routes[kind][pos].model)}`).join("")}`).join("")}<button class="btn primary full" type="submit">保存路由</button></form></section></div>`;
  if (S.adminTab === "users")
    return `<div class="table-wrap"><table><thead><tr><th>邮箱</th><th>角色</th><th>可用 / 冻结</th><th>操作</th></tr></thead><tbody>${a.users.map((u) => `<tr><td>${esc(u.email)}</td><td>${u.role}</td><td>${u.balance} / ${u.frozen}</td><td>${button("调整积分", "grant", "secondary small", "coin", `data-id="${u.id}" data-balance="${u.balance}" data-email="${esc(u.email)}"`)} ${button("查看流水", "user-ledger", "secondary small", "clock", `data-id="${u.id}"`)} ${button("重置密码", "reset-password", "secondary small", "edit", `data-id="${u.id}"`)}</td></tr>`).join("")}</tbody></table></div>`;
  if (S.adminTab === "tasks")
    return `<div class="table-wrap"><table><thead><tr><th>任务 ID</th><th>类型</th><th>状态 / 错误</th><th>操作</th></tr></thead><tbody>${a.tasks.map((t) => `<tr><td>${t.id.slice(0, 10)}</td><td>${t.kind}</td><td>${states[t.state]} ${esc(t.error || "")}</td><td>${t.state === "FAILED" ? button("重试（重新计费）", "retry", "secondary small", "refresh", `data-id="${t.id}"`) : "—"}</td></tr>`).join("")}</tbody></table></div>`;
  if (S.adminTab === "skills")
    return `<div class="actions" style="margin-bottom:20px">${button("创建 Skill 草稿", "new-skill", "primary", "plus")}</div><div class="notice">每类任务只有一条「生效中」的 Prompt，真实拆解与创作只读它。要改 Prompt 就点「编辑为新版本」：保存草稿 → 测试 → 发布，发布即替换生效版本（旧版转为已归档）。</div><div class="asset-grid">${a.skills.map((s) => `<article class="asset-card"><span class="status">${skillStates[s.status] || s.status}</span><h3>${esc(s.name)} · v${s.version}</h3><details class="skill-prompt"><summary>查看完整 Prompt</summary><pre>${esc(s.prompt)}</pre></details><div class="actions">${button("编辑为新版本", "edit-skill", "secondary small", "edit", `data-id="${s.id}"`)}${button("复制", "copy-skill", "secondary small", "copy", `data-id="${s.id}"`)}${s.status === "Draft" ? button("测试", "test-skill", "secondary small", "check", `data-id="${s.id}"`) : s.status === "Test" ? button("发布", "publish-skill", "primary small", "check", `data-id="${s.id}"`) : s.status === "Archived" ? button("回滚至此版本", "publish-skill", "primary small", "check", `data-id="${s.id}"`) : ""}</div></article>`).join("")}</div>`;
  return `<form id="config-form"><div class="admin-grid"><section class="panel"><h2>模型供应商</h2>${field("Base URL", "provider-base", c.provider.base_url)}${field("API Key", "provider-key", c.provider.api_key, "password")}${field("主文本模型", "provider-model", c.provider.model)}${field("备用文本模型", "provider-backup", c.provider.backup_model)}${field("封面模型", "provider-image", c.provider.image_model)}${field("口播转写模型（可选，兼容 /audio/transcriptions）", "provider-transcribe", c.provider.transcribe_model || "")}<label class="check-row"><input type="checkbox" id="provider-enabled" ${c.provider.enabled ? "checked" : ""}>启用模型服务</label><div class="actions" style="margin-top:15px">${button("连接测试 / 同步模型", "test-model", "secondary small", "refresh")}</div><div id="model-list" class="hint" hidden></div></section><section class="panel"><h2>TikHub 数据源</h2>${field("Base URL", "tikhub-base", c.tikhub.base_url)}${field("API Key", "tikhub-key", c.tikhub.api_key, "password")}<label class="field"><span>平台端点映射（JSON）</span><textarea id="endpoints" rows="12">${esc(JSON.stringify(c.tikhub.endpoints, null, 2))}</textarea></label><div class="hint">小红书使用 App V2 系列；请按账号实际可用接口配置抖音端点。服务保存后再测试。</div>${button("测试参考链接", "test-tikhub", "secondary small", "link")}</section><section class="panel"><h2>积分与系统</h2><label class="field"><span>运行模式</span><select id="run-mode"><option value="demo" ${c.mode === "demo" ? "selected" : ""}>演示模式</option><option value="live" ${c.mode === "live" ? "selected" : ""}>真实服务</option></select></label>${field("拆解积分", "cost-analyze", c.rules.analyze, "number")}${field("再创作积分", "cost-create", c.rules.create, "number")}${field("封面积分", "cost-cover", c.rules.cover, "number")}${field("自主创作积分", "cost-original", c.rules.original ?? c.rules.create, "number")}${field("批量上限", "batch-limit", c.limits.batch, "number")}${field("请求超时（秒）", "timeout", c.limits.timeout, "number")}${field("模型重试次数", "retries", c.limits.retries ?? 1, "number")}${field("临时资料保留时长（小时）", "temporary-ttl", c.limits.temporary_ttl_hours ?? 24, "number")}${field("博主/关键词精选条数", "discover-pick", c.limits.discover_pick ?? 3, "number")}</section><section class="panel"><h2>邮件服务（验证码）</h2><label class="check-row"><input type="checkbox" id="mail-enabled" ${c.mail?.enabled ? "checked" : ""}>启用：注册需验证邮箱，支持找回密码</label>${field("SMTP 地址", "mail-host", c.mail?.host || "")}${field("端口", "mail-port", c.mail?.port ?? 465, "number")}<label class="field"><span>加密方式</span><select id="mail-security"><option value="ssl" ${c.mail?.security !== "starttls" ? "selected" : ""}>SSL（通常 465）</option><option value="starttls" ${c.mail?.security === "starttls" ? "selected" : ""}>STARTTLS（通常 587）</option></select></label>${field("用户名", "mail-user", c.mail?.username || "")}${field("密码 / 授权码", "mail-password", c.mail?.password || "", "password")}${field("发件人", "mail-sender", c.mail?.sender || "")}<div class="actions" style="margin-top:15px">${button("发送测试邮件", "test-mail", "secondary small", "check")}</div><div class="hint">未启用时，注册不校验邮箱，找回密码需由管理员在「用户」里重置。</div></section><section class="panel"><h2>注册与白名单</h2><label class="check-row"><input type="checkbox" id="signup-whitelist" ${c.signup?.whitelist ? "checked" : ""}>开启注册白名单：只有名单内邮箱可以注册</label><label class="field"><span>白名单邮箱 <small style="display:inline;font-weight:400">每行一个，也可用逗号分隔</small></span><textarea id="signup-emails" rows="8" placeholder="name@example.com">${esc((c.signup?.emails || []).join("\n"))}</textarea></label>${field("新用户赠送积分", "signup-welcome", c.signup?.welcome_credits ?? 100, "number")}<div class="hint">白名单只限制新注册，已注册的用户不受影响；.env 里的管理员邮箱始终可以注册。赠送积分只对之后注册的新用户生效，设为 0 则不赠送。</div></section><section class="panel"><h2>内容排序权重</h2><label class="field"><span>评分权重（JSON）</span><textarea id="ranking" rows="10">${esc(JSON.stringify(c.ranking, null, 2))}</textarea></label><div class="hint">缺少真实账号近期样本和赛道中位数时，不展示未经验证的异常爆款结论。正式排序需用真实样本校准。</div></section></div><button class="btn primary" type="submit" style="margin-top:25px">${icon("check")}保存配置</button></form>`;
}
function field(label, id, value = "", type = "text") {
  return `<label class="field"><span>${label}</span><input id="${id}" type="${type}" value="${esc(value)}" ${type === "number" ? 'min="0" step="any"' : ""}></label>`;
}
function skillModal(name = "xhs_analysis", prompt = "", title = "创建 Skill 草稿") {
  modal(
    title,
    `<p class="subtext">保存会生成新的 Draft 版本，不会改动当前生效版本。结构测试通过后发布，发布即替换生效版本。</p><form id="skill-form"><label class="field"><span>任务类型</span><select id="skill-name">${["xhs_analysis", "douyin_analysis", "xhs_creation", "douyin_creation", "xhs_original", "douyin_original"].map((n) => `<option ${n === name ? "selected" : ""}>${n}</option>`).join("")}</select></label><label class="field"><span>Skill / Prompt</span><textarea id="skill-prompt" rows="12" required placeholder="输入平台拆解或创作规则…">${esc(prompt)}</textarea></label><button class="btn primary full" type="submit">保存草稿</button></form>`,
    true,
  );
}
async function coverStudio(id, saved) {
  const plan = await post("/api/cover/plan", body({ creation_id: id }));
  S.coverId = id;
  S.coverBrief = structuredClone(saved || plan.brief);
  const b = S.coverBrief;
  const photos = S.workspace.assets.filter((a) => a.kind === "图片");
  modal(
    "封面工作台",
    `<p class="subtext">先让标题被看见，再让内容被记住。免费预览 · 保存 ${S.boot.rules.cover} 积分</p>
  <div class="cover-studio"><div class="cover-controls">
  <div class="cover-options">${plan.styles.map((s) => `<button type="button" class="cover-option ${b.style === s.id ? "selected" : ""}" data-action="cover-style" data-style="${s.id}"><small>0${plan.styles.indexOf(s) + 1}${plan.recommended === s.id ? " · 推荐" : ""}</small><strong>${esc(s.name)}</strong><span>${esc(s.reason)}</span></button>`).join("")}</div>
  <p class="muted">${esc(plan.reason)} 当前标题切入点：${esc(plan.hook)}。</p>
  <label class="field"><span>主标题 <small>最多 36 字</small></span><textarea id="cover-title" rows="2" maxlength="36">${esc(b.title)}</textarea></label>
  <label class="field"><span>副标题 · 可选</span><textarea id="cover-subtitle" rows="2" maxlength="48">${esc(b.subtitle)}</textarea></label>
  <label class="field" id="cover-points-field" ${b.style !== "method" ? "hidden" : ""}><span>方法清单 · 可选，每行一项，最多 3 项</span><textarea id="cover-points" rows="3" placeholder="填写稿件里已经验证的方法">${esc((b.points || []).join("\n"))}</textarea></label>
  <label class="field"><span>品牌署名 · 可选</span><input id="cover-brand" maxlength="20" value="${esc(b.brand)}"></label>
  <div class="cover-photo-fields"><label class="field"><span>项目图片</span><select id="cover-asset"><option value="">不使用图片</option>${photos.map((a) => `<option value="${a.id}" ${b.asset_id === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>
  <label class="field"><span>图片裁切</span><select id="cover-crop">${[
    ["center", "居中"],
    ["top", "保留上方"],
    ["bottom", "保留下方"],
  ]
    .map(
      ([k, v]) =>
        `<option value="${k}" ${b.crop === k ? "selected" : ""}>${v}</option>`,
    )
    .join("")}</select></label></div>
  <label class="field"><span>直接上传产品图 / 个人 IP 图</span><input type="file" id="cover-photo-file" accept="image/png,image/jpeg,image/webp"><small>上传后保存到项目并用于当前封面，每张最多 2 MB。</small></label>
  <p class="muted">图片保持原貌，只做版式裁切；文字与照片分开排版。真人方向请使用本人或已获授权的照片，当前不自动抠图。</p>
  </div><div class="cover-preview-pane"><div class="cover-preview-label"><span>实时预览</span><button class="text-btn" data-action="cover-thumbnail">查看信息流缩略图</button></div><div id="cover-preview" aria-live="polite">正在排版…</div><div id="cover-validation" aria-live="polite"></div>
  ${button("保存新封面", "generate-cover", "primary full", "image", "disabled")}<p class="muted">不覆盖已有版本。所有中文直接排版，无需图像模型。</p></div></div>`,
    true,
  );
  $(".dialog").classList.add("cover-dialog");
  await previewCover();
}
function readCoverBrief() {
  return {
    ...S.coverBrief,
    title: $("#cover-title").value,
    subtitle: $("#cover-subtitle").value,
    points: $("#cover-points")
      .value.split("\n")
      .filter((p) => p.trim()),
    brand: $("#cover-brand").value,
    asset_id: $("#cover-asset").value,
    crop: $("#cover-crop").value,
  };
}
let coverPreviewSequence = 0,
  coverPreviewTimer;
async function previewCover() {
  if (!$("#cover-preview")) return;
  const seq = ++coverPreviewSequence;
  const brief = readCoverBrief();
  const creation = S.coverId;
  const save = $('[data-action="generate-cover"]');
  save.disabled = true;
  try {
    const p = await post(
      "/api/cover/preview",
      body({ creation_id: creation, brief }),
    );
    if (
      seq !== coverPreviewSequence ||
      !$("#cover-preview") ||
      S.coverId !== creation
    )
      return;
    $("#cover-preview").innerHTML =
      `<img src="${esc(p.url)}" alt="封面预览：${esc(brief.title)}">`;
    $("#cover-validation").innerHTML =
      `<p class="cover-checks">${p.validation.checks.map(esc).join(" · ")}</p>${p.validation.warnings.map((w) => `<p class="muted">${esc(w)}</p>`).join("")}${p.demo ? '<p class="notice">当前使用演示稿件，请替换为真实内容后发布。</p>' : ""}`;
    save.disabled = !p.validation.ready;
  } catch (e) {
    if (seq === coverPreviewSequence && $("#cover-validation")) {
      $("#cover-preview").innerHTML =
        '<div class="cover-invalid">调整文案后将重新预览</div>';
      $("#cover-validation").innerHTML =
        `<p class="inline-error">${esc(e.message)}</p>`;
    }
  }
}
document.addEventListener("input", (e) => {
  if (e.target.matches?.("#draft-editor [data-edit-field]")) updateEditorPreview();
  if (!e.target.closest(".cover-controls")) return;
  ++coverPreviewSequence;
  const save = $('[data-action="generate-cover"]');
  if (save) save.disabled = true;
  clearTimeout(coverPreviewTimer);
  coverPreviewTimer = setTimeout(previewCover, 250);
});
async function exportCover(id, format) {
  const item = S.workspace.images.find((i) => i.id === id);
  if (!item) throw new Error("封面不存在");
  const url = safeImage(item.data.url);
  if (!url) throw new Error("封面图片不存在或已失效");
  if (!url.startsWith("data:")) {
    window.open(url, "_blank", "noopener");
    toast("已打开历史图片，请在图片页面下载");
    return;
  }
  await document.fonts.ready;
  const image = new Image();
  image.src = url;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = 1080;
  canvas.height = 1440;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, 1080, 1440);
  ctx.drawImage(image, 0, 0, 1080, 1440);
  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, format === "jpg" ? "image/jpeg" : "image/png", 0.95),
  );
  if (!blob) throw new Error("图片导出失败，请重试");
  const link = document.createElement("a");
  const objectURL = URL.createObjectURL(blob);
  link.href = objectURL;
  link.download = `DAOLOOK-${id.slice(0, 8)}.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectURL), 60000);
  toast(`已导出 1080 × 1440 ${format.toUpperCase()}`);
}
function coverCard(i) {
  const d = i.data;
  return `<section class="generated-cover"><img src="${esc(safeImage(d.url))}" alt="${esc(d.brief?.title || "已生成封面")}"><p class="muted">${esc(d.brief ? { brand: "品牌杂志", method: "方法清单", portrait: "真人冲击" }[d.brief.style] : "历史封面")}${d.demo ? " · 基于演示稿件" : ""}</p><div class="actions">${button("PNG", "cover-png", "secondary small", "download", `data-id="${i.id}"`)}${button("JPG", "cover-jpg", "secondary small", "download", `data-id="${i.id}"`)}${d.brief ? button("编辑新版本", "edit-cover", "secondary small", "edit", `data-id="${i.id}"`) : ""}</div></section>`;
}

function modal(title, content, wide = false) {
  S.editSession = null;
  S.modalFocus = document.activeElement;
  $("#overlay").innerHTML =
    `<div class="overlay"><section class="dialog ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="dialog-head"><h2>${title}</h2><button class="close" data-action="close" aria-label="关闭">${icon("close")}</button></div>${content}</section></div>`;
  setTimeout(
    () =>
      $(
        ".dialog input:not([type=hidden]), .dialog textarea, .dialog button",
      )?.focus(),
    30,
  );
}
function close() {
  S.editSession = null;
  $("#overlay").innerHTML = "";
  S.modalFocus?.focus();
}
function projectsModal() {
  modal(
    "你的项目空间",
    `<p class="subtext">每个项目都有独立的参考、稿件与资料。</p>${S.boot.projects.map((p) => `<button class="project-option ${p.id === S.project ? "selected" : ""}" data-project="${p.id}">${icon("folder")}<span>${esc(p.name)}<small>${esc(p.description || "独立创作空间")}</small></span></button>`).join("")}${button("修改当前项目", "project-settings", "secondary small", "settings")}<form id="project-form" style="margin-top:24px">${field("新项目名称", "project-name")}<button class="btn primary full" type="submit">${icon("plus")}创建新项目</button></form>`,
  );
}
function assetModal(id) {
  const a = S.workspace.assets.find((a) => a.id === id);
  S.editAsset = id;
  modal(
    a ? "编辑项目资料" : "添加项目资料",
    `<form id="asset-form">${field("资料名称", "asset-name", a?.name || "")}<label class="field"><span>资料类型</span><select id="asset-kind">${["品牌资料", "产品信息", "受众画像", "禁用词", "账号", "图片", "其他"].map((k) => `<option ${a?.kind === k ? "selected" : ""}>${k}</option>`).join("")}</select></label><label class="field"><span>资料内容</span><textarea id="asset-content" rows="7" placeholder="请输入真实的品牌、产品或受众信息">${esc(a?.content || "")}</textarea></label><label class="field"><span>上传文件 · 文本 / 图片</span><input type="file" id="asset-file" accept=".txt,.md,.csv,.docx,.pdf,image/png,image/jpeg,image/webp"><small>文本、Word（.docx）、PDF 自动提取文字；文件最大 2 MB。资料不会自动在创作中全选。</small></label><button class="btn primary full" type="submit">${icon("check")}保存资料</button></form>`,
  );
}
function login(register = false, reset = false) {
  S.loginRegister = register;
  S.loginReset = reset;
  const codeField = `<label class="field"><span>邮箱验证码</span><div class="code-row"><input id="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="6 位数字"><button type="button" class="btn secondary small" data-action="send-code">发送验证码</button></div></label>`;
  const title = reset ? "找回密码" : register ? "开启你的创作空间" : "欢迎回到 DAOLOOK";
  const intro = reset
    ? "输入注册邮箱，用验证码设置新密码。"
    : register
      ? S.whitelist
        ? "目前仅限受邀邮箱注册；未开通的邮箱请联系管理员。"
        : "用邮箱创建账号，开启有依据的创作。"
      : "登录后，继续你的下一次好创作。";
  const fields =
    field("邮箱地址", "email", "", "email") +
    (reset || (register && S.mail) ? codeField : "") +
    field(reset ? "新密码（至少 8 位）" : "密码（至少 8 位）", "password", "", "password");
  const submit = reset ? "重置并登录" : register ? "创建账号" : "邮箱登录";
  const links = reset
    ? '<button class="text-btn" data-action="toggle-login">返回登录</button>'
    : `<button class="text-btn" data-action="toggle-login">${register ? "已有账号？去登录" : S.whitelist ? "受邀邮箱注册" : "还没有账号？免费注册"}</button>${register ? "" : '<button class="text-btn" data-action="forgot">忘记密码？</button>'}`;
  $("#app").innerHTML =
    `<div class="login"><section class="login-art"><div><div class="brand">DAOLOOK<span class="brand-dot">✳</span></div><div class="brand-sub">有依据 · 有灵感 · 有表达</div></div><div><h1>好内容，<br>是新灵感的<em>开始。</em></h1><p>给业务资料 → 选目标 → 拿到文案</p></div><p>YOUR NEXT GREAT IDEA STARTS HERE.</p><div class="orb"></div></section><section class="login-form"><div><h2>${title}</h2><p>${intro}</p><form id="login-form">${fields}<div id="login-error" class="inline-error"></div><button type="submit" class="btn primary full" ${reset && !S.mail ? "disabled" : ""}>${submit} ${icon("arrow")}</button></form>${reset && !S.mail ? '<p class="muted" style="margin-top:12px">管理员尚未配置邮件服务，请联系管理员重置密码。</p>' : ""}<div class="actions">${links}${S.publicMode === "demo" ? '<button class="text-btn" data-action="demo">体验演示空间 →</button>' : ""}</div></div></section></div>`;
}
async function loadPublic() {
  const pub = await api("/api/public");
  S.publicMode = pub.mode;
  S.whitelist = pub.whitelist;
  S.mail = !!pub.mail;
}
async function navigate(page) {
  const key = workspaceKey();
  S.page = page;
  S.creationSource = null;
  location.hash = page;
  render();
  if (page === "credits") {
    const ledger = await api("/api/credits");
    if (key !== workspaceKey() || S.page !== page) return;
    S.ledger = ledger;
    render();
  }
  if (page === "admin") {
    const admin = await api("/api/admin");
    if (key !== workspaceKey() || S.page !== page) return;
    S.admin = admin;
    render();
  }
  window.scrollTo({ top: 0 });
}
async function openSource(id) {
  S.detail = id;
  S.requirements = "";
  S.temporary = "";
  S.selectedAssets = [];
  S.page = "detail";
  location.hash = "detail/" + id;
  render();
  window.scrollTo({ top: 0 });
}
async function poll(ids, done) {
  S.watching = ids;
  const key = workspaceKey();
  let attempts = 0;
  const check = async () => {
    try {
      if (key !== workspaceKey() || S.watching !== ids) return;
      const tasks = await api('/api/tasks');
      if (key !== workspaceKey() || S.watching !== ids) return;
      S.tasks = tasks;
      const relevant = S.tasks.filter((t) => ids.includes(t.id));
      if (
        relevant.length === ids.length &&
        relevant.every((t) =>
          ["SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"].includes(t.state),
        )
      ) {
        await refresh();
        if (key !== workspaceKey() || S.watching !== ids) return;
        S.watching = null;
        S.busy = false;
        render();
        const success = relevant.filter((t) =>
          ["SUCCEEDED", "PARTIAL"].includes(t.state),
        );
        if (success.length) await done(success);
        const partial = relevant.filter((t) => t.state === "PARTIAL");
        if (partial.length) toast(`部分完成：${partial[0].error}`);
        const failed = relevant.filter((t) => t.state === "FAILED");
        if (failed.length)
          toast(`${failed.length} 个任务失败，积分已退回：${failed[0].error}`);
        return;
      }
      if (S.page === "tasks") render();
      if (++attempts > 180) {
        S.busy = false;
        toast("任务仍在后台处理中，可在任务记录查看");
        render();
        return;
      }
      setTimeout(check, 1500);
    } catch (e) {
      if (key !== workspaceKey() || S.watching !== ids) return;
      S.busy = false;
      toast("暂时无法查询进度；任务仍在后台，可到任务记录查看。");
      render();
    }
  };
  setTimeout(check, 500);
}
async function startAnalyze() {
  const operationKey = workspaceKey();
  const text = $("#reference").value.trim();
  if (!text) {
    toast("请先输入参考链接或关键词");
    return;
  }
  S.entryText = text;
  const transcript = $("#transcript")?.value.trim() || "";
  S.transcript = transcript;
  S.busy = true;
  const platform = $("#keyword-platform")?.value || "xhs";
  render();
  try {
    const r = await post(
      "/api/analyze",
      body({
        entry: S.entry,
        text,
        platform,
        transcript,
      }),
    );
    toast("拆解已开始，可在任务记录查看进度");
    if (operationKey !== workspaceKey()) return;
    await poll(r.task_ids, async (tasks) => {
      const ids = tasks.flatMap((t) => JSON.parse(t.result).source_ids || []);
      S.entryText = "";
      if (ids.length === 1) await openSource(ids[0]);
      else {
        S.filter = "全部";
        S.platform = "all";
        await navigate("discover");
        toast(`已完成 ${ids.length} 条内容拆解，请浏览后按需保存`);
      }
    });
  } catch (e) {
    if (operationKey !== workspaceKey()) return;
    S.busy = false;
    render();
    toast(e.message);
  }
}
async function startCreate(againId) {
  const operationKey = workspaceKey();
  if (S.busy) return;
  const sourceId = againId || S.detail;
  if (!againId) {
    if (S.imageUploading) throw new Error("图片正在上传，请完成后再生成");
    S.requirements = $("#requirements").value;
    S.temporary = $("#temporary").value;
    S.selectedAssets = $$("input[name=asset]:checked").map((x) => x.value);
  }
  S.busy = true;
  render();
  try {
    const r = await post(
      "/api/create",
      body(
        againId
          ? { source_id: againId, again: true }
          : {
              goal: S.goal,
              source_id: sourceId,
              requirements: S.requirements,
              temporary: S.temporary,
              assets: S.selectedAssets,
            },
      ),
    );
    toast("正在创作 6 到 8 条独立稿件…");
    if (operationKey !== workspaceKey()) return;
    await poll(r.task_ids, async (success) => {
      S.creationSource = sourceId;
      S.page = "creations";
      location.hash = "creations";
      render();
      let count = "6 到 8";
      try {
        count = JSON.parse(success[0].result).creation_ids.length;
      } catch (err) {}
      toast(`${count} 条新稿件已追加，历史版本完整保留`);
      if (!againId && S.temporary.trim())
        modal(
          "保存本次临时资料？",
          `<p class="subtext">这份资料可以留作下一次创作的参考，也可以仅用于本次任务。</p>${field("资料名称", "temporary-name", "本次创作补充资料")}<div class="actions">${button("保存到项目", "save-temporary", "primary", "folder")}${button("仅本次使用", "close", "secondary")}</div>`,
        );
    });
  } catch (e) {
    if (operationKey !== workspaceKey()) return;
    S.busy = false;
    render();
    toast(e.message);
  }
}
async function mutate(path, method, data) {
  await api(path, { method, body: JSON.stringify(body(data)) });
  await refresh();
  render();
}
function providerModal(id) {
  const p = S.admin.providers.find((x) => x.id === id) || {};
  S.providerId = p.id;
  modal(
    p.id ? "编辑供应商" : "添加供应商",
    `<form id="provider-form">${field("供应商名称", "extra-provider-name", p.name || "")}${field("Base URL", "extra-provider-base", p.base_url || "https://")}${field("API Key", "extra-provider-key", p.api_key || "", "password")}<label class="check-row"><input type="checkbox" id="extra-provider-enabled" ${p.enabled !== 0 ? "checked" : ""}>启用供应商</label><button class="btn primary full" style="margin-top:20px" type="submit">保存供应商</button></form>`,
  );
}
const actions = {
  "edit-draft": el => openDraftEditor(el.dataset.id),
  "restore-draft": el => saveDraftEdit(Number(el.dataset.revision)),
  "copy-editor": async () => {
    await navigator.clipboard.writeText(CreationTools.publicCopy(editorValues()));
    toast("当前正文已复制，请核对业务信息后发布");
  },
  "download-editor": () => {
    const text = CreationTools.publicCopy(editorValues());
    const url = URL.createObjectURL(new Blob([text], {type:"text/plain;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url; link.download = "DAOLOOK-正文.txt"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("正文已下载");
  },
  "latest-draft": async () => {
    const session = S.editSession;
    if (!session) return;
    await refresh();
    if (S.editSession !== session || workspaceKey() !== session.key) return;
    editStore.remove(session.storageKey);
    await openDraftEditor(session.id);
  },
  "editor-cover": async () => {
    const session = S.editSession;
    if (!session) return;
    if (session.dirty) {
      await saveDraftEdit();
      if (S.editSession?.dirty || S.editSession?.id !== session.id) return;
    }
    if (workspaceKey() !== session.key) return;
    await actions.cover({dataset:{id:session.id}});
  },
  "improve-draft": async (el) => {
    const c = S.workspace.creations.find((x) => x.id === el.dataset.id);
    const brief = briefOf(c.source_id);
    if (brief) {
      S.original = { goal: c.data.goal || "leads", platform: brief.platform,
        topic: brief.data.topic, keyword: brief.data.keyword || "",
        assets: (brief.data.assets || []).filter((id) => S.workspace.assets.some((a) => a.id === id)),
        requirements: brief.data.requirements || "", temporary: "" };
      S.entry = "original";
      await navigate("discover");
      $("#original-temporary")?.focus();
    } else {
      await openSource(c.source_id);
      S.goal = c.data.goal || "leads";
      render();
      $("#temporary")?.focus();
    }
    toast("补充真实资料后重新生成，原稿会保留");
  },
  "record-results": (el) => {
    const c = S.workspace.creations.find((x) => x.id === el.dataset.id);
    const r = c.results || {};
    S.resultsId = c.id;
    modal("这条内容带来了什么？", `<form id="results-form"><p class="subtext">填写截至目前的累计数据。不知道的留空，确实没有填 0。有效咨询指目标客户提出了具体需求。记录发布状态后，下次创作会参考同平台、同目标的结果。</p>${[["views", "浏览次数"], ["leads", "有效咨询人数"], ["orders", "订单数"], ["spend", "推广花费（元）"]].map(([key, label]) => `<label class="field"><span>${label}</span><input type="number" id="result-${key}" min="0" max="1000000000" step="${key === "spend" ? "0.01" : "1"}" value="${r[key] ?? ""}" placeholder="未记录"></label>`).join("")}<label class="field"><span>客户问了什么？（可选，不填写联系方式）</span><textarea id="result-note" maxlength="1000" rows="2">${esc(r.note || "")}</textarea></label><button type="submit" class="btn primary full">保存效果</button></form>`);
  },
  "user-ledger": async (el) => {
    const rows = await api("/api/admin/ledger?user_id=" + el.dataset.id);
    modal(
      "用户积分流水",
      `<div class="table-wrap"><table><thead><tr><th>说明</th><th>变动</th><th>时间</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.description)}</td><td>${r.amount}</td><td>${date(r.created_at)}</td></tr>`).join("")}</tbody></table></div>`,
      true,
    );
  },
  "filter-favorites": () => {
    S.onlyFavorites = !S.onlyFavorites;
    render();
  },
  "new-provider": () => providerModal(),
  "edit-provider": (el) => providerModal(el.dataset.id),
  "test-provider": async (el) => {
    el.disabled = true;
    try {
      const r = await post("/api/admin/test", { provider_id: el.dataset.id });
      modal(
        "可用模型",
        `<p class="subtext">供应商连接成功，可用模型如下，可复制到任务路由。</p><textarea rows="12" readonly>${esc(r.models.join("\n"))}</textarea>`,
      );
    } finally {
      el.disabled = false;
    }
  },
  "cancel-task": async (el) => {
    await post("/api/tasks/cancel", { id: el.dataset.id });
    await refresh();
    render();
    toast("任务已取消，冻结积分已退回");
  },
  close,
  menu: () => $(".sidebar").classList.toggle("open"),
  projects: projectsModal,
  discover: () => navigate("discover"),
  refresh: async () => {
    await refresh();
    if (S.page === "admin") S.admin = await api("/api/admin");
    if (S.page === "credits") S.ledger = await api("/api/credits");
    render();
    toast("内容已更新");
  },
  help: () =>
    modal(
      "从业务资料，到能用的文案",
      `<p class="subtext">1. 选这次想要的结果：更多人看到、咨询或下单。</p><p class="subtext">2. 粘贴或上传业务资料，点击「帮我写好」。</p><p class="subtext">3. 核对提示，复制正文发布；需要时打开配图建议和评论回复。</p><p class="subtext">4. 发布后记录浏览、有效咨询和订单，下次创作会参考你的真实结果。</p>`,
    ),
  account: () =>
    modal(
      "账号与工作空间",
      `<p class="subtext">${esc(S.boot.user.email.startsWith("demo-") ? "当前为本地演示空间，数据保存在这台设备的服务中。" : S.boot.user.email)}</p><div class="actions">${button("项目设置", "project-settings", "secondary", "settings")}${button(S.boot.user.email.startsWith("demo-") ? "登录 / 注册" : "退出账号", "logout", "secondary", "logout")}</div>`,
    ),
  "project-settings": () => {
    const project=S.boot.projects.find(p=>p.id===S.project);
    modal("项目设置", `<form id="project-settings-form">${field("项目名称", "settings-project-name", project.name)}<label class="field"><span>项目介绍</span><textarea id="settings-project-description" maxlength="2000" rows="3">${esc(project.description || "")}</textarea></label><button class="btn primary full" type="submit">保存设置</button></form>`);
  },
  logout: async () => {
    await post("/api/auth/logout", {});
    close();
    drafts.clearUser(S.boot.user.id);
    editStore.clearUser(S.boot.user.id);
    S.watching = null; S.busy = false; S.workspaceKey = null;
    S.boot = null;
    location.hash = "login";
    S.ledger = null;
    S.admin = null;
    await loadPublic();
    login();
  },
  demo: async () => {
    await post("/api/auth/demo", {});
    await bootstrap();
    S.page = "discover"; location.hash = "discover";
    render();
  },
  "toggle-login": () => login(S.loginReset ? false : !S.loginRegister),
  forgot: () => login(false, true),
  "send-code": async (el) => {
    const email = $("#email").value.trim();
    if (!email) {
      $("#login-error").textContent = "请先填写邮箱";
      return;
    }
    el.disabled = true;
    try {
      await post("/api/auth/code", {
        email,
        purpose: S.loginReset ? "reset" : "register",
      });
      toast(
        S.loginReset
          ? "如果该邮箱已注册，验证码已发送，请查看邮箱"
          : "验证码已发送，请查看邮箱",
      );
      let left = 60;
      const tick = () => {
        if (!el.isConnected) return;
        el.textContent = left > 0 ? `${left} 秒后重发` : "重新发送";
        el.disabled = left > 0;
        if (left-- > 0) setTimeout(tick, 1000);
      };
      tick();
    } catch (e) {
      el.disabled = false;
      $("#login-error").textContent = e.message;
    }
  },
  "reset-password": (el) => {
    S.resetUser = el.dataset.id;
    modal(
      "重置用户密码",
      `<form id="admin-password-form">${field("新密码（至少 8 位）", "admin-new-password", "", "password")}<p class="muted">重置后该用户的登录会话全部失效。</p><button class="btn primary full" type="submit">确认重置</button></form>`,
    );
  },
  "test-mail": async (el) => {
    el.disabled = true;
    try {
      await post("/api/admin/mail-test", {});
      toast("测试邮件已发送到管理员邮箱");
    } catch (e) {
      toast(e.message);
    } finally {
      el.disabled = false;
    }
  },
  "save-source": async (el) => {
    const s = S.workspace.sources.find((s) => s.id === el.dataset.id);
    await mutate("/api/sources/" + s.id, "PATCH", { saved: !s.saved });
    toast(s.saved ? "已移出参考收藏" : "已保存到参考收藏");
  },
  "source-creations": () => {
    S.creationSource = S.detail;
    S.page = "creations";
    location.hash = "creations";
    render();
  },
  stage: (el) => {
    S.stage = el.dataset.stage;
    render();
  },
  publish: (el) => {
    S.trackId = el.dataset.id;
    const accs = accounts();
    const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
    modal(
      "标记为已发布",
      `<p class="subtext">在平台发布后再标记。发布后第一小时内完成评论布局；V1 不会替你发布或评论。</p><form id="publish-form">${accs.length ? `<label class="field"><span>发布账号</span><select id="publish-account"><option value="">不指定</option>${accs.map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select></label>` : '<p class="muted">还没有登记账号。可以在「项目资料」添加类型为「账号」的资料，按账号铺矩阵。</p>'}<label class="field"><span>发布时间</span><input type="datetime-local" id="publish-time" value="${local}"></label><button class="btn primary full" type="submit">${icon("check")}确认已发布</button></form>`,
    );
  },
  unpublish: async (el) => {
    await track(el.dataset.id, { status: "draft" });
    toast("已撤回为待发布");
  },
  "check-item": async (el) => {
    const c = S.workspace.creations.find((x) => x.id === el.dataset.id);
    const checklist = { ...(c.tracking.checklist || {}), [el.dataset.key]: el.checked };
    await track(el.dataset.id, { checklist });
  },
  "create-again": async (el) => {
    await startCreate(el.dataset.id);
  },
  "open-source": async (el) => {
    await openSource(el.dataset.id);
  },
  "original-again": async (el) => {
    await startOriginal(el.dataset.id);
  },
  "all-creations": () => {
    S.creationSource = null;
    render();
  },
  copy: async (el) => {
    const c = S.workspace.creations.find((c) => c.id === el.dataset.id);
    await navigator.clipboard.writeText(
      [c.data.title, c.data.body, (c.data.tags || []).map((t) => "#" + t).join(" ")].filter(Boolean).join("\n\n"),
    );
    toast(c.data.quality?.status === "needs_input" || c.data.demo ? "已复制待完善稿，请补齐提示内容后发布" : "正文已复制");
  },
  "save-creation": async (el) => {
    const c = S.workspace.creations.find((c) => c.id === el.dataset.id);
    await mutate("/api/creations/" + c.id, "PATCH", { saved: !c.saved });
    toast(c.saved ? "已取消收藏" : "稿件已收藏");
  },
  "delete-creation": (el) => {
    S.deleteId = el.dataset.id;
    modal(
      "删除这条稿件？",
      '<p class="subtext">只删除当前稿件，同批其他稿件和参考拆解会保留。已完成任务的积分不退回。</p><div class="actions">' +
        button("删除稿件", "confirm-delete", "danger", "trash") +
        button("保留稿件", "close") +
        "</div>",
    );
  },
  "confirm-delete": async () => {
    await mutate("/api/creations/" + S.deleteId, "DELETE", {});
    close();
    toast("这条稿件已删除");
  },
  cover: (el) => coverStudio(el.dataset.id),
  "cover-style": async (el) => {
    S.coverBrief.style = el.dataset.style;
    $$(".cover-option").forEach((b) =>
      b.classList.toggle("selected", b === el),
    );
    $("#cover-points-field").hidden = S.coverBrief.style !== "method";
    await previewCover();
  },
  "cover-thumbnail": () => $("#cover-preview").classList.toggle("thumbnail"),
  "cover-png": (el) => exportCover(el.dataset.id, "png"),
  "cover-jpg": (el) => exportCover(el.dataset.id, "jpg"),
  "edit-cover": (el) => {
    const image = S.workspace.images.find((i) => i.id === el.dataset.id);
    return coverStudio(image.creation_id, image.data.brief);
  },
  "generate-cover": async (el) => {
    if (S.imageUploading) throw new Error("图片正在上传，请完成后再保存");
    el.disabled = true;
    try {
      const r = await post(
        "/api/cover",
        body({ creation_id: S.coverId, brief: readCoverBrief() }),
      );
      close();
      toast("封面生成中…");
      await poll(r.task_ids, async () => {
        render();
        toast("封面已生成，显示在对应稿件下方");
      });
    } catch (e) {
      el.disabled = false;
      throw e;
    }
  },
  "export-csv": () => download("csv"),
  "export-xlsx": () => download("xlsx"),
  "new-asset": () => assetModal(),
  "edit-asset": (el) => assetModal(el.dataset.id),
  "delete-asset": (el) => {
    S.deleteAsset = el.dataset.id;
    modal(
      "删除项目资料？",
      `<p class="subtext">后续创作将无法选择这份资料，已有稿件保持不变。</p><div class="actions">${button("删除资料", "confirm-delete-asset", "danger", "trash")}${button("取消", "close")}</div>`,
    );
  },
  "confirm-delete-asset": async () => {
    await mutate("/api/assets/" + S.deleteAsset, "DELETE", {});
    close();
    toast("资料已删除");
  },
  "save-temporary": async () => {
    await post(
      "/api/assets",
      body({
        name: $("#temporary-name").value || "临时创作资料",
        kind: "其他",
        content: S.temporary,
      }),
    );
    S.temporary = "";
    close();
    await refresh();
    render();
    toast("临时资料已保存");
  },
  "task-result": async (el) => {
    const t = S.tasks.find((t) => t.id === el.dataset.id),
      r = JSON.parse(t.result);
    if (t.kind === "analyze" && r.source_ids?.length === 1)
      await openSource(r.source_ids[0]);
    else if (t.kind === "original" && r.brief_id) {
      S.creationSource = r.brief_id;
      await navigate("creations");
    }
    else await navigate(t.kind === "analyze" ? "discover" : "creations");
  },
  grant: (el) => {
    S.grantUser = el.dataset.id;
    modal(
      "调整创作积分",
      `<p class="subtext">${esc(el.dataset.email || "")} · 当前可用 ${esc(el.dataset.balance || "0")} 积分。正数为发放，负数为扣减；扣减只动可用积分，不动任务冻结中的积分。</p><form id="grant-form"><label class="field"><span>调整数量</span><input id="grant-amount" type="number" step="1" min="-100000" max="100000" value="100" required></label>${field("备注（可选，记入流水）", "grant-note", "")}<button class="btn primary full" type="submit">确认调整</button></form>`,
    );
  },
  "test-model": async (el) => {
    el.disabled = true;
    try {
      const r = await post("/api/admin/test", {});
      $("#model-list").hidden = false;
      $("#model-list").textContent =
        "连接成功，可用模型：" + (r.models.join("、") || "服务未提供模型列表");
    } finally {
      el.disabled = false;
    }
  },
  "test-tikhub": () =>
    modal(
      "测试 TikHub 连接",
      `<form id="tikhub-test-form">${field("公开内容分享链接", "tikhub-test-url")}<button class="btn primary full" type="submit">测试接口</button></form>`,
    ),
  retry: async (el) => {
    await post("/api/admin/retry", { id: el.dataset.id });
    toast("任务已重新提交");
    S.admin = await api("/api/admin");
    render();
  },
  "new-skill": () => skillModal(),
  "edit-skill": (el) => {
    const s = S.admin.skills.find((x) => x.id === el.dataset.id);
    if (s)
      skillModal(
        s.name,
        s.prompt,
        `编辑 Skill · ${s.name} v${s.version} → 保存为新草稿`,
      );
  },
  "copy-skill": async (el) => {
    const s = S.admin.skills.find((x) => x.id === el.dataset.id);
    if (!s) return;
    await navigator.clipboard.writeText(s.prompt);
    toast("Prompt 已复制");
  },
  "test-skill": async (el) => {
    el.disabled = true;
    await post("/api/admin/skills/state", {
      id: el.dataset.id,
      status: "Test",
    });
    S.admin = await api("/api/admin");
    render();
    toast("结构测试通过，可发布此版本");
  },
  "publish-skill": async (el) => {
    await post("/api/admin/skills/state", {
      id: el.dataset.id,
      status: "Published",
    });
    S.admin = await api("/api/admin");
    render();
    toast("版本已发布");
  },
};
function download(format) {
  if (!S.workspace.creations.length) {
    toast("先生成稿件，再导出内容");
    return;
  }
  const a = document.createElement("a");
  a.href = "/api/export?project_id=" + S.project + "&format=" + format;
  a.download = "DAOLOOK." + format;
  a.click();
  toast("正在导出全部有效稿件");
}
document.addEventListener("click", async (e) => {
  const el = e.target.closest("button,a[data-action]");
  if (!el) return;
  try {
    if (el.dataset.action) {
      e.preventDefault();
      await actions[el.dataset.action]?.(el);
    } else if (el.dataset.page) await navigate(el.dataset.page);
    else if (el.dataset.entry) {
      S.entryText = $("#reference")?.value || "";
      S.entry = el.dataset.entry;
      render();
      $("#reference")?.focus();
    } else if (el.dataset.filter) {
      S.filter = el.dataset.filter;
      render();
    } else if (el.dataset.source) await openSource(el.dataset.source);
    else if (el.dataset.project) {
      S.project = el.dataset.project;
      localStorage.setItem("daolook-project", S.project);
      S.detail = null;
      S.ledger = null;
      close();
      await refresh();
      await navigate("discover");
    } else if (el.dataset.direction) {
      S.direction = el.dataset.direction;
      $$(".direction").forEach((b) => b.classList.toggle("active", b === el));
    } else if (el.dataset.adminTab) {
      S.adminTab = el.dataset.adminTab;
      render();
    }
  } catch (error) {
    toast(error.message);
    el.disabled = false;
  }
});
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const submit = e.target.querySelector("[type=submit]");
  try {
    if (e.target.id === "draft-editor") return await saveDraftEdit();
    if (e.target.id === "analyze-form") return await startAnalyze();
    if (e.target.id === "create-form") return await startCreate();
    if (e.target.id === "original-form") return await startOriginal();
    if (submit) submit.disabled = true;
    switch (e.target.id) {
      case "results-form": {
        const results = { note: $("#result-note").value };
        for (const key of ["views", "leads", "orders", "spend"]) {
          const value = $(`#result-${key}`).value;
          if (value !== "") results[key] = Number(value);
        }
        await post("/api/results/" + S.resultsId, body({ results }));
        close();
        await refresh();
        render();
        toast("效果已记录");
        break;
      }
      case "provider-form":
        await post("/api/admin/provider", {
          id: S.providerId,
          name: $("#extra-provider-name").value,
          base_url: $("#extra-provider-base").value,
          api_key: $("#extra-provider-key").value,
          enabled: $("#extra-provider-enabled").checked,
        });
        close();
        S.admin = await api("/api/admin");
        render();
        toast("供应商已保存");
        break;
      case "routes-form": {
        const routes = {};
        for (const kind of ["analyze", "create", "cover"]) {
          routes[kind] = {};
          for (const pos of ["primary", "backup"])
            routes[kind][pos] = {
              provider: $(`#route-${kind}-${pos}-provider`).value,
              model: $(`#route-${kind}-${pos}-model`).value,
            };
        }
        await post("/api/admin/routes", routes);
        S.admin = await api("/api/admin");
        render();
        toast("主备模型路由已保存");
        break;
      }
      case "login-form":
        await post(
          "/api/auth/" +
            (S.loginReset ? "reset" : S.loginRegister ? "register" : "login"),
          {
            email: $("#email").value,
            password: $("#password").value,
            code: $("#code")?.value.trim() || "",
          },
        );
        S.loginReset = false;
        await bootstrap();
        S.page = "discover";
        location.hash = "discover";
        render();
        break;
      case "project-settings-form": {
        await api('/api/projects/'+S.project,{method:'PATCH',body:JSON.stringify({name:$('#settings-project-name').value,description:$('#settings-project-description').value})});
        close();await refresh();render();toast('项目设置已保存');break;
      }
      case "project-form": {
        const r = await post("/api/projects", {
          name: $("#project-name").value,
        });
        S.project = r.id;
        localStorage.setItem("daolook-project", S.project);
        close();
        await refresh();
        await navigate("discover");
        toast("新项目已创建");
        break;
      }
      case "asset-form": {
        const data = {
          name: $("#asset-name").value,
          kind: $("#asset-kind").value,
          content: $("#asset-content").value,
        };
        if (S.editAsset)
          await mutate("/api/assets/" + S.editAsset, "PATCH", data);
        else await post("/api/assets", body(data));
        close();
        await refresh();
        render();
        toast("项目资料已保存");
        break;
      }
      case "publish-form": {
        const time = $("#publish-time").value;
        await track(S.trackId, {
          status: "published",
          account_id: $("#publish-account")?.value || "",
          published_at: time ? new Date(time).toISOString() : undefined,
        });
        close();
        toast("已标记发布，第一小时内完成评论布局");
        break;
      }
      case "admin-password-form":
        await post("/api/admin/password", {
          user_id: S.resetUser,
          password: $("#admin-new-password").value,
        });
        close();
        toast("密码已重置");
        break;
      case "grant-form": {
        const amount = Number($("#grant-amount").value);
        if (!Number.isInteger(amount) || amount === 0)
          throw new Error("请输入非零整数，负数为扣减");
        await post("/api/admin/grant", {
          user_id: S.grantUser,
          amount,
          note: $("#grant-note").value,
        });
        close();
        S.admin = await api("/api/admin");
        await refresh();
        render();
        toast(amount > 0 ? `已发放 ${amount} 积分` : `已扣减 ${-amount} 积分`);
        break;
      }
      case "config-form": {
        const c = S.admin.config;
        await post("/api/admin/config", {
          mode: $("#run-mode").value,
          provider: {
            ...c.provider,
            base_url: $("#provider-base").value,
            api_key: $("#provider-key").value,
            model: $("#provider-model").value,
            backup_model: $("#provider-backup").value,
            image_model: $("#provider-image").value,
            transcribe_model: $("#provider-transcribe").value.trim(),
            enabled: $("#provider-enabled").checked,
          },
          mail: {
            enabled: $("#mail-enabled").checked,
            host: $("#mail-host").value.trim(),
            port: Number($("#mail-port").value),
            security: $("#mail-security").value,
            username: $("#mail-user").value.trim(),
            password: $("#mail-password").value,
            sender: $("#mail-sender").value.trim(),
          },
          tikhub: {
            ...c.tikhub,
            base_url: $("#tikhub-base").value,
            api_key: $("#tikhub-key").value,
            endpoints: JSON.parse($("#endpoints").value),
          },
          rules: {
            analyze: Number($("#cost-analyze").value),
            create: Number($("#cost-create").value),
            cover: Number($("#cost-cover").value),
            original: Number($("#cost-original").value),
          },
          limits: {
            ...c.limits,
            batch: Number($("#batch-limit").value),
            timeout: Number($("#timeout").value),
            retries: Number($("#retries").value),
            temporary_ttl_hours: Number($("#temporary-ttl").value),
            discover_pick: Number($("#discover-pick").value),
          },
          ranking: JSON.parse($("#ranking").value),
          signup: {
            whitelist: $("#signup-whitelist").checked,
            emails: $("#signup-emails")
              .value.split(/[\s,，;；]+/)
              .map((x) => x.trim())
              .filter(Boolean),
            welcome_credits: Number($("#signup-welcome").value),
          },
        });
        S.admin = await api("/api/admin");
        await refresh();
        render();
        toast("配置已保存");
        break;
      }
      case "skill-form":
        await post("/api/admin/skills", {
          name: $("#skill-name").value,
          prompt: $("#skill-prompt").value,
        });
        close();
        S.admin = await api("/api/admin");
        render();
        toast("草稿已创建");
        break;
      case "tikhub-test-form":
        await post("/api/admin/tikhub-test", {
          url: $("#tikhub-test-url").value,
        });
        close();
        toast("TikHub 接口连接成功");
        break;
    }
  } catch (error) {
    if ($("#login-error")) $("#login-error").textContent = error.message;
    else showFormError(e.target, error.message);
  } finally {
    if (submit) submit.disabled = false;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "reference") {
    S.entryText = e.target.value;
    const cost = $("#entry-cost");
    if (cost)
      cost.textContent = analyzeEstimate();
  }
  if (e.target.id === "transcript") S.transcript = e.target.value;
  if (e.target.id === "create-goal") S.goal = e.target.value;
  if (e.target.id === "requirements") S.requirements = e.target.value;
  if (e.target.id === "temporary") S.temporary = e.target.value;
  const originalField = {
    "original-goal": "goal",
    "original-platform": "platform",
    "original-topic": "topic",
    "original-keyword": "keyword",
    "original-requirements": "requirements",
    "original-temporary": "temporary",
  }[e.target.id];
  if (originalField) S.original[originalField] = e.target.value;
  if (e.target.name === "original-asset")
    S.original.assets = $$("input[name=original-asset]:checked").map((x) => x.value);
  if (originalField || e.target.name === "original-asset") {
    saveDraft();
    const summary=$('.original-assets')?.previousElementSibling;
    if(summary) summary.textContent=`使用已保存的资料（已选 ${S.original.assets.length} 份）`;
  }
});
async function fileText(f) {
  if (!/\.(docx|pdf|doc)$/i.test(f.name)) return f.text();
  const data = await new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error("文件读取失败"));
    r.readAsDataURL(f);
  });
  toast("正在提取文件文字…");
  const r = await post("/api/extract", { name: f.name, data });
  toast("已提取文字，请核对后保存");
  return r.text;
}
async function uploadProjectPhotos(input) {
  const files = [...input.files];
  if (!files.length) return;
  if (S.imageUploading) throw new Error("图片正在上传，请稍后");
  if (files.length > 6) throw new Error("一次最多上传 6 张图片");
  for (const f of files) {
    if (!["image/png", "image/jpeg", "image/webp"].includes(f.type))
      throw new Error("只支持 PNG、JPEG 或 WebP 图片");
    if (f.size > 2 * 1024 * 1024) throw new Error("每张图片最大 2 MB");
  }
  const isOriginal = input.id === "original-photo-file";
  const isCover = input.id === "cover-photo-file",
    project = S.project;
  const creation = S.coverId;
  if (!isCover && !isOriginal) {
    S.requirements = $("#requirements").value;
    S.temporary = $("#temporary").value;
    S.selectedAssets = $$("input[name=asset]:checked").map((x) => x.value);
  }
  S.imageUploading = true;
  input.disabled = true;
  const submitted = [];
  try {
    toast("正在上传图片…");
    for (const f of files) {
      const content = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = () => reject(new Error("无法读取图片"));
        r.readAsDataURL(f);
      });
      const img = new Image();
      img.src = content;
      try {
        await img.decode();
      } catch {
        throw new Error("图片损坏或无法解码，请重新选择");
      }
      const result = await post("/api/assets", {
        project_id: project,
        name: f.name,
        kind: "图片",
        content,
      });
      submitted.push({ ...result, name: f.name, kind: "图片", content });
    }
  } finally {
    S.imageUploading = false;
    input.disabled = false;
    input.value = "";
    if (project === S.project && submitted.length) {
      S.workspace.assets.push(...submitted);
      if (isCover && $("#cover-asset") && S.coverId === creation) {
        for (const a of submitted) {
          const option = document.createElement("option");
          option.value = a.id;
          option.textContent = a.name;
          $("#cover-asset").append(option);
        }
        $("#cover-asset").value = submitted.at(-1).id;
        await previewCover();
      } else if (isOriginal) {
        S.original.assets.push(...submitted.map((a) => a.id));
        saveDraft();
        render();
      } else if (!isCover) {
        S.selectedAssets.push(...submitted.map((a) => a.id));
        render();
      }
      toast(
        `已保存 ${submitted.length} 张图片到项目${isCover ? "并用于封面" : "，已选入本次创作"}`,
      );
    }
  }
}
document.addEventListener("change", async (e) => {
  try {
    if (e.target.dataset.action === "check-item")
      return await actions["check-item"](e.target);
    if (["creation-photo-file", "cover-photo-file", "original-photo-file"].includes(e.target.id))
      return await uploadProjectPhotos(e.target);
    if (e.target.id === "source-kind-filter") {
      S.sourceKind = e.target.value;
      render();
    }
    if (e.target.id === "format-filter") {
      S.contentFormat = e.target.value;
      render();
    }
    if (e.target.id === "platform-filter") {
      S.platform = e.target.value;
      render();
    }
    if (e.target.id === "sort-filter") {
      S.sort = e.target.value;
      render();
    }
    if (e.target.id === "original-file") {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 2 * 1024 * 1024) throw new Error("文件最大支持 2 MB");
      const project = S.project;
      const text = await fileText(f);
      if (S.project !== project) return;
      S.original.temporary = [S.original.temporary, text].filter(Boolean).join("\n\n");
      saveDraft();
      render();
      toast("资料已读入，可直接生成");
      return;
    }
    if (e.target.id === "asset-file" || e.target.id === "temporary-file") {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 2 * 1024 * 1024) throw new Error("文件最大支持 2 MB");
      if (e.target.id === "temporary-file") {
        const key=workspaceKey(); const text=await fileText(f);
        if(key !== workspaceKey() || !$('#temporary')) return;
        $("#temporary").value = text; S.temporary = text;
      } else {
        if (!$("#asset-name").value) $("#asset-name").value = f.name;
        if (f.type.startsWith("image/")) {
          const reader = new FileReader();
          reader.onload = () => {
            $("#asset-content").value = reader.result;
            $("#asset-kind").value = "图片";
          };
          reader.readAsDataURL(f);
        } else $("#asset-content").value = await fileText(f);
      }
    }
  } catch (error) {
    toast(error.message);
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    close();
    $(".sidebar")?.classList.remove("open");
  }
  if (e.key === "Tab" && $(".dialog")) {
    const nodes = $$(
      ".dialog button,.dialog input,.dialog select,.dialog textarea,.dialog a",
    ).filter((n) => !n.disabled && n.offsetParent !== null);
    if (!nodes.length) return;
    if (e.shiftKey && document.activeElement === nodes[0]) {
      nodes.at(-1).focus();
      e.preventDefault();
    } else if (!e.shiftKey && document.activeElement === nodes.at(-1)) {
      nodes[0].focus();
      e.preventDefault();
    }
  }
});
document.addEventListener("keydown", (e) => {
  const tab = e.target.closest?.("[role=tab]");
  if (!tab || !tab.closest(".entry-tabs")) return;
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  e.preventDefault();
  const tabs = $$(".entry-tabs [role=tab]");
  const i = tabs.indexOf(tab);
  const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
  S.entryText = $("#reference")?.value || "";
  S.entry = next.dataset.entry;
  render();
  $(`.entry-tabs [data-entry="${next.dataset.entry}"]`)?.focus();
});
window.addEventListener("hashchange", () => {
  if (!S.boot) return;
  const hash = location.hash.slice(1);
  if (hash.startsWith("detail/")) {
    S.detail = hash.slice(7);
    S.page = "detail";
    render();
  } else if (pageNames[hash] && S.page !== hash) navigate(hash);
});
(async () => {
  try {
    await loadPublic();
    try {
      await bootstrap();
    } catch (error) {
      if (error.message !== "请先登录") throw error;
      if (S.publicMode === "demo" && location.hash !== "#login") {
        await post("/api/auth/demo", {});
        await bootstrap();
      } else {
        return login();
      }
    }
    const hash = location.hash.slice(1);
    if (hash.startsWith("detail/")) {
      S.detail = hash.slice(7);
      S.page = "detail";
    } else if (pageNames[hash]) S.page = hash;
    render();
    if (S.page === "credits" || S.page === "admin") await navigate(S.page);
    const pending = S.tasks.filter(
      (t) => !["SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"].includes(t.state),
    );
    if (pending.length)
      poll(
        pending.map((t) => t.id),
        async () => toast("后台任务已完成"),
      );
  } catch (error) {
    $("#app").innerHTML =
      `<div class="boot"><span class="brand">DAOLOOK</span><p>${esc(error.message)}</p><a class="btn primary" href="/">重新连接</a></div>`;
  }
})();
