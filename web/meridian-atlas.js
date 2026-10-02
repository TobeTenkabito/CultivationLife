/* Paired cultivation atlases: artwork is independent of the live, numbered nodes. */
(() => {
  const svg = (tag, attrs = {}, text) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [name, value] of Object.entries(attrs)) element.setAttribute(name, value);
    if (text != null) element.textContent = text;
    return element;
  };
  const html = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    if (text != null) element.textContent = text;
    return element;
  };
  const path = (parent, d, cls = 'atlas-ink') => parent.appendChild(svg('path', {d, class: cls}));
  const states = {open: '已贯通', next: '下一脉', locked: '未贯通'};
  const demonNames = [
    '天逆阙', '左劫角门', '右劫角门', '绛魄府', '左焚臂络', '右焚臂络',
    '厄业轮', '左断兵津', '右断兵津', '魔炁海', '左噬煞窍', '右噬煞窍',
    '幽墟关', '左沉锋关', '右沉锋关', '冥骨枢', '左修罗辅', '右修罗辅',
    '血渊窍', '左坠魄脉', '右坠魄脉', '伏地关', '左蚀骨轮', '右蚀骨轮',
    '镇狱轮', '左踏焰窍', '右踏焰窍',
  ];
  // Coordinates follow each illustration's perspective; the far side is not mirrored.
  // Both source images are 1122 x 1402, fitted without distortion into this rectangle.
  const artwork = {x: 60, y: 97, width: 480, height: 600};
  const layouts = {
    asura: {
      center: [[304,119],[306,210],[313,244],[318,278],[325,311],[324,347],[319,385],[312,422],[308,459]],
      left: [[179,210],[202,242],[135,326],[174,301],[195,371],[223,298],[270,494],[249,538],[230,619]],
      right: [[435,211],[405,242],[473,331],[425,306],[428,375],[379,298],[327,504],[338,559],[338,623]],
    },
    immortal: {
      center: [[302,119],[300,204],[312,240],[317,275],[321,315],[321,350],[318,388],[312,426],[308,461]],
      left: [[224,239],[214,278],[199,314],[187,349],[182,388],[266,482],[253,520],[232,581],[219,641]],
      right: [[353,244],[366,282],[381,317],[398,354],[415,388],[330,502],[338,542],[338,585],[346,632]],
    },
  };

  function background(root, demon) {
    root.append(svg('rect', {x: 12, y: 12, width: 576, height: 732, rx: 2, class: 'atlas-frame'}));
    path(root, 'M36 79 V36 H116 M484 36 H564 V79 M36 674 V721 H116 M484 721 H564 V674', 'atlas-corners');
    root.append(svg('text', {x: 300, y: 51, class: 'atlas-kicker', 'text-anchor': 'middle'}, '内 景 图 录  /  ' + (demon ? '卷 · 魔' : '卷 · 仙')));
    root.append(svg('text', {x: 300, y: 81, class: 'atlas-title', 'text-anchor': 'middle'}, demon ? '修 罗 魔 脉' : '太 清 仙 脉'));
    const halo = svg('g', {class: 'atlas-aureole'});
    halo.append(svg('ellipse', {cx: 300, cy: 382, rx: 219, ry: 299}), svg('ellipse', {cx: 300, cy: 382, rx: 211, ry: 291}));
    halo.append(svg('circle', {cx: 300, cy: 160, r: 72}), svg('circle', {cx: 300, cy: 160, r: 78}));
    root.append(halo);
    for (const [x, text] of [[48, demon ? '三首镇神 · 六臂分煞' : '三花聚顶 · 五炁朝元'], [552, '九转归一 · 廿七玄关']]) {
      root.append(svg('text', {x, y: 350, class: 'atlas-marginal', 'writing-mode': 'vertical-rl', 'text-anchor': 'middle'}, text));
    }
    for (const mirror of [false, true]) {
      const cloud = svg('g', {transform: mirror ? 'translate(600 0) scale(-1 1)' : '', class: 'atlas-cloud'});
      path(cloud, 'M83 584 Q67 578 73 566 Q78 557 89 563 Q79 545 93 539 Q108 534 114 549 Q119 535 131 542 Q142 551 131 559 Q160 554 166 570 Q144 563 132 578 Q122 590 105 582 M79 572 Q91 580 109 570 Q129 557 147 567');
      path(cloud, 'M158 694 Q183 680 203 691 Q223 683 236 694 M179 702 Q205 689 227 701 Q247 693 266 702');
      root.append(cloud);
    }
    root.append(svg('text', {x: 300, y: 717, class: 'atlas-colophon', 'text-anchor': 'middle'}, demon ? '中枢九脉 · 六臂十二络 · 下盘六关' : '中枢九脉 · 周身十八络'));
  }

  function render(v, kind = 'immortal') {
    const demon = kind === 'asura';
    const figure = html('figure', `meridian-atlas ${demon ? 'asura-meridian-figure' : 'meridian-figure'}`);
    figure.dataset.kind = kind;
    const root = svg('svg', {viewBox: '0 0 600 760', role: 'group', 'aria-label': `${demon ? '三头六臂魔身' : '人体仙脉'}经络图：已贯通 ${v.opened}/27 条`});
    root.append(svg('title', {}, demon ? '三首六臂 · 二十七魔脉' : '二十七仙脉 · 人体经络示意'));
    const art = svg('g', {'aria-hidden': 'true'});
    background(art, demon);
    const body = svg('g', {class: 'atlas-anatomy'});
    body.append(svg('image', {...artwork, href: `/assets/${kind}-anatomy.png`, preserveAspectRatio: 'xMidYMid meet'}));
    art.append(body);
    root.append(art);

    const {center, left, right} = layouts[kind];
    const branches = [center, left, right];
    const records = center.flatMap((_, row) => branches.map((branch, side) => {
      const index = row * 3 + side + 1;
      const state = demon ? (v.nodes?.find(n => n.index === index)?.status || 'locked')
        : index <= v.opened ? 'open' : index === v.opened + 1 && index <= v.layer * v.per_layer ? 'next' : 'locked';
      return {index, row, side, point: branch[row], state, name: demon ? demonNames[index - 1] : v.names?.[index - 1] || `第 ${index} 仙脉`};
    }));
    const record = (side, row) => records[row * 3 + side];
    const channels = svg('g', {'aria-hidden': 'true'});
    function connect(a, b, main = false) {
      const [x, y] = a.point, [xx, yy] = b.point;
      const middle = (y + yy) / 2;
      const d = `M${x} ${y} C${x} ${middle} ${xx} ${middle} ${xx} ${yy}`;
      const lit = a.state === 'open' && b.state === 'open';
      // Keep the cranial meridian subtle so it does not obscure the face.
      if (main && a.row === 0) {
        path(channels, d, `atlas-channel atlas-cranial-channel${lit ? ' is-open' : ''}`);
        return;
      }
      path(channels, d, 'atlas-channel-ground');
      if (main) path(channels, d, 'atlas-main-channel');
      path(channels, d, `atlas-channel${main ? ' atlas-channel-core' : ''}${lit ? ' is-open' : ''}`);
    }
    for (let row = 1; row < 9; row++) connect(record(0, row - 1), record(0, row), true);
    for (const side of [1, 2]) {
      if (demon) {
        for (let pair = 0; pair < 3; pair++) {
          connect(record(0, pair * 2 + 1), record(side, pair * 2 + 1));
          connect(record(side, pair * 2 + 1), record(side, pair * 2));
        }
        connect(record(0, 6), record(side, 6));
        connect(record(side, 6), record(side, 7));
        connect(record(side, 7), record(side, 8));
      } else {
        connect(record(0, 1), record(side, 0));
        connect(record(0, 6), record(side, 5));
        for (const row of [1, 2, 3, 4, 6, 7, 8]) connect(record(side, row - 1), record(side, row));
      }
    }
    root.append(channels);

    const detail = html('figcaption', 'atlas-detail');
    detail.setAttribute('aria-live', 'polite');
    const selectedName = html('strong', 'atlas-selected-name');
    const selectedState = html('span', 'atlas-selected-state');
    detail.append(selectedName, selectedState);
    const groups = new Map();
    function select(item) {
      for (const [index, group] of groups) group.setAttribute('aria-pressed', String(index === item.index));
      selectedName.textContent = `${String(item.index).padStart(2, '0')} · ${item.name}`;
      selectedState.textContent = `第 ${item.row + 1} 层 · ${states[item.state]} · ${item.side === 0 ? '中枢主脉' : demon && item.row < 6 ? '六臂支脉' : '周身支脉'}`;
    }
    for (const item of records) {
      const [x, y] = item.point;
      const core = item.side === 0 && [0, 3, 6, 8].includes(item.row);
      const label = `${item.index} · ${item.name} · ${states[item.state]}`;
      const legacy = demon ? 'asura-vein-node' : `meridian-node ${{open: 'opened', next: 'next', locked: 'sealed'}[item.state]}`;
      const group = svg('g', {class: `atlas-node ${legacy}`, transform: `translate(${x} ${y})`, 'data-vein': item.index, 'data-state': item.state, 'data-tier': core ? 'core' : item.side === 0 ? 'junction' : 'ordinary', role: 'button', tabindex: 0, 'aria-label': label, 'aria-pressed': 'false'});
      group.append(svg('title', {}, label), svg('circle', {r: 18, class: 'atlas-hit'}));
      if (core) path(group, 'M0 -20 L20 0 L0 20 L-20 0Z', 'atlas-core-seal');
      if (item.side === 0 || item.state === 'next') group.append(svg('circle', {r: 16, class: 'atlas-outer-ring'}));
      group.append(svg('circle', {r: 12.5, class: 'atlas-node-disc'}), svg('circle', {r: 19, class: 'atlas-selection-ring'}), svg('text', {'text-anchor': 'middle', y: 4}, String(item.index).padStart(2, '0')));
      group.addEventListener('click', () => select(item));
      group.addEventListener('focus', () => select(item));
      group.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(item); }
      });
      groups.set(item.index, group);
      root.append(group);
    }
    select(records.find(n => n.state === 'next') || [...records].reverse().find(n => n.state === 'open') || records[0]);
    const legend = html('div', 'atlas-legend');
    for (const [state, label] of Object.entries(states)) legend.append(html('span', `atlas-key atlas-key-${state}`, label));
    const hint = html('p', 'atlas-hint', '点选脉位查看名称与状态 · 每层三脉，贯通后手动冲关');
    figure.append(root, legend, detail, hint);
    return figure;
  }
  window.MeridianAtlas = {render};
})();
