/* Optional developer UI. All commands and completion metadata come from the registry. */
(() => {
  'use strict';
  let sessionId = sessionStorage.getItem('cultivation-debug-session') || '';
  let catalog = [], history = [], cursor = 0, hooks, enabled = false, initialized = false;
  let panel, output, input, badge, entry, importInput;
  let nativeImportParts = [];
  const node = (tag, text, id) => {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (id) element.id = id;
    return element;
  };
  function print(value, error = false) {
    const line = node('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2));
    if (line.textContent.length > 18000) line.textContent = line.textContent.slice(0, 18000) + '\n… output truncated';
    line.classList.toggle('debug-error', error);
    output.append(line);
    while (output.children.length > 100) output.firstChild.remove();
    output.scrollTop = output.scrollHeight;
  }
  function updateBadge() {
    badge.hidden = !sessionId;
    badge.textContent = sessionId ? `DEBUG · 独立副本 ${sessionId.slice(0, 8)} · 点击返回控制台` : '';
    entry.hidden = !enabled && !sessionId;
  }
  function setSession(value) {
    sessionId = value || '';
    if (sessionId) sessionStorage.setItem('cultivation-debug-session', sessionId);
    else sessionStorage.removeItem('cultivation-debug-session');
    updateBadge();
  }
  async function execute(command, bundle) {
    if (hooks.busy()) { print('请等待当前游戏操作完成。', true); return; }
    hooks.lock(true);
    input.disabled = true;
    print('> ' + command);
    let switched = false;
    try {
      const response = await fetch('/api/debug/command', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({command, game_id: hooks.gameId(), session_id: sessionId || null, bundle}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Debug request failed.');
      catalog = result.catalog || catalog;
      const data = result.data;
      if (data && Object.prototype.hasOwnProperty.call(data, 'session_id') && result.type === 'session') {
        setSession(data.session_id);
        switched = true;
      }
      if (data?.download) offerDownload(data.download);
      else print(data);
      if (result.diff?.total) print(result.diff);
      if (data?.return_to_title) hooks.reset();
      // Query commands must remain pure: do not follow them with a gameplay GET.
      if (!data?.return_to_title && (result.changed || result.type === 'session') && (data?.game_id || hooks.gameId())) {
        await hooks.refresh(data?.game_id || hooks.gameId());
      }
    } catch (error) {
      print(error.message, true);
      if (switched) hooks.reset();
    }
    finally { hooks.lock(false); input.disabled = false; input.focus(); }
  }
  function offerDownload(download) {
    const wrap = node('div');
    if (window.AndroidGame?.exportDebugBundle) {
      const save = node('button', '保存复现包到文件'); save.type = 'button';
      save.onclick = () => window.AndroidGame.exportDebugBundle(download.content);
      wrap.append(save); output.append(wrap);
      print('使用系统文件选择器保存。导入后可 snapshot restore last_before，再手动重试。');
      return;
    }
    const url = URL.createObjectURL(new Blob([download.content], {type: 'application/json'}));
    const link = node('a', `下载 ${download.filename}`);
    link.href = url; link.download = download.filename;
    link.onclick = () => setTimeout(() => URL.revokeObjectURL(url), 60000);
    const copy = node('button', '复制复现包');
    copy.type = 'button';
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(download.content);
        print('复现包已复制。');
      } catch (error) { print(error.message, true); }
    };
    wrap.append(link, copy); output.append(wrap);
    print('包含完整角色数据、临时覆盖和最近操作。导入后可 snapshot restore last_before，再手动重试。');
  }
  function complete() {
    const text = input.value;
    let candidates = catalog.map(row => row.name).filter(name => name.startsWith(text));
    for (const row of catalog) {
      const prefix = row.name + ' ';
      if (!text.startsWith(prefix)) continue;
      const args = text.slice(prefix.length).split(/\s+/);
      const argument = row.arguments[args.length - 1];
      if (!argument) continue;
      const start = prefix + (args.length > 1 ? args.slice(0, -1).join(' ') + ' ' : '');
      candidates.push(...argument.choices.filter(value => value.startsWith(args.at(-1))).map(value => start + value));
    }
    candidates = [...new Set(candidates)];
    if (candidates.length === 1) input.value = candidates[0] + ' ';
    else if (candidates.length) print(candidates.join('\n'));
  }
  function open() {
    if (!enabled && !sessionId) return;
    panel.showModal(); input.focus();
    if (!catalog.length && enabled) execute('help');
  }
  function initialize() {
    initialized = true;
    const css = node('link'); css.rel = 'stylesheet'; css.href = '/debug-console.css'; document.head.append(css);
    entry = node('button', '开发者控制台', 'debug-console-open'); entry.type = 'button'; entry.onclick = open;
    badge = node('button', '', 'debug-session-banner'); badge.type = 'button'; badge.onclick = open;
    panel = node('dialog', '', 'debug-console'); panel.setAttribute('aria-labelledby', 'debug-console-title');
    const heading = node('header'); heading.append(node('h2', 'Developer Console', 'debug-console-title'));
    const close = node('button', '关闭'); close.type = 'button'; close.onclick = () => panel.close(); heading.append(close);
    const description = node('p', 'debug start 复制当前角色；scenario list 查看测试开局。game view 获取操作选项，state get 只读存档。所有修改仅作用于独立副本。');
    const actions = node('div'); actions.className = 'debug-actions';
    for (const [label, command] of [['创建调试副本', 'debug start'], ['退出调试副本', 'debug stop'], ['帮助', 'help'], ['功能清单', 'capability list'], ['开局预设', 'scenario list'], ['导出复现包', 'repro export']]) {
      const button = node('button', label); button.type = 'button'; button.onclick = () => execute(command); actions.append(button);
    }
    const detach = node('button', '断开会话'); detach.type = 'button';
    detach.title = '调试被关闭或会话损坏时，仅清除本标签页的会话连接，返回标题页。';
    detach.onclick = () => { if (!hooks.busy()) { setSession(''); panel.close(); hooks.leave(); } };
    actions.append(detach);
    importInput = node('input'); importInput.type = 'file'; importInput.accept = '.json,application/json'; importInput.hidden = true;
    importInput.onchange = async () => {
      const file = importInput.files[0];
      if (file) {
        try {
          if (file.size > 64 * 1024 * 1024) throw new Error('复现包超过 64 MiB。');
          await execute('repro import', JSON.parse(await file.text()));
        } catch (error) { print(error.message, true); }
      }
      importInput.value = '';
    };
    const importButton = node('button', '导入复现包'); importButton.type = 'button';
    importButton.onclick = () => window.AndroidGame?.importDebugBundle ? window.AndroidGame.importDebugBundle() : importInput.click();
    const pasteButton = node('button', '粘贴复现包'); pasteButton.type = 'button';
    pasteButton.onclick = async () => {
      try {
        const text = window.AndroidGame?.readSaveCode ? window.AndroidGame.readSaveCode() : await navigator.clipboard.readText();
        await execute('repro import', JSON.parse(text));
      } catch (error) { print(error.message, true); }
    };
    actions.append(importButton, pasteButton, importInput);
    output = node('div', '', 'debug-console-output'); output.setAttribute('role', 'log'); output.setAttribute('aria-live', 'polite');
    const form = node('form'); const label = node('label', 'Command'); label.htmlFor = 'debug-console-input';
    input = node('input', '', 'debug-console-input'); input.autocomplete = 'off'; input.spellcheck = false;
    input.setAttribute('autocapitalize', 'none'); input.placeholder = 'player set spirit_stones 100000'; input.maxLength = 2048;
    const submit = node('button', '执行'); submit.type = 'submit';
    form.append(label, input, submit);
    form.onsubmit = event => {
      event.preventDefault(); const command = input.value.trim(); if (!command) return;
      history.push(command); history = history.slice(-100); cursor = history.length; input.value = ''; execute(command);
    };
    input.onkeydown = event => {
      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault(); cursor = Math.max(0, Math.min(history.length, cursor + (event.key === 'ArrowUp' ? -1 : 1)));
        input.value = history[cursor] || '';
      } else if (event.key === 'Tab') { event.preventDefault(); complete(); }
      else if (event.ctrlKey && event.key.toLowerCase() === 'l') { event.preventDefault(); output.replaceChildren(); }
    };
    panel.append(heading, description, actions, output, form);
    const tools = node('div', '', 'debug-tools'); tools.append(badge, entry);
    const brand = document.querySelector('.brand');
    if (brand) brand.after(tools); else document.body.prepend(tools);
    document.body.append(panel);
    document.addEventListener('keydown', event => {
      if (event.ctrlKey && event.code === 'Backquote') { event.preventDefault(); if (panel.open) panel.close(); else open(); }
    });
  }
  window.DebugConsole = {
    configure(config, callbacks) {
      hooks = callbacks; enabled = config.debug === true;
      if (window.AndroidGame?.requestDebugMode && !document.getElementById('debug-native-mode')) {
        const toggle = node('button', '开发者模式设置', 'debug-native-mode'); toggle.type = 'button';
        toggle.onclick = () => { if (!hooks.busy()) window.AndroidGame.requestDebugMode(); };
        document.getElementById('settings-card')?.append(toggle);
      }
      if (!enabled && !sessionId) return;
      if (!initialized) initialize(); updateBadge();
    },
    headers(path) {
      return sessionId && /^\/api\/(games|achievements|save-transfer|extensions)(\/|$)/.test(path)
        ? {'X-Cultivation-Debug': sessionId} : {};
    },
    active: () => !!sessionId,
    closeIfOpen() { if (panel?.open) { panel.close(); return true; } return false; },
    notify(message) { if (output) print(message); },
    async importText(text) {
      try { await execute('repro import', JSON.parse(text)); }
      catch (error) { print(error.message, true); }
    },
    beginNativeImport() { nativeImportParts = []; },
    appendNativeImport(chunk) { nativeImportParts.push(chunk); },
    finishNativeImport() {
      const text = nativeImportParts.join(''); nativeImportParts = [];
      return window.DebugConsole.importText(text);
    },
  };
})();
