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
  entry: "single",
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
  temporary: "",
  selectedAssets: [],
};
const pageNames = {
  discover: "发现灵感",
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
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败");
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
    () => $("#toast").classList.remove("show"),
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
  if (S.project)
    S.workspace = await api("/api/workspace?project_id=" + S.project);
  S.tasks = await api("/api/tasks");
  S.boot = await api("/api/bootstrap");
}
function shell() {
  const project = S.boot.projects.find((p) => p.id === S.project);
  const user = S.boot.user;
  return `<div class="shell"><aside class="sidebar"><button class="close sidebar-mobile-close" data-action="menu" aria-label="关闭菜单">${icon("close")}</button><a class="brand" href="#discover">DAOLOOK<span class="brand-dot">✳</span></a><div class="brand-sub">有依据 · 有灵感 · 有表达</div><button class="project-switch" data-action="projects"><span class="project-symbol">${icon("folder")}</span><span>${esc(project?.name || "选择项目")}<small>个人工作空间</small></span><span class="chevron">⌄</span></button><div class="nav-label">WORKSPACE</div><nav class="nav" aria-label="工作空间">${[
    ["discover", "spark", "发现灵感"],
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
    )}</nav><div class="nav-label">MANAGE</div><nav class="nav">${[["tasks", "clock", "任务记录"], ["credits", "coin", "积分账本"], ...(user.role === "admin" ? [["admin", "settings", "管理后台"]] : [])].map(([id, ic, label]) => `<button class="${S.page === id ? "active" : ""}" data-page="${id}">${icon(ic)}${label}</button>`).join("")}</nav><div class="sidebar-bottom"><div class="credit-mini"><div class="top">${icon("coin")}创作积分</div><div class="balance">${S.boot.credits.balance.toLocaleString()}<small>可用积分</small></div><div class="credit-track"><span style="width:${Math.min(100, S.boot.credits.balance / 3)}%"></span></div><button data-page="credits">每一个好想法，都值得被实现 ${icon("arrow")}</button></div><button class="profile" data-action="account"><span class="avatar">${user.email.startsWith("demo-") ? "D" : esc(user.email[0].toUpperCase())}</span><span>${user.email.startsWith("demo-") ? "灵感探索者" : esc(user.email.split("@")[0])}<small>${user.role === "admin" ? "超级管理员" : user.email.startsWith("demo-") ? "演示工作空间" : "个人创作者"}</small></span>${icon("settings")}</button></div></aside><main class="main"><header class="topbar"><div class="breadcrumb"><button class="mobile-menu" data-action="menu" aria-label="展开菜单">${icon("menu")}</button>${icon("home")}<span>/</span><span class="crumb-name">${esc(project?.name)}</span><span>/</span><strong>${pageNames[S.page]}</strong></div><div class="top-actions"><span class="mode">${S.boot.mode === "demo" ? "演示模式" : "已连接服务"}</span><button class="text-btn" data-action="help">${icon("help")}使用指南</button><span class="avatar">${user.email.startsWith("demo-") ? "D" : esc(user.email[0].toUpperCase())}</span></div></header><div class="content" id="content">${pageContent()}</div></main></div>`;
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
      '让好内容，成为你的<span class="serif">新灵感。</span>',
      "找到值得参考的内容，拆解背后的逻辑，再创作属于你的表达。",
      `<div class="step-note"><span>01 找依据</span><i>→</i><span>02 拆解</span><i>→</i><span>03 再创作</span></div>`,
    ) +
    entryPanel() +
    `<section><div class="section-head"><div><h2>${S.workspace.sources.length && S.workspace.sources.every((s) => s.data.demo) ? "拆解体验样本" : "项目参考内容"} <span>${S.workspace.sources.length} 条</span></h2><p>你提交并完成拆解的内容会保留在这里。示例有明确标识，不是实时爆款推荐。</p></div><button class="text-btn" data-action="refresh">${icon("refresh")}刷新列表</button></div>${filters()}<div class="cards" id="source-cards">${sourceCards(false)}</div><div class="bottom-note">${icon("shield")}${S.boot.mode === "demo" ? "示例内容与互动数据仅供体验，不代表真实平台数据" : "仅分析公开内容，不长期保存完整原视频"}</div></section>`
  );
}
function entryPanel() {
  const tabs = [
    ["single", "link", "单条链接"],
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
  return `<section class="entry-panel"><div class="entry-tabs" role="tablist" aria-label="参考入口">${tabs.map(([id, ic, label]) => `<button role="tab" aria-selected="${S.entry === id}" tabindex="${S.entry === id ? 0 : -1}" class="${S.entry === id ? "active" : ""}" data-entry="${id}">${icon(ic)}${label}</button>`).join("")}<span class="entry-help">好创作，从一个好参考开始</span></div><form id="analyze-form"><div class="input-row"><div class="reference-input">${icon(S.entry === "keyword" ? "search" : "link")}${S.entry === "batch" ? `<textarea id="reference" aria-label="参考内容" placeholder="${placeholder}">${esc(S.entryText)}</textarea>` : `<input id="reference" aria-label="参考内容" value="${esc(S.entryText)}" placeholder="${placeholder}" autocomplete="off">`}</div>${S.entry === "keyword" ? `<select id="keyword-platform" aria-label="搜索平台"><option value="xhs">小红书</option><option value="douyin">抖音</option></select>` : ""}<button type="submit" class="btn primary" ${S.busy ? "disabled" : ""}>${S.busy ? '<span class="spinner"></span>' : icon("spark")}${S.busy ? "正在提交" : "开始拆解"} ${!S.busy ? icon("arrow") : ""}</button></div><div class="entry-bottom"><span class="platform-marks"><span class="xhs-mark">小红书</span><span class="dy-mark">♪</span>${S.entry === "keyword" ? (S.boot.mode === "demo" ? "演示搜索仅返回预置样本，不执行真实检索" : "按所选平台搜索，取接口前 3 条可识别结果，不保证为爆款") : "自动识别平台 · 使用对应平台的拆解方式"}</span><span id="entry-cost">预计 ${S.boot.rules.analyze * (S.entry === "batch" ? Math.max(1, S.entryText.split("\n").filter((x) => x.trim()).length) : 1)} 积分${S.entry === "batch" ? " · 逐条结算" : ""} · 失败自动退还</span></div></form></section>`;
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
  return `<button class="back" data-page="discover">${icon("back")}返回发现灵感</button>${heading(esc(s.data.title), "先理解内容为什么有效，再找到属于自己的表达。", button(s.saved ? "已保存参考" : "保存参考", "save-source", s.saved ? "secondary" : "primary", s.saved ? "check" : "plus", `data-id="${s.id}"`), "CONTENT BREAKDOWN / " + (s.platform === "xhs" ? "小红书" : "抖音"))}<div class="two-col"><section class="panel"><div class="detail-cover"><img src="${art(s)}" alt="参考主题插画"></div><div class="source-meta"><span>${esc(s.data.author || "未知作者")}</span><span>${fmt(s.data.likes)} 赞</span><span>${fmt(s.data.saves)} 收藏</span>${s.url && /^https?:/.test(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>` : ""}</div>${s.data.demo ? '<div class="notice">演示拆解：以下内容用于体验产品流程，不是真实平台抓取或模型分析。</div>' : ""}<h2>把好内容拆开看</h2>${(s.analysis.sections || []).map((a, i) => `<div class="analysis-section"><span class="num">${String(i + 1).padStart(2, "0")}</span><div><h3>${esc(a.name)}</h3><p>${esc(a.text)}</p></div></div>`).join("")}</section><section class="panel composer"><h2>${icon("spark")} 创作我的版本</h2><p class="intro">借鉴这条内容的创作思路，结合你的品牌与本次要求，一次获得 3 个不同表达方案。</p><form id="create-form"><label class="field"><span>本次创作要求 <small style="display:inline;font-weight:400">可选</small></span><textarea id="requirements" rows="5" placeholder="比如：改成适合独立咖啡店的日常分享，语气轻松，面向刚接触手冲的年轻人…">${esc(S.requirements)}</textarea></label><div class="field"><span>选择项目资料 <small style="display:inline;font-weight:400">可选，不会自动使用</small></span>${S.workspace.assets.length ? S.workspace.assets.map((a) => `<label class="check-row"><input type="checkbox" name="asset" value="${esc(a.id)}" ${S.selectedAssets.includes(a.id) ? "checked" : ""}>${a.kind === "图片" ? `<img class="asset-choice-thumb" src="${esc(safeImage(a.content))}" alt="">` : icon("folder")}${esc(a.name)}</label>`).join("") : '<p class="muted">还没有长期资料，去「项目资料」添加品牌或产品信息。</p>'}</div><div class="inline-photo-upload"><label class="field"><span>上传产品图 / 个人 IP 形象图</span><input type="file" id="creation-photo-file" accept="image/png,image/jpeg,image/webp" multiple><small>每张最多 2 MB，一次最多 6 张。上传后保存到当前项目并自动勾选，用于本次创作；封面默认带入一张，可重新选择。</small></label></div><label class="field"><span>本次临时资料 <small style="display:inline;font-weight:400">可选</small></span><textarea id="temporary" rows="3" placeholder="补充本次需要的真实信息，不会自动存入项目">${esc(S.temporary)}</textarea></label><label class="text-btn" style="cursor:pointer">${icon("plus")}上传文本资料<input type="file" id="temporary-file" accept=".txt,.md,.csv" hidden></label><div class="hint">每次生成 3 条独立稿件 · 新结果追加保留<br>预计消耗 ${S.boot.rules.create} 积分，失败自动退还</div><button class="btn primary full" type="submit" ${S.busy ? "disabled" : ""}>${S.busy ? '<span class="spinner"></span>' : icon("spark")}生成 3 条我的版本 ${icon("arrow")}</button></form><div class="actions" style="margin-top:16px">${button(`查看已有稿件 (${S.workspace.creations.filter((c) => c.source_id === s.id).length})`, "source-creations", "secondary small", "edit")}</div></section></div>`;
}
function creations() {
  let items = S.workspace.creations.filter(
    (c) => !S.creationSource || c.source_id === S.creationSource,
  );
  if (S.onlyFavorites) items = items.filter((c) => c.saved);
  return (
    heading(
      "你的表达，在这里生长。",
      "每次生成都是新的可能。历史版本持续保留，随时复制、收藏与导出。",
      `<div class="actions">${button("Excel 导出", "export-xlsx", "secondary", "download")}${button("CSV 导出", "export-csv", "secondary", "download")}${button("开始新创作", "discover", "primary", "plus")}</div>`,
      "MADE BY YOU, INSPIRED BY THE WORLD",
    ) +
    `<div class="section-head"><h2>${S.onlyFavorites ? "收藏稿件" : "全部稿件"} <span>${items.length} 条</span></h2><button class="chip ${S.onlyFavorites ? "active" : ""}" data-action="filter-favorites">${S.onlyFavorites ? "查看全部" : "仅看收藏"}</button>${S.creationSource ? button("查看全部稿件", "all-creations", "secondary small") : ""}</div>${items.length ? `<div class="creation-grid">${items.map(draftCard).join("")}</div>` : empty("第一条好内容，从一个参考开始", "先找到值得借鉴的内容，进入拆解页，点击「创作我的版本」。", button("去发现灵感", "discover", "primary", "spark"))}`
  );
}
function draftCard(c) {
  const d = c.data;
  const source = S.workspace.sources.find((s) => s.id === c.source_id);
  const images = S.workspace.images.filter((i) => i.creation_id === c.id);
  return `<article class="draft"><div class="draft-top"><span>${source?.platform === "douyin" ? "♪ 抖音脚本" : "小红书图文"} · ${esc(d.angle || "原创方案")}</span><span>${date(c.created_at)}</span></div><h3>${esc(d.title)}</h3>${d.demo ? '<div class="notice">演示稿件 · 模板示例，未调用 AI 模型</div>' : ""}${d.hook ? `<div class="hint"><strong>前三秒钩子</strong><br>${esc(d.hook)}</div>` : ""}<div class="draft-body">${esc(d.body)}</div><div class="tags">${(d.tags || []).map((t) => "#" + esc(t)).join(" ")}</div><details><summary>标题备选、配图与素材提示</summary><p>${(d.titles || []).map(esc).join("<br>")}</p><p style="margin-top:8px">封面：${esc(d.cover_text)}</p><p>${(d.image_suggestions || []).map(esc).join(" / ")}</p><p>${(d.storyboard || []).map(esc).join("<br>")}</p><p>${(d.shooting_list || []).map(esc).join(" / ")}</p><p class="inline-error">${(d.missing || []).map(esc).join("<br>")}</p></details>${images.map(coverCard).join("")}<div class="actions"><button data-action="copy" data-id="${c.id}">${icon("copy")} 复制</button><button data-action="save-creation" data-id="${c.id}" class="${c.saved ? "saved-icon" : ""}">${icon(c.saved ? "check" : "star")} ${c.saved ? "已收藏" : "收藏"}</button><button data-action="cover" data-id="${c.id}">${icon("image")} 封面</button><button data-action="delete-creation" data-id="${c.id}" style="margin-left:auto;color:#a3a892" aria-label="删除此稿件">${icon("trash")}</button></div></article>`;
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
      ? `<div class="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>积分</th><th>时间</th><th>结果</th></tr></thead><tbody>${items.map((t) => `<tr><td>${{ analyze: "参考内容拆解", create: "再创作 · 3 条稿件", cover: "封面生成" }[t.kind]}</td><td><span class="status ${t.state === "FAILED" ? "failed" : t.state === "SUCCEEDED" ? "" : "pending"}">${states[t.state] || t.state}</span></td><td>${t.cost}</td><td>${date(t.created_at)}</td><td>${t.error ? `<span title="${esc(t.error)}">${esc(t.error.slice(0, 40))}</span>` : t.state === "SUCCEEDED" ? `<button class="text-btn" data-action="task-result" data-id="${t.id}">查看结果 ${icon("arrow")}</button>` : t.state === "CANCELLED" ? "—" : button("取消任务", "cancel-task", "secondary small", "close", `data-id="${t.id}"`)}</td></tr>`).join("")}</tbody></table></div>`
      : empty("还没有任务", "从一条参考链接开始，任务进度会显示在这里。"))
  );
}
function credits() {
  return (
    heading(
      "为每一次好创作，积蓄能量。",
      "操作前展示消耗，执行时冻结，成功结算，失败退回。",
      "",
      "CREDIT ACCOUNT",
    ) +
    `<div class="summary-strip"><div><p>当前可用积分</p><strong>${S.boot.credits.balance}</strong></div><div><p>正在冻结</p><strong>${S.boot.credits.frozen}</strong></div><div><p>再创作 / 3 条</p><strong>${S.boot.rules.create}<small style="font-size:12px"> 积分</small></strong></div></div><div class="notice">当前版本由管理员发放积分。已完成稿件的主动删除不会退还积分；封面生成单独计费，每次 ${S.boot.rules.cover} 积分。</div><div id="ledger">${S.ledger ? ledgerTable() : '<div class="loading-line"><span class="spinner"></span>读取积分流水…</div>'}</div>`
  );
}
function ledgerTable() {
  return `<div class="table-wrap"><table><thead><tr><th>流水说明</th><th>类型</th><th>可用积分变动</th><th>时间</th></tr></thead><tbody>${S.ledger.map((l) => `<tr><td>${esc(l.description)}</td><td>${{ GRANT: "发放", FREEZE: "冻结", REFUND: "退回", SETTLE: "结算" }[l.kind] || l.kind}</td><td style="color:${l.amount > 0 ? "#718d42" : "inherit"}">${l.amount > 0 ? "+" : ""}${l.amount}</td><td>${date(l.created_at)}</td></tr>`).join("")}</tbody></table></div>`;
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
    return `<div class="table-wrap"><table><thead><tr><th>邮箱</th><th>角色</th><th>可用 / 冻结</th><th>操作</th></tr></thead><tbody>${a.users.map((u) => `<tr><td>${esc(u.email)}</td><td>${u.role}</td><td>${u.balance} / ${u.frozen}</td><td>${button("发放积分", "grant", "secondary small", "plus", `data-id="${u.id}"`)} ${button("查看流水", "user-ledger", "secondary small", "clock", `data-id="${u.id}"`)}</td></tr>`).join("")}</tbody></table></div>`;
  if (S.adminTab === "tasks")
    return `<div class="table-wrap"><table><thead><tr><th>任务 ID</th><th>类型</th><th>状态 / 错误</th><th>操作</th></tr></thead><tbody>${a.tasks.map((t) => `<tr><td>${t.id.slice(0, 10)}</td><td>${t.kind}</td><td>${states[t.state]} ${esc(t.error || "")}</td><td>${t.state === "FAILED" ? button("重试（重新计费）", "retry", "secondary small", "refresh", `data-id="${t.id}"`) : "—"}</td></tr>`).join("")}</tbody></table></div>`;
  if (S.adminTab === "skills")
    return `<div class="actions" style="margin-bottom:20px">${button("创建 Skill 草稿", "new-skill", "primary", "plus")}</div><div class="notice">每类任务只有一条「生效中」的 Prompt，真实拆解与创作只读它。要改 Prompt 就点「编辑为新版本」：保存草稿 → 测试 → 发布，发布即替换生效版本（旧版转为已归档）。</div><div class="asset-grid">${a.skills.map((s) => `<article class="asset-card"><span class="status">${skillStates[s.status] || s.status}</span><h3>${esc(s.name)} · v${s.version}</h3><details class="skill-prompt"><summary>查看完整 Prompt</summary><pre>${esc(s.prompt)}</pre></details><div class="actions">${button("编辑为新版本", "edit-skill", "secondary small", "edit", `data-id="${s.id}"`)}${button("复制", "copy-skill", "secondary small", "copy", `data-id="${s.id}"`)}${s.status === "Draft" ? button("测试", "test-skill", "secondary small", "check", `data-id="${s.id}"`) : s.status === "Test" ? button("发布", "publish-skill", "primary small", "check", `data-id="${s.id}"`) : s.status === "Archived" ? button("回滚至此版本", "publish-skill", "primary small", "check", `data-id="${s.id}"`) : ""}</div></article>`).join("")}</div>`;
  return `<form id="config-form"><div class="admin-grid"><section class="panel"><h2>模型供应商</h2>${field("Base URL", "provider-base", c.provider.base_url)}${field("API Key", "provider-key", c.provider.api_key, "password")}${field("主文本模型", "provider-model", c.provider.model)}${field("备用文本模型", "provider-backup", c.provider.backup_model)}${field("封面模型", "provider-image", c.provider.image_model)}<label class="check-row"><input type="checkbox" id="provider-enabled" ${c.provider.enabled ? "checked" : ""}>启用模型服务</label><div class="actions" style="margin-top:15px">${button("连接测试 / 同步模型", "test-model", "secondary small", "refresh")}</div><div id="model-list" class="hint" hidden></div></section><section class="panel"><h2>TikHub 数据源</h2>${field("Base URL", "tikhub-base", c.tikhub.base_url)}${field("API Key", "tikhub-key", c.tikhub.api_key, "password")}<label class="field"><span>平台端点映射（JSON）</span><textarea id="endpoints" rows="12">${esc(JSON.stringify(c.tikhub.endpoints, null, 2))}</textarea></label><div class="hint">小红书使用 App V2 系列；请按账号实际可用接口配置抖音端点。服务保存后再测试。</div>${button("测试参考链接", "test-tikhub", "secondary small", "link")}</section><section class="panel"><h2>积分与系统</h2><label class="field"><span>运行模式</span><select id="run-mode"><option value="demo" ${c.mode === "demo" ? "selected" : ""}>演示模式</option><option value="live" ${c.mode === "live" ? "selected" : ""}>真实服务</option></select></label>${field("拆解积分", "cost-analyze", c.rules.analyze, "number")}${field("再创作积分", "cost-create", c.rules.create, "number")}${field("封面积分", "cost-cover", c.rules.cover, "number")}${field("批量上限", "batch-limit", c.limits.batch, "number")}${field("请求超时（秒）", "timeout", c.limits.timeout, "number")}${field("模型重试次数", "retries", c.limits.retries ?? 1, "number")}${field("临时资料保留时长（小时）", "temporary-ttl", c.limits.temporary_ttl_hours ?? 24, "number")}</section><section class="panel"><h2>内容排序权重</h2><label class="field"><span>评分权重（JSON）</span><textarea id="ranking" rows="10">${esc(JSON.stringify(c.ranking, null, 2))}</textarea></label><div class="hint">缺少真实账号近期样本和赛道中位数时，不展示未经验证的异常爆款结论。正式排序需用真实样本校准。</div></section></div><button class="btn primary" type="submit" style="margin-top:25px">${icon("check")}保存配置</button></form>`;
}
function field(label, id, value = "", type = "text") {
  return `<label class="field"><span>${label}</span><input id="${id}" type="${type}" value="${esc(value)}" ${type === "number" ? 'min="0"' : ""}></label>`;
}
function skillModal(name = "xhs_analysis", prompt = "", title = "创建 Skill 草稿") {
  modal(
    title,
    `<p class="subtext">保存会生成新的 Draft 版本，不会改动当前生效版本。结构测试通过后发布，发布即替换生效版本。</p><form id="skill-form"><label class="field"><span>任务类型</span><select id="skill-name">${["xhs_analysis", "douyin_analysis", "xhs_creation", "douyin_creation"].map((n) => `<option ${n === name ? "selected" : ""}>${n}</option>`).join("")}</select></label><label class="field"><span>Skill / Prompt</span><textarea id="skill-prompt" rows="12" required placeholder="输入平台拆解或创作规则…">${esc(prompt)}</textarea></label><button class="btn primary full" type="submit">保存草稿</button></form>`,
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
  $("#overlay").innerHTML = "";
  S.modalFocus?.focus();
}
function projectsModal() {
  modal(
    "你的项目空间",
    `<p class="subtext">每个项目都有独立的参考、稿件与资料。</p>${S.boot.projects.map((p) => `<button class="project-option ${p.id === S.project ? "selected" : ""}" data-project="${p.id}">${icon("folder")}<span>${esc(p.name)}<small>${esc(p.description || "独立创作空间")}</small></span></button>`).join("")}<form id="project-form" style="margin-top:24px">${field("新项目名称", "project-name")}<button class="btn primary full" type="submit">${icon("plus")}创建新项目</button></form>`,
  );
}
function assetModal(id) {
  const a = S.workspace.assets.find((a) => a.id === id);
  S.editAsset = id;
  modal(
    a ? "编辑项目资料" : "添加项目资料",
    `<form id="asset-form">${field("资料名称", "asset-name", a?.name || "")}<label class="field"><span>资料类型</span><select id="asset-kind">${["品牌资料", "产品信息", "受众画像", "禁用词", "图片", "其他"].map((k) => `<option ${a?.kind === k ? "selected" : ""}>${k}</option>`).join("")}</select></label><label class="field"><span>资料内容</span><textarea id="asset-content" rows="7" placeholder="请输入真实的品牌、产品或受众信息">${esc(a?.content || "")}</textarea></label><label class="field"><span>上传文件 · 文本 / 图片</span><input type="file" id="asset-file" accept=".txt,.md,.csv,image/png,image/jpeg,image/webp"><small>文本自动读取；图片最大 2 MB。资料不会自动在创作中全选。</small></label><button class="btn primary full" type="submit">${icon("check")}保存资料</button></form>`,
  );
}
function login(register = false) {
  S.loginRegister = register;
  $("#app").innerHTML =
    `<div class="login"><section class="login-art"><div><div class="brand">DAOLOOK<span class="brand-dot">✳</span></div><div class="brand-sub">有依据 · 有灵感 · 有表达</div></div><div><h1>好内容，<br>是新灵感的<em>开始。</em></h1><p>找依据 → 拆解 → 再创作</p></div><p>YOUR NEXT GREAT IDEA STARTS HERE.</p><div class="orb"></div></section><section class="login-form"><div><h2>${register ? "开启你的创作空间" : "欢迎回到 DAOLOOK"}</h2><p>${register ? "用邮箱创建账号，开启有依据的创作。" : "登录后，继续你的下一次好创作。"}</p><form id="login-form">${field("邮箱地址", "email", "", "email")}${field("密码（至少 8 位）", "password", "", "password")}<div id="login-error" class="inline-error"></div><button type="submit" class="btn primary full">${register ? "创建账号" : "邮箱登录"} ${icon("arrow")}</button></form><div class="actions"><button class="text-btn" data-action="toggle-login">${register ? "已有账号？去登录" : "还没有账号？免费注册"}</button>${S.publicMode === "demo" ? '<button class="text-btn" data-action="demo">体验演示空间 →</button>' : ""}</div></div></section></div>`;
}
async function navigate(page) {
  S.page = page;
  S.creationSource = null;
  location.hash = page;
  render();
  if (page === "credits") {
    S.ledger = await api("/api/credits");
    render();
  }
  if (page === "admin") {
    S.admin = await api("/api/admin");
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
  let attempts = 0;
  const check = async () => {
    try {
      await refresh();
      const relevant = S.tasks.filter((t) => ids.includes(t.id));
      if (
        relevant.length === ids.length &&
        relevant.every((t) =>
          ["SUCCEEDED", "FAILED", "CANCELLED"].includes(t.state),
        )
      ) {
        S.watching = null;
        S.busy = false;
        render();
        const success = relevant.filter((t) => t.state === "SUCCEEDED");
        if (success.length) await done(success);
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
      S.busy = false;
      toast(e.message);
      render();
    }
  };
  setTimeout(check, 500);
}
async function startAnalyze() {
  const text = $("#reference").value.trim();
  if (!text) {
    toast("请先输入参考链接或关键词");
    return;
  }
  S.entryText = text;
  S.busy = true;
  const platform = $("#keyword-platform")?.value || "xhs";
  render();
  try {
    const r = await post(
      "/api/analyze",
      body({ entry: S.entry, text, platform }),
    );
    toast("拆解已开始，可在任务记录查看进度");
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
    S.busy = false;
    render();
    toast(e.message);
  }
}
async function startCreate() {
  if (S.imageUploading) throw new Error("图片正在上传，请完成后再生成");
  S.requirements = $("#requirements").value;
  S.temporary = $("#temporary").value;
  S.selectedAssets = $$("input[name=asset]:checked").map((x) => x.value);
  S.busy = true;
  render();
  try {
    const r = await post(
      "/api/create",
      body({
        source_id: S.detail,
        requirements: S.requirements,
        temporary: S.temporary,
        assets: S.selectedAssets,
      }),
    );
    toast("正在创作 3 个独立方案…");
    await poll(r.task_ids, async () => {
      S.creationSource = S.detail;
      S.page = "creations";
      location.hash = "creations";
      render();
      toast("3 条新稿件已追加，历史版本完整保留");
      if (S.temporary.trim())
        modal(
          "保存本次临时资料？",
          `<p class="subtext">这份资料可以留作下一次创作的参考，也可以仅用于本次任务。</p>${field("资料名称", "temporary-name", "本次创作补充资料")}<div class="actions">${button("保存到项目", "save-temporary", "primary", "folder")}${button("仅本次使用", "close", "secondary")}</div>`,
        );
    });
  } catch (e) {
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
      "从参考，到自己的表达",
      `<div class="analysis-section"><span class="num">01</span><div><h3>找到依据</h3><p>粘贴小红书 / 抖音链接，或搜索博主与关键词。</p></div></div><div class="analysis-section"><span class="num">02</span><div><h3>看懂内容</h3><p>浏览平台专属拆解，值得复用的参考再收藏。</p></div></div><div class="analysis-section"><span class="num">03</span><div><h3>创作自己的版本</h3><p>按需选择项目资料，每次生成 3 条独立新稿。可以重复创作，历史结果不会覆盖。</p></div></div><div class="analysis-section"><span class="num">04</span><div><h3>让表达落地</h3><p>选择封面方向，复制文案，或导出 Excel / CSV 到飞书表格。</p></div></div>`,
    ),
  account: () =>
    modal(
      "账号与工作空间",
      `<p class="subtext">${esc(S.boot.user.email.startsWith("demo-") ? "当前为本地演示空间，数据保存在这台设备的服务中。" : S.boot.user.email)}</p><div class="actions">${button("切换账号 / 退出", "logout", "secondary", "logout")}</div>`,
    ),
  logout: async () => {
    await post("/api/auth/logout", {});
    close();
    S.boot = null;
    S.ledger = null;
    S.admin = null;
    S.publicMode = (await api("/api/public")).mode;
    login();
  },
  demo: async () => {
    await post("/api/auth/demo", {});
    await bootstrap();
    render();
  },
  "toggle-login": () => login(!S.loginRegister),
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
  "all-creations": () => {
    S.creationSource = null;
    render();
  },
  copy: async (el) => {
    const c = S.workspace.creations.find((c) => c.id === el.dataset.id);
    await navigator.clipboard.writeText(
      [
        c.data.title,
        c.data.hook,
        c.data.body,
        (c.data.tags || []).map((t) => "#" + t).join(" "),
        ...(c.data.storyboard || []),
        ...(c.data.shooting_list || []),
      ]
        .filter(Boolean)
        .join("\n\n"),
    );
    toast("文案已复制");
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
    else await navigate(t.kind === "analyze" ? "discover" : "creations");
  },
  grant: (el) => {
    S.grantUser = el.dataset.id;
    modal(
      "发放创作积分",
      `<form id="grant-form">${field("发放数量", "grant-amount", 100, "number")}<button class="btn primary full" type="submit">确认发放</button></form>`,
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
    if (e.target.id === "analyze-form") return await startAnalyze();
    if (e.target.id === "create-form") return await startCreate();
    if (submit) submit.disabled = true;
    switch (e.target.id) {
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
        await post("/api/auth/" + (S.loginRegister ? "register" : "login"), {
          email: $("#email").value,
          password: $("#password").value,
        });
        await bootstrap();
        S.page = "discover";
        render();
        break;
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
      case "grant-form":
        await post("/api/admin/grant", {
          user_id: S.grantUser,
          amount: Number($("#grant-amount").value),
        });
        close();
        S.admin = await api("/api/admin");
        await refresh();
        render();
        toast("积分已发放");
        break;
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
            enabled: $("#provider-enabled").checked,
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
          },
          limits: {
            ...c.limits,
            batch: Number($("#batch-limit").value),
            timeout: Number($("#timeout").value),
            retries: Number($("#retries").value),
            temporary_ttl_hours: Number($("#temporary-ttl").value),
          },
          ranking: JSON.parse($("#ranking").value),
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
    else toast(error.message);
  } finally {
    if (submit) submit.disabled = false;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "reference") {
    S.entryText = e.target.value;
    const cost = $("#entry-cost");
    if (cost)
      cost.textContent = `预计 ${S.boot.rules.analyze * (S.entry === "batch" ? Math.max(1, S.entryText.split("\n").filter((x) => x.trim()).length) : 1)} 积分${S.entry === "batch" ? " · 逐条结算" : ""} · 失败自动退还`;
  }
  if (e.target.id === "requirements") S.requirements = e.target.value;
  if (e.target.id === "temporary") S.temporary = e.target.value;
});
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
  const isCover = input.id === "cover-photo-file",
    project = S.project;
  const creation = S.coverId;
  if (!isCover) {
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
    if (["creation-photo-file", "cover-photo-file"].includes(e.target.id))
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
    if (e.target.id === "asset-file" || e.target.id === "temporary-file") {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 2 * 1024 * 1024) throw new Error("文件最大支持 2 MB");
      if (e.target.id === "temporary-file") {
        $("#temporary").value = await f.text();
        S.temporary = $("#temporary").value;
      } else {
        if (!$("#asset-name").value) $("#asset-name").value = f.name;
        if (f.type.startsWith("image/")) {
          const reader = new FileReader();
          reader.onload = () => {
            $("#asset-content").value = reader.result;
            $("#asset-kind").value = "图片";
          };
          reader.readAsDataURL(f);
        } else $("#asset-content").value = await f.text();
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
    S.publicMode = (await api("/api/public")).mode;
    try {
      await bootstrap();
    } catch (error) {
      if (error.message !== "请先登录") throw error;
      if (S.publicMode === "demo") {
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
      (t) => !["SUCCEEDED", "FAILED", "CANCELLED"].includes(t.state),
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
