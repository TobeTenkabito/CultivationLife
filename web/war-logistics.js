(() => {
  const node=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const num=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1});
  window.WarLogistics={render(root,war,submit){
    if(!war.supplies)return;
    const grid=node('div',null,'war-supply-grid');
    for(const side of ['attacker','defender']){
      const r=war.supplies[side],card=node('section',null,'war-supply-card');
      card.append(node('small',side==='attacker'?'进攻方军需':'防守方军需'));
      if(r.known){
        card.append(node('strong',r.balance==null?'尚未筹备':`${num(r.balance)} 灵石折值`));
        card.append(node('p',`标准会战参考成本 ${num(r.need)} · 按实物可维持 ${num(r.turns)} 回合`));
        if(r.realm_groups)card.append(node('small',`实际参战：${Object.entries(r.realm_groups).map(([rank,count])=>`${rank} 阶 ${count} 人`).join('、')||'暂无在役修士'}`));
        const bar=node('progress');bar.max=1;bar.value=r.coverage;bar.setAttribute('aria-label','上一回合补给率');card.append(bar);
        card.append(node('small',`上一回合补给 ${Math.round(r.coverage*100)}% · 战力 ${Math.round(r.factor*100)}%`));
        card.append(node('small',`最近据点：${r.base||'待确定'} · 陆路 ${num(r.distance)} 年 · 运输损耗 ${Math.round(r.loss*100)}%`));
        card.append(node('small',`累计真实采购 ${num(r.purchased)} · 消耗及损毁 ${num(r.destroyed)}`));
        if(r.items?.length){const details=node('details'),title=node('summary','查看实物清单');details.append(title);
          r.items.forEach(i=>details.append(node('small',`${i.name} ×${num(i.quantity)} · 现值 ${num(i.value)}`)));card.append(details);}
      }else{
        card.append(node('strong',r.snapshot==null?'敌情未明':`${num(r.snapshot)} 灵石折值`));
        card.append(node('p',r.snapshot==null?'派出侦察队后，才有机会获知敌方储备。':`第 ${r.snapshot_round} 回合侦察快照 · 约 ${num(r.snapshot_turns)} 回合 · ${r.snapshot_base}`));
        card.append(node('small','情报不会实时更新；侦察可能失败。'));
      }
      grid.append(card);
    }
    root.append(grid);
    if(war.player_controls&&war.status==='active'){
      const commands=node('section',null,'war-command-group');commands.append(node('h3','军需与情报'));
      const actions=node('div',null,'war-strategy-grid');
      for(const r of war.supply_actions||[]){const card=node('div',null,'war-strategy');
        const b=node('button',r.name);b.type='button';b.disabled=!r.allowed;b.dataset.warStrategy=r.action;
        b.onclick=()=>submit(r.action);card.append(b,node('small',r.description));
        if(r.reason)card.append(node('small',r.reason,'war-action-reason'));actions.append(card);}
      commands.append(actions);root.append(commands);
    }
  }};
})();
