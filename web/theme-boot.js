// Apply a cached appearance before first paint; the persisted server preference follows.
(() => {
  let value = {};
  try { value = JSON.parse(localStorage.getItem('cultivation-appearance') || '{}') || {}; } catch (_) {}
  document.documentElement.dataset.theme = 'a';
  document.documentElement.dataset.pixelTheme = value.pixel_theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.compactDocks = String(value.compact_docks !== false);
  document.documentElement.dataset.motion = value.reduced_motion === true ? 'reduced' : 'full';
  document.documentElement.dataset.visual = 'pixel';
})();
