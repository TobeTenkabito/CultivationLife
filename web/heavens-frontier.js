/* Border affairs have their own directory and one selected detail at a time. */
(() => {
  function render(host, frontier, ui, kit) {
    const {node, title, tile, back, subview, renderActions, empty, go} = kit;
    if (!ui.target) {
      title(host, '边情与战局', '从亲历的消息出发，判断是否介入一地事务。');
      const intro = node('div', null, 'heavens-frontier-intro');
      intro.append(node('span', '边', 'heavens-glyph'), node('p', '一封问讯，一处落点。来者的意图需要查证，你也可以继续自己的修行。'));
      host.append(intro);
      const directory = node('div', null, 'heavens-directory');
      const latest = frontier.reports?.at(-1);
      tile(directory, {name: frontier.name, description: '无棣原的阵眼问讯 · 岚疆草原的有限接触',
        status: latest ? '已有亲历报告' : '尚未递送问讯', glyph: '疆', onClick: () => go('frontier', frontier.id)});
      host.append(directory);
      return;
    }
    back(host, '返回边情目录', 'frontier');
    title(host, frontier.name, '只展示你已经收到或亲自核实的消息。');
    const sections = frontier.known ? [['reports', '情报'], ['field', '现场']] : [['contact', '问讯']];
    subview(host, sections, sections[0][0], (body, section) => {
      if (section === 'contact') {
        const route = node('div', null, 'heavens-frontier-route');
        route.append(node('strong', '无棣原'), node('span', '阵眼传讯 →'), node('strong', '已知异界接触点'));
        body.append(route, node('p', '查明因果遗址接触点后，可主动递送问讯。消息会包含自己的回程位置，对方可能派人核查，也可能拒绝。'));
        renderActions(body, frontier.actions.filter(a => a.action === 'frontier_inquire'));
        return;
      }
      if (section === 'reports') {
        const reports = frontier.reports || [];
        if (!reports.length) empty(body, '问讯尚在递送', '先完成当前行程，消息送达后才会记入这里。');
        else {
          const list = node('ol', null, 'heavens-timeline');
          for (const report of [...reports].reverse()) {
            const row = node('li');
            row.append(node('small', `诸天纪年 ${report.year} 年 · ${report.kind === 'identity' ? '当面核实' : report.kind === 'reply' ? '阵眼回讯' : '亲历记录'}`), node('p', report.text));
            list.append(row);
          }
          body.append(list);
        }
        if (frontier.observed && !frontier.reported) renderActions(body, frontier.actions.filter(a => a.action === 'frontier_report'));
        return;
      }
      const encounter = node('article', null, 'heavens-frontier-contact');
      const agreed = frontier.reports.some(r => r.kind === 'agreement');
      const finished = frontier.reports.some(r => r.kind === 'reply');
      encounter.append(node('span', finished ? '已收到结清回讯' : agreed ? '已约定返程' : frontier.local ? '当前可接触' : '当前无法当面接触', 'heavens-badge'),
        node('h4', frontier.person?.name || '岚疆草原 · 待查来者'),
        node('p', finished ? '此次问讯已有结论，实际收到的消息保留在情报页。' : agreed ? '对方已接受结束本次勘察。返乡回讯到达后，会记入情报页。' : frontier.local ? '先遣目前在此。可调查来意；若阵眼已恢复，可出示凭据，请对方结束此次勘察。' : '远方报告不能代替眼前事实。这里不会显示未知的行军进度或预算。'));
      body.append(encounter);
      if (finished) return;
      const names = new Set(['frontier_wait', frontier.observed ? 'frontier_parley' : 'frontier_scout']);
      if (agreed) names.delete('frontier_parley');
      renderActions(body, frontier.actions.filter(a => names.has(a.action)));
    });
  }
  window.HeavensFrontier = {render};
})();
