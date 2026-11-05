(() => {
  const el = window.GameUi.element;
  const pct=n=>`${Math.round(100*n)}%`;
  function render(game,act){
    const data=game.upper_voisinages?.ghost_body;
    const panel=document.getElementById('ghost-body-card'),root=document.getElementById('ghost-body-content');
    const dock=document.querySelector('[data-panel-target="ghost-body"]');
    const available=!!data?.available;
    panel.classList.toggle('hidden',!available);dock.classList.toggle('hidden',!available);
    if(!available){root.replaceChildren();window.UtilityPanels?.close('ghost-body');window.UtilityPanels?.schedule('ghost-body',null);return;}
    window.UtilityPanels.schedule('ghost-body',()=>{
      root.replaceChildren();const section=el('section',null,'monster-body ghost-body');
      window.BodyCultivationUI.hero(section,{family:'ghost',title:`鬼躯五法 · ${data.level}/50层`,titleClass:'ghost-body-title',level:data.level,
        names:data.rows.map(r=>r.name),description:'十层启一法，生灭皆留痕。五法独修使用各自专材，仅轮回界产出；战斗回复不修复永久魂基。'});
      section.append(el('p',`鬼躯筑基材料 · ${data.material_name}：持有 ${data.material_owned} 件`));
      const button=(text,action,key,level,disabled)=>{const b=el('button',text);b.type='button';b.disabled=disabled;
        b.onclick=()=>act({action,voisinage_id:key,expected_level:level});return b;};
      const price=c=>c?`${Number(c.opportunity).toLocaleString('zh-CN')}机缘${typeof c.materials==='number'?`、${data.material_name}×${c.materials}`:''}`:'已达上限';
      section.append(el('p',`下一层：${price(data.body_cost)}`));
      const train=button('修炼下一层鬼躯','ghost_body_train',null,data.level,!data.can_train_body);train.dataset.ghostBodyTrain='';section.append(train);
      if(data.body_reason)section.append(el('p',data.body_reason,'doctrine-note'));
      const grid=el('div',null,'monster-body-grid');
      for(const [index,row] of data.rows.entries()){
        const e=row.effects,card=el('section',null,'doctrine-entry ghost-body-change');card.dataset.ghostChange=row.id;
        const text={wuxiang:`免疫凡伤。自身态势与邻域稳固回复效率提高${pct(e.recovery_bonus)}，不提高元力或永久魂基回复。`,
          zhaoye:`一次邻域行动分为三段，每段继承${pct(e.split)}。随机合法目标，全体攻击仍为三段全体；只付费、计次一次。`,
          yuhun:`每名角色真实阵亡，回复${pct(e.death_restore)}态势与本场可用元力；制伏、逃离不算阵亡。`,
          wangqing:`按每段实际目标集合比较：不同则向其余敌人溢出${pct(e.forget)}实际伤害，相同则追加同比例一段伤害。`,
          yinguo:`每累计减少本场可用元力容量的${pct(e.karma_threshold)}，免费释放一次强度${pct(e.karma_power)}的全体攻击；回复不清空累计进度，可与照业、忘情联动。`}[row.id];
        card.append(el('h3',`${row.name} · ${row.unlocked?`${row.level}/10重`:`${row.unlock_level}层解锁`}`),el('p',text),el('p',`下一重：${price(row.cost)}`));
        window.BodyCultivationUI.card(card,{index,name:row.name,level:row.level,unlocked:row.unlocked,unlockLevel:row.unlock_level});
        for(const material of row.materials||[])window.BodyCultivationUI.material(card,material,'ghost-body-material');
        const b=button(row.level>=10?'已修至十重':`修炼${row.name}`,'ghost_body_refine',row.id,row.level,!row.can_train);b.dataset.ghostRefine=row.id;card.append(b);
        if(row.reason)card.append(el('p',row.reason,'doctrine-note'));grid.append(card);
      }
      section.append(grid,el('p','每段发出时锁定实际目标；同一角色的同一机制不能在自身因果链中再次进入，不同机制与不同分支可继续联动。','muted'));root.append(section);
    });
  }
  window.GhostBody=Object.freeze({render});
})();
