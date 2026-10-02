(() => {
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const fmt = n => Number(n || 0).toLocaleString('zh-CN');
  let owner, selected = 'seats';
  function render(game, act, root) {
    const d = game.upper_institution, c = d.court;
    if (owner !== game.id) { owner = game.id; selected = 'seats'; }
    root.classList.add('asura-court');
    const blocked = !d.local || !!game.pending_event || !!game.trial?.active || !game.player.alive || !!game.imprisonment;
    const button = (label, action, target = '', disabled = false) => {
      const b = node('button', label, 'court-button'); b.type = 'button'; b.disabled = blocked || disabled;
      b.onclick = () => act({action, target_id: target}); return b;
    };
    const note = text => node('p', text, 'court-note');
    const box = (title, description) => { const n = node('section', null, 'court-box'); n.append(node('h3', title)); if (description) n.append(node('p', description, 'court-description')); return n; };
    const grid = () => node('div', null, 'court-grid');
    const sovereign = c.seats.find(r => r.rank === 5);
    const hero = node('header', null, 'court-hero'), seal = node('div', '王', 'court-seal'), heading = node('div');
    seal.setAttribute('aria-hidden', 'true');
    heading.append(node('small', '万战魔城 · 修罗王庭', 'court-eyebrow'), node('h3', sovereign.present ? `${sovereign.name}执掌王庭` : '王座虚悬'), node('p', d.joined ? `你的爵位 · ${d.ranks[d.rank]}${c.king ? ' · 王权在握' : ''}` : '立功受爵，血战易位。'));
    hero.append(seal, heading); root.append(hero);
    const metrics = node('div', null, 'court-metrics');
    [['府库灵石', fmt(d.treasury)], ['可用功勋', fmt(d.merit)], ['民心', `${c.public_support}/100`], ['王庭政历', `${d.unit} 单位`]].forEach(([label, value]) => { const m = node('div'); m.append(node('small', label), node('strong', value)); metrics.append(m); });
    root.append(metrics);
    if (!d.local) root.append(note('前往万战魔城办理王庭事务；离界后保留爵位和进度。'));
    if (!d.joined) root.append(button('登记效力', 'join'), note('加入王庭保留原有宗门身份，所有王庭玩法均属于本体。'));
    if (c.challenge) {
      const alert = box(`${c.challenge.name}向你发起换位血战`, `最迟第 ${c.challenge.deadline} 单位回王庭回应；逾期按主动让位处理。双方负伤换位，保留性命。`);
      alert.classList.add('court-challenge'); alert.append(button('接受血战', 'answer_duel', c.challenge.npc_id), button('承认挑战并让位', 'yield_duel', c.challenge.npc_id)); root.append(alert);
    }
    const tabs = node('nav', null, 'court-tabs'); tabs.setAttribute('aria-label', '王庭事务');
    for (const [key, label] of [['seats', '爵位'], ['policies', '政令'], ['domestic', '内政'], ['merit', '功勋'], ['history', '纪事']]) {
      const tab = node('button', label); tab.type = 'button'; tab.setAttribute('aria-pressed', String(selected === key));
      tab.onclick = () => { selected = key; root.replaceChildren(); render(game, act, root); }; tabs.append(tab);
    }
    root.append(tabs);
    const body = node('div', null, 'court-body'); root.append(body);
    if (selected === 'seats') {
      const ladder = node('div', null, 'court-ladder');
      c.seats.forEach(person => {
        const next = d.joined && person.rank === d.rank + 1;
        const row = node('section', null, `court-seat${person.player ? ' is-player' : ''}${next ? ' is-next' : ''}`);
        row.append(node('span', String(person.rank).padStart(2, '0'), 'court-seat-number'));
        const identity = node('div'); identity.append(node('small', person.title), node('strong', person.name), node('span', person.player ? '你当前的席位' : person.present ? '在位廷臣' : '席位空缺', 'court-description')); row.append(identity);
        if (next) row.append(button(person.present ? '换位血战' : '接任空缺', 'blood_duel', person.id || '', !!c.challenge || d.unit - c.last_duel < 2));
        ladder.append(row);
      }); body.append(ladder);
      if (d.joined && d.rank < 5) {
        const next = d.rank + 1, need = d.rank_merit[next];
        const promotion = box('功勋受封', `晋升${d.ranks[next]}：累计功绩 ${fmt(d.earned)}/${fmt(need)}，第 ${9 + Math.floor(next / 2)} 阶修为，恩宠 ${d.regard}/${next * 20}。受封后与在位者交换爵位。`);
        promotion.append(button('申请晋阶', 'promote', '', !!c.challenge || d.earned < need || game.player.realm_index < 9 + Math.floor(next / 2) || d.regard < next * 20)); body.append(promotion);
      }
      body.append(note(`只能逐级夺位，血战实际消耗气血、法力与魔域资源，未分胜负时不换位。主动挑战间隔两单位；换位后八单位内不受挑战。NPC 战书全局至少间隔十二单位，同一人至少二十四单位。${d.unit < c.protected_until ? `当前保护期至第 ${c.protected_until} 单位。` : ''}`));
    }
    if (selected === 'policies') {
      body.append(note(c.king ? '你可亲颁王令，无需消耗功勋。新政持续生效，直至你主动更替。' : '封侯以上、恩宠八十可奏请政令，每次消耗一百功勋；NPC 修罗王每四单位议政。'));
      body.append(note(`同一时刻实行一道王令，施行费用 ${fmt(d.policy_cost)} 府库灵石，更替间隔四单位。`));
      const cards = grid();
      d.policies.forEach(p => {
        const active = p.id === d.policy, row = box(p.name, p.description);
        if (active) row.classList.add('is-active');
        row.append(button(active ? '现行王令' : c.king ? '颁行王令' : '奏请施行', 'policy', p.id, active || !d.joined || !!c.challenge || d.unit - d.last_proposal < 4 || d.treasury < d.policy_cost || (!c.king && (d.rank < 2 || d.regard < 80 || d.merit < 100)))); cards.append(row);
      }); body.append(cards);
    }
    if (selected === 'domestic') {
      if (!c.king) body.append(note('登上修罗王位后，可以任免廷臣、营建王庭并颁布内政决策。'));
      body.append(note(`现行${d.current_policy.name} · 府库基础收入倍率 ${c.effects.revenue.toFixed(2)} · 每单位官俸 ${fmt(c.effects.wages)} · 新委托功勋倍率 ${(c.effects.service * d.current_policy.service).toFixed(2)} · 养域总减免 ${Math.round(d.discount * 100)}%。民心越高，府库收入越高。`));
      const locked = !c.king || !!c.challenge, appointments = box('王庭任命', '爵位与官职分开：一人可持爵并任一官职。任命支出六万灵石，官俸每单位三万；每单位可调整一职。忠诚越高，越不愿发起血战。');
      const officials = grid();
      c.office_definitions.forEach(office => {
        const incumbent = c.candidates.find(n => n.id === c.offices[office.id]);
        const row = box(office.name, office.description);
        row.append(node('p', incumbent ? `${incumbent.name} · 才干 ${incumbent.skills[office.id]} · 忠诚 ${incumbent.loyalty}` : '暂缺主事'));
        const select = node('select'); select.setAttribute('aria-label', `${office.name}人选`);
        select.append(new Option('选择任职人选', ''));
        c.candidates.filter(n => !Object.values(c.offices).includes(n.id)).forEach(n => select.append(new Option(`${n.name} · 才干${n.skills[office.id]} · 忠诚${n.loyalty}`, n.id)));
        select.disabled = blocked || locked;
        const appoint = button('任命', 'appoint', '', true);
        select.onchange = () => { appoint.disabled = blocked || locked || !select.value || d.unit - c.appointment_at < 1 || d.treasury < 60000; };
        appoint.onclick = () => act({action: 'appoint', target_id: `${office.id}:${select.value}`});
        row.append(select, appoint, button('免职', 'appoint', `${office.id}:`, locked || !incumbent || d.unit - c.appointment_at < 1)); officials.append(row);
      }); appointments.append(officials); body.append(appointments);
      const construction = box('王庭营建', c.project ? `${c.works.find(w => w.id === c.project.id).name}正在营建，第 ${c.project.complete_at} 单位竣工。` : '每项上限三级，工期四单位；同时营建一项。建筑效果持续生效。');
      const works = grid(); c.works.forEach(w => { const row = box(`${w.name} · ${w.level}/3`, w.description); row.append(button(w.level === 3 ? '已满级' : `营建 · ${fmt(w.cost)}`, 'build', w.id, locked || !!c.project || w.level >= 3 || d.treasury < w.cost)); works.append(row); }); construction.append(works); body.append(construction);
      const decrees = box('内政决策', '决策共享四单位冷却。征税与安抚会改变民心，影响后续府库收入。'), decisions = grid();
      c.decrees.forEach(p => { const row = box(p.name, p.description); row.append(button('执行决策', 'decree', p.id, locked || d.unit - c.decree_at < 4 || d.treasury < p.cost || (p.id === 'levy' && c.public_support < 40))); decisions.append(row); }); decrees.append(decisions); body.append(decrees);
    }
    if (selected === 'merit') {
      const job = box('王庭委托', '驻地履约一个行动单位，基本报酬一百功勋；按接取时的政令、官员和武院效果确定奖励。消费功勋不会减少累计功绩。');
      if (d.obligation) job.append(note(`${d.obligation.name}，限第 ${d.obligation.deadline} 单位前交付；逾期恩宠减十五。`));
      if (d.job) job.append(node('p', `已履约 ${d.job.progress}/${d.job.years} 年 · 报酬 ${d.job.reward} 功勋`), button('继续履约', 'work', '', d.job.progress >= d.job.years), button('交付领取', 'claim', '', d.job.progress < d.job.years), button('放弃委托', 'abandon'));
      else job.append(button('接取委托', 'accept', '', !d.joined));
      body.append(job);
      const rewards = box('俸禄与府库', `当前基础俸禄 ${fmt((10000 + d.rank * 10000) * d.current_policy.income)} 灵石／单位，以府库实有为限。仅实际经过本界时间才结算，刷新界面不推进政历。`);
      rewards.append(button('100 功勋 → 250,000 灵石', 'stones', '', !d.joined || d.merit < 100 || d.treasury < 250000), button(`${d.material_merit} 功勋 → 筑域材料`, 'material', '', !d.joined || d.merit < d.material_merit)); body.append(rewards);
      if (d.joined) body.append(button('退出王庭并放弃爵位', 'leave', '', !!d.job || !!c.challenge));
    }
    if (selected === 'history') {
      const history = node('ol', null, 'court-history');
      d.log.slice().reverse().forEach(entry => { const row = node('li'); row.append(node('small', `政历 ${entry.unit}`), node('p', entry.text)); history.append(row); });
      body.append(d.log.length ? history : note('王庭尚无新的政务纪事。'));
    }
  }
  window.AsuraCourtPanel = {render};
})();
