/* Provincial affairs live inside original court and building navigation. */
(() => {
  const el=(...a)=>window.GameUi.element(...a),fmt=n=>Number(n||0).toLocaleString('zh-CN');
  const labels={vacant:'待授',appointed:'待赴任',active:'在任',handover:'待交接'};
  let stateOwner=null;const viewing=new Map();
  const remember=(key,value)=>{viewing.set(key,value);if(viewing.size>128)viewing.delete(viewing.keys().next().value);};
  const keepOpen=(node,key)=>{node.open=viewing.get(key)===true;node.addEventListener('toggle',()=>{if(node.isConnected)remember(key,node.open);});};
  const caseLabels={open:'地方审议',submitted:'王庭待批',resolved:'已履行',rejected:'已驳回',withdrawn:'已撤回',expired:'已逾期',obsolete:'已失效'};
  function military(host,row,button,choose,fold,locked){
    const m=row.military;if(!m)return;
    const panel=fold('驻军与军令','部众负责守备与据点控制，不能凭人数抵消高阶修士的实力。调防沿实际道路，出兵会减少原址守备。');
    panel.classList.add('governor-military');keepOpen(panel,`military:${row.id}`);
    const labels={stationed:'驻守',outbound:'行军',returning:'归返',issued:'待受令',delayed:'有据缓调',refused:'具名抗命',accepted:'执行中',fulfilled:'已抵达',cancelled:'已撤令',enforced:'撤任追责',obsolete:'原令失效',raised:'举兵集结',marching:'向目标推进',contested:'争夺据点',capital:'已破王庭守备',won:'王权已交接',defeated:'举兵失败',withdrawn:'撤军收束',ended:'原案结束'};
    panel.append(el('p',`实际部众 ${m.units.length} 人 · 营务余款 ${fmt(m.balance)} 灵石 · 已耗 ${fmt(m.spent)} 灵石`,'governor-case-amount'));
    if(m.shortfall)panel.append(el('p',`营务欠付 ${m.shortfall} 年；连续三年不足将循原路撤军。`,'court-note'));
    for(const u of m.units){const line=el('p',null,'governor-unit');line.append(el('strong',u.name),el('span',`${labels[u.phase]} · ${u.destination_name}${u.remaining?' · 余 '+u.remaining+' 年':''} · 年费 ${fmt(u.rate)}`),el('small',u.supporting?'已明确支持指挥人':'公职服役，不等于私人效忠','court-description'));panel.append(line);}
    if(m.order)panel.append(el('p',`中央军令 · ${labels[m.order.status]} · ${m.order.deadline}年前回应。${m.order.reason||'请在原府核验守备、道路与军费。'}`,'court-note'));
    const open=m.conflict&&['raised','marching','contested','capital'].includes(m.conflict.status);
    if(m.conflict)panel.append(el('p',`举兵争位 · ${labels[m.conflict.status]}。${m.conflict.result||'须实际抵达、突破守备并解决旧王抵抗；占城不自动登位。'}`,'court-note'));
    let allowed=[];
    if(m.mine&&m.local){allowed.push('recall');if(m.enabled){if(row.active)allowed.push('enlist','provision','dispatch','respond','rebel');else if(open)allowed.push('provision','dispatch','rebel');}}
    if(m.central){allowed.push('recall','cancel_order');if(m.enabled)allowed.push('order','press');}
    if(open&&m.mine){allowed.push('standdown');if(m.enabled)allowed.push('assault','claim');}
    if(open&&m.central&&m.enabled)allowed.push('pacify','abdicate');
    if(open&&!m.mine&&m.enabled)allowed.push('pacify');
    allowed=[...new Set(allowed)].filter(k=>m.operations[k]);
    if(allowed.length){
      const controls=el('div',null,'governor-military-controls');
      const action=choose('军政事务',allowed.map(id=>({id,name:m.operations[id]})));
      const old=viewing.get(`military-choice:${row.id}`);if(allowed.includes(old))action.value=old;
      const person=choose('征募原人物',m.candidates.map(p=>({id:p.id,name:`${p.name} · 年费 ${fmt(p.rate)}`})));
      const destination=choose('调防地点',m.destinations);
      const choice=choose('军令回应',[{id:'comply',name:'执行调防，按实减少留守'},{id:'delay',name:'出示守备或军费缺口，申请缓调'},{id:'refuse',name:'具名拒命，承担追责'}]);
      const funds=el('input');funds.type='number';funds.min='1';funds.max='1000000000000000';funds.value='1000000';funds.setAttribute('aria-label','营务军费金额');
      const note=el('p',null,'court-description');
      const send=button('执行军政事务','military',()=>({office:row.id,operation:action.value,person:person.value,destination:destination.value,choice:choice.value,amount:Number(funds.value)}));
      const update=()=>{remember(`military-choice:${row.id}`,action.value);person.hidden=action.value!=='enlist';destination.hidden=!['dispatch','order'].includes(action.value);funds.hidden=action.value!=='provision';choice.hidden=action.value!=='respond';send.disabled=locked||(action.value==='enlist'&&!m.candidates.length);note.textContent=({rebel:'公开举兵将撤销法定任职，只有明确支持你的原部将追随；军费和败战后果保留。',claim:'亲战旧王使用实际修为、装备、伤势与元力，胜出才交接王权；未决则保留原案。',abdicate:'明确承认举兵方，交出唯一王位；原债务、人员和公款保留。',press:'仅对已经拒命的总督撤任追责；实际交接可能遭部将抵抗。',provision:'从本府公款实拨，只能在原军尚在本府时交付。已耗营务不退款。',dispatch:'须预付原部众去返道路与十年驻防费用；不会移动玩家。'})[action.value]||'在提交时复核原人物、实际地点、军令与任职权限。';};
      action.onchange=update;update();controls.append(action,person,destination,choice,funds,note,send);panel.append(controls);
    }
    host.append(panel);
  }
  function disputes(host,row,button,choose,fold,local,locked){
    const d=row.disputes;if(!d||!local&&!d.active.length)return;
    const panel=fold(local?'地方争议':'地方呈案',local?'按原账目受理，三派表态供裁决参考。具名担保会随兑现或失约影响具体人物关系。':'原府具名呈交的公开案卷；批准实拨原款，任期和未结责任分别核验。');
    panel.classList.add('governor-disputes');
    keepOpen(panel,`disputes:${row.id}:${local}`);
    const control=(label,operation,c,data={},disabled=false)=>{const b=button(label,'petition',()=>({office:row.id,operation,case:c?.id,...(typeof data==='function'?data():data)}),disabled);b.dataset.petitionOperation=operation;return b;};
    if(local)panel.append(control('受理地方来报','observe',null,{},!d.can_observe));
    for(const c of d.active){
      const item=el('details',null,'governor-case');item.dataset.caseId=c.id;item.dataset.caseKind=c.kind;
      keepOpen(item,`case:${c.id}`);
      const heading=el('summary');heading.append(el('strong',c.name),el('span',caseLabels[c.status],'governor-case-status'));item.append(heading);
      item.append(el('p',c.evidence.description),el('p',`${c.evidence.source} · ${c.opened}年登记 · ${c.deadline}年前裁定`,'court-description'));
      if(c.evidence.amount)item.append(el('p',`原申请金额 ${fmt(c.evidence.amount)} 灵石`,'governor-case-amount'));
      const positions=el('div',null,'governor-positions');
      for(const w of c.witnesses){const label=c.choices.find(o=>o.id===w.choice)?.name||({approve:'赞成批准',appoint:'赞成首荐',alternative:'支持备选',decline:'暂缓任用'})[w.choice]||w.choice;positions.append(el('p',`${w.name}：${label}`),el('small',w.reason,'court-description'));}
      if(c.witnesses.length)item.append(positions);
      const pick=choose('裁决方案',c.choices);pick.disabled=locked||!c.can_decide&&!c.can_endorse;
      if(c.choices.some(o=>o.id===viewing.get(`choice:${c.id}`)))pick.value=viewing.get(`choice:${c.id}`);
      const reason=el('p',null,'court-description');
      const decide=control('按案裁定','resolve',c,()=>({choice:pick.value}),!c.can_decide);
      const endorse=control(c.pledge?'已有具名担保':'为此方案担保','endorse',c,()=>({choice:pick.value}),!c.can_endorse);
      const update=()=>{const selected=c.choices.find(o=>o.id===pick.value);reason.textContent=selected?.reason||'款物与权限在提交时再次核验。';decide.disabled=locked||!c.can_decide||!!selected?.reason||!selected;};
      pick.onchange=()=>{remember(`choice:${c.id}`,pick.value);update();};update();
      item.append(pick,reason);if(c.can_decide)item.append(decide);else item.append(el('p',c.status==='submitted'?'待王庭裁决；总督不能自行批准拨款或续任。':'当前无裁决权限。','court-note'));
      if(c.can_endorse||c.pledge)item.append(endorse);
      if(c.can_withdraw)item.append(control('撤回并留档','withdraw',c));
      panel.append(item);
    }
    if(!d.active.length)panel.append(el('p','暂无待决事项。每类事项按百年期受理；没有原始事实时不生成。','court-description'));
    if(d.history.length){const history=fold('案卷与承诺回执');for(const c of [...d.history].reverse())history.append(el('p',`${c.closed}年 · ${caseLabels[c.status]} · ${c.result}${c.pledge?'（具名担保已记入履历）':''}`));panel.append(history);}
    host.append(panel);
  }
  function render(host,game,dispatch,selected=null){
    if(stateOwner!==game.id){viewing.clear();stateOwner=game.id;}
    const d=game.upper_institution?.court?.governorship;if(!d)return;
    const root=el('section',null,'asura-governorship');root.dataset.dlcScope='asura-manifestation';
    const blocked=!!game.pending_event||!!game.trial?.active||!game.player.alive||!!game.imprisonment||!!game.map_journey;
    const send=(action,data={})=>dispatch({action:'governorship',target_id:JSON.stringify({action,token:d.token,...data})});
    const button=(label,action,data={},disabled=false)=>{const b=el('button',label,'court-button');b.type='button';b.dataset.governorAction=action;b.dataset.dlc='asura-manifestation';b.disabled=blocked||disabled;b.onclick=()=>send(action,typeof data==='function'?data():data);return b;};
    const fold=(title,description)=>{const box=el('details',null,'governor-section');box.append(el('summary',title));if(description)box.append(el('p',description,'court-description'));return box;};
    const choose=(label,rows)=>{const s=el('select');s.setAttribute('aria-label',label);for(const r of rows){const o=el('option',r.name);o.value=r.id;s.append(o);}return s;};
    const headline=el('div',null,'governor-heading');headline.append(el('span','府','governor-seal'),el('div'));
    headline.lastChild.append(el('h3',selected?'地方府务':'总督外任'),el('p',d.enabled?'任期五百年 · 原址接任 · 公私分账':'扩展已停用 · 保留原款与交接责任','court-description'));root.append(headline);
    if(!selected){
      const request=fold(d.king?'地方任命':'申请外任','战将以上、累计功绩100、恩宠20可在王庭申请。受任后沿原地图赴任，设府及工程另付原款。');
      const cities=choose('外任城市',d.cities.filter(c=>c.eligible)),people=choose('总督人选',d.candidates);
      request.append(cities);if(d.king)request.append(people);
      request.append(button(d.king?'颁发任命':'申请外任',d.king?'appoint':'request',()=>({city:cities.value,person:people.value}),!d.enabled||!d.capital||!d.cities.length||(!d.king&&!d.qualified)||(d.king&&!d.candidates.length)));
      root.append(request);
    }
    const rows=d.offices.filter(r=>!selected||[r.id,r.city_id,r.building_id].includes(selected));
    for(const r of rows){
      const box=el('article',null,'governor-office');box.dataset.governorOffice=r.id;
      const place=game.map?.locations?.find(p=>p.id===r.location)?.name||r.location;
      box.append(el('h4',r.name),el('p',`${labels[r.status]} · ${r.holder_name} · ${place}`),el('p',`任期至 ${r.expires} 年${r.cash!==undefined?' · 公款 '+fmt(r.cash)+' 灵石':''}`,'court-description'));
      if(!selected){
        box.append(el('p','赴当地建筑办理府务；设府前从原城市的「总督府」进入。','court-note'));
        if(d.king){
          const funds=el('input');funds.type='number';funds.min='1';funds.max='1000000000000000';funds.value='1000000';funds.setAttribute('aria-label',r.name+'拨款');
          const actions=fold('拨款与撤任');actions.append(funds,button('拨付公款','fund',()=>({office:r.id,amount:Number(funds.value)}),!d.enabled||!d.capital),button('撤销任命','revoke',{office:r.id},!d.enabled||!d.capital||!['active','appointed'].includes(r.status)));box.append(actions);
        }
      }else if(r.mine){
        if(r.status==='appointed')box.append(button('验收接任','assume',{office:r.id},!d.enabled||!r.local));
        if(r.active){
          const budget=fold('公款与府署','自愿资助进入本府公账，不能取回个人行囊。营造采购原市场实货，府署保留王庭产权。');
          const funds=el('input');funds.type='number';funds.min='1';funds.max='1000000000000000';funds.value=String(Math.max(1000000,r.quote?.total||0));funds.setAttribute('aria-label','资助本府金额');
          budget.append(funds,button('资助本府','donate',()=>({office:r.id,amount:Number(funds.value)}),!d.enabled));
          if(r.building_status!=='intact'&&r.quote){const q=r.quote;budget.append(el('p',`营造总价 ${fmt(q.total)} 灵石 · 其中工费 ${fmt(q.coins)}`),el('p',q.reason||'工料及施工全额实付，原址恢复。','court-description'),button(r.building_status==='unbuilt'?'营造府署':'公费原址重建','build',{office:r.id,quote:q.token,total:q.total},!d.enabled||!!q.reason));}
          box.append(budget);
          const staff=fold('属员与履约','从原址自由修士中聘任执事。项目沿原机构系统托管预算，按真实年份执行；离场和失去资格会暂停。');
          const person=choose('地方执事',[{id:'',name:'暂不聘任'},...(r.candidates||[])]);person.value=r.people?.[0]||'';
          staff.append(person,button('登记属员','staff',()=>({office:r.id,person:person.value}),!d.enabled||!!r.agenda?.job));
          window.InstitutionGovernance?.render(staff,d.management.filter(m=>m.id===r.id),payload=>send('management',{office:r.id,payload}),'asura-manifestation');box.append(staff);
        }
        const handover=fold('任职交接','上缴只将未耗公款交回王庭。辞任解除原任职，建筑、公款与历史留在原址；已耗工程与劳务不退款。');
        handover.append(button('上缴未耗公款','return',{office:r.id},!r.local||r.controller!=='player'),button('交接辞任','resign',{office:r.id},!r.local));box.append(handover);
      }
      disputes(box,r,button,choose,fold,!!selected&&r.mine,blocked);
      military(box,r,button,choose,fold,blocked);
      if(r.history?.length){const history=fold('任职与收支记录');for(const h of [...r.history].reverse())history.append(el('p',`${h.year}年 · ${h.text}`));box.append(history);}
      root.append(box);
    }
    if(!rows.length&&!selected)root.append(el('p','尚无已授地方任职。','court-description'));
    host.append(root);
  }
  window.AsuraGovernorship={render};
})();
