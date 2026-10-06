// Apply a cached appearance before first paint; the persisted server preference follows.
(() => {
  let value = {};
  try { value = JSON.parse(localStorage.getItem('cultivation-appearance') || '{}') || {}; } catch (_) {}
  value.theme = ({c:'a',e:'f'})[value.theme] || value.theme;
  document.documentElement.dataset.theme = /^[abdf]$/.test(value.theme || '') ? value.theme : 'a';
  document.documentElement.dataset.motion = value.reduced_motion === true ? 'reduced' : 'full';
})();
