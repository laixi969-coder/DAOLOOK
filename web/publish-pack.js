/* Store lossless PNGs and UTF-8 text in a standard ZIP; PNGs are already compressed. */
(function () {
  'use strict';
  const utf8 = new TextEncoder();
  const crcTable = Uint32Array.from({length: 256}, (_, index) => {
    let value = index;
    for (let bit = 0; bit < 8; bit++) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    return value >>> 0;
  });

  function zip(entries) {
    const blocks = [], directory = [];
    let offset = 0, directorySize = 0;
    for (const [name, bytes] of entries) {
      const filename = utf8.encode(name);
      let crc = 0xffffffff;
      for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8);
      crc = (crc ^ 0xffffffff) >>> 0;
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034b50, true);
      local.setUint16(4, 20, true);
      local.setUint16(6, 0x0800, true); // UTF-8 names, no data descriptor.
      local.setUint16(12, 0x21, true); // 1980-01-01, the earliest DOS date.
      local.setUint32(14, crc, true);
      local.setUint32(18, bytes.length, true);
      local.setUint32(22, bytes.length, true);
      local.setUint16(26, filename.length, true);
      blocks.push(local.buffer, filename, bytes);
      const central = new DataView(new ArrayBuffer(46));
      central.setUint32(0, 0x02014b50, true);
      central.setUint16(4, 20, true);
      new Uint8Array(central.buffer).set(new Uint8Array(local.buffer).subarray(4), 6);
      central.setUint32(42, offset, true);
      directory.push(central.buffer, filename);
      directorySize += 46 + filename.length;
      offset += 30 + filename.length + bytes.length;
    }
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true);
    end.setUint16(8, entries.length, true);
    end.setUint16(10, entries.length, true);
    end.setUint32(12, directorySize, true);
    end.setUint32(16, offset, true);
    return new Blob([...blocks, ...directory, end.buffer], {type:'application/zip'});
  }

  if (typeof module !== 'undefined') {
    module.exports = {zip};
    return;
  }

  actions['publish-pack'] = async el => {
    const project = S.project, workspace = workspaceKey();
    const {id, revision} = el.dataset;
    const path = '/api/creations/' + id + '/publish-pack?project_id=' + encodeURIComponent(project) +
      '&revision=' + encodeURIComponent(revision);
    modal('小红书图文发布包', '<div id="publish-pack" aria-live="polite">正在准备预览…</div>', true);
    const panel = $('#publish-pack');
    let request = 0;
    const current = token => panel.isConnected && workspaceKey() === workspace && token === request;

    async function preview(photo) {
      const token = ++request;
      const url = path + (photo ? '&photo=' + encodeURIComponent(photo) : '');
      panel.textContent = '正在准备预览…';
      try {
        const pack = await api(url);
        if (!current(token)) return;
        const options = pack.choices.map(a => `<option value="${esc(a.id)}" ${a.id === photo?'selected':''}>${esc(a.name)}</option>`).join('');
        const select = pack.choices.length ? `<label class="field"><span>项目实拍图</span><select id="pack-photo"><option value="">${pack.pages.length && !photo ? '沿用稿件所选照片' : '选择照片'}</option>${options}</select></label>` : '';
        panel.innerHTML = select;
        const picker = panel.querySelector('select');
        if (picker) picker.onchange = () => preview(picker.value);
        if (!pack.pages.length) {
          if (pack.needs_edit) {
            panel.insertAdjacentHTML('beforeend', `<p>${esc(pack.notice)}</p><button type="button" class="btn secondary">打开稿件</button>`);
            panel.querySelector('button').onclick = () => { close(); openDraftEditor(id).catch(e => toast(e.message)); };
          } else if (!pack.choices.length) panel.insertAdjacentHTML('beforeend','<p>请先在项目资料中上传实拍图。</p>');
          return;
        }
        const copy = CreationTools.publicCopy(pack.copy);
        const names = ['封面', '内页一', '内页二'];
        const urls = pack.pages.map(page => {
          const photoData = pack.images[page.photo];
          const svg = page.svg.replace('xlink:href="daolook-pack-photo"', () => 'xlink:href="' + photoData + '"');
          return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
        });
        const images = urls.map((url,i) => `<figure><button type="button" class="pack-zoom" aria-label="放大${names[i]}" aria-pressed="false"><img src="${esc(url)}" alt="${names[i]}"></button><figcaption>${names[i]}</figcaption></figure>`).join('');
        panel.insertAdjacentHTML('beforeend', `${pack.demo ? '<p class="notice">当前为演示稿件。</p>' : ''}<div class="pack-pages">${images}</div><details><summary>正文与话题</summary><p class="draft-body">${esc(copy)}</p></details><div class="actions"><button type="button" class="btn primary" id="pack-download">下载图文发布包 ZIP</button><button type="button" class="btn secondary" id="pack-copy">复制正文</button></div><p class="inline-error" role="status"></p>`);
        for (const zoom of panel.querySelectorAll('.pack-zoom')) zoom.onclick = () => {
          const enlarged = zoom.closest('figure').classList.toggle('enlarged');
          zoom.closest('.pack-pages').classList.toggle('zoomed', enlarged);
          zoom.setAttribute('aria-pressed', String(enlarged));
          zoom.setAttribute('aria-label', (enlarged ? '缩小' : '放大') + zoom.firstElementChild.alt);
        };
        panel.querySelector('#pack-copy').onclick = async () => {
          try {
            await navigator.clipboard.writeText(copy);
            toast('已复制正文与话题');
          } catch {
            if (current(token)) panel.querySelector('.inline-error').textContent = '请展开正文与话题后选择文字复制。';
          }
        };
        const download = panel.querySelector('#pack-download');
        download.onclick = async () => {
          download.disabled = true;
          const errorBox = panel.querySelector('.inline-error');
          errorBox.textContent = '';
          try {
            const entries = [];
            for (const [i, source] of urls.entries()) {
              if (!current(token)) return;
              const blob = await rasterizeCover(source, 'png');
              entries.push([String(i+1) + '-' + names[i] + '.png', new Uint8Array(await blob.arrayBuffer())]);
            }
            entries.push(['正文.txt', utf8.encode(copy)]);
            const checked = await api(url + '&check=' + encodeURIComponent(pack.state));
            if (!checked.ok) throw new Error('稿件或照片已变更，请重新预览');
            if (!current(token)) return;
            const href = URL.createObjectURL(zip(entries));
            const link = document.createElement('a');
            link.href = href;
            link.download = '小红书图文-' + id.slice(0,8) + '-v' + revision + '.zip';
            link.click();
            setTimeout(() => URL.revokeObjectURL(href), 60000);
          } catch (error) {
            if (current(token)) errorBox.textContent = error.message;
          } finally {
            if (current(token)) download.disabled = false;
          }
        };
      } catch (error) {
        if (current(token)) panel.textContent = error.message;
      }
    }
    await preview('');
  };
})();
