(() => {
  const panelNames = ['map', 'guixu', 'market', 'auction', 'exchange', 'ghost-parade', 'faction', 'intrigue', 'sage', 'sage-inner-outer', 'war', 'world-npc', 'ranking', 'family', 'race', 'world-route', 'extension', 'spirit-field', 'inventory', 'secret-art', 'relationship', 'transformation', 'bloodline', 'ghost-soul', 'ghost-attachment', 'captive', 'crafting', 'tianji', 'formation', 'natal-artifact', 'heavenly-court', 'settings'];

  function card(name) { return document.querySelector(`#${name}-card`); }
  function dockButton(name) { return document.querySelector(`[data-panel-target="${name}"]`); }

  function close(name) {
    card(name)?.classList.remove('panel-open');
    dockButton(name)?.classList.remove('active');
    dockButton(name)?.setAttribute('aria-expanded', 'false');
  }

  function open(name) {
    panelNames.forEach(close);
    const target = card(name);
    const trigger = dockButton(name);
    if (!target || target.classList.contains('hidden')) return;
    target.classList.add('panel-open');
    trigger?.classList.add('active');
    trigger?.setAttribute('aria-expanded', 'true');
  }

  function toggle(name) {
    if (card(name)?.classList.contains('panel-open')) close(name); else open(name);
  }

  function init() {
    panelNames.forEach(name => {
      const trigger = dockButton(name);
      if (trigger) {
        trigger.setAttribute('aria-controls', `${name}-card`);
        trigger.setAttribute('aria-expanded', 'false');
        trigger.addEventListener('click', () => toggle(name));
      }
      document.querySelector(`#${name}-toggle`)?.addEventListener('click', () => close(name));
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') panelNames.forEach(close);
    });
  }

  window.UtilityPanels = {init, open, close, toggle};
})();
