const $ = (selector) => document.querySelector(selector);
let game = null;
let busy = false;
let configData = null;
let battlePlaybackKey = null;
let battlePlaybackTimer = null;
let battleReportOpen = false;
let achievementCatalog = null;
let achievementToastTimer = null;
let gameConfirmAction = null;
const achievementToastQueue = [];
const historyFilters = new Set(['self', 'companion', 'friend', 'mentor', 'faction', 'race', 'other']);

const worldClock = () => game?.player?.world_age ?? game?.player?.age ?? 0;
const timelineText = value => (
  game?.player?.world_age != null && game.player.world_age !== game.player.age
    ? `纪年 ${value}` : `${value} 岁`
);

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '天机紊乱，请稍后再试');
  return data;
}

function toast(message) {
  const node = $('#toast'); node.textContent = message; node.classList.add('show');
  setTimeout(() => node.classList.remove('show'), 2600);
}

function closeGameConfirm() {
  gameConfirmAction = null;
  $('#game-confirm-backdrop').classList.add('hidden');
}

function openGameConfirm({title, body, confirmText = '确认', onConfirm}) {
  gameConfirmAction = onConfirm;
  $('#game-confirm-title').textContent = title;
  $('#game-confirm-body').textContent = body;
  $('#game-confirm-accept').textContent = confirmText;
  $('#game-confirm-backdrop').classList.remove('hidden');
  $('#game-confirm-cancel').focus();
}

$('#game-confirm-cancel').onclick = closeGameConfirm;
$('#game-confirm-accept').onclick = () => {
  const action = gameConfirmAction;
  closeGameConfirm();
  if (action) action();
};
$('#game-confirm-backdrop').addEventListener('click', event => {
  if (event.target === event.currentTarget) closeGameConfirm();
});

async function boot() {
  const [config, saves, achievements] = await Promise.all([api('/api/config'), api('/api/games'), api('/api/achievements')]);
  configData = config;
  const baseGame = config.base_game || {};
  const versionLabel = baseGame.version_label || `本体 v${baseGame.version || '?'}`;
  $('#base-game-version').textContent = versionLabel;
  $('#settings-base-version').textContent = `${baseGame.name || '浮生问道'} · ${versionLabel}`;
  document.title = `${baseGame.name || '浮生问道'} · v${baseGame.version || '?'}`;
  achievementCatalog = achievements;
  updateAchievementEntry();
  fillRootSelect(config);
  fillSelect('#path-select', config.paths);
  fillSelect('#monster-species-select', Object.fromEntries(Object.entries(config.monster_species || {}).map(([id, row]) => [id, row.name])));
  fillStartWorldSelect(config);
  const updateCreationFields = () => {
    fillStartWorldSelect(config);
    $('#monster-species-field').classList.toggle('hidden', $('#path-select').value !== 'monster' || !Object.keys(config.monster_species || {}).length);
  };
  $('#path-select').addEventListener('change', updateCreationFields);
  updateCreationFields();
  renderQuickStarts(config.quick_starts || []);
  renderExtensions(config.extensions || []);
  renderStartExtensionManager(config.extensions || []);
  const list = $('#save-list');
  saves.games.slice(0, 5).forEach(save => {
    const button = document.createElement('button');
    const saveVersion = save.game_version && save.game_version !== 'pre-1.0.0' ? ` · v${save.game_version}` : '';
    button.textContent = `续接 · ${save.name}${saveVersion}`;
    button.onclick = () => loadGame(save.id);
    list.appendChild(button);
  });
}

function updateAchievementEntry() {
  const progress = $('#achievement-entry-progress');
  if (progress && achievementCatalog) progress.textContent = `已解锁 ${achievementCatalog.unlocked} / ${achievementCatalog.total}`;
}

async function openAchievements() {
  if (busy) return;
  busy = true;
  try {
    achievementCatalog = await api('/api/achievements');
    updateAchievementEntry();
    renderAchievements(achievementCatalog);
    $('#start-screen').classList.add('hidden');
    $('#achievement-screen').classList.remove('hidden');
  } catch (error) { toast(error.message); }
  finally { busy = false; }
}

function closeAchievements() {
  $('#achievement-screen').classList.add('hidden');
  $('#start-screen').classList.remove('hidden');
}

function renderAchievements(catalog) {
  $('#achievement-summary').textContent = `已解锁 ${catalog.unlocked} / ${catalog.total} · 所有进度跨存档保留`;
  const root = $('#achievement-groups'); root.innerHTML = '';
  const sources = new Map();
  (catalog.achievements || []).forEach(achievement => {
    const source = achievement.source || {kind:'base', id:'base', name:'游戏本体'};
    const key = `${source.kind}:${source.id}`;
    if (!sources.has(key)) sources.set(key, {source, achievements:[]});
    sources.get(key).achievements.push(achievement);
  });
  [...sources.values()].sort((left, right) => {
    const order = {base:0, dlc:1, mod:2};
    return (order[left.source.kind] ?? 9) - (order[right.source.kind] ?? 9);
  }).forEach(group => {
    const section = document.createElement('section'); section.className = 'achievement-source';
    const head = document.createElement('div'); head.className = 'achievement-source-head';
    const title = document.createElement('h3');
    title.textContent = group.source.kind === 'base' ? '本体成就' : `${group.source.kind === 'dlc' ? 'DLC' : 'MOD'} · ${group.source.name}`;
    const progress = document.createElement('span');
    progress.textContent = `${group.achievements.filter(row => row.unlocked).length} / ${group.achievements.length}`;
    head.append(title, progress); section.appendChild(head);
    [['story','剧情成就'], ['cultivation','修炼成就']].forEach(([category, label]) => {
      const rows = group.achievements.filter(row => row.category === category);
      if (!rows.length) return;
      const categoryTitle = document.createElement('h4'); categoryTitle.className = 'achievement-category-title'; categoryTitle.textContent = label;
      const grid = document.createElement('div'); grid.className = 'achievement-grid';
      rows.forEach(achievement => {
        const row = document.createElement('div'); row.className = `achievement-row ${achievement.unlocked ? 'unlocked' : 'locked'}`;
        const medal = document.createElement('span'); medal.className = 'achievement-medal'; medal.textContent = achievement.unlocked ? '✓' : '？';
        const copy = document.createElement('div'); const name = document.createElement('b'); const condition = document.createElement('small');
        name.textContent = achievement.name; condition.textContent = `解锁条件：${achievement.description}`; copy.append(name, condition);
        if (achievement.unlocked) {
          const note = document.createElement('small'); note.className = 'achievement-unlock-note';
          const date = achievement.unlocked_at ? new Date(achievement.unlocked_at).toLocaleString('zh-CN') : '';
          note.textContent = `已解锁${achievement.player_name ? ` · ${achievement.player_name}` : ''}${date ? ` · ${date}` : ''}`; copy.appendChild(note);
        }
        row.append(medal, copy); grid.appendChild(row);
      });
      section.append(categoryTitle, grid);
    });
    root.appendChild(section);
  });
}

function queueAchievementToasts(achievements) {
  if (!achievements?.length || game?.settings?.achievement_popup === false) return;
  achievementToastQueue.push(...achievements);
  if (!achievementToastTimer) showNextAchievementToast();
}

function showNextAchievementToast() {
  const achievement = achievementToastQueue.shift();
  if (!achievement) { achievementToastTimer = null; return; }
  const node = $('#achievement-toast');
  $('#achievement-toast-name').textContent = achievement.name;
  $('#achievement-toast-description').textContent = achievement.description;
  node.classList.add('show');
  achievementToastTimer = setTimeout(() => {
    node.classList.remove('show');
    achievementToastTimer = setTimeout(showNextAchievementToast, 350);
  }, 3200);
}

function renderExtensions(extensions) {
  const list = $('#extension-list'); list.innerHTML = '';
  const loaded = extensions.filter(extension => extension.status === 'loaded').length;
  const baseVersion = configData?.base_game?.version || '?';
  $('#extension-summary').textContent = extensions.length ? `本体 v${baseVersion} · 已识别 ${extensions.length} · 已加载 ${loaded}` : `纯净本体 v${baseVersion}`;
  extensions.forEach(extension => {
    const row = document.createElement('div'); row.className = `extension-row ${extension.status}`;
    const status = extension.status === 'loaded' ? '已加载' : extension.status === 'disabled' ? '未启用' : '加载失败';
    const pending = extension.next_enabled == null ? '' : ` · 下次启动${extension.next_enabled ? '启用' : '禁用'}`;
    const title = document.createElement('b'); title.textContent = `${extension.kind_name} · ${extension.name} ${extension.version}`;
    const detail = document.createElement('small');
    detail.textContent = `${status}${pending}${extension.requires?.length ? ` · 依赖 ${extension.requires.join('、')}` : ''}${extension.description ? ` · ${extension.description}` : ''}`;
    row.append(title, detail);
    if (extension.error) { const error = document.createElement('small'); error.className = 'extension-error'; error.textContent = extension.error; row.appendChild(error); }
    list.appendChild(row);
  });
  if (!extensions.length) list.innerHTML = '<p class="empty">未安装任何 DLC 或 MOD；所有本体功能均可正常使用。</p>';
}

function renderStartExtensionManager(extensions) {
  const manager = $('#start-extension-manager');
  const list = $('#start-extension-list'); list.innerHTML = '';
  manager.classList.toggle('hidden', !extensions.length);
  extensions.forEach(extension => {
    const label = document.createElement('label'); label.className = 'start-extension-switch';
    const text = document.createElement('span'); text.textContent = extension.name;
    const kind = document.createElement('small'); kind.textContent = `${extension.kind_name}${extension.next_enabled == null ? '' : ' · 待重启'}`;
    text.appendChild(kind);
    const input = document.createElement('input'); input.type = 'checkbox';
    input.checked = extension.next_enabled == null ? !!extension.enabled : !!extension.next_enabled;
    input.disabled = extension.status === 'error';
    input.onchange = async () => {
      input.disabled = true;
      try {
        const result = await api(`/api/extensions/${encodeURIComponent(extension.id)}`, {
          method: 'POST', body: JSON.stringify({enabled: input.checked}),
        });
        extension.next_enabled = result.enabled;
        renderStartExtensionManager(extensions);
        renderExtensions(extensions);
        toast(result.message);
      } catch (error) {
        input.checked = !input.checked; input.disabled = false; toast(error.message);
      }
    };
    label.append(text, input); list.appendChild(label);
  });
}

function renderQuickStarts(presets) {
  const list = $('#quick-start-list'); list.innerHTML = '';
  presets.forEach(preset => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'quick-start-button';
    button.dataset.presetId = preset.id; button.disabled = !preset.enabled;
    const detail = preset.path === 'demonic' ? '出生魔界 · 使用魔修功法与行囊' : '使用默认属性与功法开局';
    button.innerHTML = `<b>${preset.name}</b><span>${preset.enabled ? detail : preset.status}</span>`;
    if (preset.enabled) button.onclick = () => startQuickGame(preset.id);
    list.appendChild(button);
  });
}

async function startQuickGame(presetId) {
  const form = new FormData($('#new-game-form'));
  const payload = {name: form.get('name') || '', preset_id: presetId};
  if (form.get('seed')) payload.seed = Number(form.get('seed'));
  await mutate('/api/games', payload);
}

function fillRootSelect(config) {
  const select = $('#root-select');
  const groups = new Map();
  Object.entries(config.spirit_roots).forEach(([value, label]) => {
    const detail = config.spirit_root_details[value];
    const groupKey = `${detail.tier}-${detail.efficiency}`;
    if (!groups.has(groupKey)) {
      const group = document.createElement('optgroup'); group.label = `${detail.tier} · 效率 ×${detail.efficiency.toFixed(2)}`;
      groups.set(groupKey, group); select.appendChild(group);
    }
    const option = document.createElement('option'); option.value = value; option.textContent = label;
    groups.get(groupKey).appendChild(option);
  });
}

function fillSelect(selector, values) {
  Object.entries(values).forEach(([value, label]) => {
    const option = document.createElement('option'); option.value = value; option.textContent = label;
    $(selector).appendChild(option);
  });
}

function fillStartWorldSelect(config) {
  const select = $('#start-world-select');
  const previous = select.value;
  select.innerHTML = '';
  const path = $('#path-select').value;
  (config.start_worlds?.[path] || ['human']).forEach(world => {
    const option = document.createElement('option');
    option.value = world; option.textContent = config.worlds[world] || world;
    select.appendChild(option);
  });
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}

async function loadGame(id) {
  if (busy) return;
  busy = true; document.body.classList.add('busy'); renderButtons();
  try { render(await api(`/api/games/${id}`)); } catch (error) { toast(error.message); }
  finally { busy = false; document.body.classList.remove('busy'); renderButtons(); }
}

$('#new-game-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  if (payload.seed) payload.seed = Number(payload.seed); else delete payload.seed;
  await mutate('/api/games', payload);
});

document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => {
  mutate(`/api/games/${game.id}/advance`, {action: button.dataset.action, years: 1});
}));

$('#new-game-button').onclick = showStart;
$('#restart-button').onclick = showStart;
$('#achievement-open').onclick = openAchievements;
$('#achievement-close').onclick = closeAchievements;
window.UtilityPanels?.init();
document.querySelectorAll('#history-filters input').forEach(input => input.addEventListener('change', () => {
  if (input.checked) historyFilters.add(input.value); else historyFilters.delete(input.value);
  if (game) renderHistory(game.history || []);
}));

async function mutate(path, payload) {
  if (busy) return;
  busy = true; document.body.classList.add('busy'); renderButtons();
  try { render(await api(path, {method:'POST', body:JSON.stringify(payload)})); }
  catch (error) { toast(error.message); }
  finally { busy = false; document.body.classList.remove('busy'); renderButtons(); }
}

function showStart() {
  closeGameConfirm();
  game = null; $('#start-screen').classList.remove('hidden'); $('#achievement-screen').classList.add('hidden'); $('#game-screen').classList.add('hidden'); $('#new-game-button').classList.add('hidden');
  api('/api/achievements').then(catalog => { achievementCatalog = catalog; updateAchievementEntry(); }).catch(() => {});
  ['map', 'market', 'auction', 'ghost-parade', 'faction', 'war', 'world-npc', 'ranking', 'family', 'race', 'world-route', 'extension', 'spirit-field', 'inventory', 'relationship', 'transformation', 'bloodline', 'ghost-soul', 'ghost-attachment', 'captive', 'crafting', 'natal-artifact', 'heavenly-court', 'settings'].forEach(name => window.UtilityPanels?.close(name));
  battleReportOpen = false;
  renderButtons();
}

function render(data) {
  game = data;
  $('#start-screen').classList.add('hidden'); $('#achievement-screen').classList.add('hidden'); $('#game-screen').classList.remove('hidden'); $('#new-game-button').classList.remove('hidden');
  queueAchievementToasts(data.new_achievements || []);
  const p = data.player;
  const transformationAvailable = data.transformation_system?.available !== false;
  const transformationDock = document.querySelector('[data-panel-target="transformation"]');
  transformationDock?.classList.toggle('hidden', !transformationAvailable);
  if (!transformationAvailable) window.UtilityPanels?.close('transformation');
  $('#player-name').textContent = p.name; $('#avatar').textContent = p.name.slice(0,1);
  $('#player-subtitle').textContent = `${p.spirit_root_display || p.spirit_root_name} · ${p.path_name} · ${p.world_name} · ${p.location_name}`;
  $('#slay-action span').textContent = p.path === 'monster'
    ? '猎杀异道不沾因果；击杀道修额外增长煞气'
    : '寻找弱者下手，夺宝但增加因果';
  $('#realm-name').textContent = p.awaiting_spirit_realm_crossing && p.world === 'human' ? `${p.realm_name} · 人界绝巅` : p.realm_name;
  const worldAge = p.world_age !== p.age ? ` · 世界纪年 ${p.world_age}` : '';
  $('#age-line').textContent = (p.lifespan == null ? `${p.age} 岁 · 寿元无尽` : `${p.age} 岁 · 寿元 ${p.lifespan}`) + worldAge;
  const tribulationLine = $('#tribulation-line');
  tribulationLine.classList.toggle('hidden', data.tribulation?.next_age == null);
  tribulationLine.textContent = data.tribulation?.next_age == null ? '' : `雷劫：${data.tribulation.years_remaining} 年后 · 已历 ${data.tribulation.count} 次 · 雷威 ${number(data.tribulation.power || 0)}`;
  meter('opportunity', p.opportunity, p.opportunity_required);
  renderQiMastery(p.qi_mastery || [], p.qi_gain_efficiencies || {});
  meter('hp', p.hp, p.max_hp); meter('mp', p.mp, p.max_mp);
  $('#mp-label').textContent = p.resource_name || 'MP';
  $('#mp-meter').classList.toggle('blue', p.resource_kind !== 'immortal');
  $('#mp-meter').classList.toggle('purple', p.resource_kind === 'immortal');
  const immortalPower = p.immortal_power || {};
  $('#immortal-power-stat').classList.toggle('hidden', !immortalPower.visible);
  if (immortalPower.converted) {
    $('#immortal-power-state').textContent = '已完成转化 · 可发动仙家功法';
  } else {
    const stage = number(immortalPower.conversion_stage || 0);
    const total = number(immortalPower.conversion_total || 5);
    const ratio = Math.round(Number(immortalPower.usable_ratio || 0) * 100);
    const wait = number(immortalPower.wait_units_remaining || 0);
    const chance = Math.round(Number(immortalPower.current_trigger_chance || 0) * 100);
    const timing = wait > 0 ? `距下阶段最早触发还需 ${wait} 单位` : `当前触发率 ${chance}%`;
    $('#immortal-power-state').textContent = `转化 ${stage}/${total} · 可用上限 ${ratio}% · ${timing}`;
  }
  const ghost = data.ghost_system || {};
  $('#ghost-erosion-stat').classList.toggle('hidden', !ghost.available);
  $('#ghost-wangsheng-stat').classList.toggle('hidden', !ghost.available);
  $('#ghost-system-panel').classList.toggle('hidden', !ghost.available);
  if (ghost.available) {
    $('#ghost-erosion').textContent = `${Number(ghost.erosion_rate_pp || 0).toFixed(4)}%`;
    $('#ghost-wangsheng').textContent = number(ghost.wangsheng || 0);
    $('#ghost-system-title').textContent = '魂蚀、往生与轮回';
    const ihp = ghost.intrinsic_hp || {}, imp = ghost.intrinsic_mp || {};
    const erosionTime = ghost.erosion_time || {};
    const erosionClock = `魂蚀计时 ${formatDecimal(erosionTime.elapsed_equivalent_years || 0)}/${number(erosionTime.time_unit_years || p.time_unit_years)} 年（${precisePercent(erosionTime.progress_ratio || 0)}）`;
    const markText = ghost.effective_marks ? ` · 本境有效轮回 ${ghost.effective_marks} 次（突破 +${percent(ghost.breakthrough_bonus)}）` : '';
    const capText = `最终有效突破率封顶 ${percent(ghost.breakthrough_probability_cap || .98)}`;
    $('#ghost-system-summary').textContent = ghost.suspended
      ? `${ghost.suspension_reason} · 本魂 HP ${number(ihp.current)}/${number(ihp.reference)} · MP ${number(imp.current)}/${number(imp.reference)} · ${capText}`
      : `${ghost.soul_integrity?.label || '魂基'} · ${erosionClock} · 魂基 HP ${number(ihp.current)}/${number(ihp.reference)}（承载 ${percent(ihp.carry_ratio)}） · MP ${number(imp.current)}/${number(imp.reference)}（承载 ${percent(imp.carry_ratio)}）${markText} · ${capText} · 历史最高 ${ghost.highwater?.name || '未记录'}`;
    const hpDetail = `本体魂基 ${number(ihp.current)} / ${number(ihp.reference)}；本体承载 ${precisePercent(ihp.carry_ratio)}；外物原始 +${number(ihp.external_raw)}，实际 +${number(ihp.external_effective)}`;
    const mpDetail = `本体魂基 ${number(imp.current)} / ${number(imp.reference)}；本体承载 ${precisePercent(imp.carry_ratio)}；外物原始 +${number(imp.external_raw)}，实际 +${number(imp.external_effective)}`;
    $('#hp-text').title = hpDetail; $('#hp-text').dataset.tooltip = hpDetail;
    $('#mp-text').title = mpDetail; $('#mp-text').dataset.tooltip = mpDetail;
    $('#ghost-integrity-detail').textContent = `${erosionClock}；所有行动共享此进度，只有累计满一个当前境界时间单位才结算魂蚀。魂体完整度 ${precisePercent(ghost.soul_integrity?.ratio || 0)}（${ghost.soul_integrity?.label || '未知'}）。HP：${hpDetail}。MP：${mpDetail}。`;
    const imprintRows = ghost.imprints || [];
    $('#ghost-imprint-list').textContent = imprintRows.length
      ? `轮回印记（共 ${number(ghost.total_imprints)}）：${imprintRows.map(row => `${row.realm_name}${row.layer}层 ×${row.count}`).join('；')}。当前道路有效 ${number(ghost.effective_marks)} 枚，经验加成 ${percent(ghost.breakthrough_bonus)}。最近轮回锚点：${ghost.last_anchor?.name || '无'}。`
      : '轮回印记：当前修炼体系没有可记录的瓶颈。';
    const preview = ghost.reincarnation_preview;
    $('#ghost-reincarnation-preview').classList.toggle('hidden', !preview);
    $('#ghost-reincarnation-preview').textContent = preview
      ? `本次轮回预览：${preview.source} → ${preview.destination}；新增本境第 ${preview.next_imprint_count} 枚印记，${preview.affected_road}突破经验 +${percent(preview.added_bonus)}；往生 ${preview.wangsheng_before} → 0；魂蚀率保持 ${Number(preview.erosion_rate_pp).toFixed(4)}%；魂基 HP ${number(preview.intrinsic_hp_current)}、MP ${number(preview.intrinsic_mp_current)} 均不恢复；本体成长最高水位保持 ${preview.highwater}，重新超过前不再获得重复境界的 Intrinsic HP/MP。`
      : '';
    $('#ghost-wangsheng-action').textContent = `往生息蚀 · ${ghost.wangsheng_cost} 点`;
    $('#ghost-wangsheng-action').title = `魂蚀率 -${Number(ghost.wangsheng_reduction_pp || 0).toFixed(4)} 个百分点；不恢复既有魂伤`;
    $('#ghost-wangsheng-all-action').textContent = `尽数往生 · ${number(ghost.wangsheng_available_uses)} 次`;
    $('#ghost-wangsheng-all-action').title = '一次消耗当前能够支付的全部往生次数；魂蚀率最低为 0，溢出的压制不会恢复魂基';
    $('#ghost-reincarnate-action').classList.toggle('hidden', !ghost.can_reincarnate);
    renderGhostPhaseTwo(ghost.phase_two || {});
  } else {
    $('#hp-text').removeAttribute('title'); $('#hp-text').removeAttribute('data-tooltip');
    $('#mp-text').removeAttribute('title'); $('#mp-text').removeAttribute('data-tooltip');
    renderGhostPhaseTwo({enabled:false});
  }
  const combatNode = $('#combat-power');
  combatNode.textContent = number(p.combat_power);
  const combatHint = `当前境界期望战斗力：${number(p.expected_combat_power)}。${p.combat_power_assessment}`;
  combatNode.title = combatHint; combatNode.dataset.tooltip = combatHint;
  $('#karma').textContent = number(p.karma);
  $('#sha-qi').textContent = number(p.sha_qi || 0);
  $('#fame').textContent = number(p.fame || 0);
  $('#fame').title = p.fame_assessment || '';
  $('#battle-power').textContent = number(p.battle_power || p.combat_power);
  $('#heart-demon-stat').classList.toggle('hidden', p.heart_demon == null);
  $('#heart-demon').textContent = p.heart_demon == null ? '' : number(p.heart_demon);
  $('#effective-karma').textContent = `${number(p.effective_karma)} × ${p.karma_factor}`;
  $('#technique').textContent = p.technique ? `${p.technique.name} Lv.${p.technique.level}` : '尚未获得';
  renderTechniques(p.technique_slots);
  renderKnownTechniques(p.known_techniques || []);
  renderTransformationSystem(data.transformation_system || {});
  renderMonsterBloodline(data.monster_bloodline || {});
  renderRelationships(p.master, p.disciples || [], p.disciple_requests || [], p.inventory || [], p.known_techniques || []);
  renderDaoCompanion(data.dao_companion, p.inventory || [], p.known_techniques || [], Number(p.next_companion_conception_bonus || 0));
  renderDaoFriends(data.dao_friends || []);
  renderPersonalRelations(data.personal_relations || {high:[], low:[]});
  renderParty(data.party || []);
  renderWanted(data.wanted || []);
  renderPrison(data.imprisonment);
  $('#root-efficiency').textContent = `×${Number(p.cultivation_efficiency || 0).toFixed(2)}`;
  $('#root-efficiency').title = `灵根基础 ×${p.spirit_root_efficiency.toFixed(2)}；最终效率已计入主修功法、物品与气环境`;
  const qi = p.qi_environment || {};
  $('#qi-environment').textContent = (qi.display || []).map(entry => `${entry.name}${number(entry.concentration)}`).join(' · ');
  $('#qi-environment').title = qi.main_multiplier == null ? '尚无主修功法' : `当前主修环境倍率 ×${Number(qi.main_multiplier).toFixed(3)}`;
  const bodyCultivation = data.body_cultivation || {};
  $('#body-training').textContent = p.body_training
    ? `${p.body_training}/100 层${bodyCultivation.technique ? ` · 《${bodyCultivation.technique.name}》` : ''}${bodyCultivation.training_speed_multiplier > 1 ? ` · 修炼×${Number(bodyCultivation.training_speed_multiplier).toFixed(1)}` : ''}`
    : (bodyCultivation.technique ? `0/100 层 · 《${bodyCultivation.technique.name}》${bodyCultivation.training_speed_multiplier > 1 ? ` · 修炼×${Number(bodyCultivation.training_speed_multiplier).toFixed(1)}` : ''}` : '未入门');
  const sense = p.divine_sense || {};
  $('#divine-sense').textContent = `Lv.${sense.level || 0} · 御傀 ${sense.used || 0}/${sense.capacity || 0}`;
  $('#divine-sense').title = sense.technique ? `《${sense.technique.name}》· 当前环境 ×${Number(sense.technique.environment_multiplier || 0).toFixed(3)}` : '尚未配置神识功法';
  $('#player-race').textContent = p.lineage_race_name === p.allegiance_race_name
    ? p.lineage_race_name
    : `血缘 ${p.lineage_race_name} · 势力 ${p.allegiance_race_name}`;
  $('#action-heading').textContent = p.time_unit_years === 1 ? '这一年，你将如何度过？' : `未来 ${p.time_unit_years} 年，你将如何度过？`;
  $('#time-unit-hint').textContent = `当前境界每个行动单位流逝 ${p.time_unit_years} 年；期间收益、寿元、NPC 修炼、突破与陨落均逐年结算。重大事件会在发生年份中断本期行动。`;
  const breakthrough = data.breakthrough || {};
  $('#breakthrough-panel').classList.toggle('hidden', !breakthrough.ready || !!data.monster_bloodline?.awaiting_evolution);
  $('#breakthrough-title').textContent = breakthrough.target_realm ? `冲击${breakthrough.target_realm}` : '境界瓶颈';
  $('#breakthrough-action').textContent = breakthrough.action_label || '突破瓶颈';
  const chanceText = breakthrough.chance ? `本次成功率 ${percent(breakthrough.chance.final)}（基础 ${percent(breakthrough.chance.base)}${breakthrough.chance.pity_bonus ? `，连续失败保底 +${percent(breakthrough.chance.pity_bonus)}` : ''}${breakthrough.chance.aid_bonus ? `，丹药 +${percent(breakthrough.chance.aid_bonus)}` : ''}${breakthrough.chance.reincarnation_bonus ? `，轮回经验 +${percent(breakthrough.chance.reincarnation_bonus)}` : ''}${breakthrough.chance.devouring_bonus ? `，吞噬元神 +${percent(breakthrough.chance.devouring_bonus)}` : ''}${breakthrough.chance.companion_bonus ? `，道侣同修 +${percent(breakthrough.chance.companion_bonus)}` : ''}${breakthrough.chance.artifact_bonus ? `，法宝 +${percent(breakthrough.chance.artifact_bonus)}` : ''}${breakthrough.chance.body_training_bonus ? `，炼体 +${percent(breakthrough.chance.body_training_bonus)}` : ''}${breakthrough.chance.optimal_state_bonus ? `，状态极佳 +${percent(breakthrough.chance.optimal_state_bonus)}` : ''}${breakthrough.chance.heart_demon_penalty ? `，心魔 -${percent(breakthrough.chance.heart_demon_penalty)}` : ''}）` : '';
  const aidText = breakthrough.active_aids?.length ? ` 已服：${breakthrough.active_aids.map(item => item.name).join('、')}。` : '';
  $('#breakthrough-reason').textContent = breakthrough.met ? `${chanceText}。可继续整备后再冲关。${aidText}` : breakthrough.reason;
  $('#body-breakthrough-panel').classList.toggle('hidden', !bodyCultivation.ready);
  $('#body-breakthrough-title').textContent = bodyCultivation.target_layer ? `冲击炼体${bodyCultivation.target_layer}层` : '炼体已达极限';
  const bodyChance = bodyCultivation.chance;
  $('#body-breakthrough-reason').textContent = bodyChance
    ? `成功率 ${percent(bodyChance.final)}（基础 ${percent(bodyChance.base)}${bodyChance.technique_bonus ? `，功法 +${percent(bodyChance.technique_bonus)}` : ''}${bodyChance.pity_bonus ? `，累计保底 +${percent(bodyChance.pity_bonus)}` : ''}）；失败保留七成积累。`
    : '';
  const bodyTrain = $('#body-train-action');
  bodyTrain.querySelector('span').textContent = !bodyCultivation.technique
    ? '需要先获得并配置一部炼体功法'
    : bodyCultivation.layer >= bodyCultivation.max_layer
      ? '肉身已达一百层极限'
      : bodyCultivation.ready
        ? '积累圆满，请先手动冲击下一层'
        : `积累 ${number(bodyCultivation.progress || 0)}/${number(bodyCultivation.required || 0)} · 《${bodyCultivation.technique.name}》`;
  const senseTrain = $('#sense-train-action');
  senseTrain.querySelector('span').textContent = !sense.technique
    ? '需要先获得并配置一部神识功法'
    : `经验 ${number(sense.level_experience || 0)}/${number(sense.next_level_experience || 0)} · 《${sense.technique.name}》`;
  const senseBreakthrough = $('#sense-breakthrough-action');
  senseBreakthrough.classList.toggle('hidden', !sense.technique);
  senseBreakthrough.querySelector('b').textContent = `突破神识至 ${Number(sense.level || 0) + 1} 级`;
  senseBreakthrough.querySelector('span').textContent = `消耗 ${number(sense.next_level_experience || 0)} 经验；境界自动提升神识时不消耗经验`;
  const cultivate = $('#cultivate-action');
  cultivate.querySelector('b').textContent = p.spirit_root === 'none' ? '打熬筋骨' : '潜心修炼';
  cultivate.querySelector('span').textContent = p.spirit_root === 'none' ? '寻求凡人炼体机缘' : '稳定积累机缘';
  const crossing = $('#spirit-crossing-action');
  const canNormalCross = p.path !== 'demonic' && !p.cultivation_suppressed && p.world === 'human' && p.realm_index === 5 && p.layer <= 3 && !p.spirit_realm_attempted && p.alive;
  const trueDemonGate = data.demonic_system?.true_demon_ascension;
  const canDemonicCross = !p.cultivation_suppressed && !!trueDemonGate?.available;
  const canCelestialCross = !!data.world_travel?.can_ascend_celestial;
  const canAsuraCross = !!data.world_travel?.can_ascend_asura;
  const canCross = canNormalCross || canDemonicCross || canCelestialCross || canAsuraCross;
  const companionCanCross = canNormalCross && data.dao_companion?.alive && data.dao_companion.world === 'human'
    && data.dao_companion.realm_index === 5 && data.dao_companion.layer <= 3;
  const crossingFriends = canNormalCross ? (data.dao_friends || []).filter(friend =>
    friend.alive && friend.world === 'human' && friend.realm_index === p.realm_index
  ) : [];
  crossing.classList.toggle('hidden', !canCross);
  crossing.dataset.operation = canCelestialCross ? 'celestial-ascension' : canAsuraCross ? 'asura-ascension' : 'spirit-crossing';
  crossing.querySelector('b').textContent = canCelestialCross ? '渡劫飞升' : canAsuraCross ? '飞升修罗界' : canDemonicCross ? `飞升${p.world === 'human' ? '魔界' : '真魔界'}` : `偷渡${p.path === 'ghost' ? '地狱界' : p.path === 'monster' ? '妖界' : '灵界'}`;
  crossing.querySelector('span').textContent = canCelestialCross
    ? '开启九重飞升判定；第三、六、九关为可受雷伤减免影响的仙雷'
    : canAsuraCross
    ? '开启九重修罗天魔劫；第三、六、九关为可受雷伤减免影响的兵雷'
    : canDemonicCross
    ? (p.world === 'demon' && trueDemonGate
      ? `魔气等级 ${trueDemonGate.current_demon_qi_level}/${trueDemonGate.required_demon_qi_level}；未达要求仍可强行飞升，但会直接陨落；傀儡也无法携带`
      : '跨越界壁时无法携带任何傀儡，现有傀儡将全部遗失')
    : `${companionCanCross
      ? `你与${data.dao_companion.name}同为化神初期，道侣将安全同行`
      : '一次机会，连续通过信物、HP 与战力三重死关'}${crossingFriends.length ? `；另有 ${crossingFriends.length} 位同境道友愿冒险同行（生还率较低）` : ''}`;
  const worldTravel = data.world_travel || {};
  const crossWorld = $('#cross-world-action');
  const crossWorldSecondary = $('#cross-world-secondary-action');
  const netherDestinations = worldTravel.can_descend_monster && worldTravel.can_descend_phantom
    ? ['monster_realm', 'phantom_underworld'] : [];
  const crossDestination = netherDestinations[0] || (worldTravel.can_return_human ? 'human' : worldTravel.can_return_spirit ? 'spirit' : worldTravel.can_return_hell ? 'hell' : worldTravel.can_return_demon ? 'demon' : worldTravel.can_return_true_demon ? 'true_demon' : worldTravel.can_descend_spirit ? 'spirit' : worldTravel.can_return_celestial ? 'celestial' : worldTravel.can_descend_true_demon ? 'true_demon' : worldTravel.can_return_asura ? 'asura' : worldTravel.can_descend_phantom ? 'phantom_underworld' : worldTravel.can_return_nether ? 'nether' : '');
  crossWorld.classList.toggle('hidden', !crossDestination);
  crossWorld.dataset.destination = crossDestination;
  const secondaryDestination = netherDestinations[1] || '';
  crossWorldSecondary.classList.toggle('hidden', !secondaryDestination);
  crossWorldSecondary.dataset.destination = secondaryDestination;
  const destinationNames = {human:'人界', spirit:'灵界', demon:'魔界', true_demon:'真魔界', hell:'地狱界', reincarnation:'轮回界', celestial:'仙界', asura:'修罗界', monster_realm:'妖界', phantom_underworld:'幻冥界', nether:'幽冥界'};
  $('#cross-world-title').textContent = crossDestination ? `${netherDestinations.length ? '下界' : '返回'}${destinationNames[crossDestination]}` : '跨界移动';
  $('#cross-world-secondary-title').textContent = secondaryDestination ? `下界${destinationNames[secondaryDestination]}` : '跨界移动';
  $('#cross-world-secondary-hint').textContent = '真灵道果将封存至大乘九层；可随时重返幽冥界';
  $('#cross-world-hint').textContent = worldTravel.can_descend_spirit
    ? '仙境修为将受灵界法则压制至大乘九层；飞升按钮不会再次出现'
    : worldTravel.can_descend_true_demon
    ? '修罗道果将受真魔界法则压制至魔尊九层；可随时重返修罗界'
    : worldTravel.can_descend_phantom
    ? '真灵道果将受下界法则压制至大乘九层；可随时重返幽冥界'
    : crossDestination === 'celestial'
      ? '解除灵界压制，完整复原仙境道果'
      : crossDestination === 'asura'
        ? '解除真魔界压制，完整复原修罗道果'
      : crossDestination === 'nether'
        ? '解除妖界或幻冥界压制，完整复原真灵道果'
      : ['human', 'demon'].includes(crossDestination)
        ? `修为将受界面压制至${crossDestination === 'demon' ? '化魔' : '化神'}初期三层`
        : `解除界面压制，完整复原${crossDestination === 'true_demon' ? '魔尊' : '大乘'}道果`;
  $('#seed-label').textContent = `天机数 ${data.seed}`;
  $('#world-news-debug').textContent = `跨界 Debug：${data.debug_world_news ? '开' : '关'}`;
  $('#world-news-debug').classList.toggle('active', !!data.debug_world_news);
  renderInventory(p.inventory); renderArtSkills(data.art_skills || []); renderSpiritField(data.spirit_field || {}); renderDemonicSystem(data.demonic_system || {}); renderMap(data.map, data.auction_system); renderMarket(data.market); renderAuction(data.auction_system || {}); renderFaction(data.faction); renderWars(data.war_system || {}); renderFamily(data.family, data.governance); renderWorldNpcs(data.world_npcs || []); renderSpiritRanking(data.spirit_ranking); renderRaceSystem(data.race_system); renderWorldRoute(data.world_route); renderCrafting(data.crafting_system || {}); renderNatalArtifact(data.natal_artifact || {}); renderHeavenlyCourt(data.heavenly_court || {}); renderHistory(data.history); renderSettings(data.settings || {}); renderBattleReport(data.last_combat_report); renderEvent();
  $('#ending-card').classList.toggle('hidden', p.alive);
  $('#death-reason').textContent = p.death_reason || '';
  renderPostBattlePossession();
  renderButtons();
}

function renderPostBattlePossession() {
  const pending = game?.pending_event;
  const active = !game?.player?.alive && pending?.id === 'SYS_POST_BATTLE_POSSESSION';
  const panel = $('#post-battle-possession');
  const choices = $('#post-battle-possession-choices');
  panel.classList.toggle('hidden', !active);
  choices.innerHTML = '';
  if (!active) return;
  (pending.choices || []).forEach(choice => {
    const button = document.createElement('button');
    button.className = 'post-battle-possession-choice';
    button.textContent = choice.text;
    button.disabled = busy || choice.enabled === false;
    button.onclick = () => mutate(`/api/games/${game.id}/post-battle-possession`, {target_id:choice.id});
    choices.appendChild(button);
  });
}

const craftingStatOrder = ['combat_power','max_hp','max_mp','opportunity_efficiency','body_training_efficiency','divine_sense_efficiency','tribulation_reduction','breakthrough_bonus'];

function craftingPayload() {
  const allocations = {};
  document.querySelectorAll('#crafting-allocations input[data-stat]').forEach(input => allocations[input.dataset.stat] = Number(input.value || 0));
  return {
    mold_id:$('#crafting-mold').value, primary_id:$('#crafting-primary').value,
    secondary_a_id:$('#crafting-secondary-a').value, secondary_b_id:$('#crafting-secondary-b').value,
    quench_id:$('#crafting-quench').value, name:$('#crafting-name').value, allocations,
  };
}

function craftingStatText(stat, value, names) {
  const numeric = Number(value || 0);
  const shown = stat.endsWith('efficiency') || stat.endsWith('reduction') || stat === 'breakthrough_bonus'
    ? percent(numeric) : number(numeric);
  return `${names[stat] || stat} +${shown}`;
}

function renderCrafting(system) {
  const panel = $('#crafting-card'), dock = document.querySelector('[data-panel-target="crafting"]');
  panel.classList.toggle('hidden', !system.visible); dock?.classList.toggle('hidden', !system.visible);
  if (!system.visible) { window.UtilityPanels?.close('crafting'); return; }
  $('#crafting-heading').textContent = `炼器 ${system.active_count}/${system.active_slots} · 材料 ${system.materials?.length || 0}`;
  const moldSelect = $('#crafting-mold'); moldSelect.innerHTML = '';
  (system.molds || []).forEach(mold => {
    const option = document.createElement('option'); option.value = mold.id;
    option.textContent = `${mold.name} · ${mold.rule.name}：${mold.rule.description}`; moldSelect.appendChild(option);
  });
  const fillMaterials = (selector, role) => {
    const select = $(selector); select.innerHTML = '';
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = `选择${role === 'primary' ? '主材' : role === 'secondary' ? '辅材' : '淬火材料'}`; select.appendChild(placeholder);
    (system.materials || []).filter(row => row.roles?.includes(role)).forEach(material => {
      const option = document.createElement('option'); option.value = material.id;
      const effect = material.role_effects?.[role]?.description || '';
      option.textContent = `${material.name} · ${material.state} · 价值 ${number(material.material_value)} · ${effect}`;
      select.appendChild(option);
    });
  };
  fillMaterials('#crafting-primary', 'primary'); fillMaterials('#crafting-secondary-a', 'secondary');
  fillMaterials('#crafting-secondary-b', 'secondary'); fillMaterials('#crafting-quench', 'quench');

  const allocations = $('#crafting-allocations'); allocations.innerHTML = '';
  craftingStatOrder.forEach(stat => {
    const label = document.createElement('label'); const title = document.createElement('span');
    const input = document.createElement('input'); const cost = Number(system.stat_costs?.[stat] || 1);
    title.textContent = `${system.stat_names?.[stat] || stat} · 每点占 ${Number.isInteger(cost) ? cost : cost.toFixed(1)}`;
    input.type = 'number'; input.min = '0'; input.max = String(system.budget || 0); input.step = '1'; input.value = '0'; input.dataset.stat = stat;
    input.oninput = updateCraftingBudget; label.append(title, input); allocations.appendChild(label);
  });
  updateCraftingBudget();
  $('#crafting-preview-result').innerHTML = '<p class="empty">选定五位与属性预算后，可先推演全部固定效果和品质概率。</p>';
  $('#crafting-preview').onclick = previewCrafting;
  $('#crafting-save-blueprint').onclick = () => mutate(`/api/games/${game.id}/crafting-blueprint`, craftingPayload());

  const library = $('#crafting-material-library'); library.innerHTML = '';
  (system.materials || []).forEach(material => {
    const row = document.createElement('div'); row.className = 'crafting-material-row';
    const name = document.createElement('b'); name.textContent = material.name;
    const detail = document.createElement('small');
    detail.textContent = `${material.state} · ${material.source} · 材料价值 ${number(material.material_value)} · ${material.roles.map(role => ({primary:'主材',secondary:'辅材',quench:'淬火'})[role]).join('、')}`;
    row.append(name, detail); library.appendChild(row);
  });
  if (!system.materials?.length) library.innerHTML = '<p class="empty">暂无炼器材料。各界坊市每次换货会额外出现三份有独立品相的炼器材料；部分灵田实生灵植也可入器。</p>';

  const artifactList = $('#crafted-artifact-list'); artifactList.innerHTML = '';
  (system.artifacts || []).forEach(artifact => {
    const row = document.createElement('div'); row.className = `crafted-artifact-row${artifact.equipped ? ' active' : ''}`;
    const info = document.createElement('div'); const title = document.createElement('b'); const detail = document.createElement('small'); const stats = document.createElement('small');
    title.textContent = `${artifact.is_natal ? '本命 · ' : ''}${artifact.name} · ${artifact.quality_name}`;
    detail.textContent = `${artifact.mold_name} · 创制于 ${timelineText(artifact.created_year)} · 锚定价值 ${number(artifact.anchor_value)}灵石`;
    stats.textContent = Object.entries(artifact.actual_stats || {}).filter(([,value]) => Number(value)).map(([key,value]) => craftingStatText(key,value,system.stat_names || {})).join(' · ') || '未分配常驻属性';
    info.append(title, detail, stats);
    const tools = document.createElement('div'); tools.className = 'crafted-artifact-tools';
    const equip = document.createElement('button'); equip.textContent = artifact.equipped ? '卸下' : '装备';
    equip.disabled = artifact.is_natal; equip.dataset.craftingUnavailable = artifact.is_natal ? '1' : '0'; equip.onclick = () => mutate(`/api/games/${game.id}/crafted-artifact`, {artifact_id:artifact.id, action:artifact.equipped ? 'unequip' : 'equip'});
    const natal = document.createElement('button'); natal.textContent = artifact.is_natal ? '解除本命' : '炼为本命';
    natal.onclick = () => openGameConfirm({title:artifact.is_natal ? '解除本命' : '本命认主', body:artifact.is_natal ? `确认解除“${artifact.name}”的本命关系？法宝本身不会消失。` : `确认将“${artifact.name}”设为唯一的组合式本命法宝？原有组合式本命关系会解除。`, confirmText:'确认', onConfirm:()=>mutate(`/api/games/${game.id}/crafted-artifact`, {artifact_id:artifact.id, action:artifact.is_natal ? 'unbind_natal' : 'natal'})});
    const sell = document.createElement('button'); sell.textContent = `坊市出售 · ${number(Math.round(artifact.anchor_value * .55))}`;
    sell.disabled = artifact.equipped; sell.dataset.craftingUnavailable = artifact.equipped ? '1' : '0'; sell.onclick = () => openGameConfirm({title:'出售唯一法宝实例', body:`确认出售“${artifact.name}”？成交后该实例将永久离开存档，不能赎回。`, confirmText:'确认出售', onConfirm:()=>mutate(`/api/games/${game.id}/crafted-artifact`, {artifact_id:artifact.id, action:'sell'})});
    tools.append(equip, natal, sell);
    if (system.auction_available && !artifact.equipped) {
      const start = document.createElement('input'); start.type = 'number'; start.min = String(Math.ceil(artifact.anchor_value * .25)); start.max = String(Math.floor(artifact.anchor_value * 5)); start.value = String(Math.round(artifact.anchor_value * .8)); start.title = '寄拍起拍价';
      const consign = document.createElement('button'); consign.textContent = '寄拍'; consign.onclick = () => mutate(`/api/games/${game.id}/crafted-artifact`, {artifact_id:artifact.id, action:'consign', start_price:Number(start.value || 0)});
      tools.append(start, consign);
    }
    row.append(info, tools); artifactList.appendChild(row);
  });
  if (!system.artifacts?.length) artifactList.innerHTML = '<p class="empty">尚未炼成组合式法宝。</p>';

  const blueprints = $('#crafting-blueprint-list'); blueprints.innerHTML = '';
  (system.blueprints || []).forEach(blueprint => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'crafting-blueprint';
    button.textContent = `${blueprint.name} · ${blueprint.material_types.join(' / ')}`;
    button.onclick = () => applyCraftingBlueprint(blueprint, system);
    blueprints.appendChild(button);
  });
  if (!system.blueprints?.length) blueprints.innerHTML = '<p class="empty">暂无图谱。</p>';
}

function updateCraftingBudget() {
  const system = game?.crafting_system || {}; let used = 0;
  document.querySelectorAll('#crafting-allocations input[data-stat]').forEach(input => used += Number(input.value || 0) * Number(system.stat_costs?.[input.dataset.stat] || 1));
  const label = $('#crafting-budget'); if (!label) return;
  label.textContent = `${used.toFixed(1)} / ${number(system.budget || 0)}`; label.classList.toggle('over', used > Number(system.budget || 0));
}

async function previewCrafting() {
  if (busy) return;
  busy = true; document.body.classList.add('busy'); renderButtons();
  try {
    const preview = await api(`/api/games/${game.id}/crafting-preview`, {method:'POST', body:JSON.stringify(craftingPayload())});
    const root = $('#crafting-preview-result'); root.innerHTML = '';
    const title = document.createElement('h4'); title.textContent = `${preview.mold.rule.name} · 锚定价值 ${number(preview.anchor_value)}灵石`;
    const effects = document.createElement('p'); effects.textContent = [preview.mold.rule.description, ...(preview.material_effects || []).map(row => `${row.name}：${row.description}`)].join(' ');
    const normal = document.createElement('p'); normal.textContent = `普通品质：${Object.entries(preview.theoretical_stats.normal || {}).filter(([,value]) => Number(value)).map(([key,value]) => craftingStatText(key,value,game.crafting_system.stat_names || {})).join(' · ')}`;
    const odds = document.createElement('p'); odds.className = 'muted'; odds.textContent = `品质概率：${Object.entries(preview.quality_probabilities).map(([key,value]) => `${preview.quality_names[key]} ${percent(value)}`).join(' · ')}`;
    const forge = document.createElement('button'); forge.className = 'primary'; forge.textContent = '确认开炉';
    forge.onclick = () => openGameConfirm({title:'确认组合炼器', body:`将永久消耗这四份具体材料实例，成品最低为残缺品质，不会彻底失败。锚定价值 ${number(preview.anchor_value)} 灵石。`, confirmText:'开炉炼器', onConfirm:()=>mutate(`/api/games/${game.id}/crafting-forge`, craftingPayload())});
    root.append(title, effects, normal, odds, forge);
  } catch (error) { toast(error.message); }
  finally { busy = false; document.body.classList.remove('busy'); renderButtons(); }
}

function applyCraftingBlueprint(blueprint, system) {
  $('#crafting-mold').value = blueprint.mold_id;
  const used = new Set(); const selectors = ['#crafting-primary','#crafting-secondary-a','#crafting-secondary-b','#crafting-quench'];
  blueprint.material_types.forEach((definitionId, index) => {
    const material = (system.materials || []).find(row => row.definition_id === definitionId && !used.has(row.id));
    $(selectors[index]).value = material?.id || ''; if (material) used.add(material.id);
  });
  document.querySelectorAll('#crafting-allocations input[data-stat]').forEach(input => input.value = String(blueprint.allocations?.[input.dataset.stat] || 0));
  updateCraftingBudget();
  toast('已按图谱填入当前拥有的同类材料；缺少的实例保持为空。');
}

function renderNatalArtifact(system) {
  const panel=$('#natal-artifact-card'), dock=document.querySelector('[data-panel-target="natal-artifact"]');
  panel.classList.toggle('hidden',!system.visible); dock?.classList.toggle('hidden',!system.visible);
  if(!system.visible){window.UtilityPanels?.close('natal-artifact');return;}
  const root=$('#natal-artifact-content');root.innerHTML='';
  if(!system.bound){
    $('#natal-artifact-heading').textContent='结丹后开放';
    const lead=document.createElement('p');lead.className='muted';lead.textContent='选择一件传统法宝收入丹田。认主后不可交易，其原有属性将随祭炼等级持续成长；组合炼器成品请在“器”界面单独设置本命。';root.appendChild(lead);
    const candidates=document.createElement('div');candidates.className='natal-candidates';
    (system.candidates||[]).forEach(item=>{const row=document.createElement('div'),text=document.createElement('span'),name=document.createElement('b'),detail=document.createElement('small'),button=document.createElement('button');name.textContent=item.name;detail.textContent=item.description;text.append(name,detail);button.className='natal-action';button.textContent='炼为本命';button.onclick=()=>mutate(`/api/games/${game.id}/natal-artifact`,{action:'bind',item_id:item.id});row.append(text,button);candidates.appendChild(row);});
    if(!system.candidates?.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='背包中暂无可认主的法宝或装备。';candidates.appendChild(empty);}root.appendChild(candidates);return;
  }
  $('#natal-artifact-heading').textContent=`${system.name} · ${system.level}/${system.max_level}级`;
  const head=document.createElement('div');head.className='natal-head';
  const identity=document.createElement('div'),title=document.createElement('h3'),description=document.createElement('p');title.textContent=system.name;description.className='muted';description.textContent=system.description;identity.append(title,description);
  const refine=document.createElement('button');refine.className='natal-action';refine.textContent=system.level>=system.max_level?'祭炼圆满':`灵石温养 · ${number(system.refine_cost)}`;refine.dataset.natalUnavailable=system.can_refine?'0':'1';refine.onclick=()=>mutate(`/api/games/${game.id}/natal-artifact`,{action:'refine'});head.append(identity,refine);root.appendChild(head);
  const progress=document.createElement('div');progress.className='natal-level-progress';const fill=document.createElement('i');fill.style.width=system.level>=system.max_level?'100%':`${Math.min(100,Number(system.experience)/Math.max(1,Number(system.experience_required))*100)}%`;const label=document.createElement('span');label.textContent=system.level>=system.max_level?'祭炼已臻圆满':`祭炼经验 ${system.experience}/${system.experience_required}`;progress.append(fill,label);root.appendChild(progress);
  const bonuses=document.createElement('div');bonuses.className='natal-bonuses';[['战斗力',number(system.bonuses.combat_bonus)],['最大 HP',number(system.bonuses.hp_bonus)],['最大 MP',number(system.bonuses.mp_bonus)],['机缘效率',`+${Math.round(system.bonuses.opportunity_bonus*100)}%`],['雷劫减免',`+${Math.round(system.bonuses.tribulation_reduction*100)}%`]].forEach(([name,value])=>{const row=document.createElement('span'),small=document.createElement('small'),strong=document.createElement('b');small.textContent=name;strong.textContent=value;row.append(small,strong);bonuses.appendChild(row);});root.appendChild(bonuses);
  const visual=document.createElement('div');visual.className='natal-artifact-visual';
  const swordShadow=document.createElement('img');swordShadow.className='natal-sword-shadow';swordShadow.src='/assets/natal-artifact-ancient-sword.png?v=20260912-1';swordShadow.alt='';swordShadow.setAttribute('aria-hidden','true');
  const sword=document.createElement('img');sword.className='natal-sword natal-sword-body';sword.src='/assets/natal-artifact-ancient-sword.png?v=20260912-1';sword.alt='';sword.setAttribute('aria-hidden','true');
  visual.append(swordShadow,sword);
  const slotLayer=document.createElement('div');slotLayer.className='natal-slot-layer';
  const picker=document.createElement('div');picker.className='natal-material-picker hidden';visual.append(slotLayer,picker);
  const closePicker=()=>picker.classList.add('hidden');
  (system.slots||[]).forEach(slot=>{const button=document.createElement('button');button.className=`natal-slot slot-${slot.index} ${slot.unlocked?'':'locked'} ${slot.material_id?'filled':''}`;button.dataset.natalUnavailable=slot.unlocked?'0':'1';button.innerHTML=slot.material_id?'<span>◆</span>':'<span>＋</span>';const caption=document.createElement('small');caption.textContent=slot.unlocked?(slot.name||'空槽'):`${slot.index+1}槽·未解锁`;button.appendChild(caption);button.title=slot.description||caption.textContent;
    if(slot.unlocked&&slot.material_id){button.onclick=()=>mutate(`/api/games/${game.id}/natal-artifact`,{action:'unsocket',slot_index:slot.index});}
    else if(slot.unlocked){button.onclick=()=>{picker.innerHTML='';picker.classList.remove('hidden');const heading=document.createElement('b');heading.textContent=`第 ${slot.index+1} 槽 · 选择材料`;const close=document.createElement('button');close.textContent='×';close.onclick=closePicker;picker.append(heading,close);const choices=document.createElement('div');(system.materials||[]).forEach(material=>{const option=document.createElement('button');option.className='natal-material-choice';option.dataset.natalUnavailable=material.available?'0':'1';option.textContent=`${material.name} ×${material.quantity}`;option.title=material.description;option.onclick=()=>mutate(`/api/games/${game.id}/natal-artifact`,{action:'socket',item_id:material.item_id,slot_index:slot.index});choices.appendChild(option);});picker.appendChild(choices);renderButtons();};}
    slotLayer.appendChild(button);});
  root.appendChild(visual);
  const hint=document.createElement('p');hint.className='natal-hint';hint.textContent=`已解锁 ${system.unlocked_slots}/7 槽。点击空槽选择材料；点击已有材料可安全取回。修炼时本命法宝会随周天自动积累祭炼经验。`;root.appendChild(hint);
}

function renderHeavenlyCourt(court) {
  const panel = $('#heavenly-court-card');
  const dock = document.querySelector('[data-panel-target="heavenly-court"]');
  const visible = !!court.visible;
  panel.classList.toggle('hidden', !visible); dock?.classList.toggle('hidden', !visible);
  if (!visible) { window.UtilityPanels?.close('heavenly-court'); return; }
  const root = $('#heavenly-court-content'); root.innerHTML = '';
  if (!court.initialized) { root.textContent = '天庭正在汇集仙域宗门名册。'; return; }
  $('#court-heading').textContent = `第 ${court.unit} 单位 · ${court.seat_count} 席（大${court.seat_sizes?.large||0}·中${court.seat_sizes?.medium||0}·小${court.seat_sizes?.small||0}）`;
  const summary = document.createElement('div'); summary.className = 'court-summary';
  [['天庭权威',number(court.authority)],['府库灵石',number(court.treasury)],['战备装备',number(court.equipment)],['你的官阶',`${court.player_grade}品`],['功德',`${number(court.player_merit)}${court.next_grade_merit ? ` / ${number(court.next_grade_merit)}` : ''}`],['个人支持度',`${Number(court.player_support).toFixed(1)}%`],['掌握七曜',`${court.player_controls} / 7`],['本宗影响力',number(court.player_seat_influence)]].forEach(([label,value]) => {
    const row=document.createElement('div'), small=document.createElement('small'), strong=document.createElement('strong'); small.textContent=label; strong.textContent=value; row.append(small,strong); summary.appendChild(row);
  }); root.appendChild(summary);
  const officeSection=document.createElement('section'), officeTitle=document.createElement('h3'), offices=document.createElement('div'); officeTitle.textContent='七曜星君'; offices.className='court-offices';
  (court.offices||[]).forEach(office => { const row=document.createElement('div'), name=document.createElement('b'), holder=document.createElement('small'); row.className=office.holder?.holder_id==='player'?'player-held':''; name.textContent=`${office.name} · ${office.element}`; holder.textContent=office.holder?`${office.holder.holder_name}${office.holder.holder_id==='player'?'（你）':''} · 至第 ${office.holder.end_unit} 单位`:'席位待选'; row.append(name,holder); offices.appendChild(row); });
  officeSection.append(officeTitle,offices); root.appendChild(officeSection);
  if (court.election) {
    const election=document.createElement('section'), heading=document.createElement('h3'), candidates=document.createElement('p'), method=document.createElement('select'), pledge=document.createElement('select'), resolve=document.createElement('button'); election.className='court-election'; heading.textContent=`${court.election.office_name}大选 · 第 ${court.election.round} 轮`; candidates.textContent=`候选：${court.election.candidates.map(row=>`${row.name}${row.id==='player'?'（你）':''}·${row.grade}品`).join('、')}`;
    [['none','不额外拉票'],['relationship','动用人脉'],['faction','花费本宗影响力'],['promise_decree','承诺推行决议'],['promise_law','承诺制定或废除天条']].forEach(([value,label])=>{const option=document.createElement('option');option.value=value;option.textContent=label;method.appendChild(option);});
    const updatePledges=()=>{pledge.innerHTML='';const rows=method.value==='promise_decree'?court.decrees:method.value==='promise_law'?court.laws:[];rows.forEach(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=row.name;pledge.appendChild(option);});pledge.classList.toggle('hidden',!method.value.startsWith('promise_'));}; method.onchange=updatePledges; updatePledges();
    resolve.className='court-action'; resolve.textContent='完成本轮投票（不流逝时间）'; resolve.onclick=()=>mutate(`/api/games/${game.id}/heavenly-election`,{method:method.value,pledge_id:pledge.value}); election.append(heading,candidates,method,pledge,resolve);
    if(court.election.votes){const prior=document.createElement('small');prior.textContent=`上一轮：${Object.values(court.election.votes).sort((a,b)=>b-a).join(' / ')} 票，最高者未达 13 票。`;election.appendChild(prior);} root.appendChild(election);
  }
  const exam=document.createElement('section'), examText=document.createElement('span'), examButton=document.createElement('button'); exam.className='court-inline'; examText.textContent=court.player_grade>1?`晋升 ${court.player_grade-1} 品需 ${number(court.next_grade_merit)} 功德，并通过考核。`:'你已位列一品天官。'; examButton.className='court-action'; examButton.textContent='接受进阶考核'; examButton.dataset.courtUnavailable=court.player_grade<=1||court.player_merit<court.next_grade_merit?'1':'0'; examButton.onclick=()=>mutate(`/api/games/${game.id}/heavenly-court`,{action:'examination'}); exam.append(examText,examButton); root.appendChild(exam);
  const influence=document.createElement('input'); influence.type='number'; influence.min='0'; influence.max=String(Math.min(15,court.player_seat_influence)); influence.value='0'; influence.placeholder='宗门影响力 0-15'; influence.dataset.courtUnavailable=court.player_is_representative?'0':'1'; influence.title='宗门代表可花费至多15影响力：提高天条游说率或强化决议效果';
  const target=document.createElement('select'); target.className='court-target'; (court.target_npcs||[]).forEach(npc=>{const option=document.createElement('option');option.value=npc.id;option.textContent=`${npc.name} · ${npc.realm_name}${npc.wanted?' · 通缉中':''}`;target.appendChild(option);});
  const policies=document.createElement('div'), decreeSection=document.createElement('section'), decreeTitle=document.createElement('h3'), active=document.createElement('p'); policies.className='court-policy-grid'; decreeTitle.textContent=`决议（${court.active_decrees.length}/${court.decree_slots}）`; active.className='muted'; active.textContent=court.active_decrees.length?`生效中：${court.active_decrees.map(row=>`${row.name}至第${row.expires_unit}单位`).join('、')}`:'当前没有生效中的临时决议。'; decreeSection.append(decreeTitle,active,influence,target);
  (court.decrees||[]).forEach(decree=>{const button=document.createElement('button');button.className='court-action court-policy';button.textContent=decree.enabled?decree.name:`${decree.name}（${decree.disabled_reason}）`;button.dataset.courtUnavailable=decree.enabled?'0':'1';button.onclick=()=>mutate(`/api/games/${game.id}/heavenly-court`,{action:`decree:${decree.id}`,target_id:target.value,influence_spend:Number(influence.value)||0});decreeSection.appendChild(button);});
  const lawSection=document.createElement('section'), lawTitle=document.createElement('h3');lawTitle.textContent='天条';lawSection.appendChild(lawTitle);
  (court.laws||[]).forEach(law=>{const row=document.createElement('div'),text=document.createElement('span'),name=document.createElement('b'),detail=document.createElement('small'),button=document.createElement('button');row.className=`court-law ${law.active?'active':''}`;name.textContent=`${law.name} · ${law.active?'施行中':'未施行'}`;detail.textContent=law.description;text.append(name,detail);button.className='court-action';button.textContent=law.active?'提请废除':'提请施行';button.dataset.courtUnavailable=court.player_controls<1?'1':'0';button.onclick=()=>mutate(`/api/games/${game.id}/heavenly-court`,{action:`law:${law.id}`,enact:!law.active,influence_spend:Number(influence.value)||0});row.append(text,button);lawSection.appendChild(row);});
  policies.append(decreeSection,lawSection);root.appendChild(policies);
  if(court.pledges?.length){const pledges=document.createElement('p');pledges.className='court-pledges';pledges.textContent=`尚待兑现：${court.pledges.map(row=>`${row.kind==='law'?'天条':'决议'} ${row.id}（第${row.deadline_unit}单位前）`).join('、')}`;root.appendChild(pledges);}
}

function renderFaction(faction) {
  const summary = $('#faction-summary'); summary.innerHTML = '';
  const diplomacyDetail = $('#faction-diplomacy-detail'); diplomacyDetail.innerHTML = '';
  const rewards = $('#faction-rewards'); const roster = $('#faction-roster'); const dispatch = $('#faction-dispatch');
  rewards.classList.toggle('hidden', !faction.member); roster.classList.toggle('hidden', !faction.member);
  dispatch.classList.toggle('hidden', !faction.member || !faction.can_dispatch);
  if (!faction.member) {
    $('#faction-title').textContent = `${faction.world_name}宗门`; $('#faction-role').textContent = faction.system_available ? '尚未入门' : '暂未开放';
    $('#faction-description').textContent = faction.system_available
      ? `在${faction.world_name}游历时可能遇到当地宗门招募。加入后可领取年度福利，也必须承担本界宗门任务。`
      : `${faction.world_name}当前尚未配置可加入宗门。`;
    faction.available.forEach(entry => {
      const card = document.createElement('div'); card.className = 'faction-brief';
      const name = document.createElement('b'); name.textContent = entry.name;
      const detail = document.createElement('span'); detail.textContent = `${entry.path} · ${entry.description}`;
      card.append(name, detail); summary.appendChild(card);
    });
    if (faction.can_found) summary.appendChild(namedCreationForm('创建自己的宗门', '宗门名号', '开宗立派', name => mutate(`/api/games/${game.id}/create-faction`, {name})));
    return;
  }
  $('#faction-title').textContent = faction.name; $('#faction-role').textContent = faction.role;
  $('#faction-description').textContent = faction.description;
  const details = document.createElement('p'); details.className = 'faction-meta';
  details.textContent = `${timelineText(faction.join_age)}入门 · 宗门贡献 ${faction.contribution}`; summary.appendChild(details);
  if (faction.can_leave) {
    const leave = document.createElement('button'); leave.className = 'relationship-exit'; leave.textContent = '退出宗门';
    leave.onclick = () => mutate(`/api/games/${game.id}/leave-faction`, {}); summary.appendChild(leave);
  }
  if (faction.founded_by_player && faction.pressure > 0) {
    const warning = document.createElement('p'); warning.className = 'governance-warning';
    warning.textContent = `护山失败 ${faction.pressure}/${faction.pressure_limit}；每次排挤都会触发守山事件，第三次防守失败才会解散。`;
    summary.appendChild(warning);
  }
  if (faction.has_diplomatic_voice && faction.diplomacy?.length) {
    summary.appendChild(diplomacyForm(
      faction.diplomacy, `/api/games/${game.id}/faction-diplomacy`, '召开宗门外交表决'
    ));
    faction.diplomacy.filter(entry => entry.transfer_candidates?.length).forEach(entry => {
      summary.appendChild(vassalTransferForm('sect', entry.target_id, entry.target_name, entry.transfer_candidates));
    });
  }
  if (faction.diplomacy?.length) {
    const heading = document.createElement('h3'); heading.textContent = '外交详情与大事'; diplomacyDetail.appendChild(heading);
  }
  (faction.diplomacy || []).forEach(entry => {
    const card = document.createElement('div'); card.className = `diplomacy-detail-card ${entry.status}`;
    const vote = entry.last_vote ? ` · 最近表决 ${entry.last_vote.yes}/${entry.last_vote.total} 票${entry.last_vote.passed ? '通过' : '未通过'}` : '';
    const truce = entry.truce_units_remaining ? ` · 停战期剩 ${entry.truce_units_remaining} 单位` : '';
    const dependency = entry.status === 'vassal' ? ` · ${entry.overlord === faction.id ? '对方依附本宗' : '本宗依附对方'}` : '';
    const leaders = entry.leaders?.length ? entry.leaders.join('、') : '暂无坐镇修士';
    card.innerHTML = `<b>${entry.target_name} · ${entry.status_name}</b><small>宗门好感 ${number(entry.affinity)} · 在册 ${entry.living_count} 人 · 总战力 ${number(entry.combined_power)}${truce}${dependency}${vote}</small><small>坐镇修士：${leaders}</small>`;
    if (entry.recent_events?.length) {
      const news = document.createElement('div'); news.className = 'diplomacy-news';
      entry.recent_events.forEach(event => {
        const line = document.createElement('small'); line.textContent = `${timelineText(event.age)} · ${event.summary}`; news.appendChild(line);
      });
      card.appendChild(news);
    }
    diplomacyDetail.appendChild(card);
  });
  if (faction.diplomacy_events?.length) {
    const feed = document.createElement('section'); feed.className = 'diplomacy-news';
    const heading = document.createElement('h3'); heading.textContent = '近期宗门外交大事'; feed.appendChild(heading);
    faction.diplomacy_events.forEach(event => {
      const line = document.createElement('small'); line.textContent = `${timelineText(event.age)} · ${event.summary}`; feed.appendChild(line);
    });
    diplomacyDetail.appendChild(feed);
  }
  if (faction.can_dispatch) {
    $('#faction-dispatch-hint').textContent = faction.dispatch_used
      ? '本年度已经派遣过弟子，来年方可再次差遣。'
      : `每年可派遣一次，消耗 ${faction.dispatch_cost} 点宗门贡献；成功率约 ${percent(faction.dispatch_success)}。`;
    document.querySelectorAll('[data-dispatch]').forEach(button => {
      button.onclick = () => mutate(`/api/games/${game.id}/faction-dispatch`, {target:button.dataset.dispatch});
      button.disabled = busy || faction.dispatch_used || faction.contribution < faction.dispatch_cost || !!game.pending_event || !game.player.alive;
    });
  }
  $('#faction-reward-hint').textContent = faction.fixed_reward_unlocked
    ? '元婴初期后拥有议事席，可勾选并固定今后的年度奖励。'
    : '元婴初期前，年度结算会从下列福利中随机发放一项。';
  const options = $('#faction-reward-options'); options.innerHTML = '';
  Object.entries(faction.reward_options).forEach(([id, reward]) => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'reward-choice';
    if (faction.reward_preference === id) button.classList.add('selected');
    button.innerHTML = `<b>${reward.name}</b><span>${reward.description}</span>`;
    button.disabled = !faction.fixed_reward_unlocked || busy || !!game.pending_event || !game.player.alive;
    button.onclick = () => mutate(`/api/games/${game.id}/faction-reward`, {reward_id:id});
    options.appendChild(button);
  });
  $('#faction-roster-note').textContent = `按修为降序 · 已陨落 ${faction.fallen_count} 人`;
  const list = $('#faction-roster-list'); list.innerHTML = '';
  faction.roster.forEach((npc, index) => {
    const row = document.createElement('div'); row.className = 'roster-row';
    if (npc.is_player) row.classList.add('self');
    const order = document.createElement('i'); order.textContent = String(index + 1).padStart(2, '0');
    const relation = npc.is_master ? ' · 师父' : npc.is_disciple ? ' · 弟子' : npc.is_friend ? ' · 道友' : '';
    const identity = document.createElement('span'); identity.innerHTML = `<b>${npc.name}${npc.is_player ? '（你）' : ''}${relation}${npc.wounds ? `（负伤${npc.wounds}级）` : ''}</b><small>${npc.title} · ${npc.race_name || '种族未明'} · ${npc.path_name || '道统未明'} · ${npc.spirit_root_name || '灵根未明'} · ${npc.age} 岁 · 寿元 ${npc.lifespan == null ? '无尽' : npc.lifespan}</small><small>战力 ${number(npc.combat_power || 0)} · ${npc.breakthrough_chance == null ? '当前无瓶颈' : `突破率 ${percent(npc.breakthrough_chance)}`} · ${npc.affinity == null ? '' : `好感 ${number(npc.affinity)} / ${npc.attitude}`}${npc.treasure_name ? ` · 重宝 ${npc.treasure_name}` : ''}</small>`;
    const cultivation = document.createElement('strong'); cultivation.textContent = npc.realm_name;
    const controls = document.createElement('div'); controls.className = 'relationship-actions';
    if (npc.can_request_master) controls.appendChild(relationshipButton(npc, 'master', '拜师'));
    if (npc.can_accept_disciple) controls.appendChild(relationshipButton(npc, 'disciple', '收徒'));
    if (npc.in_party) controls.appendChild(partyButton(npc, 'leave', '离队'));
    else if (npc.can_invite_party) controls.appendChild(partyButton(npc, 'invite', '邀请同行'));
    if (npc.can_propose_companion) controls.appendChild(companionProposalButton(npc));
    if (npc.can_befriend) controls.appendChild(friendButton(npc));
    if (npc.can_intercept) {
      const intercept = document.createElement('button'); intercept.className = 'relationship-action danger'; intercept.textContent = '截杀';
      intercept.dataset.available = '1';
      intercept.onclick = () => mutate(`/api/games/${game.id}/faction-intercept`, {npc_id:npc.id});
      controls.appendChild(intercept);
    }
    row.append(order, identity, cultivation, controls); list.appendChild(row);
  });

  function relationshipButton(npc, role, label) {
    const button = document.createElement('button'); button.className = 'relationship-action'; button.textContent = label;
    button.onclick = () => mutate(`/api/games/${game.id}/faction-relationship`, {npc_id:npc.id, role});
    return button;
  }
  function partyButton(npc, action, label) {
    const button = document.createElement('button'); button.className = 'party-action'; button.textContent = label;
    button.onclick = () => mutate(`/api/games/${game.id}/party`, {npc_id:npc.id, action});
    return button;
  }
  function companionProposalButton(npc) {
    const button = document.createElement('button'); button.className = 'companion-action'; button.textContent = '结为道侣';
    button.onclick = () => mutate(`/api/games/${game.id}/dao-companion`, {npc_id:npc.id, action:'propose'});
    return button;
  }
  function friendButton(npc) {
    const button = document.createElement('button'); button.className = 'friend-action'; button.textContent = '结为道友';
    button.onclick = () => mutate(`/api/games/${game.id}/dao-friend`, {npc_id:npc.id, action:'befriend'});
    return button;
  }
}

function renderWars(system) {
  const list = $('#war-list'); list.innerHTML = '';
  $('#war-status').textContent = system.active_count ? `${system.active_count} 场战争进行中` : '当前无战事';
  if (!system.wars?.length) {
    list.innerHTML = '<p class="empty">尚无战争记录。外交宣战通过后，真正的征伐会在这里展开。</p>';
    return;
  }
  system.wars.forEach(war => {
    const card = document.createElement('details'); card.className = `war-card ${war.status}`;
    card.open = ['active', 'peace_ready'].includes(war.status);
    const summary = document.createElement('summary');
    const state = war.status === 'ended' ? '已结束' : war.status === 'peace_ready' ? '胜负已定' : war.controller === 'player' ? '由你指挥' : 'AI 演算中';
    summary.innerHTML = `<b>${war.attacker_name || '未知进攻方'} vs ${war.defender_name || '未知防御方'}</b><span>${state} · 战争分数 ${number(war.war_score || 0)}</span>`;
    const body = document.createElement('div'); body.className = 'war-body';
    const morale = document.createElement('div'); morale.className = 'war-morale';
    const attackPower = war.power_summary?.attacker || {};
    const defendPower = war.power_summary?.defender || {};
    morale.innerHTML = `<div><b>${war.attacker_name || '未知进攻方'}</b><span>士气 ${number(war.morale.attacker)} · 厌战 ${number(war.exhaustion.attacker)}%</span><small>总战力 ${number(attackPower.total || 0)} · 高阶战力 ${number(attackPower.elite || 0)}</small><i style="width:${Math.min(100, war.morale.attacker)}%"></i></div><div><b>${war.defender_name || '未知防御方'}（守方战力 +10%）</b><span>士气 ${number(war.morale.defender)} · 厌战 ${number(war.exhaustion.defender)}%</span><small>总战力 ${number(defendPower.total || 0)} · 高阶战力 ${number(defendPower.elite || 0)}</small><i style="width:${Math.min(100, war.morale.defender)}%"></i></div>`;
    body.appendChild(morale);
    const coalitions = document.createElement('div'); coalitions.className = 'war-coalitions';
    ['attacker', 'defender'].forEach(side => {
      const column = document.createElement('section');
      const heading = document.createElement('b'); heading.textContent = side === 'attacker' ? '进攻阵营' : '防御阵营'; column.appendChild(heading);
      (war.coalitions?.[side] || []).forEach(power => {
        const tag = document.createElement('span'); tag.textContent = `${power.name || power.id || '未知势力'}${power.role === 'leader' ? '（战争领袖）' : '（盟友）'}`; column.appendChild(tag);
      });
      coalitions.appendChild(column);
    });
    body.appendChild(coalitions);
    const rosters = document.createElement('div'); rosters.className = 'war-rosters';
    ['attacker', 'defender'].forEach(side => {
      const column = document.createElement('section');
      const heading = document.createElement('h3'); heading.textContent = side === 'attacker' ? '进攻方参战修士' : '防御方参战修士'; column.appendChild(heading);
      (war.roster?.[side] || []).forEach(npc => {
        const row = document.createElement('small');
        row.className = !npc.alive ? 'fallen' : npc.escaped ? 'escaped' : '';
        row.textContent = `${npc.name || '无名修士'}〔${npc.owner_name || '势力未明'}〕 · ${npc.realm_name || '境界未明'} · 战力 ${number(npc.combat_power)}${!npc.alive ? ' · 阵亡' : npc.escaped ? ' · 逃脱' : npc.wounds ? ` · 负伤${npc.wounds}级` : ''}`;
        column.appendChild(row);
      });
      rosters.appendChild(column);
    });
    body.appendChild(rosters);
    if (war.player_controls && war.status !== 'ended') {
      const actions = document.createElement('div'); actions.className = 'war-actions';
      if (war.can_call_allies && war.status === 'active') actions.appendChild(warAllyForm(war));
      if (!war.preliminary_resolved && war.status === 'active') actions.appendChild(warButton(war.id, 'conquest', '先锋出阵'));
      if (war.status === 'active') actions.appendChild(warButton(war.id, 'round', war.preliminary_resolved ? '推进一场会战' : '跳过先锋战，直接会战'));
      if (war.status === 'active') actions.appendChild(warButton(war.id, 'retreat', '主动撤退', true));
      body.appendChild(actions);
      if (war.peace_offer?.recipient_side === war.player_side) body.appendChild(warPeaceOffer(war));
      else if (war.can_negotiate) body.appendChild(warPeaceForm(war, system.terms || {}));
    } else if (war.status !== 'ended' && war.player_side) {
      const hint = document.createElement('p'); hint.className = 'muted'; hint.textContent = '你属于参战方，但尚无势力话语权；战争暂由决策者按总战力演算。取得话语权后将自动接管并补录此前战报。'; body.appendChild(hint);
    }
    if (war.logs?.length) {
      const logs = document.createElement('details'); logs.className = 'war-logs'; logs.open = war.status !== 'ended';
      const logSummary = document.createElement('summary'); logSummary.textContent = `战报 ${war.logs.length} 条`;
      logs.appendChild(logSummary);
      [...war.logs].reverse().forEach(log => { const line = document.createElement('small'); line.textContent = `${timelineText(log.age)} · ${log.title}：${log.text}`; logs.appendChild(line); });
      body.appendChild(logs);
    }
    card.append(summary, body); list.appendChild(card);
  });

  function warButton(warId, action, label, danger = false) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
    if (danger) button.className = 'danger';
    button.onclick = () => mutate(`/api/games/${game.id}/war-action`, {war_id:warId, action});
    return button;
  }

  function warAllyForm(war) {
    const form = document.createElement('form'); form.className = 'war-ally-form';
    const select = document.createElement('select');
    (war.callable_allies || []).forEach(ally => {
      const option = document.createElement('option'); option.value = ally.id;
      option.textContent = `邀请 ${ally.name || ally.id}（成功率约 ${number(ally.chance_percent)}%）`;
      select.appendChild(option);
    });
    const button = document.createElement('button'); button.type = 'submit'; button.textContent = '发送参战邀请';
    form.append(select, button);
    form.onsubmit = event => { event.preventDefault(); mutate(`/api/games/${game.id}/war-action`, {war_id:war.id, action:'call_allies', ally_id:select.value}); };
    return form;
  }

  function warPeaceForm(war, terms) {
    const form = document.createElement('form'); form.className = 'war-peace-form';
    const heading = document.createElement('b'); heading.textContent = '提出和谈条件';
    const term = document.createElement('select');
    Object.entries(terms).forEach(([id, def]) => {
      if (war.kind === 'race' && ['dissolve', 'annex'].includes(id)) return;
      const powerRequirement = def.power_ratio ? `，总战力比至少 ${def.power_ratio}` : '';
      const option = document.createElement('option'); option.value = id; option.textContent = `${def.name}${def.cost ? `（需战争分数 ${def.cost}${powerRequirement}）` : ''}`; term.appendChild(option);
    });
    const targetPower = document.createElement('select'); targetPower.className = 'conditional-power';
    const enemySide = war.player_side === 'attacker' ? 'defender' : 'attacker';
    (war.coalitions?.[enemySide] || []).forEach(power => { const option = document.createElement('option'); option.value = power.id; option.textContent = `和谈对象：${power.name}${power.role === 'leader' ? '' : '（盟友条款成本 +25%）'}`; targetPower.appendChild(option); });
    const target = document.createElement('select'); target.className = 'conditional-target';
    const fillTargets = () => {
      target.innerHTML = '';
      (war.roster?.[enemySide] || []).filter(npc => npc.alive && npc.owner_id === targetPower.value).forEach(npc => { const option = document.createElement('option'); option.value = npc.id; option.textContent = `处死 ${npc.name}`; target.appendChild(option); });
    };
    const third = document.createElement('select'); third.className = 'conditional-third';
    (war.third_parties || []).forEach(power => { const option = document.createElement('option'); option.value = power.id; option.textContent = `第三方：${power.name}`; third.appendChild(option); });
    const thirdStatus = document.createElement('select'); thirdStatus.className = 'conditional-third';
    Object.entries(game?.governance?.diplomacy_statuses || {}).filter(([id]) => id !== 'war').forEach(([id, name]) => { const option = document.createElement('option'); option.value = id; option.textContent = `改为${name}`; thirdStatus.appendChild(option); });
    const demand = document.createElement('button'); demand.type = 'submit'; demand.textContent = '以战果提出条件';
    const concede = document.createElement('button'); concede.type = 'button'; concede.textContent = '出卖本方利益求和'; concede.className = 'danger';
    const sync = () => { target.classList.toggle('hidden', term.value !== 'execute'); third.classList.toggle('hidden', term.value !== 'change_relation'); thirdStatus.classList.toggle('hidden', term.value !== 'change_relation'); };
    targetPower.onchange = fillTargets; fillTargets();
    term.onchange = sync; sync();
    form.append(heading, term, targetPower, target, third, thirdStatus, demand, concede);
    const payload = forceConcede => ({war_id:war.id, term:term.value, target_power_id:targetPower.value || '', target_id:target.value || '', third_party_id:third.value || '', third_status:thirdStatus.value || 'neutral', concede:forceConcede});
    form.onsubmit = event => { event.preventDefault(); mutate(`/api/games/${game.id}/war-peace`, payload(false)); };
    concede.onclick = () => mutate(`/api/games/${game.id}/war-peace`, {...payload(true), target_id:''});
    return form;
  }

  function warPeaceOffer(war) {
    const offer = document.createElement('section'); offer.className = 'war-peace-offer';
    const heading = document.createElement('b'); heading.textContent = `敌方和约要求（可用 ${war.peace_offer.budget} / 已用 ${war.peace_offer.total_cost} 战争分数）`; offer.appendChild(heading);
    (war.peace_offer.demands || []).forEach(row => {
      const line = document.createElement('span');
      line.textContent = `${row.label}：${row.target_power_name}${row.target_name ? ` · ${row.target_name}` : ''}（${row.cost}）`; offer.appendChild(line);
    });
    offer.appendChild(warButton(war.id, 'accept_ai_peace', '接受战败和约', true));
    return offer;
  }
}

function namedCreationForm(title, placeholder, buttonLabel, onSubmit) {
  const form = document.createElement('form'); form.className = 'governance-form';
  const heading = document.createElement('b'); heading.textContent = title;
  const input = document.createElement('input'); input.maxLength = 18; input.placeholder = placeholder;
  const button = document.createElement('button'); button.type = 'submit'; button.textContent = buttonLabel;
  form.append(heading, input, button);
  form.onsubmit = event => { event.preventDefault(); if (input.value.trim()) onSubmit(input.value.trim()); };
  return form;
}

function diplomacyForm(targets, endpoint, title) {
  const form = document.createElement('form'); form.className = 'governance-form diplomacy-form';
  const heading = document.createElement('b'); heading.textContent = title;
  const target = document.createElement('select');
  targets.forEach(entry => {
    const option = document.createElement('option'); option.value = entry.target_id || entry.id;
    option.textContent = `${entry.target_name || entry.name}（现为${entry.status_name || '中立'}）`; target.appendChild(option);
  });
  const status = document.createElement('select');
  Object.entries(game?.governance?.diplomacy_statuses || {}).forEach(([value, label]) => {
    const option = document.createElement('option'); option.value = value; option.textContent = label; status.appendChild(option);
  });
  const button = document.createElement('button'); button.type = 'submit'; button.textContent = '提交表决';
  form.append(heading, target, status, button);
  form.onsubmit = event => {
    event.preventDefault(); mutate(endpoint, {target_id:target.value, status:status.value});
  };
  return form;
}

function vassalTransferForm(kind, targetId, targetName, candidates) {
  const form = document.createElement('form'); form.className = 'governance-form';
  const heading = document.createElement('b'); heading.textContent = `从${targetName}调遣外援`;
  const select = document.createElement('select');
  candidates.forEach(npc => {
    const option = document.createElement('option'); option.value = npc.id;
    option.textContent = `${npc.name} · ${npc.realm_name}`; select.appendChild(option);
  });
  const button = document.createElement('button'); button.type = 'submit'; button.textContent = '执行调动';
  form.append(heading, select, button);
  form.onsubmit = event => { event.preventDefault(); mutate(`/api/games/${game.id}/vassal-transfer`, {kind, target_id:targetId, npc_id:select.value}); };
  return form;
}

function renderFamily(family, governance) {
  const content = $('#family-content'); content.innerHTML = '';
  $('#family-status').textContent = family?.exists ? (family.extinct ? '传承已绝' : `${family.living_count} 人在册`) : '尚未立族';
  $('#family-title').textContent = family?.exists ? family.name : '修仙家族';
  $('#family-description').textContent = family?.exists
    ? family.description
    : '与道侣缠绵可能孕育后代；双方境界越高概率越低，化神起无法自然孕育。拥有踏入仙途的后代后方可立族。';

  const children = document.createElement('div'); children.className = 'family-list';
  const childTitle = document.createElement('h3'); childTitle.textContent = '血脉后代'; children.appendChild(childTitle);
  if (!family?.offspring?.length) children.innerHTML += '<p class="empty">族谱尚无后代。</p>';
  (family?.offspring || []).forEach(child => {
    const row = document.createElement('div'); row.className = 'family-row';
    row.innerHTML = `<b>${child.name}</b><small>${child.age} 岁 · ${child.spirit_root_name} · ${child.realm_name}</small>`;
    children.appendChild(row);
  });
  content.appendChild(children);
  if (!family?.exists && family?.can_found) {
    content.appendChild(namedCreationForm('建立修仙家族', '家族名号', '开枝立族', name => mutate(`/api/games/${game.id}/create-family`, {name})));
  }
  if (family?.exists) {
    const roster = document.createElement('div'); roster.className = 'family-list';
    roster.innerHTML = '<h3>家族名册</h3>';
    (family.roster || []).forEach(member => {
      const row = document.createElement('div'); row.className = `family-row${member.alive ? '' : ' fallen'}`;
      row.innerHTML = `<b>${member.name} · ${member.member_type}${member.wounds ? `（负伤${member.wounds}级）` : ''}</b><small>${member.realm_name} · ${member.spirit_root_name} · ${member.age} 岁 · 战力 ${number(member.combat_power)}</small>`;
      roster.appendChild(row);
    });
    content.appendChild(roster);
  }
  const bounty = document.createElement('div'); bounty.className = 'family-list';
  bounty.innerHTML = '<h3>势力通缉令</h3>';
  if (!governance?.can_issue_bounty) {
    bounty.innerHTML += '<p class="empty">取得种族、宗门或家族任一方的话语权后即可颁令。</p>';
  } else if (governance.bounty_candidates?.length) {
    const form = document.createElement('form'); form.className = 'governance-form';
    const authority = document.createElement('select');
    (governance.bounty_authorities || []).forEach(entry => {
      const option = document.createElement('option'); option.value = entry.id;
      option.textContent = `以${entry.name}名义`; authority.appendChild(option);
    });
    const select = document.createElement('select');
    governance.bounty_candidates.forEach(npc => {
      const option = document.createElement('option'); option.value = npc.id;
      option.textContent = `${npc.name} · ${npc.realm_name} · ${npc.source}`; select.appendChild(option);
    });
    const button = document.createElement('button'); button.type = 'submit'; button.textContent = '颁布通缉';
    form.append(authority, select, button); form.onsubmit = event => { event.preventDefault(); mutate(`/api/games/${game.id}/issue-bounty`, {npc_id:select.value, authority:authority.value}); };
    bounty.appendChild(form);
  }
  (governance?.bounties || []).forEach(order => {
    const row = document.createElement('div'); row.className = 'family-row';
    row.innerHTML = `<b>${order.name}</b><small>${order.issuer_name || '麾下势力'} · ${order.status === 'active' ? `追缉中 · 已追索 ${order.attempts} 次` : order.status === 'completed' ? '已伏诛' : order.status === 'suspended' ? '权限中断，暂停追缉' : '已结案'}</small>`;
    bounty.appendChild(row);
  });
  content.appendChild(bounty);
}

function renderWorldNpcs(npcs) {
  const list = $('#world-npc-list'); list.innerHTML = '';
  npcs.forEach(npc => {
    const row = document.createElement('div'); row.className = `world-npc-row${npc.perceived_alive ? '' : ' absent'}`;
    const info = document.createElement('div');
    const name = document.createElement('b'); name.textContent = `${npc.name} · ${npc.title}${npc.wounds ? `（负伤${npc.wounds}级）` : ''}`;
    const detail = document.createElement('small');
    detail.textContent = `${npc.realm_name} · ${npc.path_name} · ${npc.race_name} · ${npc.spirit_root_name} · ${npc.age}岁/寿元${npc.lifespan == null ? '无尽' : npc.lifespan}`;
    const combat = npc.combat_power == null ? '' : ` · 战力 ${number(npc.combat_power)} · 好感 ${number(npc.affinity)} / ${npc.attitude}`;
    detail.textContent += combat;
    const controls = document.createElement('div'); controls.className = 'world-npc-controls';
    const status = document.createElement('span'); status.textContent = npc.status; controls.appendChild(status);
    if (npc.in_party || npc.can_invite_party) {
      const button = document.createElement('button'); button.className = 'party-action';
      button.textContent = npc.in_party ? '离队' : '邀请同行';
      button.onclick = () => mutate(`/api/games/${game.id}/party`, {npc_id:npc.id, action:npc.in_party ? 'leave' : 'invite'});
      controls.appendChild(button);
    }
    if (npc.can_propose_companion) {
      const button = document.createElement('button'); button.className = 'companion-action'; button.textContent = '结为道侣';
      button.onclick = () => mutate(`/api/games/${game.id}/dao-companion`, {npc_id:npc.id, action:'propose'});
      controls.appendChild(button);
    }
    if (npc.can_befriend) {
      const button = document.createElement('button'); button.className = 'friend-action'; button.textContent = '结为道友';
      button.onclick = () => mutate(`/api/games/${game.id}/dao-friend`, {npc_id:npc.id, action:'befriend'});
      controls.appendChild(button);
    }
    info.append(name, detail); row.append(info, controls); list.appendChild(row);
  });
}

function renderSpiritRanking(ranking) {
  const card = $('#ranking-card'); card.classList.toggle('hidden', !ranking?.available);
  document.querySelector("[data-panel-target='ranking']")?.classList.toggle('hidden', !ranking?.available);
  const list = $('#ranking-list'); list.innerHTML = '';
  if (!ranking?.available) return;
  $('#ranking-title').textContent = ranking.title || '上界天榜前二十';
  $('#ranking-player-status').textContent = ranking.on_board ? `你当前位列第 ${ranking.player_rank}` : `你当前未入前二十（总排名 ${ranking.player_rank}）`;
  ranking.entries.forEach(entry => {
    const row = document.createElement('div'); row.className = `ranking-row${entry.is_player ? ' self' : ''}`;
    row.innerHTML = `<i>${String(entry.rank).padStart(2, '0')}</i><span><b>${entry.name}${entry.is_player ? '（你）' : ''}</b><small>${entry.title || `${ranking.world_name || '上界'}强者`} · ${entry.race_name} · 战力 ${number(entry.combat_power)}</small></span><strong>${entry.realm_name}</strong>`;
    list.appendChild(row);
  });
}

function renderParty(party) {
  const list = $('#party-list'); list.innerHTML = '';
  if (!party.length) { list.innerHTML = '<p class="empty">当前独自行动，可邀请宗门或世界 NPC 同行。</p>'; return; }
  party.forEach(member => {
    const row = document.createElement('div'); row.className = 'party-row';
    const info = document.createElement('div'); info.className = 'party-member-info';
    info.innerHTML = `<b>${member.name}</b><small>${member.realm_name} · 战力 ${number(member.combat_power)}</small><small>关系：${member.attitude} · 好感 ${number(member.affinity || 0)}</small>`;
    const tools = document.createElement('div'); tools.className = 'party-tools';
    const interact = document.createElement('button'); interact.className = 'party-action'; interact.textContent = member.can_interact ? '交流心得' : '本期已交流';
    interact.dataset.available = member.can_interact ? '1' : '0';
    interact.onclick = () => mutate(`/api/games/${game.id}/party`, {npc_id:member.id, action:'interact'});
    tools.appendChild(interact);
    if (member.can_cross_spirit || member.selected_for_crossing) {
      const crossing = document.createElement('button'); crossing.className = 'party-action';
      crossing.textContent = member.selected_for_crossing ? '取消飞升同行' : '约定同行飞升';
      crossing.dataset.available = '1';
      crossing.onclick = () => mutate(`/api/games/${game.id}/party`, {npc_id:member.id, action:member.selected_for_crossing ? 'crossing_remove' : 'crossing_add'});
      tools.appendChild(crossing);
    }
    const leave = document.createElement('button'); leave.className = 'party-action'; leave.textContent = '离队'; leave.dataset.available = '1';
    leave.onclick = () => mutate(`/api/games/${game.id}/party`, {npc_id:member.id, action:'leave'});
    tools.appendChild(leave); row.append(info, tools); list.appendChild(row);
  });
}

function renderWanted(entries) {
  const list = $('#wanted-list'); list.innerHTML = '';
  if (!entries.length) { list.innerHTML = '<p class="empty">尚未被任何势力通缉。</p>'; return; }
  entries.forEach(entry => {
    const row = document.createElement('div'); row.className = 'wanted-row';
    row.innerHTML = `<b>${entry.display_name || entry.name}</b><small>敌对值 ${number(entry.hostility)} · 每次时间流逝均可能遭遇追杀</small>`;
    list.appendChild(row);
  });
}

function renderPrison(prison) {
  const card = $('#prison-card'); card.classList.toggle('hidden', !prison);
  $('#action-card').classList.toggle('hidden', !!prison);
  if (!prison) return;
  $('#prison-title').textContent = `${prison.name}大牢`;
  const liveHostility = prison.hostility ?? game?.player?.hostility?.[prison.key] ?? 0;
  const cultivationRisk = game?.player?.realm_index >= 9 ? '真仙及以上不会跌落境界' : '服刑可能导致修为倒退';
  $('#prison-description').textContent = `尚余刑期 ${prison.remaining_years} 年，当前敌对值 ${number(liveHostility)}。每次服刑都会降低敌意；${cultivationRisk}，越狱失败则会加重敌对值。`;
}

$('#prison-endure').onclick = () => mutate(`/api/games/${game.id}/prison-action`, {action:'endure'});
$('#prison-escape').onclick = () => mutate(`/api/games/${game.id}/prison-action`, {action:'escape'});

function renderRaceSystem(system) {
  const card = $('#race-card'); card.classList.toggle('hidden', !system?.available);
  document.querySelector("[data-panel-target='race']")?.classList.toggle('hidden', !system?.available);
  if (!system?.available) return;
  $('#race-world-label').textContent = `${system.world_name || '上界'}族群`;
  $('#race-description').textContent = system.has_diplomatic_voice
    ? `你当前属于${system.player_race_name}，并已拥有大乘议席；可对任一异族提出宣战、结盟、停战、断盟或依附决议。`
    : `你当前属于${system.player_race_name}。族群外交会影响遭遇、截杀与盟友因果；大乘后可取得一人一票的议席。`;
  const races = $('#race-list'); races.innerHTML = '';
  const raceEntries = Object.values(system.races);
  let initialChip = null;
  const showRace = race => {
    const detail = $('#race-detail'); detail.innerHTML = '';
    const heading = document.createElement('div'); heading.className = 'race-detail-heading';
    heading.innerHTML = `<b>${race.name}</b><span>${race.description || ''}</span>`;
    const relations = document.createElement('div'); relations.className = 'race-relations';
    (race.relations || []).forEach(relation => {
      const row = document.createElement('div'); row.className = `race-relation ${relation.status}`;
      row.innerHTML = `<b>${relation.race_name}</b><span>${relation.status_name} · 好感 ${number(relation.affinity)}</span>`;
      relations.appendChild(row);
    });
    const factions = document.createElement('div'); factions.className = 'race-factions';
    factions.innerHTML = '<h3>支持该族的宗门</h3>';
    (race.supported_factions || []).forEach(faction => {
      const row = document.createElement('p');
      row.innerHTML = `<b>${faction.name}${faction.active ? '' : '（预设）'}</b><span>长老：${(faction.elders || []).join('、') || '尚未推举'}</span>`;
      factions.appendChild(row);
    });
    const events = document.createElement('div'); events.className = 'race-events';
    events.innerHTML = '<h3>族群大事</h3>';
    if (!(race.recent_events || []).length) events.innerHTML += '<p class="empty">尚无载入史册的宣战、结盟、停战、依附或断盟。</p>';
    (race.recent_events || []).forEach(event => {
      const row = document.createElement('p'); row.innerHTML = `<b>${timelineText(event.age)}</b><span>${event.summary}</span>`; events.appendChild(row);
    });
    detail.append(heading, factions, relations, events);
    if (system.has_diplomatic_voice && race.id !== 'human') {
      const humanRelation = (race.relations || []).find(entry => entry.race === 'human') || {status_name:'中立'};
      detail.appendChild(diplomacyForm(
        [{target_id:race.id, target_name:race.name, status_name:humanRelation.status_name}],
        `/api/games/${game.id}/race-diplomacy`, '发起人族大乘议会'
      ));
      const transfer = (system.vassal_transfers || []).find(entry => entry.target_id === race.id);
      if (transfer) detail.appendChild(vassalTransferForm('race', transfer.target_id, transfer.target_name, transfer.candidates));
    }
  };
  raceEntries.forEach(race => {
    const chip = document.createElement('button'); chip.type = 'button'; chip.className = `race-chip${race.id === system.player_race ? ' current' : ''}`;
    chip.textContent = race.name; chip.title = race.description || '';
    chip.onclick = () => { races.querySelectorAll('.race-chip').forEach(node => node.classList.remove('selected')); chip.classList.add('selected'); showRace(race); };
    if (race.id === system.player_race) initialChip = chip;
    races.appendChild(chip);
  });
  const initial = raceEntries.find(race => race.id === system.player_race) || raceEntries[0];
  if (initial) { (initialChip || races.firstElementChild)?.classList.add('selected'); showRace(initial); }
  const list = $('#race-alliance-list'); list.innerHTML = '';
  system.alliances.forEach(alliance => {
    const row = document.createElement('div'); row.className = 'race-alliance';
    const namesById = Object.fromEntries(raceEntries.map(race => [race.id, race.name]));
    const names = alliance.members.map(id => namesById[id] || id).join('、');
    const relationText = alliance.status === 'vassal' ? '处于依附关系' : '处于结盟状态';
    row.innerHTML = `<b>${alliance.name}</b><span>${names}${relationText}；主动击杀友好族群成员会使因果大幅增加。</span>`;
    list.appendChild(row);
  });
}

function renderWorldRoute(route) {
  if (!route) return;
  $('#world-route-title').textContent = `${route.name} · ${route.path_name}`;
  $('#world-route-status').textContent = `当前：${route.current_world_name}`;
  $('#world-route-description').textContent = route.lineage_race_name === route.allegiance_race_name
    ? `血缘与势力归属均为${route.lineage_race_name}。未开放的界面仅展示架构，不会提前触发内容。`
    : `血缘仍为${route.lineage_race_name}，当前政治与宗门势力归属为${route.allegiance_race_name}。`;
  const list = $('#world-route-stages'); list.innerHTML = '';
  (route.stages || []).forEach((stage, index) => {
    const row = document.createElement('div');
    row.className = `world-route-stage${stage.current ? ' current' : ''}${stage.enabled ? '' : ' future'}${stage.kind === 'system' ? ' system' : ''}`;
    row.innerHTML = `<i>${index + 1}</i><span><b>${stage.label}</b><small>${stage.current ? '当前所在界面' : stage.enabled ? '界面已启用' : stage.kind === 'system' ? '未来跨界系统框架' : '未来独立界面'}${stage.description ? ` · ${stage.description}` : ''}</small></span>`;
    list.appendChild(row);
  });
}

function renderMonsterBloodline(system) {
  const panel = $('#bloodline-card');
  const dock = document.querySelector('[data-panel-target="bloodline"]');
  const visible = !!system.visible;
  panel.classList.toggle('hidden', !visible);
  dock?.classList.toggle('hidden', !visible);
  if (!visible) { window.UtilityPanels?.close('bloodline'); return; }
  const current = $('#bloodline-current');
  const marks = $('#bloodline-marks');
  const history = $('#bloodline-history');
  const candidates = $('#bloodline-candidates');
  [current, marks, history, candidates].forEach(node => { node.innerHTML = ''; });
  if (!system.available) {
    const generalTraits = system.general_traits || [];
    $('#bloodline-summary').textContent = `本体通用特质 · ${generalTraits.length} / ${system.general_trait_pool_size || 16}`;
    $('#bloodline-note').textContent = system.reason || '血脉内容当前不可用。';
    $('#bloodline-evolution-section').classList.add('hidden');
    const heading = document.createElement('div'); heading.className = 'bloodline-identity';
    heading.innerHTML = '<span><b>凡妖蜕性</b><small>仅在血脉 DLC 未启用时生效；每次成功突破大境界随机获得一项未拥有特质。</small></span>';
    current.appendChild(heading);
    const traitList = document.createElement('div'); traitList.className = 'bloodline-traits';
    generalTraits.forEach(trait => {
      const chip = document.createElement('span'); chip.className = 'general';
      chip.textContent = trait.name; chip.title = trait.description; traitList.appendChild(chip);
    });
    if (!generalTraits.length) {
      const empty = document.createElement('p'); empty.className = 'empty';
      empty.textContent = '尚未取得通用特质；下一次成功突破大境界时获得。'; traitList.appendChild(empty);
    }
    current.appendChild(traitList);
    return;
  }
  $('#bloodline-evolution-section').classList.toggle('hidden', !system.awaiting_evolution);
  const pool = system.species_trait_pool || {acquired:0, total:0};
  $('#bloodline-summary').textContent = `${system.species.name} · ${system.current.name} · 族血 ${pool.acquired}/${pool.total}`;
  $('#bloodline-note').textContent = '每次成功突破大境界，从本源族群血脉库随机觉醒一项未拥有特质；血脉是永久本体，当前节点六维直接替代上一节点。';

  const heading = document.createElement('div'); heading.className = 'bloodline-identity';
  const identity = document.createElement('span');
  const title = document.createElement('b'); title.textContent = system.current.name;
  const detail = document.createElement('small'); detail.textContent = `本源：${system.species.name} · ${system.current.description}`;
  identity.append(title, detail); heading.appendChild(identity); current.appendChild(heading);
  const statNames = {might:'威能', guard:'防护', mobility:'身法', sense:'神识', sustain:'续航', breach:'破法'};
  const stats = document.createElement('div'); stats.className = 'bloodline-profile';
  Object.entries(system.current.profile || {}).forEach(([id, value]) => {
    const item = document.createElement('span');
    const name = document.createElement('small'); name.textContent = statNames[id] || id;
    const amount = document.createElement('b'); amount.textContent = `×${Number(value).toFixed(2)}`;
    item.append(name, amount); stats.appendChild(item);
  });
  current.appendChild(stats);
  const currentTraits = document.createElement('div'); currentTraits.className = 'bloodline-traits';
  (system.current.traits || []).forEach(trait => {
    const chip = document.createElement('span'); chip.textContent = trait.name; chip.title = trait.description; currentTraits.appendChild(chip);
  });
  (system.current.abilities || []).forEach(ability => {
    const chip = document.createElement('span'); chip.className = 'ability'; chip.textContent = ability; currentTraits.appendChild(chip);
  });
  current.appendChild(currentTraits);

  const markRows = [
    ...(system.adaptations || []).map(row => ({...row, kind:'适应'})),
    ...(system.imprints || []).map(row => ({...row, kind:'血脉'})),
    ...(system.acquired_traits || []).map(row => ({...row, kind:'觉醒'})),
    ...(system.general_traits || []).map(row => ({...row, kind:'冻结通用'})),
  ];
  markRows.forEach(mark => {
    const chip = document.createElement('span'); chip.className = mark.kind === '血脉' ? 'imprint' : mark.kind === '冻结通用' ? 'general frozen' : '';
    chip.textContent = `${mark.kind} · ${mark.name}`; chip.title = mark.description || ''; marks.appendChild(chip);
  });
  if (!markRows.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = '尚未获得适应印记或特殊血脉印记。'; marks.appendChild(empty); }
  (system.history || []).forEach((node, index) => {
    if (index) { const arrow = document.createElement('i'); arrow.textContent = '→'; history.appendChild(arrow); }
    const item = document.createElement('span'); item.textContent = node.name; history.appendChild(item);
  });

  const lineageSection = $('#custom-lineage-section');
  const lineageBox = $('#custom-lineage'); lineageBox.innerHTML = '';
  const lineage = system.custom_lineage;
  const editor = system.custom_lineage_editor;
  lineageSection.classList.toggle('hidden', !lineage && !editor && !system.custom_lineage_retroactive_available);
  if (lineage) {
    const summary = document.createElement('div'); summary.className = 'custom-lineage-summary';
    const identity = document.createElement('b'); identity.textContent = `${lineage.name} · ${lineage.stage_name}`;
    const meta = document.createElement('small'); meta.textContent = `祖血编号 ${lineage.id} · 已用功业点 ${lineage.spent_points} · 规则 ${lineage.rules?.length || 0} 条`;
    summary.append(identity, meta);
    (lineage.rules || []).forEach((rule, index) => {
      const row = document.createElement('p'); row.textContent = `${index + 1}. ${rule.description}（${rule.cost}点）`; summary.appendChild(row);
    });
    lineageBox.appendChild(summary);
  }
  if (system.custom_lineage_retroactive_available && !editor) {
    const notice = document.createElement('div'); notice.className = 'custom-lineage-retroactive';
    const text = document.createElement('span'); text.textContent = '检测到V3自立血脉存档，可按当前可重建的进化、渡劫和事件记录补刻祖血。';
    const button = document.createElement('button'); button.textContent = '补刻祖血';
    button.onclick = () => mutate(`/api/games/${game.id}/custom-lineage-prepare`, {evolution_id:'__retroactive__'});
    notice.append(text, button); lineageBox.appendChild(notice);
  }
  if (editor) {
    const form = document.createElement('form'); form.className = 'custom-lineage-editor';
    const deedTitle = document.createElement('b'); deedTitle.textContent = `${editor.stage_name} · 功业点 ${editor.deeds.total} · 规则槽 ${editor.slots}`;
    const deedList = document.createElement('div'); deedList.className = 'custom-lineage-deeds';
    editor.deeds.breakdown.forEach(deed => {
      const chip = document.createElement('span'); chip.textContent = `${deed.source}·${deed.name} +${deed.points}`; chip.title = deed.detail; deedList.appendChild(chip);
    });
    const nameLabel = document.createElement('label'); nameLabel.textContent = '祖血名称';
    const nameInput = document.createElement('input'); nameInput.maxLength = 16; nameInput.required = true;
    nameInput.value = editor.existing?.name || ''; nameInput.placeholder = '2—16字，与内部编号独立';
    nameInput.disabled = !!editor.existing; nameLabel.appendChild(nameInput);
    const rulesBox = document.createElement('div'); rulesBox.className = 'custom-lineage-rules';
    const total = document.createElement('strong'); total.className = 'custom-lineage-total';
    const invalidReason = document.createElement('small'); invalidReason.className = 'custom-lineage-invalid';
    const components = editor.components;
    const byId = key => Object.fromEntries((components[key] || []).map(row => [row.id, row]));
    const indexes = {phases:byId('phases'), schedules:byId('schedules'), conditions:byId('conditions'), targets:byId('targets'), effects:byId('effects')};
    const valuePools = editor.values || {};
    const selectedRules = (editor.existing?.rules || []).map(rule => ({...rule}));
    let submitButton = null;
    let addButton = null;
    const optionSelect = (rows, value, field, locked) => {
      const select = document.createElement('select'); select.dataset.field = field;
      rows.forEach(entry => { const option = document.createElement('option'); option.value = entry.id ?? entry.value; option.textContent = entry.name || entry.label; select.appendChild(option); });
      if (value != null) select.value = String(value); select.disabled = locked; return select;
    };
    const describeRule = rule => {
      const phase = indexes.phases[rule.phase];
      const schedule = indexes.schedules[rule.schedule];
      const condition = indexes.conditions[rule.condition];
      const effect = indexes.effects[rule.effect];
      const value = (valuePools[effect?.value_pool] || []).find(entry => String(entry.value) === String(rule.value));
      if (!phase || !schedule || !condition || !effect || !value) return '规则组件尚未完整选择。';
      const timing = phase.id === 'round_start' ? '开始时' : '结束时';
      const conditionText = condition.kind === 'always' ? '' : `若${condition.name}，`;
      const targetText = rule.target === 'player' ? '自身' : '敌方';
      const verb = effect.kind === 'restore_combat_state' ? '恢复' : rule.target === 'player' ? '提高' : '降低';
      return `${schedule.name}${timing}，${conditionText}${targetText}${effect.name}${verb}${value.label}。`;
    };
    const calculate = () => {
      let spent = 0;
      const reasons = [];
      [...rulesBox.children].forEach((row, index) => {
        const read = field => row.querySelector(`[data-field="${field}"]`)?.value;
        const rule = Object.fromEntries(['phase','schedule','condition','target','effect','value'].map(field => [field, read(field)]));
        const schedule = indexes.schedules[read('schedule')] || {};
        const condition = indexes.conditions[read('condition')] || {};
        const target = indexes.targets[read('target')] || {};
        const effect = indexes.effects[read('effect')] || {};
        const value = (valuePools[effect.value_pool] || []).find(entry => String(entry.value) === read('value')) || {};
        const cost = Math.max(editor.minimum_rule_cost, Number(schedule.cost||0)+Number(effect.cost||0)+Number(value.cost||0)+Number(target.cost||0)-Number(condition.discount||0));
        const rowReasons = [];
        if (!indexes.phases[rule.phase] || !schedule.id || !condition.id || !target.id || !effect.id || value.value == null) rowReasons.push('规则组件不完整');
        if (effect.id && !effect.phases?.includes(rule.phase)) rowReasons.push('该效果不能在所选时点触发');
        if (effect.id && !effect.targets?.includes(rule.target)) rowReasons.push('该效果不能作用于所选目标');
        row.querySelector('.rule-cost').textContent = `${cost}点`;
        row.querySelector('.rule-preview').textContent = describeRule(rule);
        row.querySelector('.rule-invalid').textContent = rowReasons.join('；');
        row.classList.toggle('invalid', rowReasons.length > 0);
        if (rowReasons.length) reasons.push(`第${index + 1}条：${rowReasons.join('、')}`);
        spent += cost;
      });
      const remaining = editor.deeds.total - spent;
      total.textContent = `当前费用 ${spent} 点 · 剩余血脉点数 ${remaining} / ${editor.deeds.total}`;
      total.classList.toggle('invalid', remaining < 0);
      if (remaining < 0) reasons.push(`血脉点数不足，还缺 ${-remaining} 点`);
      const cleanName = nameInput.value.trim();
      if (cleanName.length < 2 || cleanName.length > 16) reasons.push('祖血名称须为 2 至 16 个字符');
      if (!rulesBox.children.length) reasons.push('至少需要铭刻一条规则');
      invalidReason.textContent = reasons.length ? `不合法原因：${reasons.join('；')}` : '当前配置合法，可以确认铭刻。';
      invalidReason.classList.toggle('valid', reasons.length === 0);
      if (submitButton) submitButton.disabled = reasons.length > 0;
      if (addButton) addButton.disabled = rulesBox.children.length >= editor.slots;
    };
    const addRule = (rule = null, locked = false) => {
      if (rulesBox.children.length >= editor.slots) return;
      const row = document.createElement('div'); row.className = `custom-lineage-rule${locked ? ' frozen' : ''}`;
      const phase = optionSelect(components.phases, rule?.phase || 'round_start', 'phase', locked);
      const schedule = optionSelect(components.schedules, rule?.schedule || 'round_1', 'schedule', locked);
      const condition = optionSelect(components.conditions, rule?.condition || 'always', 'condition', locked);
      const target = optionSelect(components.targets, rule?.target || 'player', 'target', locked);
      const effect = optionSelect(components.effects, rule?.effect || 'might', 'effect', locked);
      const values = optionSelect(valuePools[indexes.effects[effect.value]?.value_pool] || [], rule?.value ?? 0.03, 'value', locked);
      const cost = document.createElement('span'); cost.className = 'rule-cost';
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = locked ? '已铭刻' : '移除'; remove.disabled = locked;
      const preview = document.createElement('p'); preview.className = 'rule-preview';
      const reason = document.createElement('small'); reason.className = 'rule-invalid';
      remove.onclick = () => { row.remove(); calculate(); };
      const refreshValues = () => {
        const prior = values.value; values.innerHTML = '';
        (valuePools[indexes.effects[effect.value]?.value_pool] || []).forEach(entry => { const option = document.createElement('option'); option.value = entry.value; option.textContent = entry.label; values.appendChild(option); });
        if ([...values.options].some(option => option.value === prior)) values.value = prior;
        calculate();
      };
      const refreshEffects = () => {
        const prior = effect.value; effect.innerHTML = '';
        components.effects.filter(entry => entry.phases.includes(phase.value) && entry.targets.includes(target.value)).forEach(entry => {
          const option = document.createElement('option'); option.value = entry.id; option.textContent = entry.name; effect.appendChild(option);
        });
        if ([...effect.options].some(option => option.value === prior)) effect.value = prior;
        refreshValues();
      };
      [schedule, condition, values].forEach(select => select.onchange = calculate);
      phase.onchange = refreshEffects; target.onchange = refreshEffects;
      effect.onchange = refreshValues;
      row.append(phase, schedule, condition, target, effect, values, cost, remove, preview, reason); rulesBox.appendChild(row); refreshEffects();
    };
    selectedRules.forEach(rule => addRule(rule, true));
    const controls = document.createElement('div'); controls.className = 'custom-lineage-controls';
    const add = document.createElement('button'); add.type = 'button'; add.textContent = '追加规则'; add.onclick = () => addRule(); addButton = add;
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消'; cancel.onclick = () => loadGame(game.id);
    const submit = document.createElement('button'); submit.type = 'submit'; submit.textContent = editor.retroactive ? '确认补刻' : `确认${editor.stage_name}并进化`; submitButton = submit;
    controls.append(add, cancel, submit);
    nameInput.oninput = calculate;
    form.append(deedTitle, deedList, nameLabel, rulesBox, total, invalidReason, controls);
    form.onsubmit = event => {
      event.preventDefault();
      const rules = [...rulesBox.children].map(row => Object.fromEntries(['phase','schedule','condition','target','effect','value'].map(field => {
        const value = row.querySelector(`[data-field="${field}"]`).value; return [field, field === 'value' ? Number(value) : value];
      })));
      mutate(`/api/games/${game.id}/custom-lineage-confirm`, {evolution_id:editor.evolution_id, name:nameInput.value, rules});
    };
    lineageBox.appendChild(form); calculate();
  }

  const requirementText = requirement => {
    if (!requirement) return [];
    if (requirement.kind === 'leaf') return [{text:requirement.text, met:requirement.met}];
    if (requirement.kind === 'not') return (requirement.children || []).flatMap(requirementText).map(row => ({text:`不满足：${row.text}`, met:requirement.met}));
    const join = requirement.kind === 'any' ? '以下任一：' : '';
    const rows = (requirement.children || []).flatMap(requirementText);
    return join && rows.length ? rows.map(row => ({...row, text:`${join}${row.text}`})) : rows;
  };
  (system.candidates || []).forEach(candidate => {
    const card = document.createElement('article'); card.className = `bloodline-candidate${candidate.enabled ? '' : ' locked'}`;
    const top = document.createElement('div');
    const text = document.createElement('span'); const name = document.createElement('b'); const description = document.createElement('small');
    name.textContent = candidate.name; description.textContent = candidate.description; text.append(name, description);
    const button = document.createElement('button'); button.className = 'bloodline-evolve'; button.textContent = candidate.enabled ? '选择进化' : '条件未满足';
    button.dataset.available = candidate.enabled ? '1' : '0';
    button.onclick = () => mutate(
      `/api/games/${game.id}/${candidate.custom_lineage ? 'custom-lineage-prepare' : 'monster-evolve'}`,
      {evolution_id:candidate.id},
    );
    top.append(text, button); card.appendChild(top);
    const changes = document.createElement('small'); changes.className = 'bloodline-change';
    changes.textContent = `${Object.entries(candidate.profile || {}).map(([id, value]) => `${statNames[id]}×${Number(value).toFixed(2)}`).join(' · ')}${candidate.lifespan_gain ? ` · 寿元 +${candidate.lifespan_gain}` : ''}`;
    card.appendChild(changes);
    const checks = document.createElement('div'); checks.className = 'bloodline-checks';
    const qi = candidate.monster_qi_level || {};
    if (Number(qi.required || 0) > 0) {
      const row = document.createElement('span'); row.className = qi.met ? 'met' : 'missing'; row.textContent = `${qi.met ? '✓' : '✗'} 妖气等级 ${qi.current}/${qi.required}`; checks.appendChild(row);
    }
    requirementText(candidate.requirements).forEach(check => {
      const row = document.createElement('span'); row.className = check.met ? 'met' : 'missing'; row.textContent = `${check.met ? '✓' : '✗'} ${check.text}`; checks.appendChild(row);
    });
    if (candidate.stable_continuation) { const row = document.createElement('span'); row.className = 'met'; row.textContent = '✓ 稳态延续，不会卡死存档'; checks.appendChild(row); }
    card.appendChild(checks); candidates.appendChild(card);
  });
}

$('#spirit-crossing-action').onclick = () => mutate(`/api/games/${game.id}/${$('#spirit-crossing-action').dataset.operation || 'spirit-crossing'}`, {});
$('#sense-breakthrough-action').onclick = () => mutate(`/api/games/${game.id}/sense-breakthrough`, {});
$('#cross-world-action').onclick = () => mutate(`/api/games/${game.id}/cross-world`, {destination:$('#cross-world-action').dataset.destination});
$('#cross-world-secondary-action').onclick = () => mutate(`/api/games/${game.id}/cross-world`, {destination:$('#cross-world-secondary-action').dataset.destination});
$('#breakthrough-action').onclick = () => mutate(`/api/games/${game.id}/breakthrough`, {});
$('#body-breakthrough-action').onclick = () => mutate(`/api/games/${game.id}/body-breakthrough`, {});
$('#ghost-wangsheng-action').onclick = () => mutate(`/api/games/${game.id}/ghost-wangsheng`, {});
$('#ghost-wangsheng-all-action').onclick = () => mutate(`/api/games/${game.id}/ghost-wangsheng`, {all:true});
$('#ghost-reincarnate-action').onclick = () => mutate(`/api/games/${game.id}/ghost-reincarnation-prompt`, {});
$('#world-news-debug').onclick = () => mutate(`/api/games/${game.id}/debug-world-news`, {enabled:!game.debug_world_news});

function renderGhostPhaseTwo(system) {
  const enabled = !!system.enabled;
  const soulCard = $('#ghost-soul-card'), soulDock = document.querySelector('[data-panel-target="ghost-soul"]');
  const attachmentCard = $('#ghost-attachment-card'), attachmentDock = document.querySelector('[data-panel-target="ghost-attachment"]');
  soulCard.classList.toggle('hidden', !enabled); soulDock?.classList.toggle('hidden', !enabled);
  attachmentCard.classList.toggle('hidden', !enabled); attachmentDock?.classList.toggle('hidden', !enabled);
  const parade = system.parade || {};
  const paradeVisible = enabled && !!parade.status && parade.status !== 'dormant';
  const paradeCard = $('#ghost-parade-card'), paradeDock = document.querySelector('[data-panel-target="ghost-parade"]');
  paradeCard.classList.toggle('hidden', !paradeVisible); paradeDock?.classList.toggle('hidden', !paradeVisible);
  if (!enabled) {
    ['ghost-soul','ghost-attachment','ghost-parade'].forEach(name => window.UtilityPanels?.close(name));
    return;
  }
  if (!paradeVisible) window.UtilityPanels?.close('ghost-parade');
  const limit = system.possession_limit == null ? '无限' : system.possession_limit;
  $('#ghost-soul-summary').textContent = `入位 ${number((system.slots || []).filter(slot => slot.soul).length)}/10 · 拘魂 ${number((system.bound_souls || []).length)}`;
  $('#ghost-attachment-summary').textContent = system.state === 'attached' ? '当前已附灵' : system.state_name;
  $('#ghost-phase-state').textContent = `${system.state_name} · 魂压 ${Number(system.pressure || 0).toFixed(2)}（未来魂蚀增长 +${percent(system.pressure_modifier || 0)}） · 夺舍 ${number(system.possession_count)}/${limit}${system.souls_suspended ? ' · 宿身期间十魂与鬼魂核心全数沉寂' : ''}`;
  const constraints = $('#ghost-constraint-actions'); constraints.innerHTML = '';
  constraints.classList.toggle('hidden', system.state !== 'controlled');
  if (system.state === 'controlled') {
    const note = document.createElement('span'); note.textContent = `拘魂者：${system.captor?.name || '未知'} · 失败的反抗与夺舍均会魂飞魄散`;
    constraints.appendChild(note);
    [['wait','忍耐一年'],['resist','反抗拘魂者'],['possess','夺舍拘魂者']].forEach(([action,label]) => {
      const button = document.createElement('button'); button.textContent = label; button.disabled = busy || !game.player.alive;
      button.onclick = () => mutate(`/api/games/${game.id}/ghost-constraint`, {action}); constraints.appendChild(button);
    });
  }
  const hostTools = $('#ghost-host-actions'); hostTools.innerHTML = ''; hostTools.classList.toggle('hidden', system.state !== 'possessed');
  if (system.state === 'possessed') {
    const note = document.createElement('span'); note.textContent = `宿主：${system.host?.name || '未知'} · ${system.host?.path_name || ''}`;
    const leave = document.createElement('button'); leave.textContent = '主动离舍'; leave.disabled = busy;
    leave.onclick = () => window.confirm('离舍会永久毁去当前肉身，且不返还夺舍次数。确认继续？') && mutate(`/api/games/${game.id}/ghost-leave-host`, {});
    hostTools.append(note, leave);
  }
  const paradeList = $('#ghost-parade-list'); paradeList.innerHTML = '';
  if (paradeVisible) {
    const live = parade.status === 'active';
    $('#ghost-parade-summary').textContent = live ? '正在夜行' : `${timelineText(parade.start_age)}开启`;
    $('#ghost-parade-description').textContent = live
      ? `${parade.location_name || parade.location_id}阴门洞开；${parade.at_location ? '你已抵达会场，可以参悟、结交或拘魂。' : '你尚未抵达会场，请从地图赶往标记地点。'}`
      : `阴司已在${parade.location_name || parade.location_id}留下预告。活动开启前可提前赶路，地图上已显示夜行标记。`;
    paradeDock?.classList.add('notice'); paradeDock?.classList.toggle('live', live);
    if (paradeDock) {
      paradeDock.title = live ? '百鬼夜行正在发生' : '百鬼夜行预告';
      const label = paradeDock.querySelector('small'); if (label) label.textContent = live ? '夜行中' : '预告';
    }
    const intro = document.createElement('p'); intro.className = 'muted';
    intro.textContent = `${parade.location_name || parade.location_id} · ${parade.status === 'active' ? `正在夜行，${(parade.souls || []).length} 魂仍在` : `将于${timelineText(parade.start_age)}开启`} · ${parade.at_location ? '你正在会场' : '地图已有标记'}`; paradeList.appendChild(intro);
    if (parade.status === 'active' && parade.at_location && system.state === 'free') {
      const join = document.createElement('button'); join.textContent = parade.participated ? '本次已参悟' : '参悟夜行'; join.disabled = busy || parade.participated;
      join.onclick = () => mutate(`/api/games/${game.id}/ghost-parade`, {action:'participate'}); paradeList.appendChild(join);
      (parade.souls || []).forEach(soul => {
        const row = document.createElement('div'); row.className = 'captive-row';
        row.innerHTML = `<b>${soul.name}${soul.defeated ? ' · 已击溃' : ''}</b><small>境界 ${soul.realm_index}/${soul.layer} · 战力 ${number(soul.combat_power)} · 魂压 ${Number(soul.soul_pressure).toFixed(2)} · ${soul.soul_trait?.name || '无性'}：${soul.soul_trait?.description || ''}</small>`;
        const tools = document.createElement('div'); tools.className = 'captive-tools';
        [['befriend',soul.befriended?'本次已结交':'结交'],[soul.defeated?'bind':'fight',soul.defeated?'拘魂':'交锋'],['capture','战而拘魂']].forEach(([action,label]) => { const b=document.createElement('button'); b.textContent=label; b.disabled=busy || (action === 'befriend' && soul.befriended); b.onclick=()=>mutate(`/api/games/${game.id}/ghost-parade`,{action,soul_id:soul.id}); tools.appendChild(b); });
        row.appendChild(tools); paradeList.appendChild(row);
      });
    }
  } else if (paradeDock) {
    paradeDock.classList.remove('notice', 'live');
  }
  const slotList = $('#ghost-soul-slots'); slotList.innerHTML = '';
  (system.slots || []).forEach(slot => {
    const row=document.createElement('div'); row.className=`captive-row ${slot.curve === 'unbounded_diminishing' ? 'three-soul' : 'seven-spirit'}`; row.innerHTML=`<b>${slot.id} · ${slot.stat_name}</b><small>${slot.soul ? `${slot.soul.name} · 当前加成 ${percent(slot.effect || 0)} · ${slot.soul.soul_trait?.name || '无性'}：${slot.soul.soul_trait?.description || '无额外规则'}` : '空位'}</small>`;
    if (slot.soul && system.state !== 'possessed') { const b=document.createElement('button'); b.textContent='卸下'; b.disabled=busy; b.onclick=()=>mutate(`/api/games/${game.id}/ghost-soul`,{action:'unequip',soul_id:slot.soul.id,slot:slot.id}); row.appendChild(b); } slotList.appendChild(row);
  });
  const soulList=$('#ghost-bound-souls'); soulList.innerHTML='';
  (system.bound_souls || []).forEach(soul => {
    const row=document.createElement('div'); row.className='captive-row'; row.innerHTML=`<b>${soul.name}</b><small>战力 ${number(soul.combat_power)} · 魂压 ${Number(soul.soul_pressure).toFixed(2)} · ${soul.soul_trait?.name || '无性'}</small>`;
    const tools=document.createElement('div'); tools.className='captive-tools'; const select=document.createElement('select');
    (system.slots || []).forEach(slot=>{const o=document.createElement('option');o.value=slot.id;o.textContent=`${slot.id}·${slot.stat_name}${slot.soul?`（替换${slot.soul.name}）`:''}`;select.appendChild(o);});
    const equip=document.createElement('button');equip.textContent='入魂位';equip.disabled=busy||system.state==='possessed';equip.onclick=()=>mutate(`/api/games/${game.id}/ghost-soul`,{action:'equip',soul_id:soul.id,slot:select.value});
    const release=document.createElement('button');release.textContent='放归';release.disabled=busy;release.onclick=()=>openGameConfirm({title:'放归拘魂',body:`确认解除${soul.name}的魂印并永久放归？该魂会同时离开魂位与拘魂册，此操作不可撤销。`,confirmText:'确认放归',onConfirm:()=>mutate(`/api/games/${game.id}/ghost-soul`,{action:'release',soul_id:soul.id})});tools.append(select,equip,release);row.appendChild(tools);soulList.appendChild(row);
  });
  if (!soulList.children.length) soulList.innerHTML='<p class="empty">尚未拘得真实魂魄。</p>';
  const attachment=$('#ghost-attachment-list'); attachment.innerHTML='';
  if (system.attachment) { const p=document.createElement('p');p.textContent=`${system.attachment.spirit_name} · 魂蚀增长 ×${Number(system.attachment.erosion_growth_multiplier).toFixed(2)} · 修炼效率 ×${Number(system.attachment.cultivation_efficiency_multiplier).toFixed(2)}`; const b=document.createElement('button');b.className='ghost-attachment-action';b.dataset.available='1';b.textContent='离器';b.disabled=busy;b.onclick=()=>mutate(`/api/games/${game.id}/ghost-attachment`,{action:'leave'});attachment.append(p,b); }
  else (system.attachable_items || []).forEach(item=>{const b=document.createElement('button');b.className='ghost-attachment-action';b.dataset.available=system.state==='free'?'1':'0';b.textContent=`附入 ${item.name}`;b.disabled=busy||b.dataset.available!=='1';b.onclick=()=>mutate(`/api/games/${game.id}/ghost-attachment`,{action:'attach',item_id:item.id});attachment.appendChild(b);});
  if (!attachment.children.length) attachment.innerHTML='<p class="empty">行囊中没有可附灵器物。</p>';
}

function renderMap(map, auction) {
  if (!map) return;
  $('#map-title').textContent = `${map.world_name}地图`;
  $('#map-current').textContent = `当前：${map.current_name}`;
  $('#map-description').textContent = '移动按最短路线消耗时间；坊市、探宝与四种气经验获取效率均受当前地域影响。世界与 NPC 会在旅途中逐年演化。';
  const list = $('#map-locations'); list.innerHTML = '';
  (map.locations || []).forEach(location => {
    const row = document.createElement('article');
    row.className = `map-location${location.current ? ' current' : ''}${location.travel_status === 'lethal' ? ' lethal' : ''}`;
    const heading = document.createElement('div'); heading.className = 'map-location-heading';
    const name = document.createElement('b'); name.textContent = location.name;
    const themes = document.createElement('span'); themes.textContent = (location.themes || []).join(' · ');
    heading.append(name, themes);
    const description = document.createElement('p'); description.textContent = location.description;
    if (auction?.available && auction.location_id === location.id) {
      const marker = document.createElement('strong'); marker.className = 'auction-map-marker';
      marker.textContent = auction.status === 'scheduled' ? `拍卖会预告 · ${auction.actions_until_open}个操作节点后开幕` : auction.status === 'open' ? '拍卖会正在举行' : '散场黑市正在开放';
      description.append(' ', marker);
    }
    if (location.ghost_parade) {
      const marker = document.createElement('strong'); marker.className = 'auction-map-marker';
      marker.textContent = location.ghost_parade.status === 'active'
        ? '百鬼夜行正在发生' : `百鬼夜行预告 · ${timelineText(location.ghost_parade.start_age)}开启`;
      description.append(' ', marker);
    }
    const qiNames = {spirit:'灵气', demon:'魔气', monster:'妖气', yin:'阴气'};
    const qiEfficiency = document.createElement('small');
    qiEfficiency.textContent = `气经验：${Object.entries(location.qi_gain_efficiencies || {}).map(([source, value]) => `${qiNames[source] || source} ×${Number(value).toFixed(2)}`).join(' · ')}`;
    const route = document.createElement('small');
    route.textContent = location.current
      ? '你当前身在此地'
      : `${(location.route_names || []).join(' → ')} · 预计 ${location.travel_years} 年${location.warning ? ` · ${location.warning}` : ''}`;
    const button = document.createElement('button');
    button.className = 'map-travel'; button.dataset.destination = location.id;
    button.dataset.travelStatus = location.travel_status;
    button.dataset.unavailable = location.current || location.travel_status === 'blocked' ? '1' : '0';
    button.textContent = location.current ? '所在地' : location.travel_status === 'blocked' ? '境界不足' : location.travel_status === 'lethal' ? '强行前往（必死）' : `前往 · ${location.travel_years}年`;
    button.disabled = busy || location.current || location.travel_status === 'blocked' || !!game.pending_event || !!game.imprisonment || game?.ghost_system?.phase_two?.state === 'controlled' || !game.player.alive;
    button.onclick = () => {
      if (location.travel_status === 'lethal' && !window.confirm(`${location.warning}。仍要强行前往吗？`)) return;
      mutate(`/api/games/${game.id}/map-travel`, {destination:location.id});
    };
    row.append(heading, description, qiEfficiency, route, button); list.appendChild(row);
  });
}

function renderMarket(market) {
  const card = $('#market-card'); card.classList.toggle('hidden', !market?.available);
  if (!market?.available) return;
  $('#market-title').textContent = market.name;
  $('#market-wallet').textContent = `灵石 ${market.spirit_stones}`;
  $('#market-description').textContent = `货物只在当前世界流通，灵石跨界通用；每件货位有 ${percent(market.next_tier_chance)} 概率出现高一境界珍品，绝不会越过两个境界。坊市每年换货。`;
  const list = $('#market-offers'); list.innerHTML = '';
  [...(market.offers || []), ...(market.crafting_material_offers || [])].forEach(offer => {
    const row = document.createElement('div'); row.className = `market-offer${offer.sold ? ' sold' : ''}`;
    const info = document.createElement('div'); const title = document.createElement('b');
    title.textContent = `${offer.kind === 'technique' ? '《' : ''}${offer.name}${offer.kind === 'technique' ? '》' : ''}`;
    const detail = document.createElement('small');
    detail.textContent = `${offer.tier_name} · ${offer.description}${offer.kind === 'technique' && !offer.compatible ? ' · 灵根不符，购得后暂不可修炼' : ''}`;
    info.append(title, detail);
    const buy = document.createElement('button'); buy.textContent = offer.sold ? '已售' : offer.owned ? '已掌握' : `${offer.price} 灵石`;
    buy.className = 'market-buy'; buy.dataset.offerId = offer.id;
    buy.disabled = busy || offer.sold || offer.owned || market.spirit_stones < offer.price || !!game.pending_event || !game.player.alive;
    buy.onclick = () => mutate(`/api/games/${game.id}/market-buy`, {offer_id:offer.id});
    row.append(info, buy); list.appendChild(row);
  });
  const plantSection = $('#market-plant-sell-section');
  const plantSellables = $('#market-plant-sellables'); plantSellables.innerHTML = '';
  const plants = market.sellable_plants || [];
  plantSection.classList.toggle('hidden', !plants.length);
  plants.forEach(item => {
    const button = document.createElement('button');
    button.textContent = `出售${item.name} ×1/${item.quantity} · ${number(item.price)}灵石`;
    button.onclick = () => mutate(`/api/games/${game.id}/market-sell-plant`, {item_id:item.id});
    plantSellables.appendChild(button);
  });
}

function renderAuction(system) {
  const card = $('#auction-card');
  const dock = document.querySelector("[data-panel-target='auction']");
  card.classList.toggle('hidden', !system.available);
  dock?.classList.toggle('hidden', !system.available);
  if (!system.available) return;
  const statusNames = {scheduled:'拍卖会预告', open:'拍卖会', black_market:'散场黑市'};
  $('#auction-title').textContent = `${system.location_name}·${statusNames[system.status] || '交易集会'}`;
  $('#auction-wallet').textContent = `灵石 ${number(system.spirit_stones || 0)}`;
  $('#auction-description').textContent = system.status === 'scheduled'
    ? `将在 ${system.actions_until_open} 个有时间消耗的操作节点后开幕；公告期可提前赶路和寄拍。`
    : system.status === 'open'
      ? `第 ${Number(system.round || 0) + 1}/${system.max_rounds} 轮；所有会内操作均不消耗时间。单次最低加价同时受起拍价和当前价约束。`
      : `拍卖散场后立即形成的临时黑市；检索、买卖均不消耗时间，开始新的岁月行动后黑市关闭。`;
  const warning = $('#auction-travel-warning');
  warning.classList.toggle('hidden', system.at_location);
  warning.textContent = system.at_location ? '' : `你当前不在${system.location_name}，只能查看公告，无法交易。请从地图赶往会场；若地图有境界禁制，拍卖方不会为你解除。`;

  const identitySection = $('#auction-identity-section');
  identitySection.classList.toggle('hidden', system.status !== 'open' || !system.at_location);
  const identities = $('#auction-identities'); identities.innerHTML = '';
  (system.player_aliases || []).forEach(alias => {
    const button = document.createElement('button');
    button.textContent = alias === system.player_alias ? `${alias} · 当前身份` : alias;
    button.classList.toggle('selected', alias === system.player_alias);
    button.dataset.auctionUnavailable = alias === system.player_alias ? '1' : '0';
    button.disabled = alias === system.player_alias;
    button.onclick = () => mutate(`/api/games/${game.id}/auction-identity`, {alias});
    identities.appendChild(button);
  });

  const consignSection = $('#auction-consign-section');
  consignSection.classList.toggle('hidden', !system.at_location || !['scheduled', 'open'].includes(system.status));
  const consignSelect = $('#auction-consign-item'); consignSelect.innerHTML = '';
  (system.consignable_items || []).forEach(item => {
    const option = document.createElement('option'); option.value = item.id;
    option.textContent = `${item.name} ×${item.quantity} · 额定 ${number(item.rated_price)} · 起拍 ${number(item.minimum_start_price)}—${number(item.maximum_start_price)} · 占位费 ${number(item.listing_fee)}`;
    option.dataset.suggested = item.suggested_start_price;
    option.dataset.minimum = item.minimum_start_price;
    option.dataset.maximum = item.maximum_start_price;
    option.dataset.fee = item.listing_fee;
    consignSelect.appendChild(option);
  });
  const syncStartPrice = () => {
    const option = consignSelect.selectedOptions[0];
    if (option) {
      const input = $('#auction-start-price');
      input.value = option.dataset.suggested || 1;
      input.min = option.dataset.minimum;
      input.max = option.dataset.maximum;
      input.title = `允许 ${number(option.dataset.minimum)}—${number(option.dataset.maximum)} 灵石；上拍即付占位费 ${number(option.dataset.fee)} 灵石`;
    }
  };
  consignSelect.onchange = syncStartPrice; syncStartPrice();
  $('#auction-consign-form').onsubmit = event => {
    event.preventDefault();
    if (!consignSelect.value) return toast('没有可寄拍的物品');
    mutate(`/api/games/${game.id}/auction-consign`, {item_id:consignSelect.value, start_price:Number($('#auction-start-price').value || 0)});
  };

  const lotsSection = $('#auction-lots-section');
  lotsSection.classList.toggle('hidden', system.status !== 'open' || !system.at_location);
  const lots = $('#auction-lots'); lots.innerHTML = '';
  (system.lots || []).forEach(lot => {
    const row = document.createElement('div'); row.className = 'auction-lot';
    const info = document.createElement('div');
    const title = document.createElement('b'); title.textContent = `${lot.kind === 'technique' ? '《' : ''}${lot.name}${lot.kind === 'technique' ? '》' : ''}`;
    const detail = document.createElement('small'); detail.textContent = `${lot.tier_name} · ${lot.description} · 额定 ${number(lot.rated_price)} · 当前 ${number(lot.current_bid)} 灵石（${lot.current_bidder_name}）`;
    info.append(title, detail);
    const bid = document.createElement('button'); bid.className = 'auction-bid'; bid.dataset.lotId = lot.id;
    if (lot.seller === 'player') bid.textContent = `你的寄拍 · 预计实得 ${number(Math.floor(lot.current_bid * (1 - system.commission_rate)))}灵石`;
    else if (lot.current_bidder === 'player') bid.textContent = '当前由你领拍';
    else if (lot.current_bid + lot.minimum_increment > lot.maximum_bid) bid.textContent = '已达五倍竞价上限';
    else bid.textContent = `加价至 ${number(lot.current_bid + lot.minimum_increment)}`;
    bid.dataset.auctionUnavailable = lot.seller === 'player' || lot.current_bidder === 'player' || lot.current_bid + lot.minimum_increment > lot.maximum_bid || system.spirit_stones < lot.current_bid + lot.minimum_increment ? '1' : '0';
    bid.disabled = bid.dataset.auctionUnavailable === '1';
    bid.onclick = () => mutate(`/api/games/${game.id}/auction-bid`, {lot_id:lot.id});
    row.append(info, bid); lots.appendChild(row);
  });
  const advance = $('#auction-advance-round');
  advance.textContent = Number(system.round || 0) + 1 >= Number(system.max_rounds || 1) ? '推进并完成结拍' : '推进一轮竞价';
  advance.onclick = () => mutate(`/api/games/${game.id}/auction-advance`, {});

  const attendeeSection = $('#auction-attendees-section');
  attendeeSection.classList.toggle('hidden', system.status !== 'open' || !system.at_location);
  const attendees = $('#auction-attendees'); attendees.innerHTML = '';
  (system.attendees || []).forEach(npc => {
    const wrapper = document.createElement('div'); wrapper.className = 'auction-attendee-wrap';
    const row = document.createElement('div'); row.className = 'auction-attendee';
    const info = document.createElement('span'); info.textContent = `${npc.name} · ${npc.title || npc.realm_name} · 好感 ${number(npc.affinity)}`;
    const button = document.createElement('button'); button.textContent = npc.private_trade_unlocked ? '已开启私下交易' : npc.interacted ? '已交涉' : '借机交涉'; button.dataset.auctionUnavailable = npc.interacted ? '1' : '0'; button.disabled = npc.interacted;
    button.onclick = () => mutate(`/api/games/${game.id}/auction-negotiate`, {npc_id:npc.id});
    row.append(info, button); wrapper.appendChild(row);
    if (npc.private_trade_unlocked) {
      const trade = document.createElement('details'); trade.className = 'private-trade-card';
      const summary = document.createElement('summary'); summary.textContent = `与${npc.name}私下交易（可各还价一次）`; trade.appendChild(summary);
      const offers = document.createElement('div'); offers.className = 'private-trade-offers';
      (npc.trade_offers || []).forEach(offer => {
        const offerRow = document.createElement('div'); offerRow.className = 'auction-lot';
        const text = document.createElement('div'); text.innerHTML = `<b>${offer.name}</b><small>${offer.description}</small>`;
        const tools = document.createElement('span'); tools.className = 'private-trade-tools';
        const haggle = document.createElement('button'); haggle.textContent = offer.bargained ? '已还价' : '讨价'; haggle.disabled = offer.bargained || offer.sold;
        haggle.dataset.auctionUnavailable = offer.bargained || offer.sold ? '1' : '0';
        haggle.onclick = () => mutate(`/api/games/${game.id}/auction-private-bargain`, {npc_id:npc.id, side:'buy', asset_id:offer.id});
        const buy = document.createElement('button'); buy.textContent = offer.sold ? '已售' : `${number(offer.price)} 灵石`; buy.disabled = offer.sold || system.spirit_stones < offer.price;
        buy.dataset.auctionUnavailable = offer.sold || system.spirit_stones < offer.price ? '1' : '0';
        buy.onclick = () => mutate(`/api/games/${game.id}/auction-private-buy`, {npc_id:npc.id, offer_id:offer.id});
        tools.append(haggle, buy); offerRow.append(text, tools); offers.appendChild(offerRow);
      });
      trade.appendChild(offers);
      const sellForm = document.createElement('div'); sellForm.className = 'private-trade-sell';
      const select = document.createElement('select');
      (system.private_sellable_items || []).forEach(item => {
        const option = document.createElement('option'); option.value = item.id;
        const multiplier = Number(npc.sell_bargains?.[item.id] || 1);
        option.textContent = `${item.name} ×${item.quantity} · 约 ${number(Math.round(item.private_base_price * multiplier))}灵石`;
        select.appendChild(option);
      });
      const sellHaggle = document.createElement('button'); sellHaggle.textContent = '抬价';
      sellHaggle.onclick = () => select.value && mutate(`/api/games/${game.id}/auction-private-bargain`, {npc_id:npc.id, side:'sell', asset_id:select.value});
      const sell = document.createElement('button'); sell.textContent = '卖给对方';
      sell.onclick = () => select.value && mutate(`/api/games/${game.id}/auction-private-sell`, {npc_id:npc.id, item_id:select.value});
      if (!select.options.length) { sellHaggle.disabled = true; sell.disabled = true; sellHaggle.dataset.auctionUnavailable = '1'; sell.dataset.auctionUnavailable = '1'; }
      sellForm.append(select, sellHaggle, sell); trade.appendChild(sellForm);
      wrapper.appendChild(trade);
    }
    attendees.appendChild(wrapper);
  });

  const logSection = $('#auction-log-section');
  logSection.classList.toggle('hidden', system.status !== 'open' || !system.at_location);
  const logs = $('#auction-bid-logs'); logs.innerHTML = '';
  (system.bid_logs || []).slice().reverse().forEach(message => {
    const line = document.createElement('p'); line.textContent = message; logs.appendChild(line);
  });

  const black = $('#black-market-section');
  black.classList.toggle('hidden', system.status !== 'black_market' || !system.at_location);
  $('#black-market-search-form').onsubmit = event => {
    event.preventDefault();
    mutate(`/api/games/${game.id}/black-market-search`, {pattern:$('#black-market-pattern').value});
  };
  const results = $('#black-market-results'); results.innerHTML = '';
  (system.black_market_results || []).forEach(result => {
    const row = document.createElement('div'); row.className = 'auction-lot';
    const info = document.createElement('div');
    const title = document.createElement('b'); title.textContent = `${result.kind === 'technique' ? '《' : ''}${result.name}${result.kind === 'technique' ? '》' : ''}`;
    const detail = document.createElement('small'); detail.textContent = `${result.tier_name} · ${result.description}`; info.append(title, detail);
    const buy = document.createElement('button'); buy.textContent = `${number(result.price)} 灵石`; buy.dataset.auctionUnavailable = system.spirit_stones < result.price ? '1' : '0'; buy.disabled = buy.dataset.auctionUnavailable === '1';
    buy.onclick = () => mutate(`/api/games/${game.id}/black-market-buy`, {result_id:result.id});
    row.append(info, buy); results.appendChild(row);
  });
  const sellables = $('#black-market-sellables'); sellables.innerHTML = '';
  [...(system.black_market_sellable_items || []).map(item => ({...item, kind:'item'})), ...(system.black_market_sellable_puppets || []).map(item => ({...item, kind:'puppet'}))].forEach(asset => {
    const button = document.createElement('button');
    button.textContent = `出手${asset.name}${asset.quantity ? ` ×1/${asset.quantity}` : ''}${asset.black_market_price ? ` · ${number(asset.black_market_price)}灵石` : ''}`;
    button.onclick = () => mutate(`/api/games/${game.id}/black-market-sell`, {kind:asset.kind, asset_id:asset.id});
    sellables.appendChild(button);
  });
  $('#black-market-leave').onclick = () => mutate(`/api/games/${game.id}/black-market-leave`, {});
}

function meter(id, value, maximum) {
  const current = Math.max(0, Number(value));
  $(`#${id}-text`).textContent = `${number(current)} / ${number(maximum)}`;
  $(`#${id}-bar`).style.width = `${Math.min(100, current / maximum * 100)}%`;
}

function renderQiMastery(masteries, efficiencies) {
  const list = $('#qi-mastery'); list.innerHTML = '';
  masteries.forEach(entry => {
    const row = document.createElement('div'); row.className = 'qi-mastery-item'; row.dataset.source = entry.source;
    const heading = document.createElement('div');
    const name = document.createElement('b'); name.textContent = `${entry.name} Lv.${entry.level}`;
    const progress = document.createElement('span'); progress.textContent = `${number(entry.level_experience)} / ${number(entry.next_level_experience)}`;
    const meter = document.createElement('div'); meter.className = 'qi-mini-meter';
    const fill = document.createElement('i'); fill.style.width = `${Math.min(100, entry.level_experience / Math.max(1, entry.next_level_experience) * 100)}%`;
    meter.appendChild(fill); heading.append(name, progress); row.append(heading, meter);
    row.title = `累计经验 ${number(entry.experience)}；当前地图获取效率 ×${Number(efficiencies[entry.source] || 0).toFixed(2)}`;
    list.appendChild(row);
  });
}

function renderArtSkills(skills) {
  const list = $('#art-mastery'); list.innerHTML = '';
  skills.forEach(skill => {
    const row = document.createElement('div'); row.className = 'art-mastery-item';
    const heading = document.createElement('div');
    const name = document.createElement('b'); name.textContent = `${skill.name} Lv.${skill.level}`;
    const progress = document.createElement('span'); progress.textContent = `${number(skill.level_experience)} / ${number(skill.next_level_experience)}`;
    const meter = document.createElement('div'); meter.className = 'qi-mini-meter';
    const fill = document.createElement('i'); fill.style.width = `${Math.min(100, skill.level_experience / Math.max(1, skill.next_level_experience) * 100)}%`;
    meter.appendChild(fill); heading.append(name, progress); row.append(heading, meter);
    row.title = `累计${skill.name}经验 ${number(skill.experience)}`;
    list.appendChild(row);
  });
}

function renderSpiritField(field) {
  $('#spirit-field-summary').textContent = `${number(field.reclaimed_qing || 0)}/${number(field.max_qing || 0)} 顷`;
  $('#spirit-field-note').textContent = field.reclaimed_qing
    ? `已有 ${field.free_qing} 顷空闲。按数量级向下取整：201 年记作 200 年，2,001 年记作 2,000 年；年份更高不保证品质更好。`
    : '尚未开垦。开垦消耗时间与灵石，期间世界正常演进。';
  const plots = $('#spirit-field-plots'); plots.innerHTML = '';
  for (let index = 0; index < Number(field.max_qing || 0); index += 1) {
    const crop = (field.plots || []).find(entry => Number(entry.slot) === index);
    const row = document.createElement('div'); row.className = `spirit-crop-tile${crop?.best ? ' best' : ''}${index >= field.reclaimed_qing ? ' locked' : ''}`;
    const tileNo = document.createElement('i'); tileNo.textContent = `${index + 1}`; row.appendChild(tileNo);
    if (index >= field.reclaimed_qing) {
      const locked = document.createElement('b'); locked.textContent = '荒地'; row.appendChild(locked);
      const detail = document.createElement('small'); detail.textContent = index === field.reclaimed_qing && field.can_reclaim ? `${number(field.reclaim_cost)} 灵石 · ${number(field.reclaim_years)} 年` : '须依次开垦'; row.appendChild(detail);
      if (index === field.reclaimed_qing && field.can_reclaim) {
        const reclaim = document.createElement('button'); reclaim.textContent = '开垦此顷';
        reclaim.disabled = field.spirit_stones < field.reclaim_cost; reclaim.dataset.actionUnavailable = reclaim.disabled ? '1' : '0';
        reclaim.onclick = () => mutate(`/api/games/${game.id}/spirit-field-reclaim`, {}); row.appendChild(reclaim);
      }
      plots.appendChild(row); continue;
    }
    if (!crop) {
      const empty = document.createElement('b'); empty.textContent = '空闲沃土'; row.appendChild(empty);
      const seed = document.createElement('select');
      (field.seeds || []).forEach(entry => {
        const option = document.createElement('option'); option.value = entry.plant_id; option.textContent = `${entry.name}种 ×${entry.quantity}`; seed.appendChild(option);
      });
      const plant = document.createElement('button'); plant.textContent = '播种'; plant.disabled = !seed.options.length;
      plant.dataset.actionUnavailable = plant.disabled ? '1' : '0';
      plant.onclick = () => seed.value && mutate(`/api/games/${game.id}/spirit-field-plant`, {plant_id:seed.value, slot:index});
      row.append(seed, plant); plots.appendChild(row); continue;
    }
    const info = document.createElement('div');
    const title = document.createElement('b'); title.textContent = crop.name;
    const detail = document.createElement('small'); detail.textContent = `实龄 ${number(crop.growth_years)} 年 → 采收记 ${number(crop.display_years)} 年 · 品质 ${percent(crop.quality)} · 最佳 ${number(crop.optimal_years)} 年${crop.best ? ' · 正当药龄' : ''}`;
    info.append(title, detail);
    const tools = document.createElement('div'); tools.className = 'spirit-crop-tools';
    const amount = document.createElement('input'); amount.type = 'number'; amount.min = Math.ceil(field.irrigation_min_mp); amount.max = Math.floor(Math.min(field.irrigation_max_mp, field.mp)); amount.value = Math.max(Number(amount.min), Math.min(Number(amount.max), Math.round(field.max_mp * .12))); amount.title = `投入越多催熟越快；本境界投入全部最大 MP 约等效 ${number(field.irrigation_years_at_full_mp)} 年`;
    const booster = document.createElement('select');
    const noBooster = document.createElement('option'); noBooster.value = ''; noBooster.textContent = crop.requires_booster && !crop.booster_unlocked ? '须选造化灵液' : '不使用培育物'; booster.appendChild(noBooster);
    (field.boosters || []).forEach(entry => { const option = document.createElement('option'); option.value = entry.id; option.textContent = `${entry.name} ×${entry.quantity}`; booster.appendChild(option); });
    const water = document.createElement('button'); water.textContent = '灌溉催熟'; water.disabled = field.mp < field.irrigation_min_mp || (crop.requires_booster && !crop.booster_unlocked && !(field.boosters || []).length);
    water.dataset.actionUnavailable = water.disabled ? '1' : '0';
    water.onclick = () => mutate(`/api/games/${game.id}/spirit-field-irrigate`, {plot_id:crop.id, mp_amount:Number(amount.value), booster_id:booster.value});
    const harvest = document.createElement('button'); harvest.textContent = '采收'; harvest.disabled = !crop.can_harvest;
    harvest.dataset.actionUnavailable = harvest.disabled ? '1' : '0';
    harvest.onclick = () => mutate(`/api/games/${game.id}/spirit-field-harvest`, {plot_id:crop.id});
    tools.append(amount, booster, water, harvest); row.append(info, tools); plots.appendChild(row);
  }
  const alchemy = field.alchemy || {};
  const target = $('#alchemy-target'); target.innerHTML = '';
  (alchemy.targets || []).forEach(entry => { const option = document.createElement('option'); option.value = entry.id; option.textContent = `${entry.tier}阶 · ${entry.name}`; target.appendChild(option); });
  const materials = $('#alchemy-materials'); materials.innerHTML = '';
  (alchemy.materials || []).forEach(item => {
    const label = document.createElement('label'); label.textContent = `${item.name}（品质 ${percent(item.quality)}，有 ${item.quantity}）`;
    const input = document.createElement('input'); input.type = 'number'; input.min = '0'; input.max = item.quantity; input.value = '0'; input.dataset.itemId = item.id;
    label.appendChild(input); materials.appendChild(label);
  });
  const refine = $('#alchemy-refine'); refine.disabled = !target.options.length || !(alchemy.materials || []).length;
  refine.dataset.actionUnavailable = refine.disabled ? '1' : '0';
  refine.onclick = () => {
    const selected = [...materials.querySelectorAll('input')].map(input => ({item_id:input.dataset.itemId, quantity:Number(input.value || 0)})).filter(row => row.quantity > 0);
    if (!selected.length) return toast('至少投入一株药材');
    mutate(`/api/games/${game.id}/alchemy`, {target_item_id:target.value, materials:selected});
  };
}

function renderInventory(items) {
  const list = $('#inventory-list'); list.innerHTML = '';
  if (!items.length) { list.innerHTML = '<p class="empty">袖中空空，唯有清风。</p>'; return; }
  const definitions = [
    ['丹药与突破材料', item => item.breakthrough_bonus > 0 || item.tags?.includes('pill') || item.tags?.includes('breakthrough')],
    ['灵植与种子', item => item.tags?.includes('spirit_plant') || item.tags?.includes('seed')],
    ['灵根法门', item => item.tags?.includes('root_manual')],
    ['法宝与装备', item => item.combat_bonus > 0 || item.tags?.includes('artifact') || item.tags?.includes('equipment')],
    ['灵石与货币', item => item.tags?.includes('currency')],
    ['剧情信物', item => item.tags?.some(tag => ['story', 'key', 'contract'].includes(tag))],
    ['材料与杂物', () => true],
  ];
  const groups = new Map(definitions.map(([name]) => [name, []]));
  items.forEach(item => groups.get(definitions.find(([, match]) => match(item))[0]).push(item));
  groups.forEach((groupItems, categoryName) => {
    if (!groupItems.length) return;
    const section = document.createElement('section'); section.className = 'inventory-category';
    const heading = document.createElement('h3'); heading.textContent = `${categoryName} · ${groupItems.length}`; section.appendChild(heading);
    groupItems.forEach(item => {
    const row = document.createElement('div'); row.className = `item${item.is_natal_artifact ? ' natal-artifact-item' : ''}`;
    const text = document.createElement('span');
    const name = document.createElement('b'); name.textContent = `${item.is_natal_artifact ? '本命 · ' : ''}${item.name} × ${item.quantity}`;
    const effect = document.createElement('small'); effect.textContent = item.description || '可用于特定事件。';
    text.append(name, effect); row.appendChild(text);
    const trialRecovery = (item.trial_restore_hp > 0 || item.trial_restore_mp > 0) && game.trial?.active;
    const specialPlantUse = (item.plant_id === 'mystic_heaven_vine' && item.plant_years >= 10000) || (item.plant_id === 'nebula_manjushaka' && item.plant_years >= 5000);
    const normalUse = item.id === 'healing_pill' || item.id.startsWith('jinque_') || item.id.startsWith('zique_') || item.id.startsWith('moque_') || item.breakthrough_bonus > 0 || item.conception_bonus > 0 || item.permanent_intrinsic_hp_bonus > 0 || item.permanent_intrinsic_mp_bonus > 0 || specialPlantUse;
    if ((trialRecovery || (normalUse && !game.pending_event)) && game.player.alive) {
      const use = document.createElement('button'); use.className = 'item-use'; use.textContent = '服用';
      if (item.id.startsWith('jinque_') || item.id.startsWith('zique_') || item.id.startsWith('moque_')) use.textContent = '参悟';
      if (specialPlantUse) { use.textContent = '使用'; use.onclick = () => mutate(`/api/games/${game.id}/spirit-plant-use`, {item_id:item.id}); }
      const ghostBreakthroughPill = Boolean(game.ghost_system?.available && item.breakthrough_bonus > 0);
      if (ghostBreakthroughPill) {
        use.textContent = '鬼修不可用';
        use.disabled = true;
        use.dataset.itemUnavailable = '1';
        use.title = '阴魂不受血肉丹火重塑；鬼修只能通过轮回经验提高正常修为突破率';
      }
      use.dataset.allowDuringTrial = trialRecovery ? '1' : '0';
      if (!specialPlantUse && !ghostBreakthroughPill) use.onclick = () => mutate(`/api/games/${game.id}/use-item`, {item_id:item.id});
      row.appendChild(use);
    }
      section.appendChild(row);
    });
    list.appendChild(section);
  });
}

function renderDemonicSystem(system) {
  $('#puppet-capacity').textContent = `神识容量 ${system.used || 0}/${system.capacity || 0}`;
  $('#devour-bonus').textContent = `当前吞噬突破加成 ${percent(system.breakthrough_bonus || 0)}`;
  $('#puppet-time-note').textContent = system.time_behavior || '';
  const captiveList = $('#captive-list'); captiveList.innerHTML = '';
  (system.prisoners || []).forEach(person => {
    const row = document.createElement('div'); row.className = 'captive-row';
    row.innerHTML = `<b>${person.name}</b><small>${person.realm_name || `境界 ${person.realm_index}`} · ${person.path_name || person.path} · 战力 ${number(person.combat_power)} · 好感 ${number(person.affinity || 0)}</small>`;
    const tools = document.createElement('div'); tools.className = 'captive-tools';
    const actions = [['release','释放'],['torture','拷打']];
    if (game?.ghost_system?.available && !game?.ghost_system?.suspended) actions.push(['possess','夺舍']);
    if (system.is_demonic) actions.push(['corpse','直接炼化'],['living','种下标记']);
    actions.forEach(([action,label]) => {
      const button = document.createElement('button'); button.textContent = label; button.className = action === 'corpse' ? 'danger' : '';
      if (action === 'possess') { button.disabled = busy || !person.can_possess; button.title = person.possession_reason || '夺舍失败将魂飞魄散'; }
      button.onclick = () => mutate(`/api/games/${game.id}/captive-action`, {target_id:person.id, action}); tools.appendChild(button);
    });
    row.appendChild(tools); captiveList.appendChild(row);
  });
  if (!captiveList.children.length) captiveList.innerHTML = '<p class="empty">尚未生擒任何修士。</p>';

  const puppetList = $('#puppet-list'); puppetList.innerHTML = '';
  (system.puppets || []).forEach(puppet => {
    const row = document.createElement('div'); row.className = 'puppet-row';
    const control = puppet.type === 'living' ? ` · 控制度 ${number(puppet.control)}%` : '';
    row.innerHTML = `<b>${puppet.type_name} · ${puppet.name}</b><small>${puppet.realm_name} · 自身战力 ${number(puppet.combat_power)} · ${puppet.battle_contribution_mode || '战力贡献'} ${number(puppet.battle_contribution || 0)}（${percent(puppet.battle_contribution_ratio || 0)}） · 主修《${puppet.main_technique_name}》${control}</small><small>培养积累 ${number(puppet.cultivation_progress || 0)} · 下次突破加成 ${percent(puppet.breakthrough_bonus || 0)}${puppet.annual_opportunity ? ` · 每年机缘 +${Number(puppet.annual_opportunity).toFixed(1)}` : ''}</small>`;
    const tools = document.createElement('div'); tools.className = 'puppet-tools';
    if (puppet.type !== 'mechanical') tools.appendChild(puppetButton('灌注气', puppet.id, 'infuse'));
    if ((system.pill_options || []).length && puppet.type !== 'mechanical') {
      const select = optionSelect(system.pill_options); tools.append(select, puppetButton('喂丹', puppet.id, 'pill', select));
    }
    if (puppet.type === 'living' && (system.technique_options || []).length) {
      const select = optionSelect(system.technique_options); tools.append(select, puppetButton('更换功法', puppet.id, 'technique', select));
    }
    if (system.is_demonic && puppet.type === 'living') tools.appendChild(puppetButton(`加固控制（${number(system.control_mp_cost || 0)} MP）`, puppet.id, 'reinforce_control'));
    if (system.is_demonic && puppet.type !== 'mechanical') tools.appendChild(puppetButton('吞噬', puppet.id, 'devour'));
    tools.appendChild(puppetButton('解除', puppet.id, 'dismiss'));
    row.appendChild(tools); puppetList.appendChild(row);
  });
  if (!puppetList.children.length) puppetList.innerHTML = '<p class="empty">尚无受控傀儡。</p>';

  const soulList = $('#foreign-soul-list'); soulList.innerHTML = '';
  const souls = system.foreign_souls || [];
  const activeSouls = souls.filter(soul => !soul.refined);
  const refinedSouls = souls.filter(soul => soul.refined);
  const appendSoul = (parent, soul, compact = false) => {
    const row = document.createElement('div'); row.className = 'soul-row';
    row.innerHTML = compact
      ? `<b>${soul.name}之元神</b><small>强度 ${number(soul.strength)} · 已炼化</small>`
      : `<b>${soul.name}之元神</b><small>强度 ${number(soul.strength)} · 炼化 ${number(soul.progress)}/${number(soul.required)} · 待释放突破潜力 ${percent(soul.remaining_bonus || 0)}</small>`;
    parent.appendChild(row);
  };
  activeSouls.forEach(soul => appendSoul(soulList, soul));
  if (refinedSouls.length) {
    const archive = document.createElement('details'); archive.className = 'soul-archive';
    const summary = document.createElement('summary'); summary.textContent = `已炼化元神 ${refinedSouls.length} 道（展开归档）`;
    const archiveList = document.createElement('div'); archiveList.className = 'soul-archive-list';
    refinedSouls.forEach(soul => appendSoul(archiveList, soul, true));
    archive.append(summary, archiveList); soulList.appendChild(archive);
  }
  if (!souls.length) soulList.innerHTML = '<p class="empty">识海中没有外来元神。</p>';
  $('#craft-puppet').onclick = () => mutate(`/api/games/${game.id}/craft-puppet`, {});
  $('#refine-souls').onclick = () => mutate(`/api/games/${game.id}/refine-souls`, {});
  const secludedRefine = $('#secluded-refine-souls');
  secludedRefine.classList.toggle('hidden', !system.is_demonic);
  secludedRefine.textContent = `闭关炼化（预计 ${number(system.secluded_refine_years || 0)} 年）`;
  secludedRefine.title = `一次炼化全部未净元神，不消耗机缘与 MP；耗时为正常炼化的 ${percent(system.secluded_refine_multiplier || 1.2)}。`;
  secludedRefine.onclick = () => mutate(`/api/games/${game.id}/secluded-refine-souls`, {});

  function optionSelect(options) {
    const select = document.createElement('select');
    options.forEach(option => { const node = document.createElement('option'); node.value = option.id; node.textContent = option.name; select.appendChild(node); });
    return select;
  }
  function puppetButton(label, puppetId, action, select = null) {
    const button = document.createElement('button'); button.textContent = label;
    if (action === 'devour') button.className = 'danger';
    button.onclick = () => mutate(`/api/games/${game.id}/puppet-action`, {puppet_id:puppetId, action, content_id:select?.value || ''});
    return button;
  }
}

function renderTechniques(slots) {
  const list = $('#technique-list'); list.innerHTML = '';
  const transformationAllowed = game?.player?.path !== 'monster';
  const equippedCount = [slots.main, slots.support, slots.body, slots.divine_sense, ...(transformationAllowed ? [slots.transformation] : []), ...(slots.combat || [])].filter(Boolean).length;
  $('#equipped-technique-count').textContent = `（${equippedCount}）`;
  const add = (role, technique, activeText) => {
    if (!technique) return;
    const row = document.createElement('div'); row.className = 'technique-row';
    const name = document.createElement('b'); name.textContent = `${role} · ${technique.name}`;
    const effect = document.createElement('small'); effect.textContent = activeText(technique);
    row.append(name, effect); list.appendChild(row);
  };
  const source = art => `${art.source_display || '灵源'}${art.environment_multiplier == null ? '' : ` · 环境 ×${Number(art.environment_multiplier).toFixed(3)}`}`;
  add('主修', slots.main, art => `${source(art)} · 启用机缘 +${percent(art.opportunity_bonus)}${art.karma_multiplier !== 1 ? `，因果倍率 ×${art.karma_multiplier}` : ''}`);
  add('辅修', slots.support, art => `${source(art)} · 启用 HP +${percent(art.hp_bonus)}，MP +${percent(art.mp_bonus)}`);
  add('炼体', slots.body, art => `${source(art)} · 炼体突破 +${percent(art.body_breakthrough_bonus)}（适用至 ${art.body_bonus_max_layer} 层）`);
  add('神识', slots.divine_sense, art => `${source(art)} · 神识修炼 +${percent(art.divine_sense_bonus)}`);
  if (transformationAllowed) add('变身', slots.transformation, art => `容量 ${art.transformation_capacity} · 空间 ${art.transformation_space} · 战斗开始后由预案自动启用`);
  slots.combat.forEach(art => add('战斗', art, value => `${source(value)} · 门槛 ${value.combat_requirement_display}${value.combat_requirement_met ? '' : ' · 当前失效'} · 独立战斗力 +${number(value.combat_bonus)}（气环境不参与）`));
  if (!slots.main) addEmpty('主修');
  if (!slots.support) addEmpty('辅修');
  if (!slots.body) addEmpty('炼体');
  if (!slots.divine_sense) addEmpty('神识');
  if (transformationAllowed && !slots.transformation) addEmpty('变身');
  if (!slots.combat.length) addEmpty('战斗');
  function addEmpty(role) {
    const row = document.createElement('div'); row.className = 'technique-row';
    row.innerHTML = `<b>${role} · 空</b><small>需要通过事件与机缘获得功法</small>`;
    list.appendChild(row);
  }
}

function renderKnownTechniques(techniques) {
  const list = $('#known-technique-list'); list.innerHTML = '';
  $('#known-technique-count').textContent = `（${techniques.length}）`;
  if (!techniques.length) { list.innerHTML = '<p class="empty">尚无可配置功法。</p>'; return; }
  techniques.forEach(art => {
    const row = document.createElement('div'); row.className = 'known-technique';
    const info = document.createElement('div'); const name = document.createElement('b'); name.textContent = `${art.name} · ${art.category_name || '修仙'} · ${art.element_name}`;
    const sourceText = art.source_display || '灵源';
    const detail = document.createElement('small'); detail.textContent = art.category === 'body'
      ? `${sourceText} · 炼体突破 +${percent(art.body_breakthrough_bonus)}（至 ${art.body_bonus_max_layer} 层） · 通用四维：机缘 +${percent(art.opportunity_bonus)} · HP +${percent(art.hp_bonus)} · MP +${percent(art.mp_bonus)} · 战力 +${number(art.combat_bonus)}`
      : art.category === 'divine_sense'
        ? `${sourceText} · 神识修炼 +${percent(art.divine_sense_bonus)} · 当前环境倍率参与神识经验计算`
      : art.category === 'transformation'
        ? `变身容量 ${art.transformation_capacity} · 战斗空间 ${art.transformation_space} · 形态由真灵素材独立解锁`
      : `${sourceText} · 战斗门槛 ${art.combat_requirement_display}${art.required_body_training ? ` · 炼体门槛 ${art.required_body_training} 层${art.body_requirement_met ? '' : '（未满足）'}` : ''}${art.requires_immortal_power ? ` · 仙灵力消耗 ${percent(art.immortal_power_cost)}` : ''} · 机缘 +${percent(art.opportunity_bonus)} · HP +${percent(art.hp_bonus)} · MP +${percent(art.mp_bonus)} · 战力 +${number(art.combat_bonus)}`;
    info.append(name, detail); row.appendChild(info);
    const buttons = document.createElement('div'); buttons.className = 'technique-equip-buttons';
    const slotChoices = art.category === 'body' ? [['body','体']] : art.category === 'divine_sense' ? [['divine_sense','识']] : art.category === 'transformation' ? (game.player.path === 'monster' ? [] : [['transformation','变']]) : [['main','主'],['support','辅'],['combat','战']];
    slotChoices.forEach(([slot,label]) => {
      const button = document.createElement('button'); button.className = 'technique-equip'; button.textContent = label;
      const eligible = art.compatible && (slot !== 'combat' || art.combat_requirement_met);
      button.dataset.compatible = eligible ? '1' : '0';
      button.title = art.requires_immortal_power && !art.immortal_power_met
        ? '尚未完成仙灵力转化'
        : art.required_body_training && !art.body_requirement_met ? `肉身不足：需要炼体${art.required_body_training}层`
        : slot === 'combat' && !art.combat_requirement_met ? `气等级不足：${art.combat_requirement_display}` : '';
      button.disabled = busy || !eligible || !!game.pending_event || !game.player.alive;
      button.onclick = () => mutate(`/api/games/${game.id}/equip-technique`, {technique_id:art.id, slot});
      buttons.appendChild(button);
    });
    row.appendChild(buttons); list.appendChild(row);
  });
}

function renderTransformationSystem(system) {
  const technique = system.technique;
  $('#transformation-summary').textContent = technique
    ? `${technique.name} · ${system.stored?.length || 0}/${system.capacity} · 启用 ${system.active?.length || 0}/${system.space}`
    : '尚未配置变身功法';
  $('#transformation-note').textContent = technique
    ? `功法只提供容量与战斗空间，不再预设形态。启用顺序决定权重：${(system.stored || []).filter(form => form.active).map(form => `${form.name} ${percent(form.weight)}`).join('、') || '尚未启用'}。开战后全程自动。`
    : '先炼化真灵之血、精魄或元神解锁形态；配置变身功法后才能存放并加入自动战斗预案。';
  const combined = $('#transformation-combined'); combined.innerHTML = '';
  (system.combined_stats || []).forEach(stat => {
    const row = document.createElement('div'); row.className = 'transformation-stat';
    row.innerHTML = `<span>${stat.name}</span><b>×${Number(stat.multiplier).toFixed(3)}</b>`;
    combined.appendChild(row);
  });
  const materials = $('#transformation-materials'); materials.innerHTML = '';
  (system.materials || []).forEach(material => {
    const row = document.createElement('div'); row.className = 'transformation-form transformation-material';
    const title = document.createElement('b'); title.textContent = `${material.name} ×${material.quantity}`;
    const detail = document.createElement('small');
    detail.textContent = `${material.form_name} · ${material.source_type} · 原纯度 ${finePercent(material.purity)} · 直接培养 +${finePercent(material.direct_gain)} · 两份提纯后 +${finePercent(material.purified_gain)}`;
    const target = document.createElement('select'); target.setAttribute('aria-label', '选择培养属性');
    const statNames = {might:'威能', guard:'防护', mobility:'身法', sense:'神识', sustain:'续航', breach:'破法'};
    Object.entries(statNames).forEach(([id, name]) => {
      const option = document.createElement('option'); option.value = id;
      const progress = Number(material.stat_progress?.[id] || 0);
      option.textContent = `培养${name}（${percent(progress)}${progress >= 1 ? '·已圆满' : ''}）`;
      option.disabled = progress >= 1; target.appendChild(option);
    });
    const tools = document.createElement('div'); tools.className = 'transformation-form-tools';
    const absorb = document.createElement('button'); absorb.textContent = '炼化'; absorb.dataset.available = material.can_improve ? '1' : '0';
    absorb.disabled = !material.can_improve || busy || !!game.pending_event || !game.player.alive;
    absorb.onclick = () => mutate(`/api/games/${game.id}/transformation-absorb`, {item_id:material.id, stat_id:target.value});
    const purify = document.createElement('button'); purify.textContent = '两份合炼提纯'; purify.dataset.available = material.can_purify ? '1' : '0';
    purify.disabled = !material.can_purify || busy || !!game.pending_event || !game.player.alive;
    purify.onclick = () => mutate(`/api/games/${game.id}/transformation-purify`, {item_id:material.id, stat_id:target.value});
    tools.append(absorb, purify); row.append(title, detail, target, tools); materials.appendChild(row);
  });
  if (!materials.children.length) materials.innerHTML = '<p class="empty">行囊中没有真灵之血、精魄或元神。</p>';
  const stored = $('#transformation-stored'); stored.innerHTML = '';
  (system.stored || []).forEach(form => stored.appendChild(transformationFormCard(form, system, true)));
  if (!stored.children.length) stored.innerHTML = '<p class="empty">当前功法尚未存入任何变身。</p>';
  const known = $('#transformation-known'); known.innerHTML = '';
  (system.known || []).forEach(form => known.appendChild(transformationFormCard(form, system, false)));
  if (!known.children.length) known.innerHTML = '<p class="empty">没有等待存入的已悟变身。</p>';
}

function transformationFormCard(form, system, isStored) {
  const row = document.createElement('div'); row.className = `transformation-form${form.active ? ' active' : ''}`;
  const title = document.createElement('b');
  title.textContent = `${form.name} · ${form.realm_name} · 属性圆满度 ${percent(form.completion)} · 距离满属性 ${percent(form.remaining)}${form.active ? ` · 权重 ${percent(form.weight)}` : ''}`;
  const progress = document.createElement('div'); progress.className = 'transformation-progress'; progress.title = `距离满属性还有 ${percent(form.remaining)}`;
  const progressFill = document.createElement('i'); progressFill.style.width = `${Math.max(0, Math.min(100, Number(form.completion) * 100))}%`; progress.appendChild(progressFill);
  const stats = (form.stats || []).map(stat => `${stat.name}${percent(stat.progress)}·×${Number(stat.multiplier).toFixed(2)}/上限${Number(stat.cap).toFixed(2)}`).join(' · ');
  const detail = document.createElement('small'); detail.textContent = `${form.description} 当前生效：${stats}`;
  const traits = document.createElement('small'); traits.textContent = (form.traits || []).length
    ? `特质：${form.traits.map(trait => `${trait.unlocked ? '已解锁' : `需${percent(trait.required_purity)}`}·${trait.name}`).join('；')}` : '无独立特质';
  const tools = document.createElement('div'); tools.className = 'transformation-form-tools';
  const addButton = (label, action, disabled = false) => {
    const button = document.createElement('button'); button.textContent = label;
    button.dataset.available = disabled ? '0' : '1';
    button.disabled = disabled || busy || !!game.pending_event || !game.player.alive;
    button.onclick = () => mutate(`/api/games/${game.id}/transformation`, {form_id:form.id, action});
    tools.appendChild(button);
  };
  if (!isStored) {
    addButton('存入', 'store', (system.stored?.length || 0) >= system.capacity);
  } else if (form.active) {
    addButton('提高权重', 'promote', form.active_order <= 1);
    addButton('降低权重', 'demote', form.active_order >= (system.active?.length || 0));
    addButton('停用', 'deactivate');
    addButton('移除', 'remove');
  } else {
    addButton('启用', 'activate', (system.active?.length || 0) >= system.space);
    addButton('移除', 'remove');
  }
  row.append(title, progress, detail, traits, tools);
  return row;
}

function renderSettings(settings) {
  const popup = $('#setting-combat-popup');
  const achievementPopup = $('#setting-achievement-popup');
  const autoWar = $('#setting-auto-war');
  if (popup) popup.checked = settings.combat_popup === false;
  if (achievementPopup) achievementPopup.checked = settings.achievement_popup === false;
  if (autoWar) autoWar.checked = !!settings.auto_advance_player_wars;
}

function renderRelationships(master, disciples, requests, inventory, techniques) {
  const list = $('#relationship-list'); list.innerHTML = '';
  const append = (role, person) => {
    const row = document.createElement('div'); row.className = 'relationship-row';
    if (!person.alive) row.classList.add('fallen');
    const name = document.createElement('b'); name.textContent = `${role} · ${person.name}${person.alive ? '' : '（已故）'}`;
    const detail = document.createElement('small');
    detail.textContent = `${person.realm_name} · ${person.path_name || '道统未明'} · ${person.spirit_root_name || '灵根未明'} · ${person.age} 岁 / 寿元 ${person.lifespan == null ? '无尽' : person.lifespan} · ${person.source === 'event' ? '游历结缘' : '宗门结缘'}`;
    row.append(name, detail);
    if (role === '师父' && person.alive) row.appendChild(masterActions(person));
    if (role === '弟子' && person.alive) row.appendChild(discipleActions(person));
    list.appendChild(row);
  };
  if (master) append('师父', master);
  disciples.forEach(person => append('弟子', person));
  requests.forEach(person => {
    const row = document.createElement('div'); row.className = 'relationship-row pending-request';
    const name = document.createElement('b'); name.textContent = `待决拜师帖 · ${person.name}`;
    const detail = document.createElement('small'); detail.textContent = `${person.realm_name} · ${person.spirit_root_name || '灵根未明'} · ${person.age} 岁 / 寿元 ${person.lifespan}`;
    const actions = document.createElement('div'); actions.className = 'relationship-tools';
    actions.append(
      interactionButton('收入门下', '1', () => mutate(`/api/games/${game.id}/disciple-request`, {request_id:person.id, accept:true})),
      interactionButton('婉拒', '1', () => mutate(`/api/games/${game.id}/disciple-request`, {request_id:person.id, accept:false})),
    );
    row.append(name, detail, actions); list.appendChild(row);
  });
  if (!master && !disciples.length && !requests.length) list.innerHTML = '<p class="empty">尚无师徒缘分；可通过事件或宗门名单结缘。</p>';

  function masterActions(person) {
    const actions = document.createElement('div'); actions.className = 'relationship-tools';
    const requested = person.last_requests || {};
    actions.append(
      interactionButton('索要物品', requested.item === worldClock() ? '0' : '1', () => mutate(`/api/games/${game.id}/master-request`, {kind:'item'})),
      interactionButton('请教功法', requested.technique === worldClock() ? '0' : '1', () => mutate(`/api/games/${game.id}/master-request`, {kind:'technique'})),
    );
    if (person.can_invite_faction) actions.appendChild(interactionButton('引荐入宗', '1', () => mutate(`/api/games/${game.id}/relationship-faction`, {npc_id:person.id})));
    if (game.player.path === 'demonic') actions.appendChild(interactionButton('尝试生擒师父', '1', () => mutate(`/api/games/${game.id}/relationship-capture`, {kind:'master'}), 'danger'));
    actions.appendChild(interactionButton('脱离师门', '1', () => mutate(`/api/games/${game.id}/relationship-exit`, {kind:'master', npc_id:person.id}), 'danger'));
    return actions;
  }

  function discipleActions(person) {
    const tools = document.createElement('div'); tools.className = 'disciple-gifts';
    const itemSelect = optionSelect(inventory.filter(item => item.quantity > 0), item => item.id, item => `${item.name} ×${item.quantity}`, '无物可赠');
    const itemButton = interactionButton('赠物', itemSelect.dataset.available, () => mutate(`/api/games/${game.id}/disciple-gift`, {disciple_id:person.id, kind:'item', content_id:itemSelect.value}));
    const taught = new Set(person.techniques || []);
    const availableTechniques = techniques.filter(art => !taught.has(art.id));
    const techniqueSelect = optionSelect(availableTechniques, art => art.id, art => art.name, '无新法可传');
    const techniqueButton = interactionButton('传功', techniqueSelect.dataset.available, () => mutate(`/api/games/${game.id}/disciple-gift`, {disciple_id:person.id, kind:'technique', content_id:techniqueSelect.value}));
    tools.append(itemSelect, itemButton, techniqueSelect, techniqueButton);
    if (game.player.path === 'demonic') {
      tools.append(
        interactionButton('炼为尸傀', '1', () => mutate(`/api/games/${game.id}/captive-action`, {target_id:person.id, action:'corpse'}), 'danger'),
        interactionButton('种下傀印', '1', () => mutate(`/api/games/${game.id}/captive-action`, {target_id:person.id, action:'living'})),
      );
    }
    tools.appendChild(interactionButton('逐出门下', '1', () => mutate(`/api/games/${game.id}/relationship-exit`, {kind:'disciple', npc_id:person.id}), 'danger'));
    return tools;
  }

  function optionSelect(values, getValue, getLabel, emptyLabel) {
    const select = document.createElement('select'); select.className = 'relationship-select';
    select.dataset.available = values.length ? '1' : '0'; select.disabled = !values.length;
    if (!values.length) {
      const option = document.createElement('option'); option.textContent = emptyLabel; select.appendChild(option);
    } else values.forEach(value => {
      const option = document.createElement('option'); option.value = getValue(value); option.textContent = getLabel(value); select.appendChild(option);
    });
    return select;
  }

  function interactionButton(label, available, handler, tone = '') {
    const button = document.createElement('button'); button.className = 'relationship-interaction';
    if (tone) button.classList.add(tone);
    button.textContent = label; button.dataset.available = available; button.disabled = available !== '1'; button.onclick = handler;
    return button;
  }
}

function renderDaoCompanion(companion, inventory, techniques, conceptionBonus = 0) {
  const list = $('#dao-companion-list'); list.innerHTML = '';
  if (!companion) {
    list.innerHTML = '<p class="empty">尚无道侣；可在事件、宗门名单或世界人物中结缘。</p>';
    return;
  }
  const row = document.createElement('div'); row.className = `companion-row${companion.alive ? '' : ' fallen'}`;
  const same = companion.same_cultivation ? ` · 同法同境，突破 +${percent(companion.breakthrough_bonus)}` : '';
  row.innerHTML = `<b>${companion.name}${companion.alive ? '' : '（已故）'}</b><small>${companion.realm_name} · ${companion.spirit_root_name} · ${companion.age} 岁 / 寿元 ${companion.lifespan == null ? '无尽' : companion.lifespan}</small><small>战力 ${number(companion.combat_power || 0)} · 主修《${companion.main_technique_name}》 · 好感 ${number(companion.affinity || 0)}${same}</small>`;
  if (conceptionBonus > 0) {
    const medicine = document.createElement('small'); medicine.className = 'positive';
    medicine.textContent = `孕育药力：下一次缠绵的后代概率 +${percent(conceptionBonus)}`;
    row.appendChild(medicine);
  }
  if (companion.alive && companion.world === game.player.world) {
    const actions = document.createElement('div'); actions.className = 'companion-tools';
    const last = companion.last_interactions || {};
    actions.append(
      companionButton(companion.in_party ? '暂离队伍' : '邀请同行', companion.in_party || companion.can_invite_party ? '1' : '0', {party_action:companion.in_party ? 'leave' : 'invite'}),
      companionButton('亲密交谈', last.intimacy === worldClock() ? '0' : '1', {action:'intimacy'}),
      companionButton('缠绵共参', last.entwine === worldClock() ? '0' : '1', {action:'entwine'}),
      companionButton('索要物品', last.request_item === worldClock() ? '0' : '1', {action:'request_item'}),
      companionButton('索要功法', last.request_technique === worldClock() ? '0' : '1', {action:'request_technique'}),
    );
    if (companion.can_invite_faction) actions.appendChild(companionButton('引荐入宗', '1', {faction_invite:true}));
    if (game.player.path === 'demonic') {
      const capture = companionButton('尝试生擒道侣', '1', null, 'danger');
      capture.onclick = () => mutate(`/api/games/${game.id}/relationship-capture`, {kind:'companion'}); actions.appendChild(capture);
    }
    actions.appendChild(companionButton('解除道侣', '1', {relationship_exit:'companion'}, 'danger'));
    const giftSelect = companionSelect(inventory.filter(item => item.quantity > 0), item => item.id, item => `${item.name} ×${item.quantity}`, '无物可赠');
    const gift = companionButton('赠送物品', giftSelect.dataset.available, null);
    gift.onclick = () => mutate(`/api/games/${game.id}/dao-companion`, {action:'gift_item', content_id:giftSelect.value});
    const techniqueSelect = companionSelect(techniques, art => art.id, art => art.name, '无功法可传');
    const teach = companionButton('替换其主修', techniqueSelect.dataset.available, null);
    teach.onclick = () => mutate(`/api/games/${game.id}/dao-companion`, {action:'teach_technique', content_id:techniqueSelect.value});
    actions.append(giftSelect, gift, techniqueSelect, teach); row.appendChild(actions);
  }
  list.appendChild(row);

  function companionButton(label, available, payload, tone = '') {
    const button = document.createElement('button'); button.className = 'companion-action'; button.textContent = label;
    if (tone) button.classList.add(tone);
    button.dataset.available = available; button.disabled = available !== '1';
    if (payload?.party_action) button.onclick = () => mutate(`/api/games/${game.id}/party`, {npc_id:companion.id, action:payload.party_action});
    else if (payload?.faction_invite) button.onclick = () => mutate(`/api/games/${game.id}/relationship-faction`, {npc_id:companion.id});
    else if (payload?.relationship_exit) button.onclick = () => mutate(`/api/games/${game.id}/relationship-exit`, {kind:payload.relationship_exit, npc_id:companion.id});
    else if (payload) button.onclick = () => mutate(`/api/games/${game.id}/dao-companion`, payload);
    return button;
  }
  function companionSelect(values, getValue, getLabel, emptyLabel) {
    const select = document.createElement('select'); select.className = 'companion-select';
    select.dataset.available = values.length ? '1' : '0'; select.disabled = !values.length;
    if (!values.length) {
      const option = document.createElement('option'); option.textContent = emptyLabel; select.appendChild(option);
    } else values.forEach(value => {
      const option = document.createElement('option'); option.value = getValue(value); option.textContent = getLabel(value); select.appendChild(option);
    });
    return select;
  }
}

function renderDaoFriends(friends) {
  const list = $('#dao-friend-list'); list.innerHTML = '';
  if (!friends.length) { list.innerHTML = '<p class="empty">尚无道友；与高好感修士结交后可切磋论道。</p>'; return; }
  friends.forEach(friend => {
    const row = document.createElement('div'); row.className = `friend-row${friend.alive ? '' : ' fallen'}`;
    const status = friend.alive ? (friend.world === game.player.world ? '' : ` · 身在${friend.world === 'spirit' ? '灵界' : '人界'}`) : ` · ${friend.death_reason || '已经陨落'}`;
    row.innerHTML = `<b>${friend.name}${friend.alive ? '' : '（已故）'}</b><small>${friend.realm_name} · ${friend.spirit_root_name || '灵根未明'} · ${friend.age} 岁 / 寿元 ${friend.lifespan == null ? '无尽' : friend.lifespan}${status}</small><small>战力 ${number(friend.combat_power)} · 主修《${friend.main_technique_name}》 · 好感 ${number(friend.affinity || 0)}</small>`;
    if (friend.alive && friend.world === game.player.world) {
      const tools = document.createElement('div'); tools.className = 'friend-tools';
      const last = friend.last_interactions || {};
      const add = (label, action, available = true) => {
        const button = document.createElement('button'); button.className = 'friend-action'; button.textContent = label; button.dataset.available = available ? '1' : '0';
        button.onclick = () => action === 'party'
          ? mutate(`/api/games/${game.id}/party`, {npc_id:friend.id, action:friend.in_party ? 'leave' : 'invite'})
          : action === 'faction' ? mutate(`/api/games/${game.id}/relationship-faction`, {npc_id:friend.id})
          : action === 'exit' ? mutate(`/api/games/${game.id}/relationship-exit`, {kind:'friend', npc_id:friend.id})
          : mutate(`/api/games/${game.id}/dao-friend`, {npc_id:friend.id, action});
        tools.appendChild(button);
      };
      add(friend.in_party ? '暂离队伍' : '邀请同行', 'party', friend.in_party || friend.can_invite_party);
      add('点到切磋', 'spar', last.spar !== worldClock());
      add('交流心得', 'discuss', last.discuss !== worldClock());
      if (friend.can_invite_faction) add('引荐入宗', 'faction');
      if (game.player.path === 'demonic') {
        const capture = document.createElement('button'); capture.className = 'friend-action danger'; capture.textContent = '尝试生擒';
        capture.dataset.available = last.capture_attempt === worldClock() ? '0' : '1';
        capture.onclick = () => mutate(`/api/games/${game.id}/relationship-capture`, {kind:'friend', target_id:friend.id});
        tools.appendChild(capture);
      }
      add('解除道友', 'exit');
      row.appendChild(tools);
    }
    list.appendChild(row);
  });
}

function renderPersonalRelations(relations) {
  const renderList = (selector, people, emptyText) => {
    const list = $(selector); list.innerHTML = '';
    if (!people.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = emptyText; list.appendChild(empty); return; }
    people.forEach(person => {
      const row = document.createElement('div'); row.className = `affinity-row ${person.affinity < 0 ? 'hostile' : 'friendly'}`;
      const name = document.createElement('b'); name.textContent = `${person.name} · ${person.relationship}`;
      const detail = document.createElement('small'); detail.textContent = `${person.realm_name} · 好感 ${number(person.affinity)} / ${person.attitude}${person.faction_name ? ` · ${person.faction_name}` : ''}`;
      row.append(name,detail); list.appendChild(row);
    });
  };
  renderList('#high-affinity-list', relations.high || [], '暂无达到“颇有好感”的人物。');
  renderList('#low-affinity-list', relations.low || [], '暂无明确敌视你的人物。');
}

function renderHistory(history) {
  const list = $('#history-list'); list.innerHTML = '';
  history.forEach(record => {
    const tags = new Set(record.tags || []);
    const categories = [];
    if (tags.has('dao_companion') || tags.has('companion')) categories.push('companion');
    if (tags.has('friend')) categories.push('friend');
    if (tags.has('master') || tags.has('disciple')) categories.push('mentor');
    if (tags.has('faction')) categories.push('faction');
    if (tags.has('race')) categories.push('race');
    if (!categories.length && (tags.has('npc') || tags.has('world_npc') || tags.has('duel') || tags.has('diplomacy') || tags.has('revenge') || tags.has('personal_affinity'))) categories.push('other');
    if (!categories.length) categories.push('self');
    const priority = ['companion', 'friend', 'mentor', 'faction', 'race', 'other', 'self'];
    const primary = priority.find(category => categories.includes(category)) || 'self';
    if (!historyFilters.has(primary)) return;
    const row = document.createElement('div'); row.className = `record record-${primary}`;
    const year = document.createElement('div'); year.className = 'year'; year.textContent = timelineText(record.age);
    const story = document.createElement('div'); story.className = 'story';
    const title = document.createElement('h3'); title.textContent = record.title;
    const summary = document.createElement('p'); summary.textContent = record.summary;
    story.append(title, summary); row.append(year, story); list.appendChild(row);
  });
  if (!list.children.length) list.innerHTML = '<p class="empty">当前筛选下暂无可见纪事。</p>';
}

function renderBattleReport(report) {
  const card = $('#battle-report-card');
  card.classList.toggle('hidden', !report);
  if (!report) {
    if (battlePlaybackKey === null) battlePlaybackKey = 'none';
    return;
  }
  const reportKey = `${report.age}:${report.title}:${report.result}:${report.rounds?.length || 0}`;
  const shouldPlay = battlePlaybackKey !== null && battlePlaybackKey !== reportKey;
  battlePlaybackKey = reportKey;
  if (shouldPlay) battleReportOpen = game?.settings?.combat_popup !== false;
  card.classList.toggle('report-closed', !battleReportOpen);
  const objectiveNames = {kill:'击杀', capture:'生擒', repel:'击退'};
  const resultNames = {killed:'目标击杀', captured:'目标生擒', victory:'目标达成', victory_escape:'敌方逃脱', defeat:'未达目标', defeat_survived:'涅槃生还', dead:'身死'};
  $('#battle-report-title').textContent = report.title || '最近战报';
  $('#battle-report-grade').textContent = `${report.result_grade || '结算'} · ${resultNames[report.result] || report.result || ''}`;
  const natural = report.natural_terrain || report.battlefield_tags?.[0] || '开阔';
  const artificial = report.artificial_conditions?.length
    ? report.artificial_conditions.join('、') : '无';
  $('#battle-report-summary').textContent = `${report.mode || '标准自动战斗'} · 目标 ${objectiveNames[report.objective] || report.objective} · 战前判断 ${report.assessment || '未知'} · 共 ${report.rounds?.length || 0} 轮 · 自然场地 ${natural} · 人工条件 ${artificial}。开战后完全由预案自动执行。`;
  const rosters = $('#battle-rosters'); rosters.innerHTML = '';
  [
    ['你方参战', report.player_roster || []],
    ['敌方参战', report.enemy_roster || []],
  ].forEach(([label, units]) => {
    const group = document.createElement('section');
    const heading = document.createElement('b'); heading.textContent = label; group.appendChild(heading);
    units.forEach(unit => {
      const chip = document.createElement('span');
      const committed = Number(unit.engaged_power ?? unit.power);
      const full = Number(unit.power);
      const partial = committed + 0.5 < full;
      chip.textContent = `${unit.name} · ${unit.kind_name || '战斗单位'} · 总战力 ${number(full)}${partial ? ` · 本线投入 ${percent(unit.commitment)}` : ''}`;
      chip.title = partial
        ? `${unit.name}完整战斗力 ${number(full)}；因牵制其他敌人、维持阵法或承受别处攻势，本战线实际投入 ${number(committed)}`
        : `${unit.name}以完整战斗力 ${number(full)} 参与本战线`;
      group.appendChild(chip);
    });
    rosters.appendChild(group);
  });
  renderBattleRoundProgress(report, shouldPlay);

  const keyList = $('#battle-key-events'); keyList.innerHTML = '';
  (report.key_events || []).forEach(text => {
    const row = document.createElement('p'); row.textContent = text; keyList.appendChild(row);
  });

  const stats = $('#battle-stat-grid'); stats.innerHTML = '';
  (report.stat_comparison || []).forEach(stat => {
    const row = document.createElement('div');
    const name = document.createElement('b'); name.textContent = stat.name;
    const values = document.createElement('span'); values.textContent = `你 ${number(stat.player)} / 敌 ${number(stat.enemy)}`;
    const meter = document.createElement('i');
    const share = Number(stat.player) / Math.max(1, Number(stat.player) + Number(stat.enemy));
    meter.style.setProperty('--battle-share', `${Math.max(5, Math.min(95, share * 100))}%`);
    row.append(name, values, meter); stats.appendChild(row);
  });

  const rounds = $('#battle-round-list'); rounds.innerHTML = '';
  (report.rounds || []).forEach(round => {
    const block = document.createElement('section');
    const title = document.createElement('b'); title.textContent = `第 ${round.round} 轮 · ${round.initiative === 'player' ? '你方先手' : '敌方先手'}`;
    block.appendChild(title);
    (round.events || []).forEach(text => { const event = document.createElement('p'); event.textContent = text; block.appendChild(event); });
    const state = document.createElement('small');
    state.textContent = `你方战斗态势 ${number(round.player_combat_state)}/${number(round.player_combat_state_max)} · 敌方 ${number(round.enemy_combat_state)}/${number(round.enemy_combat_state_max)} · MP ${percent(round.player_mp_ratio)} · 双方战意 ${number(round.player_morale)}/${number(round.enemy_morale)}`;
    block.appendChild(state); rounds.appendChild(block);
  });
}

function renderBattleRoundProgress(report, shouldPlay) {
  if (battlePlaybackTimer) { clearInterval(battlePlaybackTimer); battlePlaybackTimer = null; }
  const container = $('#battle-round-progress'); container.innerHTML = '';
  const rounds = report.rounds || [];
  // Only draw rounds that actually belong to this battle.  Quick resolutions
  // often end in one round; placeholder circles made a finished fight look stuck.
  const nodeCount = Math.max(1, Math.min(8, rounds.length));
  const nodes = [];
  for (let index = 0; index < nodeCount; index += 1) {
    if (index) { const line = document.createElement('i'); line.textContent = '—'; container.appendChild(line); }
    const node = document.createElement('span');
    node.setAttribute('role', 'img'); node.setAttribute('tabindex', '0');
    container.appendChild(node); nodes.push(node);
  }
  const advantage = report.assessment === '碾压' || report.assessment === '优势'
    ? '你方' : report.assessment === '劣势' || report.assessment === '绝境' ? '敌方' : '双方均有机会';
  const paint = current => nodes.forEach((node, index) => {
    const round = rounds[index];
    const finished = index < current;
    const active = index === current && current < rounds.length;
    node.className = finished ? 'complete' : active ? 'active' : 'future';
    node.textContent = finished ? '●' : active ? '◎' : '○';
    node.title = finished && round
      ? `第 ${index + 1} 轮：${round.events?.join(' ') || '该轮已经结束'}${index === rounds.length - 1 ? ' 战斗于本轮结束。' : ''}`
      : active ? `当前第 ${index + 1} 轮正在发生，预计${advantage}取得优势`
      : '当前阶段尚未发生';
    node.setAttribute('aria-label', node.title);
  });
  if (!shouldPlay) { paint(rounds.length); return; }
  let current = 0; paint(current);
  battlePlaybackTimer = setInterval(() => {
    current += 1; paint(current);
    if (current >= rounds.length) { clearInterval(battlePlaybackTimer); battlePlaybackTimer = null; }
  }, 520);
}

function renderEvent() {
  const event = game.pending_event;
  const postBattlePossession = event?.id === 'SYS_POST_BATTLE_POSSESSION';
  $('#event-card').classList.toggle('hidden', !event || postBattlePossession);
  $('#action-card').classList.toggle('hidden', !!event || !game.player.alive);
  const choices = $('#event-choices'); choices.innerHTML = '';
  if (!event || postBattlePossession) return;
  $('#event-title').textContent = event.title;
  $('#event-body').textContent = `${event.body}${game.trial?.active ? `（当前第 ${game.trial.step}/${game.trial.total_steps} 关）` : ''}`;
  event.choices.forEach(choice => {
    const button = document.createElement('button');
    button.textContent = choice.enabled === false ? `${choice.text}（${choice.disabled_reason || '条件不满足'}）` : choice.text;
    button.disabled = choice.enabled === false;
    button.onclick = () => mutate(`/api/games/${game.id}/choice`, {choice_id:choice.id}); choices.appendChild(button);
  });
}

function renderButtons() {
  document.querySelectorAll('[data-action]').forEach(button => {
    const mortalCommission = button.dataset.action === 'commission' && game?.player?.realm_index === 0;
    const mortalCombat = ['hunt_beast', 'spar', 'slay', 'capture'].includes(button.dataset.action) && game?.player?.realm_index === 0;
    const adaptingToImmortalPower = game?.player?.world === 'celestial' && !game?.player?.immortal_power?.converted;
    const blockedDuringAdaptation = adaptingToImmortalPower && !['cultivate', 'rest', 'commission'].includes(button.dataset.action);
    const controlledGhost = game?.ghost_system?.phase_two?.state === 'controlled' && !['cultivate', 'rest'].includes(button.dataset.action);
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment || mortalCommission || mortalCombat || blockedDuringAdaptation || controlledGhost;
  });
  document.querySelectorAll('#event-choices button').forEach(button => {
    const index = [...button.parentNode.children].indexOf(button);
    const choice = game?.pending_event?.choices?.[index];
    button.disabled = busy || !choice || choice.enabled === false;
  });
  $('#new-game-button').disabled = busy;
  document.querySelectorAll('.reward-choice').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !game?.faction?.fixed_reward_unlocked;
  });
  document.querySelectorAll('[data-dispatch]').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || game?.faction?.dispatch_used || (game?.faction?.contribution || 0) < (game?.faction?.dispatch_cost || 0);
  });
  document.querySelectorAll('.market-buy').forEach(button => {
    const offer = [...(game?.market?.offers || []), ...(game?.market?.crafting_material_offers || [])].find(entry => entry.id === button.dataset.offerId);
    button.disabled = busy || !game?.player?.alive || !!game?.pending_event || !offer || offer.sold || offer.owned || game.market.spirit_stones < offer.price;
  });
  document.querySelectorAll('#auction-card button, #auction-card input, #auction-card select').forEach(control => {
    if (control.id !== 'auction-toggle') control.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || control.dataset.auctionUnavailable === '1';
  });
  document.querySelectorAll('#spirit-field-card button, #spirit-field-card select, #market-plant-sellables button').forEach(control => {
    if (control.id !== 'spirit-field-toggle') control.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || control.dataset.actionUnavailable === '1';
  });
  document.querySelectorAll('.technique-equip').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || button.dataset.compatible !== '1';
  });
  document.querySelectorAll('.transformation-form-tools button').forEach(button => {
    button.disabled = button.dataset.available === '0' || busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  });
  document.querySelectorAll('.bloodline-evolve').forEach(button => {
    button.disabled = button.dataset.available !== '1' || busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  });
  document.querySelectorAll('.item-use').forEach(button => {
    button.disabled = button.dataset.itemUnavailable === '1' || busy || !game?.player.alive || (!!game?.pending_event && button.dataset.allowDuringTrial !== '1');
  });
  document.querySelectorAll('.relationship-action').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event;
  });
  document.querySelectorAll('.relationship-exit').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  });
  document.querySelectorAll('.party-action').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment || button.dataset.available === '0';
  });
  document.querySelectorAll('.companion-action').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment || button.dataset.available === '0';
  });
  document.querySelectorAll('.friend-action').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment || button.dataset.available === '0';
  });
  document.querySelectorAll('.companion-select').forEach(select => {
    select.disabled = busy || !game?.player.alive || !!game?.pending_event || select.dataset.available !== '1';
  });
  ['#prison-endure', '#prison-escape'].forEach(selector => {
    $(selector).disabled = busy || !game?.player.alive || !game?.imprisonment || !!game?.pending_event;
  });
  document.querySelectorAll('.relationship-interaction').forEach(button => {
    button.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment || button.dataset.available !== '1';
  });
  document.querySelectorAll('.relationship-select').forEach(select => {
    select.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment || select.dataset.available !== '1';
  });
  document.querySelectorAll('.governance-form input, .governance-form select, .governance-form button').forEach(control => {
    control.disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  });
  document.querySelectorAll('#heavenly-court-card button, #heavenly-court-card select, #heavenly-court-card input').forEach(control => {
    if (control.id !== 'heavenly-court-toggle') control.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || control.dataset.courtUnavailable === '1';
  });
  document.querySelectorAll('#natal-artifact-card button').forEach(control => {
    if (control.id !== 'natal-artifact-toggle') control.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || control.dataset.natalUnavailable === '1';
  });
  document.querySelectorAll('#crafting-card button, #crafting-card input, #crafting-card select').forEach(control => {
    if (control.id !== 'crafting-toggle') control.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || control.dataset.craftingUnavailable === '1';
  });
  $('#spirit-crossing-action').disabled = busy || !game?.player.alive || !!game?.pending_event;
  $('#cross-world-action').disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  $('#cross-world-secondary-action').disabled = busy || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  $('#breakthrough-action').disabled = busy || !game?.breakthrough?.enabled || !!game?.pending_event;
  $('#body-breakthrough-action').disabled = busy || !game?.body_cultivation?.ready || !!game?.pending_event || !!game?.imprisonment;
  $('#ghost-wangsheng-action').disabled = busy || !game?.ghost_system?.can_spend_wangsheng;
  $('#ghost-wangsheng-all-action').disabled = busy || !game?.ghost_system?.can_spend_wangsheng;
  $('#ghost-reincarnate-action').disabled = busy || !game?.ghost_system?.can_reincarnate;
  document.querySelectorAll('.map-travel').forEach(button => {
    button.disabled = busy || button.dataset.unavailable === '1' || !game?.player.alive || !!game?.pending_event || !!game?.imprisonment;
  });
  const bodyTrain = $('#body-train-action');
  if (bodyTrain) bodyTrain.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || !game?.body_cultivation?.technique || game?.body_cultivation?.ready || game?.body_cultivation?.layer >= game?.body_cultivation?.max_layer;
  const senseTrain = $('#sense-train-action');
  if (senseTrain) senseTrain.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || !game?.player?.divine_sense?.technique;
  const senseBreakthrough = $('#sense-breakthrough-action');
  if (senseBreakthrough) senseBreakthrough.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || !game?.player?.divine_sense?.breakthrough_ready;
  document.querySelectorAll('.captive-tools button, .puppet-tools button').forEach(button => {
    button.disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment;
  });
  document.querySelectorAll('.ghost-attachment-action').forEach(button => {
    button.disabled = busy || !game?.player?.alive || button.dataset.available !== '1';
  });
  const demonic = game?.demonic_system || {};
  $('#craft-puppet').disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || (demonic.used || 0) >= (demonic.capacity || 0);
  $('#refine-souls').disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || !demonic.is_demonic || !(demonic.foreign_souls || []).some(soul => !soul.refined);
  $('#secluded-refine-souls').disabled = busy || !game?.player?.alive || !!game?.pending_event || !!game?.imprisonment || !demonic.is_demonic || !(demonic.foreign_souls || []).some(soul => !soul.refined);
  $('#world-news-debug').disabled = busy || !game;
  document.querySelectorAll('.strategy-dock button, .utility-panel .panel-heading button, #faction-toggle, #market-toggle').forEach(button => button.disabled = busy);
  $('#restart-button').disabled = busy;
  document.querySelectorAll('.post-battle-possession-choice').forEach(button => button.disabled = busy);
  document.querySelectorAll('#new-game-form button, #save-list button, .quick-start-button').forEach(button => {
    const preset = configData?.quick_starts?.find(entry => entry.id === button.dataset.presetId);
    button.disabled = busy || (preset ? !preset.enabled : false);
  });
}

function number(value) { return Math.round(Number(value)).toLocaleString('zh-CN'); }
function formatDecimal(value) { return Number(value || 0).toLocaleString('zh-CN', {maximumFractionDigits: 2}); }
function percent(value) { return `${Math.round(Number(value) * 100)}%`; }
function precisePercent(value) { return `${(Number(value || 0) * 100).toFixed(2)}%`; }
function finePercent(value) {
  const amount = Number(value) * 100;
  return `${amount < 1 ? amount.toFixed(2) : amount.toFixed(1)}%`;
}

$('#setting-combat-popup').onchange = event => mutate(`/api/games/${game.id}/settings`, {
  setting:'combat_popup', enabled:!event.target.checked,
});
$('#setting-achievement-popup').onchange = event => mutate(`/api/games/${game.id}/settings`, {
  setting:'achievement_popup', enabled:!event.target.checked,
});
$('#setting-auto-war').onchange = event => mutate(`/api/games/${game.id}/settings`, {
  setting:'auto_advance_player_wars', enabled:event.target.checked,
});

$('#battle-report-toggle').onclick = () => {
  battleReportOpen = false;
  $('#battle-report-card').classList.add('report-closed');
};
$('#battle-report-open').onclick = () => {
  if (!game?.last_combat_report) { toast('尚无战报'); return; }
  battleReportOpen = true;
  $('#battle-report-card').classList.remove('report-closed');
};
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    battleReportOpen = false;
    $('#battle-report-card').classList.add('report-closed');
  }
});

boot().catch(error => toast(error.message));
