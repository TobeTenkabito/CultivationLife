/* Political theatre → organization campaign → original battle receipts. */
(() => {
  let identity, selected, tab='态势', campaign, latest, compact=window.innerWidth<600;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const phases={mobilizing:'动员',active:'交战',armistice:'停战',settling:'撤军',ended:'终战'};
  const stages={marching:'行军',engaged:'交锋',returning:'归返',home:'已归营',lost:'无法出战'};
  const number=n=>new Intl.NumberFormat('zh-CN',{maximumFractionDigits:0,notation:n>=100000?'compact':'standard'}).format(n||0);
  const svg=(name,attrs={})=>{const n=document.createElementNS('http://www.w3.org/2000/svg',name);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n;};
  function render(system,saveId,submit){
    latest=[system,saveId,submit];compact=window.innerWidth<600;
    const host=document.querySelector('#war-list');if(!host)return;
    let root=document.querySelector('#strategic-war-panel');
    if(!root){root=el('section',undefined,'strategy');root.id='strategic-war-panel';host.before(root);}
    root.replaceChildren();
    if(identity!==saveId){identity=saveId;selected=null;tab='态势';campaign=null;}
    const wars=system?.wars||[];
    if(!system?.available&&!wars.length&&!system?.legacy_relations?.length&&!system?.legacy_wars?.length){root.hidden=true;return;}root.hidden=false;
    const header=el('div',undefined,'strategy-heading');
    const heading=el('div');heading.append(el('small',`${system.world} · 联军议事`,'strategy-kicker'),el('h3','山河战局'));
    header.append(heading,el('span',`${wars.filter(w=>w.status!=='ended').length} 案进行中`,'strategy-seal'));root.append(header);
    if(!wars.length){const empty=el('div',undefined,'strategy-empty');empty.append(el('span','旌旗未起','strategy-empty-seal'),el('p','在「同道 → 种族」提交族议，宗门与家族将按各自承诺出征。'));root.append(empty);}
    const send=(payload)=>submit({...payload,command_seq:system.command_seq,command_id:crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`});
    const button=(text,payload,allowed=true)=>{const b=el('button',text,'strategy-command');b.type='button';b.dataset.strategyAllowed=allowed?'1':'0';b.disabled=!allowed;if(!allowed)b.title='当前身份、战局阶段或议事冷却不允许此操作';b.onclick=()=>send(payload);return b;};
    const row=wars.find(w=>w.id===selected)||wars[0];
    if(row){
      selected=row.id;
      if(wars.length>1){const select=el('select');select.setAttribute('aria-label','选择战争');wars.forEach(w=>{const option=el('option',`${w.attacker} / ${w.defender} · ${phases[w.status]}`);option.value=w.id;option.selected=w.id===selected;select.append(option);});select.onchange=()=>{selected=select.value;campaign=null;render(system,saveId,submit);};header.append(select);}
      const hero=el('div',undefined,'strategy-hero');
      const side=(label,name,commander,cls)=>{const box=el('div',undefined,`strategy-side ${cls}`);box.append(el('small',label),el('strong',name),el('span',`统帅 · ${commander}`));return box;};
      const center=el('div',undefined,'strategy-balance');center.append(el('b',phases[row.status]),el('strong',row.score>0?`+${row.score}`:String(row.score)),el('small',`历时 ${number(row.elapsed)} 年`));
      hero.append(side('进攻议盟',row.attacker,row.commanders.attacker,'strategy-attack'),center,side('守备议盟',row.defender,row.commanders.defender,'strategy-defend'));root.append(hero);
      const scale=el('div',undefined,'strategy-scale');scale.setAttribute('role','meter');scale.setAttribute('aria-label','战争态势，正值偏向攻方');scale.setAttribute('aria-valuemin','-100');scale.setAttribute('aria-valuemax','100');scale.setAttribute('aria-valuenow',row.score);const marker=el('i');marker.style.left=`${50+row.score/2}%`;scale.append(marker);root.append(scale);
      const progress=el('ol',undefined,'strategy-progress');['mobilizing','active','armistice','settling','ended'].forEach((phase,i)=>{const node=el('li',phases[phase],phase===row.status?'current':'');node.append(el('small',String(i+1).padStart(2,'0')));progress.append(node);});root.append(progress);
      const nav=el('nav',undefined,'strategy-tabs');nav.setAttribute('aria-label','战争详情');nav.setAttribute('role','tablist');['态势','战役','议事','战报'].forEach((name,index)=>{const b=el('button',name);b.type='button';b.setAttribute('role','tab');b.setAttribute('aria-selected',String(tab===name));b.tabIndex=tab===name?0:-1;b.onclick=()=>{tab=name;render(system,saveId,submit);};b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const names=['态势','战役','议事','战报'];tab=names[e.key==='Home'?0:e.key==='End'?3:(index+(e.key==='ArrowLeft'?-1:1)+4)%4];render(system,saveId,submit);root.querySelector('[aria-selected=true]')?.focus();}};nav.append(b);});root.append(nav);
      const body=el('div',undefined,'strategy-body');body.setAttribute('role','tabpanel');root.append(body);
      const command=(text,payload,allowed=true)=>button(text,{war_id:row.id,expected_revision:row.revision,...payload},allowed);
      if(tab==='态势'){
        const map=svg('svg',{viewBox:compact?'0 0 340 250':'0 0 680 250',class:'strategy-theatre',role:'img','aria-label':`${row.attacker}与${row.defender}的组织战役示意，不代表地图距离`});
        map.append(svg('path',{d:'M0 218 Q80 120 160 185 T330 166 T490 180 T680 140',class:'strategy-mountains'}));
        row.campaigns.forEach((c,i)=>{const y=65+i*114,m=compact?170:340,left=compact?38:110,right=compact?302:570;map.append(svg('path',{d:`M${left} ${y} C${m-80} ${y-35} ${m+80} ${y+35} ${right} ${y}`,class:'strategy-road'}));const dot=svg('circle',{cx:m,cy:y,r:18,class:'strategy-front'});map.append(dot);const seal=svg('text',{x:m,y:y+5,'text-anchor':'middle'});seal.textContent=c.phase==='engaged'?'战':c.phase==='home'?'定':'行';map.append(seal);[[left,c.attacker],[right,c.defender]].forEach(([x,name],index)=>{map.append(svg('circle',{cx:x,cy:y,r:6,class:'strategy-pin'}));const t=svg('text',{x:compact?(index?330:10):x,y:y-20,'text-anchor':compact?(index?'end':'start'):'middle',class:'strategy-map-label'});t.textContent=compact&&name.length>9?name.slice(0,8)+'…':name;const title=svg('title');title.textContent=name;t.append(title);map.append(t);});const place=svg('text',{x:m,y:y+42,'text-anchor':'middle',class:'strategy-map-place'});place.textContent=c.location;map.append(place);});
        if(!row.campaigns.length){const t=svg('text',{x:compact?170:340,y:120,'text-anchor':'middle',class:'strategy-map-label'});t.textContent='征询组织承诺 · 尚未开拔';map.append(t);}body.append(map);
        const stats=el('div',undefined,'strategy-stats');[[row.commitments.length,'承诺组织'],[row.campaigns.length,'组织战役'],[row.campaigns.reduce((n,c)=>n+c.battles,0),'实际交锋']].forEach(([v,label])=>{const box=el('div');box.append(el('strong',String(v)),el('small',label));stats.append(box);});body.append(stats);
        const goals=el('div',undefined,'strategy-goals');row.objectives.forEach(o=>{const g=el('div');g.append(el('span',o.status==='completed'?'◆':'◇','strategy-goal-icon'),el('b',o.name),el('small',o.status==='completed'?(o.result>0?'攻方达成':o.result<0?'守方达成':'相持结束'):'执行中'));goals.append(g);});body.append(goals);
      }else if(tab==='战役'){
         const grid=el('div',undefined,'strategy-campaigns');row.campaigns.forEach(c=>{const b=el('button',undefined,`strategy-campaign ${campaign===c.id?'selected':''}`);b.type='button';b.dataset.campaignId=c.id;b.setAttribute('aria-pressed',String(campaign===c.id));b.append(el('small',`${stages[c.phase]} · ${c.location}`),el('b',`${c.attacker} → ${c.defender}`),el('span',`${c.coalitions?.attacker.length||1} 宗 对 ${c.coalitions?.defender.length||1} 宗 · ${c.battles} 次交锋${c.remaining?` · 行程余 ${c.remaining} 年`:c.phase==='engaged'?` · 下次会战 ${c.next_in} 年后`:''}`));b.onclick=()=>{campaign=c.id;render(system,saveId,submit);};grid.append(b);});body.append(grid);
         const c=row.campaigns.find(c=>c.id===campaign)||row.campaigns[0];if(c){campaign=c.id;const detail=el('section',undefined,'strategy-detail');detail.append(el('h4',`${c.attacker} / ${c.defender}`),el('p',`已实际调拨军需 ${number(c.paid)} · 交锋 ${c.battles} 场`,'strategy-caption'));
           const armies=el('div',undefined,'strategy-armies');for(const side of ['attacker','defender']){const column=el('div',undefined,`strategy-army strategy-army-${side}`);column.append(el('h5',side==='attacker'?'进攻联军':'守备联军'));(c.coalitions?.[side]||[]).forEach(o=>{const card=el('div',undefined,'strategy-unit');card.append(el('b',o.name),el('span',`${o.count} 名 · ${stages[o.phase]||o.phase}`),el('small',o.remaining?`行程余 ${o.remaining} 年`:'原组织名册'));column.append(card);});armies.append(column);}detail.append(armies);
           if(row.player_commander&&row.status==='active'){const reserve=el('section',undefined,'strategy-reserves');reserve.append(el('h5','闲置预备队'));if(c.dispatch_choices?.length){const form=el('div',undefined,'strategy-dispatch');const select=el('select');select.setAttribute('aria-label','选择闲置宗门');c.dispatch_choices.forEach(o=>{const option=el('option',`${o.name} · ${number(o.cost)} 灵石 · 行军 ${o.years} 年`);option.value=o.id;select.append(option);});const dispatch=command('调入此战役',{});dispatch.onclick=()=>{const o=c.dispatch_choices.find(o=>o.id===select.value);if(o)send({war_id:row.id,expected_revision:row.revision,action:'dispatch',campaign_id:c.id,org_id:o.id,org_kind:o.kind,expected_cost:o.cost});};form.append(select,dispatch);reserve.append(form);}else reserve.append(el('p','暂无可调遣的闲置宗门','strategy-caption'));reserve.append(el('small','行军、交战、撤军中的宗门均不可调遣。','strategy-caption'));detail.append(reserve);}
          if(c.org){const local=el('div',undefined,'strategy-commands');for(const [name,stance] of [['本部固守','hold'],['本部进攻','advance']])local.append(command(name,{action:'campaign_stance',campaign_id:c.id,org_id:c.org.id,org_kind:c.org.kind,stance},c.can_withdraw));local.append(command('撤回本组织',{action:'withdraw',campaign_id:c.id,org_id:c.org.id,org_kind:c.org.kind},c.can_withdraw));detail.append(local);}
          const reports=el('div',undefined,'strategy-reports');(c.reports||[]).forEach(r=>{const report=el('details');report.append(el('summary',`${r.age} 年 · ${r.title}`),el('p',r.text));reports.append(report);});detail.append(reports);body.append(detail);
        }else body.append(el('p','组织承诺后，战役将在此展开。','strategy-caption'));
      }else if(tab==='议事'){
         const ledger=el('div',undefined,'strategy-commitments');row.commitments.forEach(c=>{const line=el('div');line.append(el('span',c.side==='attacker'?'攻':'守','strategy-org-seal'),el('b',c.name),el('small',`${c.idle?'闲置预备':'战役占用'} · 批准上限 ${number(c.budget)}`));ledger.append(line);});body.append(ledger);
        const actions=el('div',undefined,'strategy-commands');row.commit_choices.forEach(o=>{const b=command(`批准 ${o.name} 出征`,{action:'commit',org_id:o.id,org_kind:o.kind,expected_budget:o.budget});b.append(el('small',`军费上限 ${number(o.budget)} 灵石`,'strategy-budget'));actions.append(b);});(row.nomination_choices||[]).forEach(side=>actions.append(command('竞任联军统帅',{action:'nominate',side})));if(row.player_commander){actions.append(command('联军转入守备',{action:'stance',stance:'hold'}),command('联军恢复进攻',{action:'stance',stance:'advance'}));}actions.append(command('提出总停战',{action:'offer_peace'},row.can_peace));body.append(actions,el('p','承诺由原组织执行；停战须取得对方确认。','strategy-caption'));
      }else{
        const timeline=el('ol',undefined,'strategy-timeline');[...row.logs].reverse().forEach(log=>{const li=el('li');li.append(el('small',`${log.age} 年`),el('b',log.title),el('p',log.text));timeline.append(li);});body.append(timeline);
      }
    }
    if(system.legacy_relations?.length){const legacy=el('details',undefined,'strategy-legacy');legacy.append(el('summary',`旧约待确认 · ${system.legacy_relations.length}`));system.legacy_relations.forEach(r=>{const line=el('div');line.append(el('span',r.name),button(r.status==='war'?'确认并收束无实战旧案':'确认原约归属本界',{action:'adopt_relation',relation_key:r.key},r.can_adopt));legacy.append(line);});root.append(legacy);}
    if(system.legacy_wars?.length){const legacy=el('details',undefined,'strategy-legacy');legacy.append(el('summary',`旧族战待接续 · ${system.legacy_wars.length}`));system.legacy_wars.forEach(w=>{const line=el('div');line.append(el('span',`${w.name} · 原案条款：${w.terms.join('、')}`),button('表决结清原案',{action:'settle_legacy',legacy_id:w.id,expected_battles:w.battles,expected_status:w.status},w.allowed));legacy.append(line);});root.append(legacy);}
    syncBusy();
  }
  function syncBusy(){document.querySelectorAll('[data-strategy-allowed]').forEach(b=>b.disabled=document.body.classList.contains('busy')||b.dataset.strategyAllowed!=='1');}
  window.StrategicWarPanel={render,syncBusy};
  window.addEventListener('resize',()=>{if(latest&&compact!==(window.innerWidth<600))render(...latest);});
})();
