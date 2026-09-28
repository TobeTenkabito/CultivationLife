/* Portable bearer codes: DEFLATE -> AES-256-GCM -> base64url. No external service. */
(() => {
  'use strict';
  const PREFIX = 'FSWD1.', PART = 'FSWDP1', CHUNK = 100000, MAX_CODE = 17 * 1024 * 1024;
  const aad = new TextEncoder().encode('浮生问道 / FSWD1 / deflate / AES-256-GCM');
  const base64 = bytes => {
    let text = '';
    for (let i = 0; i < bytes.length; i += 8192) text += String.fromCharCode(...bytes.subarray(i, i + 8192));
    return btoa(text);
  };
  const unbase64 = text => Uint8Array.from(atob(text), ch => ch.charCodeAt(0));
  async function encode(payload) {
    if (!crypto.subtle) throw new Error('当前浏览器不支持存档加密，请使用游戏本地入口。');
    const keyBytes = crypto.getRandomValues(new Uint8Array(32));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['encrypt']);
    const encrypted = new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM', iv, additionalData:aad}, key, unbase64(payload)));
    const packet = new Uint8Array(44 + encrypted.length);
    packet.set(keyBytes); packet.set(iv, 32); packet.set(encrypted, 44);
    return PREFIX + base64(packet).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  async function decode(text) {
    const code = text.replace(/\s/g, '');
    if (code.length > MAX_CODE || !/^FSWD1\.[A-Za-z0-9_-]+$/.test(code)) throw new Error('存档码格式不正确，请完整复制 FSWD1 开头的文本。');
    try {
      const packet = unbase64(code.slice(PREFIX.length).replace(/-/g, '+').replace(/_/g, '/'));
      if (packet.length < 61) throw new Error('short');
      const key = await crypto.subtle.importKey('raw', packet.slice(0, 32), 'AES-GCM', false, ['decrypt']);
      const raw = await crypto.subtle.decrypt({name:'AES-GCM', iv:packet.slice(32, 44), additionalData:aad}, key, packet.slice(44));
      return base64(new Uint8Array(raw));
    } catch (_) { throw new Error('存档码不完整或校验失败，请重新复制。'); }
  }
  async function split(code, size = CHUNK) {
    if (code.length <= size) return [code];
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(code)));
    const id = [...digest.slice(0, 12)].map(b => b.toString(16).padStart(2, '0')).join('');
    const count = Math.ceil(code.length / size), parts = [];
    for (let i = 0; i < count; i++) parts.push(`${PART}.${id}.${i+1}.${count}.${code.slice(i*size,(i+1)*size)}`);
    return parts;
  }
  class Collector {
    constructor() { this.reset(); }
    reset() { this.id = ''; this.count = 0; this.parts = new Map(); }
    async add(text) {
      if (typeof text !== 'string' || text.length > MAX_CODE + 200000) throw new Error('存档文本过长。');
      const compact = text.replace(/\s/g, '');
      if (compact.startsWith(PREFIX)) { this.reset(); return compact; }
      const rows = compact.match(/FSWDP1\.[a-f0-9]{24}\.\d+\.\d+\.[A-Za-z0-9_.-]+?(?=FSWDP1\.|$)/g);
      if (!rows || rows.join('') !== compact) throw new Error('请输入完整存档码，或 FSWDP1 开头的分段。');
      const next = new Map(this.parts); let id = this.id, count = this.count;
      for (const row of rows) {
        const match = /^FSWDP1\.([a-f0-9]{24})\.(\d+)\.(\d+)\.(.+)$/.exec(row);
        const [, fingerprint, number, total, body] = match; const n = Number(number), t = Number(total);
        if (n < 1 || n > t || t < 2 || t > 180 || body.length > CHUNK || (id && id !== fingerprint) || (count && count !== t)) throw new Error('分段不属于同一份存档，请清空后重新粘贴。');
        if (next.has(n) && next.get(n) !== body) throw new Error('重复分段内容不一致。');
        id = fingerprint; count = t; next.set(n, body);
      }
      if ([...next.values()].reduce((sum, part) => sum + part.length, 0) > MAX_CODE) throw new Error('存档文本过长。');
      this.id = id; this.count = count; this.parts = next;
      if (next.size !== count) return null;
      const code = Array.from({length:count}, (_, i) => next.get(i+1)).join('');
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(code)));
      const actual = [...digest.slice(0,12)].map(b=>b.toString(16).padStart(2,'0')).join('');
      if (actual !== id) throw new Error('分段拼合校验失败，请重新复制。');
      return code;
    }
  }
  window.SaveCode = {encode, decode, split, Collector};

  const dialog = document.createElement('dialog'); dialog.id = 'save-transfer-dialog'; dialog.className = 'save-transfer-dialog';
  dialog.setAttribute('aria-labelledby', 'transfer-title');
  dialog.innerHTML = `<div class="transfer-heading"><div><p class="eyebrow">一卷藏生涯</p><h2 id="transfer-title">存档传承</h2></div><button type="button" id="transfer-close">关闭</button></div>
    <p id="transfer-help" class="muted"></p><p id="transfer-status" role="status" aria-live="polite"></p>
    <label class="transfer-label" for="transfer-code">存档码</label><textarea id="transfer-code" spellcheck="false" autocapitalize="off" autocomplete="off" aria-label="存档码"></textarea>
    <div id="transfer-paging" class="transfer-actions hidden"><button type="button" id="transfer-prev">上一段</button><span id="transfer-page"></span><button type="button" id="transfer-next">下一段</button></div>
    <div class="transfer-actions"><button type="button" id="transfer-copy">复制存档码</button><button type="button" id="transfer-paste">从剪贴板粘贴</button><button type="button" id="transfer-preview">预览存档</button><button type="button" id="transfer-clear">清空重来</button></div>
    <section id="transfer-preview-card" class="transfer-preview hidden"></section>
    <div id="transfer-confirm" class="hidden"><label class="transfer-replace hidden"><input type="checkbox" id="transfer-replace-check"><span>我确认用此进度替换本机的同一存档</span></label><button type="button" id="transfer-import" class="primary">恢复存档</button></div><button type="button" id="transfer-play" class="primary hidden">进入恢复的存档</button>`;
  document.body.appendChild(dialog);
  const el = id => dialog.querySelector(`#transfer-${id}`);
  let working = false, mode = '', parts = [], page = 0, packed = '', preview = null, collector = new Collector();
  function status(message, error = false) { el('status').textContent = message; el('status').classList.toggle('error', error); }
  function lock(value) {
    working = value;
    dialog.querySelectorAll('button').forEach(button => { button.disabled = value; });
    el('code').readOnly = value || mode === 'export';
    el('replace-check').disabled = value;
    if (!value) { el('prev').disabled = page === 0; el('next').disabled = page >= parts.length - 1; syncConfirm(); }
  }
  function syncConfirm() { el('import').disabled = working || !preview || (!!preview.existing_hash && !el('replace-check').checked); }
  function resetPreview() { packed = ''; preview = null; el('preview-card').classList.add('hidden'); el('confirm').classList.add('hidden'); el('replace-check').checked = false; }
  function open(which) {
    if (working || busy) return false;
    mode = which; parts = []; page = 0; collector.reset(); resetPreview(); el('code').value = ''; status(''); el('play').classList.add('hidden');
    el('title').textContent = which === 'export' ? '封存此生' : '续接前缘';
    el('help').textContent = which === 'export' ? '复制存档码并妥善保存。持有完整存档码即可恢复此刻的进度。' : '粘贴完整存档码，或逐段粘贴并收录。导入前会显示角色信息供你核对。';
    el('copy').classList.toggle('hidden', which !== 'export');
    ['paste','preview','clear'].forEach(id => el(id).classList.toggle('hidden', which !== 'import'));
    el('paging').classList.add('hidden'); lock(false); dialog.showModal(); return true;
  }
  function renderPart() {
    el('code').value = parts[page] || ''; el('page').textContent = `第 ${page+1} / ${parts.length} 段`;
    el('copy').textContent = parts.length > 1 ? `复制第 ${page+1} 段` : '复制存档码';
    el('paging').classList.toggle('hidden', parts.length < 2); lock(false);
  }
  async function exportSave(id) {
    if (!open('export')) return;
    lock(true); status('正在压缩与封存，请稍候……');
    try {
      const data = await api('/api/save-transfer/export', {method:'POST', body:JSON.stringify({id})});
      const code = await encode(data.payload); parts = await split(code); renderPart();
      status(`${data.name} · 原存档 ${(data.original_bytes/1024/1024).toFixed(2)} MB → ${Math.ceil(code.length/1024)} KB 存档码${parts.length>1 ? ` · 共 ${parts.length} 段，请逐段保存` : ''}`);
    } catch (error) { status(error.message, true); }
    finally { lock(false); }
  }
  async function previewCode() {
    if (working) return; lock(true); resetPreview(); status('正在校验存档……');
    try {
      const code = await collector.add(el('code').value);
      if (!code) { el('code').value = ''; status(`已收录 ${collector.parts.size} / ${collector.count} 段，请粘贴下一段。`); return; }
      packed = await decode(code);
      preview = await api('/api/save-transfer/preview', {method:'POST', body:JSON.stringify({payload:packed})});
      const card = el('preview-card'); card.replaceChildren();
      const title = document.createElement('h3'); title.textContent = preview.name;
      const desc = document.createElement('p'); desc.textContent = `${preview.realm} · ${preview.layer} 层 · ${preview.age} 岁 · ${preview.path} · ${preview.world}`;
      const meta = document.createElement('p'); meta.textContent = `本体 v${preview.version} · 履历 ${preview.history_count} 条`;
      const note = document.createElement('p'); note.textContent = preview.existing_hash ? '本机已有同一存档。恢复将替换其进度，原进度会保留为备份；其它角色不受影响。' : '将新增此角色的存档，其它角色不受影响。';
      card.append(title, desc, meta, note);
      if (preview.missing_extensions.length) { const warning = document.createElement('p'); warning.textContent = '此存档含当前未启用的 DLC / MOD。相关数据会保留，建议启用原扩展后继续游玩。'; card.appendChild(warning); }
      card.classList.remove('hidden'); el('confirm').classList.remove('hidden');
      dialog.querySelector('.transfer-replace').classList.toggle('hidden', !preview.existing_hash);
      status('校验通过，请核对后恢复。');
    } catch (error) { resetPreview(); status(error.message, true); }
    finally { lock(false); }
  }
  el('import').onclick = async () => {
    if (working || !preview || (preview.existing_hash && !el('replace-check').checked)) return;
    lock(true); status('正在恢复存档……');
    try {
      const result = await api('/api/save-transfer/import', {method:'POST', body:JSON.stringify({payload:packed, existing_hash:preview.existing_hash})});
      renderSaveList((await api('/api/games')).games);
      if (game?.id === result.id) { game = null; showStart(); }
      status(`「${result.name}」已恢复，可从存档列表续接。`);
      resetPreview(); el('code').value = ''; collector.reset();
      el('play').classList.remove('hidden');
      el('play').onclick = () => { if (!working) { dialog.close(); loadGame(result.id); } };
    } catch (error) { status(error.message, true); }
    finally { lock(false); }
  };
  el('copy').onclick = async () => {
    try {
      const text = parts[page]; if (!text) throw new Error('请先生成存档码。');
      if (window.AndroidGame?.copySaveCode) { if (!AndroidGame.copySaveCode(text)) throw new Error('剪贴板写入失败，请长按文本复制。'); }
      else if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else { el('code').select(); if (!document.execCommand('copy')) throw new Error('请选中文本后复制。'); }
      status(parts.length > 1 ? `第 ${page+1} 段已复制，共 ${parts.length} 段。` : '存档码已复制。');
    } catch (error) { status(error.message, true); }
  };
  el('paste').onclick = async () => {
    try {
      const text = window.AndroidGame?.readSaveCode ? AndroidGame.readSaveCode() : await navigator.clipboard.readText();
      if (!text) throw new Error('剪贴板为空或不可读取，请长按文本框粘贴。');
      resetPreview(); el('code').value = text; status('已粘贴，点击预览存档以收录并校验。');
    } catch (_) { status('请长按文本框或使用 Ctrl+V 粘贴存档码。', true); el('code').focus(); }
  };
  el('prev').onclick = () => { page--; renderPart(); }; el('next').onclick = () => { page++; renderPart(); };
  el('preview').onclick = previewCode;
  el('replace-check').onchange = syncConfirm;
  el('code').addEventListener('input', resetPreview);
  el('clear').onclick = () => { collector.reset(); resetPreview(); el('code').value = ''; el('play').classList.add('hidden'); status('已清空，可以粘贴另一份存档。'); };
  el('close').onclick = () => { if (!working) dialog.close(); };
  dialog.addEventListener('cancel', event => { if (working) event.preventDefault(); });
  dialog.addEventListener('close', () => { if (!working) { parts = []; collector.reset(); resetPreview(); el('code').value = ''; } });
  window.SaveTransfer = {exportSave, openImport:() => open('import'), isWorking:() => working};
  document.querySelectorAll('[data-save-import]').forEach(button => button.onclick = () => open('import'));
  document.querySelector('[data-save-export-current]').onclick = () => { if (game && !busy) exportSave(game.id); };
})();
