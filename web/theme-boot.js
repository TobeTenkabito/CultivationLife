// Apply a cached appearance before first paint; the persisted server preference follows.
(() => {
  let value = {};
  try { value = JSON.parse(localStorage.getItem('cultivation-appearance') || '{}') || {}; } catch (_) {}
  document.documentElement.dataset.theme = /^[a-f]$/.test(value.theme || '') ? value.theme : 'a';
  document.documentElement.dataset.motion = value.reduced_motion === true ? 'reduced' : 'full';
})();
