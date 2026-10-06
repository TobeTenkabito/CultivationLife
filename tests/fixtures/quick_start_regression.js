/* Real quick-start/save/action paths; no generated character or UI fixtures. */
window.QuickStartProbe = (() => {
  const errors = [];
  const originalToast = toast;
  toast = message => { errors.push(String(message)); originalToast(message); };
  window.addEventListener('error', e => errors.push(e.message));
  window.addEventListener('unhandledrejection', e => errors.push(String(e.reason)));
  const check = (value, message) => { if (!value) throw new Error(message); };
  async function run(preset) {
    errors.length = 0;
    document.querySelector('#new-game-form [name=seed]').value = '1411';
    await startQuickGame(preset, 'serpent');
    check(!errors.length, preset + ': ' + errors.join('; '));
    const id = game.id, age = game.player.world_age;
    if (preset === 'demonic_void') {
      check(game.player.path === 'demonic' && game.player.realm_index === 6, 'Wrong demonic void preset');
      check(document.querySelectorAll('.intrigue-member').length > 0, 'Missing actual intrigue members');
      for (const theme of 'abdf') {
        document.querySelector('[data-theme-picker=dialog] [data-theme-choice=' + theme + ']').click();
        await GameThemes.saved;
        render(game);
        check(!busy && !document.querySelector('[data-action=cultivate]').disabled, theme + ': disabled action');
      }
    }
    await mutate('/api/games/' + id + '/advance', {action:'cultivate', years:1});
    check(!errors.length, preset + ': action ' + errors.join('; '));
    check(game.player.world_age > age, preset + ': action did not advance');
    const advancedAge = game.player.world_age;
    await loadGame(id);
    check(!errors.length, preset + ': reload ' + errors.join('; '));
    check(game.id === id && game.player.world_age === advancedAge && !busy, preset + ': reload mismatch');
    return {preset, id, age:advancedAge};
  }
  return {run, errors};
})();
