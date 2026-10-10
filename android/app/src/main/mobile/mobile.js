/* This file is packaged only for Android. Desktop compositions remain independent. */
(() => {
  const root = document.documentElement;
  root.dataset.platform = 'android';
  const syncTheme = () => window.AndroidGame?.setTheme(root.dataset.theme || 'a');
  new MutationObserver(syncTheme).observe(root, {attributes:true, attributeFilter:['data-theme']});
  syncTheme();
  const syncPanels = () => {
    document.body.classList.toggle('android-panel-open', !!document.querySelector('.panel-open'));
    document.body.classList.toggle('android-economy-panel-open', !!document.querySelector(
      '#map-card.panel-open, #merchant-card.panel-open, #personal-economy-card.panel-open, #war-card.panel-open'));
  };
  const panelObserver=new MutationObserver(syncPanels);
  document.querySelectorAll('.utility-panel').forEach(panel=>panelObserver.observe(panel,
    {attributes:true,attributeFilter:['class']}));
  const viewport = window.visualViewport;
  const keyboard = () => document.body.classList.toggle('android-keyboard',
    !!viewport && window.innerHeight - viewport.height > 140);
  viewport?.addEventListener('resize', keyboard);

  window.AndroidUI = {back:() => {
    if (window.SaveTransfer?.isWorking()) { toast('正在处理存档，请稍候'); return true; }
    if (typeof busy !== 'undefined' && busy) { toast('正在结算，请稍候'); return true; }
    if (window.TutorialGuide?.isGuiding()) { window.TutorialGuide.pause(); return true; }
    if (window.GameNavigation?.close()) return true;
    const confirm = document.querySelector('#game-confirm-backdrop:not(.hidden)');
    if (confirm) { closeGameConfirm(); return true; }
    const dialog = document.querySelector('dialog[open]');
    if (dialog) { dialog.close(); return true; }
    const panel = document.querySelector('.panel-open');
    if (panel) { window.UtilityPanels.close(panel.id.replace(/-card$/, '')); return true; }
    const report = document.querySelector('#battle-report-card:not(.report-closed):not(.hidden)');
    if (report && typeof battleReportOpen !== 'undefined' && battleReportOpen) {
      document.querySelector('#battle-report-toggle').click(); return true;
    }
    if (!document.querySelector('#achievement-screen').classList.contains('hidden')) {
      closeAchievements(); return true;
    }
    if (typeof game !== 'undefined' && game) { showStart(); return true; }
    return false;
  }};

  function restartButton(container) {
    if (!container || container.querySelector('.android-restart')) return;
    const button = document.createElement('button');
    button.className = 'android-restart';
    button.textContent = '重启应用，使 DLC 设置生效';
    button.onclick = () => {
      if (busy) { toast('正在结算，请稍候'); return; }
      openGameConfirm({title:'重新展开山河',body:'当前进度已自动保存。重启后将应用新的 DLC 设置。',
        confirmText:'重启应用',onConfirm:() => window.AndroidGame.restart()});
    };
    container.appendChild(button);
  }
  restartButton(document.querySelector('#extension-card'));
  // The startup manager is generated asynchronously by boot().
  const addStartupRestart = () => restartButton(document.querySelector('#start-extension-manager'));
  const startupObserver = new MutationObserver(addStartupRestart);
  startupObserver.observe(document.querySelector('#start-screen'), {childList:true,subtree:true});
  addStartupRestart();
  const settings = document.querySelector('#settings-card');
  if (settings) {
    const credits = document.createElement('details');
    credits.className = 'android-license';
    const summary = document.createElement('summary');
    summary.textContent = '安卓首版 · 字体与开源许可';
    const text = document.createElement('pre');
    credits.append(summary,text); settings.appendChild(credits);
    credits.addEventListener('toggle',async () => {
      if (credits.open && !text.textContent) {
        try { text.textContent = await (await fetch('/android/NOTICE.txt')).text(); }
        catch (_) { text.textContent = '许可文件包含在安装包中。'; }
      }
    });
  }
})();
