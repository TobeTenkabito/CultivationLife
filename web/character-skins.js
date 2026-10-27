/* Cosmetic choices use the authoritative unlocked list and the normal command port. */
window.CharacterSkins = (() => {
  let current, select, pending = false;
  const section = document.createElement('details');
  section.className = 'character-skins';
  section.id = 'character-skins';
  const heading = document.createElement('summary');
  heading.textContent = '皮肤 · 形貌衣橱';
  const gallery = document.createElement('div');
  gallery.className = 'skin-gallery';
  const help = document.createElement('p');
  help.className = 'muted';
  section.append(heading, help, gallery);
  document.getElementById('player-details-content').append(section);
  function draw() {
    const state = current.player.character_skins || {};
    help.textContent = state.blocked ? '寄身、附身或变化期间暂不能切换。' : '随时换回曾经解锁的形貌，修为与战力保持原值。';
    gallery.replaceChildren();
    const options = [{id: '', name: '随成长变化'}, ...(state.available || []),
      ...(state.locked || []).map(skin => ({...skin, locked: true}))];
    for (const skin of options) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.skinId = skin.id;
      button.setAttribute('aria-pressed', String(skin.id === (state.selected || '')));
      button.disabled = pending || state.blocked || skin.locked;
      button.classList.toggle('skin-locked', !!skin.locked);
      if (skin.thumbnail) {
        const img = document.createElement('img');
        img.src = skin.thumbnail; img.alt = ''; img.width = 128; img.height = 144;
        img.loading = 'lazy'; img.onerror = () => img.remove(); button.append(img);
      } else {
        const auto = document.createElement('span'); auto.className = 'skin-auto'; auto.textContent = '随境'; button.append(auto);
      }
      const label = document.createElement('span'); label.textContent = skin.name; button.append(label);
      if (skin.unlock_label) {
        const badge = document.createElement('small'); badge.className = 'skin-unlock';
        badge.textContent = skin.locked ? skin.unlock_label : '全道途通用 · 已解锁';
        button.append(badge);
      }
      button.onclick = async () => {
        if (pending || skin.id === (state.selected || '')) return;
        pending = true; draw();
        try { await select(skin.id); }
        finally { pending = false; draw(); }
      };
      gallery.append(button);
    }
  }
  return {render(data, command) { current = data; select = command; draw(); }};
})();
