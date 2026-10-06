/* One selected military detail; distant reports never become live telemetry. */
(() => {
  function render(host, campaign, ui, kit) {
    const {node, title, back, subview, renderActions, empty} = kit;
    back(host, '返回边情目录', 'frontier');
    title(host, '岚疆界门', '一地的守备与去留，取决于真实人物、道路和补给。');
    if (!campaign?.known) {
      empty(host, '尚无施工情报', '取得现场见闻或守方送达的预警后，才能查阅此地战局。');
      return;
    }
    const actions = (body, names) => renderActions(body, campaign.actions.filter(a => names.includes(a.action)));
    subview(host, [['dispatches', '军情'], ['gate', '界门'], ['engagement', '交锋'], ['aid', '援助']], 'dispatches', (body, section) => {
      if (section === 'dispatches') {
        const list = node('ol', null, 'heavens-timeline');
        for (const report of [...campaign.reports].reverse()) {
          const item = node('li');
          item.append(node('small', `诸天纪年 ${report.year} 年`), node('p', report.text));
          list.append(item);
        }
        body.append(list);
        const request = campaign.actions.find(a => a.action === 'campaign_report');
        if (request?.enabled) renderActions(body, [request]);
        return;
      }
      if (section === 'gate') {
        const card = node('article', null, 'heavens-frontier-contact');
        card.append(node('span', campaign.local ? '岚疆现场' : '远方消息', 'heavens-badge'));
        const gate = campaign.gate;
        if (gate) {
          const names = {planned: '尚未施工', building: '目标端施工中', open: '界门稳定', interrupted: '输送中断', destroyed: '界门已拆除'};
          card.append(node('h4', names[gate.state]), node('p', '这里只展示当前亲自查明的目标端。来源端预算与远方队列不在你的视野内。'));
          if (gate.state === 'building') {
            const progress = node('progress');
            progress.max = gate.duration; progress.value = gate.target_progress;
            progress.setAttribute('aria-label', '目标端施工进度');
            card.append(progress, node('small', `${gate.target_progress} / ${gate.duration} 年施工`));
          }
        } else card.append(node('h4', '须亲自查勘'), node('p', '历史预警保留在军情页；到岚疆草原查勘，才能判断现场设施。'));
        body.append(card);
        actions(body, ['campaign_scout', ...(gate?.state !== 'destroyed' ? ['campaign_sabotage'] : [])]);
        return;
      }
      if (section === 'engagement') {
        const people = campaign.people || [];
        if (!campaign.local) empty(body, '尚未抵达战场', '交锋须在岚疆草原当面进行。可以自行离开，也可以继续原有修行。');
        else if (!people.length) empty(body, '未查明当前在场人物', '先到界门页查勘；没有真实对手时不会生成替代敌人。');
        else {
          const roster = node('div', null, 'heavens-campaign-roster');
          for (const person of people) {
            const row = node('article');
            row.append(node('small', person.side), node('strong', person.name));
            roster.append(row);
          }
          body.append(roster);
        }
        actions(body, ['campaign_assault', 'campaign_capture']);
        return;
      }
      const aid = campaign.aid;
      title(body, '灵界有限援助', '太玄门独立决定是否提供一件阵材，经限定路线运往无棣原，运输需要十六年。');
      if (aid?.collected) empty(body, '阵材已交付', '唯一物资已进入你的阵材库存，可按原有阵法规则使用。');
      else if (aid?.cancelled) empty(body, '已收到撤销回函', '原批准已经失效，未交付阵材归回原专项。回函保留在军情页。');
      else if (aid?.refused) empty(body, '本次未接受援助', '此选择已保留，不会重新生成物资或替代援军。');
      else if (aid) {
        empty(body, aid.available ? '物资已到无棣原' : '已登记援助申请', '到无棣原办理实际交接；远方运输进度不会实时显示。');
        actions(body, ['campaign_collect']);
      } else actions(body, ['campaign_report', 'campaign_aid', 'campaign_decline']);
      actions(body, ['campaign_wait']);
    });
  }
  window.HeavensCampaign = {render};
})();
