(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1});
  const effects={strike:'邻域杀伤',suppress:'镇压',seal:'封锁退路与支援',restrict:'禁制功法',restore_body:'修复肉身',restore_spirit:'稳定心神',restore_field:'修复邻域稳固'};
  const opened=new Set();let owner=null;
  function render(game,act){
    const data=game.upper_voisinages||{},aperture=game.aperture||{};
    const card=document.getElementById('upper-voisinage-card'),dock=document.querySelector('[data-panel-target="upper-voisinage"]');
    card.classList.toggle('hidden',!data.available);dock.classList.toggle('hidden',!data.available);
    if(!data.available){window.UtilityPanels?.close('upper-voisinage');return;}
    if(owner!==game.id){owner=game.id;opened.clear();}
    card.querySelector('h2').textContent=data.title;card.setAttribute('aria-label',data.title);
    dock.title=data.title;dock.querySelector('small').textContent=data.title;
    const root=document.getElementById('upper-voisinage-content');root.replaceChildren();
    const blocked=!!game.pending_event||!!game.active_trial||!game.player.alive||!!game.imprisonment;
    const button=(text,payload,disabled=false)=>{const b=el('button',text);b.type='button';b.disabled=blocked||disabled;b.onclick=()=>act(payload);return b;};
    root.append(el('p',data.description,'doctrine-lead'),el('p','本界邻域可兼修，每场只采用当前选定的一种。领悟即能上阵，培养至九级；消耗所示积累后必定进益，不额外推进年月。离界后进度保留，本界邻域暂时沉寂。','muted'));
    const reserve=el('section',null,'doctrine-entry');
    const refill=el('button',`前往${aperture.title}凝练`);refill.type='button';refill.onclick=()=>window.UtilityPanels.open('immortal-aperture');
    reserve.append(el('h3',`${data.energy} ${fmt(aperture.current)} / ${fmt(aperture.capacity)}`),el('p','展开、维持与施权都消耗这份储量，战后不会自动补满。恢复邻域可以修复伤势或稳固，不能恢复元力。'),refill);root.append(reserve);
    root.append(el('p',`现有机缘 ${fmt(data.opportunity)} · 灵石 ${fmt(data.stones)}`));
    for(const row of data.rows){
      const panel=el('details',null,'doctrine-entry doctrine-compact');panel.dataset.voisinageId=row.id;
      panel.open=opened.has(row.id);panel.addEventListener('toggle',()=>{if(panel.isConnected){if(panel.open)opened.add(row.id);else opened.delete(row.id);}});
      const summary=el('summary'),seal=el('span',row.name[0],'doctrine-seal'),text=el('span');
      text.append(el('b',row.name),el('small',`${row.level?`Lv${row.level}${row.active?' · 已上阵':''}`:'尚未领悟'} · ${row.field.effects.map(e=>effects[e.kind]).join('、')}`));summary.append(seal,text);panel.append(summary,el('p',row.description));
      const f=row.field;panel.append(el('p',`${row.level?'当前威能':'领悟后威能'}：稳固 ${fmt(f.stability)} · 侵夺 ${fmt(f.incursion)} · 权能 ${fmt(f.authority)}`),el('p',`展开 ${fmt(f.opening_cost)} / 每轮维持 ${fmt(f.upkeep_cost)} / 施权 ${fmt(f.effect_cost)} ${data.energy} · 每个额外覆盖对象另耗 ${fmt(f.extra_target_cost)}，最多 ${f.max_targets} 个对象。`,'muted'));
      if(row.level)panel.append(button(row.active?'当前上阵':'选为斗法邻域',{action:'select',voisinage_id:row.id},row.active));
      if(row.cost){
        const c=row.cost;
        if(c.discount)panel.append(el('p',`本界机构政务生效：机缘与灵石费用减免 ${Math.round(c.discount*100)}%，下列费用已含优惠。`,'doctrine-note'));
        panel.append(el('p',`${row.level?'培养':'领悟'}至 Lv${row.level+1}：须第 ${c.realm} 阶修为，机缘 ${fmt(c.opportunity)}、灵石 ${fmt(c.stones)}${c.materials?`、${c.material_name} ${c.owned_materials} / ${c.materials} 份`:''}。`));
        if(row.next_field){const n=row.next_field;panel.append(el('p',`下一层：稳固 ${fmt(n.stability)} · 侵夺 ${fmt(n.incursion)} · 权能 ${fmt(n.authority)}`,'muted'));}
        if(c.materials)panel.append(el('p','筑域材料来自本界坊市的炼器材料栏，自动优先消耗品相较低的同种普通材料。','muted'));
        if(row.reason)panel.append(el('p',row.reason,'doctrine-note'));
        panel.append(button(row.level?'培养下一层':'领悟并开域',{action:'train',voisinage_id:row.id},!row.can_train));
      }else panel.append(el('p','九级圆成，已达本界修习上限。','doctrine-note'));
      root.append(panel);
    }
    root.append(el('p','三界修习不需仙界道统、注解或仙痕。机缘仍有上限，培养与境界冲关需分别准备；本体普通突破、天劫和已启用的道途规则各自适用。','muted'));
  }
  window.UpperVoisinagePanel={render};
})();
