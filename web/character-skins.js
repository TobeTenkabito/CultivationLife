/* Cosmetic choices use the authoritative unlocked list and the normal command port. */
window.CharacterSkins = (() => {
  let current, select, pending = false;
  const section = document.createElement('dialog');
  section.className = 'appearance-dialog character-skins';
  section.id = 'character-skins';
  section.setAttribute('aria-labelledby', 'character-skins-title');
  const header = document.createElement('div');
  header.className = 'dialog-heading';
  const heading = document.createElement('h2');
  heading.id = 'character-skins-title';
  heading.textContent = '皮肤 · 形貌衣橱';
  const close = document.createElement('button');
  close.type = 'button'; close.id = 'character-skins-close';
  close.textContent = '返回人物'; close.autofocus = true;
  close.onclick = () => section.close();
  header.append(heading, close);
  const opener = document.createElement('button');
  opener.type = 'button'; opener.id = 'character-skins-open';
  opener.textContent = '衣橱'; opener.title = '打开形貌衣橱';
  opener.setAttribute('aria-label', '打开形貌衣橱');
  opener.setAttribute('aria-haspopup', 'dialog');
  opener.setAttribute('aria-controls', section.id);
  opener.onclick = () => { if (current && !section.open) section.showModal(); };
  document.querySelector('.pixel-character-visual').append(opener);
  const gallery = document.createElement('div');
  gallery.className = 'skin-gallery';
  const help = document.createElement('p');
  help.className = 'muted';
  section.append(header, help, gallery);
  document.body.append(section);
  document.getElementById('player-details-dialog').addEventListener('close', () => section.close());
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
