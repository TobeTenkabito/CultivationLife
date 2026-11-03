(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1}),pct=n=>fmt((n||0)*100)+'%';
  function render(game,act){
    const data=game.upper_voisinages?.monster_body;
    const panel=document.getElementById('monster-body-card'),root=document.getElementById('monster-body-content');
    const dock=document.querySelector('[data-panel-target="monster-body"]');
    const available=!!data?.available;panel.classList.toggle('hidden',!available);dock.classList.toggle('hidden',!available);
    if(!available){root.replaceChildren();window.UtilityPanels?.close('monster-body');window.UtilityPanels?.schedule('monster-body',null);return;}
    window.UtilityPanels.schedule('monster-body',()=>{root.replaceChildren();paint(root,data,act);});
  }
  function paint(root,data,act){
    const section=el('section',null,'monster-body');
    window.BodyCultivationUI.hero(section,{family:'monster',title:`妖躯五蜕 · ${data.level}/50层 · 每十层解锁一蜕`,titleClass:'monster-body-title',level:data.level,
      names:data.rows.map(r=>r.name),description:'玄肤护身，逆骨承锋，五蜕渐返祖脉。专属材料仅幽冥界产出，烈脏每次择一施权。'});
    const button=(label,action,key,level,disabled)=>{const b=el('button',label);b.type='button';b.disabled=disabled;b.onclick=()=>act({action,voisinage_id:key,expected_level:level});return b;};
    const materials=(parent,rows)=>{for(const r of rows)window.BodyCultivationUI.material(parent,r,'monster-body-material');};
    section.append(el('p','普通炼体须达100层。妖躯上限50层，五蜕各可独立修炼至十重，实扣机缘与对应材料。'));
    const bar=el('progress');bar.max=50;bar.value=data.level;bar.setAttribute('aria-label','妖躯修炼进度');section.append(bar);
    if(data.body_cost){section.append(el('p',`下一层：${fmt(data.body_cost.opportunity)}机缘`));materials(section,data.body_materials);}
    const train=button('锻炼下一层妖躯','monster_body_train',null,data.level,!data.can_train_body);train.dataset.monsterBodyTrain='';section.append(train);
    if(data.body_reason)section.append(el('p',data.body_reason,'doctrine-note'));
    const grid=el('div',null,'monster-body-grid');
    for(const [index,row] of data.rows.entries()){
      const card=el('section',null,'doctrine-entry monster-change');card.dataset.change=row.id;card.append(el('h3',`${row.name} · ${row.unlocked?`${row.level}/10重`:`妖躯${row.unlock_level}层解锁`}`));
      const e=row.effects;const text={xuanfu:`免疫凡伤，仙级攻击的战斗态势削减降低${pct(e.state_guard)}；肉身损伤另计。`,nigu:`自身邻域存在时，每段敌方主动施权有${pct(e.evade)}概率闪避，在该段实际作用时判定。`,liezang:'实际闪避后免费施权一次。初始治疗，培养逐渐开放心神、稳固、镇压、封锁及禁制；每次择一，不同机制可联动，同一角色机制不得沿因果链重入。',feixue:`被支配后消耗本场可用容量的${pct(e.release_cost)}元力解除支配，本轮不重算对抗。`,shenhun:`每场一次，轮首元力比例低于${pct(e.exchange_threshold)}且低于对手时交换比例，按各自可用容量回写。`}[row.id];
      card.append(el('p',row.unlocked?text:'达到解锁层数后可独立培养。'));
      if(row.unlocked&&row.id==='liezang')card.append(el('p',`数值效果${pct(e.retaliate_power)}；封锁与禁制类反击成功率${pct(e.retaliate_control??1)}，仍须通过目标抵抗。`));
      materials(card,row.materials);
      window.BodyCultivationUI.card(card,{index,name:row.name,level:row.level,unlocked:row.unlocked,unlockLevel:row.unlock_level});
      if(row.cost){card.append(el('p',`下一重：${fmt(row.cost.opportunity)}机缘`));const b=button(`修炼${row.name}至第${row.level+1}重`,'monster_body_refine',row.id,row.level,!row.can_train);b.dataset.monsterChange=row.id;card.append(b);}
      if(row.reason)card.append(el('p',row.reason,'doctrine-note'));grid.append(card);
    }
    section.append(grid);
    const select=el('select');select.setAttribute('aria-label','烈脏每次施权择一');select.disabled=!data.can_select;
    for(const r of data.choices){const option=el('option',r.name+(r.unlocked?'':'（培养后解锁）'));option.value=r.id;option.disabled=!r.unlocked;select.append(option);}
    select.value=data.reaction;select.onchange=()=>act({action:'monster_body_select',voisinage_id:select.value});
    section.append(el('label','烈脏选择：'),select,el('p','自动择一优先恢复自身，再镇压或封锁刚才的施术者。固定选择无合法目标时不执行。选项随入战快照冻结。','muted'));root.append(section);
  }
  window.MonsterBody=Object.freeze({render});
})();
