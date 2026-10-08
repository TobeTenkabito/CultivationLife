(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1});
  const effects={strike:'邻域杀伤',suppress:'镇压',seal:'封锁退路与支援',restrict:'禁制功法',isolate:'隔绝支援',restore_body:'修复肉身',restore_spirit:'稳定心神',restore_field:'修复邻域稳固'};
  const features={fortify:'固守',opening:'先发',retaliate:'反击',sacrifice:'舍身',frugal:'节用',shelter:'庇护',execution:'终局'};
  const rankName=n=>!n?'尚未领悟':n===13?'至臻':`${['初成','化境','大成'][Math.floor((n-1)/4)]}${(n-1)%4+1}层`;
  const effectName=e=>effects[e.kind]+(e.restriction==='voisinage'?'（邻域）':'');
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
    root.append(el('p',data.description,'doctrine-lead'),el('p','本界邻域可兼修，每场只采用当前选定的一种。领悟即能上阵，依次修至初成、化境、大成各四层及至臻；消耗所示积累后必定进益，不额外推进年月。离界后进度保留，本界邻域暂时沉寂。','muted'));
    const reserve=el('section',null,'doctrine-entry');
    const refill=el('button',`前往${aperture.title}凝练`);refill.type='button';refill.onclick=()=>window.UtilityPanels.open('immortal-aperture');
    reserve.append(el('h3',`${data.energy} ${fmt(aperture.current)} / ${fmt(aperture.capacity)}`),el('p','展开、维持与施权都消耗这份储量，战后不会自动补满。恢复邻域可以修复伤势或稳固，不能恢复元力。'),refill);root.append(reserve);
    root.append(el('p',`现有机缘 ${fmt(data.opportunity)} · 灵石 ${fmt(data.stones)}`));
    const form=data.true_form;
    if(form){
      const box=el('section',null,'doctrine-entry true-form-panel');box.dataset.trueForm='';
      box.append(el('span','血脉 · 本相 · 归真','true-form-eyebrow'),el('h3',form.name||'本相铸域'));
      if(form.reason)box.append(el('p',form.reason,'doctrine-note'));
      else{
        box.append(el('p',form.route==='ancestral'?'真灵返祖 · 沿祖相而铸域':'自成血脉 · 以已确认祖谱为根'));
        const stages=el('div',null,'true-form-stages');
        for(const [rank,name] of [[1,'立相'],[5,'铭辅'],[9,'调校'],[13,'归真']]){
          const step=el('span',`${rankName(rank)} · ${name}`,Number(form.level||0)>=rank?'attained':'');stages.append(step);
        }box.append(stages);
        const preview=form.preview;
        box.append(el('p',`本源权能：${preview.effects.map(e=>effects[e]).join(' / ')} · 特征：${features[preview.feature.kind]} ${fmt(preview.feature.value*100)}%`));
        box.append(el('p',`基础偏向：稳固 ×${fmt(preview.stability)} · 侵夺 ×${fmt(preview.incursion)} · 权能 ×${fmt(preview.authority)}。同阶使用通用冥域的修习报价与元力消耗。`,'muted'));
        const choose=(label,choices,action,names)=>{
          const wrap=el('div',null,'true-form-choice'),field=el('label',label),select=el('select');
          select.setAttribute('aria-label',label);for(const key of choices){const option=el('option',names[key]||key);option.value=key;select.append(option);}
          field.append(select);wrap.append(field);
          const go=button(action==='true_form_confirm'?'确认本相蓝图':action==='true_form_secondary'?'铭定辅权能':'锁定归真方向',{},false);
          go.dataset.trueFormAction=action;go.onclick=()=>act({action,voisinage_id:select.value});wrap.append(go);box.append(wrap);
        };
        if(!form.blueprint){
          const cost=form.first_cost;
          box.append(el('p',`确认后领悟一级需：机缘 ${fmt(cost.opportunity)}、灵石 ${fmt(cost.stones)}${cost.materials?`、${cost.material_name} ×${cost.materials}`:''}。`));
          box.append(el('p','预览不消耗资源。确认后主权能永久锁定；不会赠送一级境界或补充元力。','doctrine-note'));
          choose('主权能',form.choices,'true_form_confirm',effects);
        }else{
          const b=form.blueprint;
          box.append(el('p',`主权能：${effects[b.primary]} · 辅权能：${effects[b.secondary]||'初成四层后铭定'} · 归真方向：${form.tunings[b.tuning]||'化境四层后择定'}`));
          if(form.level===4&&!b.secondary_locked)choose('辅权能',form.secondary_choices.filter(k=>k!==b.primary),'true_form_secondary',effects);
          if(form.level===8&&!b.tuning_locked)choose('归真方向',Object.keys(form.tunings),'true_form_tuning',form.tunings);
          if(b.finalized)box.append(el('p','本相归真 · 主辅相合，祖相长存。','doctrine-note'));
          else box.append(el('p','下方展开本相条目修习或上阵。已铭定的选择随蓝图保存，离界与关闭 DLC 均不会重置。','muted'));
        }
      }root.append(box);
    }
    const soul=data.soul_form;
    if(soul){
      const box=el('section',null,'doctrine-entry true-form-panel soul-form-panel');box.dataset.soulForm='';
      box.append(el('span','前尘 · 今心 · 后愿','true-form-eyebrow'),el('h3','照魂归真'));
      const stages=el('div',null,'true-form-stages');
      for(const [rank,name] of [[1,'定魂'],[5,'铭辅'],[9,'魂痕'],[13,'归一']])stages.append(el('span',`${rankName(rank)} · ${name}`,soul.level>=rank?'attained':''));
      box.append(stages);
      if(soul.reason)box.append(el('p',soul.reason,'doctrine-note'));
      else{
        const history=el('details',null,'doctrine-compact');history.append(el('summary','前尘回望 · 真实经历'));
        for(const e of soul.evidence)history.append(el('p',`${e.title}：${e.text}`));
        if(!soul.evidence.length)history.append(el('p','尚无可供回望的重大经历。十二魂因均可通过标准照魂试炼参悟。'));
        box.append(history);
        const b=soul.blueprint;
        if(!b){
          const controls=el('div',null,'true-form-choice'),cause=el('select'),route=el('select'),preview=el('div',null,'soul-form-preview');
          const cLabel=el('label','魂因'),rLabel=el('label','归真道路预览');cause.setAttribute('aria-label','魂因');route.setAttribute('aria-label','归真道路预览');
          for(const [key,name] of Object.entries(soul.causes))cause.add(new Option(name,key));
          if(soul.contemplation){cause.value=soul.contemplation.cause;cause.disabled=true;box.append(el('p',`照魂进度：${soul.contemplation.elapsed} / ${soul.contemplation.required} 年；处理当前事件后继续，已完成时间保留。`,'doctrine-note'));}
          for(const [key,name] of Object.entries(soul.routes))route.add(new Option(name,key));
          cLabel.append(cause);rLabel.append(route);controls.append(cLabel,rLabel);box.append(controls,preview);
          const show=()=>{const f=soul.forms[`${cause.value}.${route.value}`];preview.replaceChildren(el('h4',f.name),el('p',f.description+' '+f.battle_role),el('p',`主权能：${effectName(f.effects[0])} · 化境基础辅效：${effectName(f.effects[1])}`),el('p',`辅权能候选：${f.secondary_choices.map(effectName).join(' / ')}`),el('p',`魂痕候选：${f.feature_choices.map(k=>features[k]).join(' / ')}`),el('p',`稳固 ×${f.stability} · 侵夺 ×${f.incursion} · 权能 ×${f.authority}`),el('p',`取舍：${f.weakness}`,'doctrine-note'));};cause.onchange=route.onchange=show;show();
          const start=button('照前尘 · 参悟一单位',{});start.onclick=()=>act({action:'soul_form_contemplate',voisinage_id:cause.value});box.append(start,el('p','参悟消耗一单位真实时间；随后在试炼中选择守念、断执或化愿。确认永久定性，领悟另按下方报价修习，不补充元力。','muted'));
        }else{
          const f=soul.forms[`${b.cause}.${b.route}`];box.append(el('h4',f.name),el('p',`${soul.causes[b.cause]} · ${soul.routes[b.route]} · ${rankName(soul.level)}`),el('p',f.battle_role),el('p',f.weakness,'doctrine-note'));
          const choose=(title,choices,action)=>{const wrap=el('div',null,'true-form-choice'),label=el('label',title),select=el('select');select.setAttribute('aria-label',title);for(const [key,name] of choices)select.add(new Option(name,key));label.append(select);const go=button(title,{});go.onclick=()=>act({action,voisinage_id:select.value});wrap.append(label,go);box.append(wrap);};
          if(soul.level===4&&!b.secondary_locked)choose('铭定魂相辅权能',f.secondary_choices.map(e=>[e.kind+(e.restriction?':'+e.restriction:''),effectName(e)]),'soul_form_secondary');
          if(soul.level===8&&!b.feature_locked)choose('铭定魂痕',b.offered_candidates.map(k=>[k,features[k]]),'soul_form_feature');
          box.append(el('p',`辅权能：${b.secondary?effectName(b.secondary):'初成四层后铭定'} · 魂痕：${features[b.feature]||'化境四层后铭定'}`));
          if(b.finalized)box.append(el('p','真我归一 · 前尘仍在，魂相已成。','doctrine-note'));
        }
      }root.append(box);
    }
    for(const row of data.rows){
      const panel=el('details',null,'doctrine-entry doctrine-compact');panel.dataset.voisinageId=row.id;
      panel.open=opened.has(row.id);panel.addEventListener('toggle',()=>{if(panel.isConnected){if(panel.open)opened.add(row.id);else opened.delete(row.id);}});
      const summary=el('summary'),seal=el('span',row.name[0],'doctrine-seal'),text=el('span');
      text.append(el('b',row.name),el('small',`${row.level?`${rankName(row.level)}${row.active?' · 已上阵':''}`:'尚未领悟'} · ${row.field.effects.map(e=>effects[e.kind]).join('、')}`));summary.append(seal,text);panel.append(summary,el('p',row.description));
      const f=row.field;panel.append(el('p',`${row.level?'当前威能':'领悟后威能'}：稳固 ${fmt(f.stability)} · 侵夺 ${fmt(f.incursion)} · 权能 ${fmt(f.authority)}`),el('p',`展开 ${fmt(f.opening_cost)} / 每轮维持 ${fmt(f.upkeep_cost)} / 施权 ${fmt(f.effect_cost)} ${data.energy} · 每个额外覆盖对象另耗 ${fmt(f.extra_target_cost)}，最多 ${f.max_targets} 个对象。`,'muted'));
      if(row.level)panel.append(button(row.active?'当前上阵':'选为斗法邻域',{action:'select',voisinage_id:row.id},row.active));
      if(row.cost){
        const c=row.cost;
        if(c.discount)panel.append(el('p',`本界机构政务生效：机缘与灵石费用减免 ${Math.round(c.discount*100)}%，下列费用已含优惠。`,'doctrine-note'));
        panel.append(el('p',`${row.level?'培养':'领悟'}至 ${rankName(row.level+1)}：须第 ${c.realm} 阶修为，机缘 ${fmt(c.opportunity)}、灵石 ${fmt(c.stones)}${c.materials?`、${c.material_name} ${c.owned_materials} / ${c.materials} 份`:''}。`));
        if(row.next_field){const n=row.next_field;panel.append(el('p',`下一层：稳固 ${fmt(n.stability)} · 侵夺 ${fmt(n.incursion)} · 权能 ${fmt(n.authority)}`,'muted'));}
        if(c.materials)panel.append(el('p','筑域材料来自本界坊市的炼器材料栏，自动优先消耗品相较低的同种普通材料。','muted'));
        if(row.reason)panel.append(el('p',row.reason,'doctrine-note'));
        panel.append(button(row.level?'培养下一层':'领悟并开域',{action:'train',voisinage_id:row.id},!row.can_train));
      }else panel.append(el('p','至臻圆成，已达邻域培养上限。','doctrine-note'));
      root.append(panel);
    }
    root.append(el('p','三界修习不需仙界道统、注解或仙痕。机缘仍有上限，培养与境界冲关需分别准备；突破劫难与邻域培养分别结算；前两劫存活五轮，末劫须击杀全部敌人。','muted'));
  }
  window.UpperVoisinagePanel={render};
})();
