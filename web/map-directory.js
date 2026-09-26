/* A dedicated atlas ledger for temporary gatherings and permanent offices. */
(() => {
  let world = null, mode = 'terrain', category = 'all', selected = null;
  const node = (tag, text, cls = '') => {
    const el = document.createElement(tag); el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  };
  const button = (text, action, cls = '') => {
    const el = node('button', text, cls); el.type = 'button'; el.onclick = action; return el;
  };
  function render(map, auction, state) {
    if (world !== map.world) { world = map.world; mode = 'terrain'; category = 'all'; selected = null; }
    const places = map.locations || [];
    if (!places.some(place => place.id === selected)) selected = null;
    const entries = new Map(places.map(place => [place.id, []]));
    const add = (id, entry) => entries.get(id)?.push(entry);
    (state?.merchant_system?.alliances || []).forEach(alliance => {
      const label = alliance.cross_world && alliance.home_world !== map.world ? '分总部' : '本界总部';
      // Public headquarters are world-local; the originating HQ need not be exposed.
      add(alliance.hq, {kind:'merchant', title:alliance.name, detail:label, seal:'盟'});
      (alliance.offices || []).forEach(office => add(office.location_id, {
        kind:'merchant', title:alliance.name, detail:`${office.name}分部`, seal:'盟',
      }));
    });
    if (auction?.available) add(auction.location_id, {
      kind:'event', theme:'auction', title:auction.status === 'black_market' ? '散场黑市' : '拍卖会', seal:'拍',
      detail:auction.status === 'scheduled' ? `${auction.actions_until_open}个时间单位后开幕`
        : auction.status === 'open' ? '正在举行' : '散场黑市开放中',
      live:auction.status !== 'scheduled',
    });
    const exchange = state?.exchange_system;
    if (exchange?.available) add(exchange.location_id, {
      kind:'event', theme:'exchange', title:'匿名交换会', seal:'易',
      detail:exchange.status === 'scheduled' ? `${exchange.actions_until_open}个时间单位后开幕` : '正在举行 · 以物易物',
      live:exchange.status !== 'scheduled',
    });
    places.forEach(place => {
      if (place.ghost_parade) add(place.id, {
        kind:'event', theme:'ghost', title:'百鬼夜行', seal:'夜', live:place.ghost_parade.status === 'active',
        detail:place.ghost_parade.status === 'active' ? '正在发生' : `${timelineText(place.ghost_parade.start_age)}开启`,
      });
      (place.ground_formations || []).forEach(array => add(place.id, {
        kind:'formation', title:array.name, seal:'阵',
        detail:`${array.owner_kind === 'sect' ? `${array.owner_name}护山阵` : '私阵'} · 完整度 ${Number(array.durability).toFixed(0)}%`,
      }));
    });
    entries.forEach(rows => rows.sort((a, b) => ({event:0, merchant:1, formation:2}[a.kind] - {event:0, merchant:1, formation:2}[b.kind])));
    const tabs = document.querySelector('#map-view-tabs');
    const terrain = document.querySelector('#map-locations');
    const directory = document.querySelector('#map-directory');
    const scrollTop = () => document.querySelector('#map-card').scrollTo({top:0, behavior:'instant'});
    const switchMode = value => { mode = value; draw(); scrollTop(); };
    function draw() {
      tabs.replaceChildren();
      [['terrain','地域地图'],['directory','活动与据点']].forEach(([id, title]) => {
        const tab = button(title, () => switchMode(id));
        tab.setAttribute('aria-pressed', String(mode === id));
        tab.setAttribute('aria-controls', id === 'terrain' ? 'map-locations' : 'map-directory');
        tabs.append(tab);
      });
      terrain.classList.toggle('hidden', mode !== 'terrain');
      directory.classList.toggle('hidden', mode !== 'directory');
      directory.replaceChildren();
      const intro = node('div', null, 'map-directory-intro');
      intro.append(node('strong', '坊间见闻 · 商旅名录'), node('p', '会期、异象与商盟地址，依所在地域收录。'));
      directory.append(intro);
      const filters = node('div', null, 'map-directory-filters');
      filters.setAttribute('aria-label', '名录分类');
      [['all','全部'],['event','时令活动'],['merchant','商盟据点']].forEach(([id, title]) => {
        const filter = button(title, () => { category = id; draw(); });
        filter.setAttribute('aria-pressed', String(category === id)); filters.append(filter);
      });
      directory.append(filters);
      if (selected) {
        const scope = node('div', null, 'map-directory-scope');
        scope.append(node('span', `正在查看：${places.find(place => place.id === selected).name}`),
          button('查看全界', () => { selected = null; draw(); }));
        directory.append(scope);
      }
      const list = node('div', null, `map-directory-list${selected ? ' focused' : ''}`);
      let count = 0;
      places.forEach(place => {
        const rows = entries.get(place.id).filter(entry => category === 'all' || entry.kind === category);
        if (!rows.length || selected && selected !== place.id) return;
        count += rows.length;
        const card = node('section', null, 'map-directory-place'); card.dataset.location = place.id;
        const heading = node('div', null, 'map-directory-heading');
        heading.append(node('h3', place.name), node('span', place.current ? '当前所在地' : `${rows.length}条记录`));
        card.append(heading);
        rows.forEach(entry => {
          const row = node('div', null, `map-directory-entry ${entry.theme || entry.kind}`);
          const copy = node('div');
          copy.append(node('strong', entry.title), node('p', entry.detail));
          row.append(node('span', entry.seal, 'map-directory-seal'), copy);
          if (entry.live) row.append(node('span', '进行中', 'map-directory-live'));
          card.append(row);
        });
        card.append(button('在地图中定位', () => {
          switchMode('terrain');
          const target = [...terrain.children].find(row => row.dataset.location === place.id);
          target?.scrollIntoView({block:'center'});
          target?.focus({preventScroll:true});
        }, 'map-directory-locate'));
        list.append(card);
      });
      if (!count) list.append(node('p', category === 'event' ? '此范围内暂无已公布的活动。' : '此范围内暂无相关记录。', 'map-directory-empty'));
      directory.append(list);
    }
    draw();
    return location => {
      const rows = entries.get(location.id) || [];
      if (!rows.length) return null;
      const strip = node('div', null, 'map-directory-links');
      [['event','活动'],['merchant','商盟'],['formation','驻阵']].forEach(([id, title]) => {
        const count = rows.filter(entry => entry.kind === id).length;
        if (!count) return;
        const link = button(`${title} · ${count}`, () => {
          selected = location.id; category = id === 'formation' ? 'all' : id; switchMode('directory');
        }, `map-directory-link ${id}`);
        link.setAttribute('aria-label', `查看${location.name}的${title}（${count}条）`);
        strip.append(link);
      });
      return strip;
    };
  }
  window.MapDirectory = {render};
})();
