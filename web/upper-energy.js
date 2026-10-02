/* Shared labels and units for the main HUD, character sheet and reservoir. */
(() => {
  function display(data) {
    const p = data.player, a = data.aperture;
    if (a?.available && !a.lower && a.native) return {
      kind:a.energy_kind, mode:'reserve', label:a.name, current:a.current, maximum:a.capacity,
      detail:a.asura_conversion ? `转化 ${Math.round(a.conversion * 100)}% · 五重煞元` : '元府储量',
    };
    if (a?.available && !a.lower && p.immortal_power?.visible) return {
      kind:'immortal', mode:'conversion', label:`${a.name}转化`, current:a.conversion * 100, maximum:100, detail:'转化程度',
    };
    return {kind:'mana', mode:'mana', label:'法力 MP', current:p.mp, maximum:p.max_mp, detail:'本源法力'};
  }
  window.UpperEnergy = {display};
})();
