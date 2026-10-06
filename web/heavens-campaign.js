/* One selected military detail; distant reports never become live telemetry. */
(() => {
  function render(host, campaign, ui, kit) {
    const {node, title, back, subview, renderActions, empty} = kit;
    back(host, '返回边情目录', 'frontier');
    const heading = node('header', null, 'heavens-campaign-heading');
    title(heading, '岚疆界门', '一地的守备与去留，取决于真实人物、道路和补给。');
    host.append(heading);
    if (!campaign?.known) {
      empty(host, '尚无施工情报', '取得现场见闻或守方送达的预警后，才能查阅此地战局。');
      return;
    }
    const actions = (body, names) => renderActions(body, campaign.actions.filter(a => names.includes(a.action)));
    const chooser = (body, names, label) => {
      const rows = campaign.actions.filter(a => names.includes(a.action));
      const select = node('select'); select.setAttribute('aria-label', label);
      for (const row of rows) { const option = node('option', row.label); option.value = row.action; select.append(option); }
      select.value = (rows.find(a => a.enabled) || rows[0])?.action || '';
      const field = node('label', label, 'heavens-campaign-field'); field.append(select);
      const detail = node('div'); body.append(field, detail);
      const update = () => {detail.replaceChildren(); renderActions(detail, rows.filter(a => a.action === select.value));};
      select.onchange = update; update();
    };
    subview(host, [['dispatches', '军情'], ['gate', '界门'], ['engagement', '交锋'], ['aid', '援助'], ['settlement', '地方']], 'dispatches', (body, section) => {
      if (section === 'settlement') {
        const state = campaign.settlement;
        if (!state) { empty(body, '地方职责尚未登记', '实际年度推进后，再到当地查阅。'); return; }
        const select = node('select'); select.setAttribute('aria-label', '地方档案');
        for (const [value, text] of [['order', '地方秩序'], ['treaty', '议约文书'], ['recovery', '救护与去留']]) {
          const option = node('option', text); option.value = value; select.append(option);
        }
        select.value = ui.campaignLocal || 'order';
        const label = node('label', '查阅档案', 'heavens-campaign-field'); label.append(select);
        const detail = node('div', null, 'heavens-campaign-detail'); body.append(label, detail);
        const update = () => {
          ui.campaignLocal = select.value; detail.replaceChildren();
          if (select.value === 'order') {
            const card = node('article', null, 'heavens-territory');
            card.append(node('small', '人界 · 岚疆草原'), node('h4', state.control || '尚无现场见闻'));
            const route = node('ol', null, 'heavens-territory-route'); route.setAttribute('aria-label', '地点关系');
            for (const text of ['无棣原\n接应与议报', '岚疆草原\n本案唯一管辖点', '赤髓城\n异界来路']) route.append(node('li', text));
            card.append(route, node('p', '控制只及岚疆。其他地点和宗门不会随此地交锋转属。'));
            detail.append(card);
            if (state.resolution) detail.append(node('p', state.resolution, 'heavens-finding'));
            if (state.duties.length) {
              const duties = node('dl', null, 'heavens-campaign-duties');
              for (const duty of state.duties) duties.append(node('dt', duty.duty), node('dd', duty.name));
              detail.append(duties);
            }
            const policies = node('ul', null, 'heavens-evidence');
            for (const policy of state.policies) policies.append(node('li', policy));
            detail.append(policies, node('small', '地方职责依靠原驻军与实有专项；缺人、断供或授权失效时，原管辖不会自行延续。'));
            return;
          }
          if (select.value === 'treaty') {
            const treaty = state.treaty;
            const document = node('article', null, 'heavens-treaty-document');
            document.append(node('small', '地方议约 · 仅限岚疆'), node('h4', treaty?.name || '双方具名代表议约'));
            if (treaty) document.append(node('p', `签于 ${treaty.signed_at} 年 · 约定期限至 ${treaty.expires_at} 年`));
            else document.append(node('p', '你可以提出方案。双方代表须持有独立委任并实际到场，玩家不能代替宗门签署。'));
            const clauses = node('ol', null, 'heavens-evidence');
            for (const clause of treaty?.clauses || state.clauses.truce) clauses.append(node('li', clause));
            document.append(clauses); detail.append(document);
            if (!treaty) {
              const choices = node('select'); choices.setAttribute('aria-label', '议约方案');
              for (const [kind, text] of [['truce', '当地停战'], ['vassal', '限期附约'], ['withdrawal', '修复后撤军']]) {
                const option = node('option', text); option.value = kind; choices.append(option);
              }
              const field = node('label', '拟议条款', 'heavens-campaign-field'); field.append(choices);
              const control = node('div'); detail.append(field, control);
              const choose = () => {
                clauses.replaceChildren(); for (const clause of state.clauses[choices.value]) clauses.append(node('li', clause));
                control.replaceChildren(); actions(control, [`campaign_${choices.value}`]);
              };
              choices.onchange = choose; choose();
            } else detail.append(node('small', '这是你见证的原签署文书。远方履约情况须通过现场查验；旧文书不代表新任者已经续约。'));
            return;
          }
          title(detail, '救护与去留', '败退不结束修行。留在当地调息，或沿原道路回到无棣原。');
          if (state.patients.length) {
            const roster = node('div', null, 'heavens-campaign-roster');
            for (const patient of state.patients) {
              const card = node('article'); card.append(node('small', patient.treated ? '本案已救护' : `实际伤势 ${patient.wounds} 重`), node('strong', patient.name)); roster.append(card);
            }
            detail.append(roster);
          } else detail.append(node('p', state.local ? '现场未发现待救护的伤员。' : '伤员情况须抵达现场确认。'));
          const route = node('ol', null, 'heavens-visit-route');
          for (const text of ['岚疆出发', '循本界道路', '无棣原接应']) route.append(node('li', text));
          detail.append(route, node('small', '途中事件可中断行程；伤员死亡、离开或受控时不能隔空救护。释放只适用于你实际控制的原俘虏。'));
          chooser(detail, ['campaign_relief', 'campaign_release', 'campaign_evacuate'], '选择当前事务');
        };
        select.onchange = update; update(); return;
      }
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
      } else {
        body.append(node('p', '阵材交付后归你使用；这份物资不会附带援军，也不会改变地方归属。', 'heavens-finding'));
        const request = campaign.actions.find(a => a.action === 'campaign_report');
        if (request?.enabled) renderActions(body, [request]);
        else chooser(body, ['campaign_aid', 'campaign_decline'], '援助意向');
      }
      if (aid && !aid.collected && !aid.refused && !aid.cancelled) actions(body, ['campaign_wait']);
    });
  }
  window.HeavensCampaign = {render};
})();
