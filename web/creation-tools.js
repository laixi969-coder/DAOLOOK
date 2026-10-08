/* Observable preparation signals, not predicted engagement. */
(function (root) {
  'use strict';
  const fields = ['title', 'body', 'cover_text', 'hook', 'cta'];
  function editable(data) {
    const value = Object.fromEntries(fields.map(key => [key, data[key] || '']));
    value.tags = [...(data.tags || [])];
    if (data.comment_layout) value.comments = {
      atmosphere: (data.comment_layout.atmosphere || []).join('\n'),
      knowledge: (data.comment_layout.knowledge || []).join('\n'),
      pinned: data.comment_layout.pinned?.text || '',
    };
    return value;
  }
  function publicCopy(data) {
    return [data.title, data.body, (data.tags || []).map(t => '#' + t).join(' ')].filter(Boolean).join('\n\n');
  }
  function fingerprint(value) {
    return JSON.stringify([...fields.map(key => value[key] || ''), value.tags || [],
      value.comments ? ['atmosphere','knowledge','pinned'].map(key => value.comments[key] || '') : null]);
  }
  function shortlist(items, workspace) {
    const first = items.find(c => c.tracking?.status !== 'published');
    if (!first) return null;
    const batch = items.filter(c => c.tracking?.status !== 'published' &&
      (first.task_id ? c.task_id === first.task_id : c.id === first.id));
    const facts = c => {
      const hasCover = workspace.images.some(i => i.creation_id === c.id);
      const hasPhoto = (c.data.image_asset_ids || []).some(id => workspace.assets.some(a => a.id === id && a.kind === '图片'));
      const q = c.data.quality;
      const issues = q?.issues?.length || 0;
      const readiness = q?.status === 'checked' ? 3 : q?.status === 'review' ? 2 : q ? 0 : 1;
      return {c, hasCover, hasPhoto, issues, readiness};
    };
    const ranked = batch.map(facts).sort((a,b) => b.readiness-a.readiness || a.issues-b.issues || Number(b.hasCover)-Number(a.hasCover) || Number(b.hasPhoto)-Number(a.hasPhoto));
    const best = ranked[0];
    const reasons = [best.c.data.quality?.status === 'checked' ? '已通过基础交付检查' : best.c.data.quality?.status === 'review' ? '已有手动编辑稿，事实仍需核对' : best.issues ? `这篇仍有 ${best.issues} 项待核对，是本批待补项较少的稿件` : '本批暂时没有足够的检查信息，先从这篇核对'];
    if (best.hasCover) reasons.push('已保存封面，可在下方下载');
    else if (best.hasPhoto) reasons.push('关联的产品或人物照片仍可用于制作封面');
    const picks = [best.c];
    const angle = c => [c.data.direction, c.data.angle].filter(Boolean).join(':');
    for (const {c} of ranked.slice(1)) {
      if (picks.length === 3) break;
      if (angle(c) && !picks.some(p => angle(p) === angle(c))) picks.push(c);
    }
    return {main: best.c, alternatives: picks.slice(1), rest: items.filter(c => !picks.includes(c)), reasons};
  }
  function createEditStore(storage, now = Date.now) {
    const prefix = 'daolook-edit:';
    const clean = changes => {
      const value = editable(changes);
      if (changes.comments) value.comments = Object.fromEntries(
        ['atmosphere','knowledge','pinned'].map(k => [k, String(changes.comments[k] || '').slice(0,4000)]));
      return value;
    };
    return {
      save(key, revision, changes) {
        try { storage.setItem(prefix+key, JSON.stringify({at:now(), revision, changes:clean(changes)})); return true; } catch { return false; }
      },
      read(key) {
        try {
          const value = JSON.parse(storage.getItem(prefix+key));
          if (!value || !Number.isFinite(value.at) || value.at > now() || now()-value.at > 86400000 || !Number.isInteger(value.revision) || !value.changes || typeof value.changes.body !== 'string') { this.remove(key); return null; }
          return value;
        } catch { return null; }
      },
      remove(key) { try { storage.removeItem(prefix+key); } catch {} },
      clearUser(user) { try {for(let i=storage.length-1;i>=0;i--){const key=storage.key(i);if(key?.startsWith(prefix+user+':'))storage.removeItem(key);}}catch{} },
    };
  }
  const tools = {editable, publicCopy, fingerprint, shortlist, createEditStore};
  if (typeof module !== 'undefined') module.exports = tools;
  else root.CreationTools = tools;
})(typeof window !== 'undefined' ? window : this);
