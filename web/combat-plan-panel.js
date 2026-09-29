(() => {
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  function render(data,save){
    const p=data.combat_plan||{}, visible=!!p.manual;
    const card=document.getElementById('combat-plan-card');card.classList.toggle('hidden',!visible);
    document.querySelector('[data-panel-target="combat-plan"]').classList.toggle('hidden',!visible);
    if(!visible){window.UtilityPanels?.close('combat-plan');return;}
    const root=document.getElementById('combat-plan-content');root.replaceChildren();
    root.append(el('p','预案在开战时生效。战斗目的仍由当前行动决定；关闭手动后沿用自动策略，手动配置会保留。'));
    const form=el('form');form.className='combat-plan-form';
    const controls={};
    const add=(key,title,input)=>{const label=el('label');label.append(el('span',title),input);input.setAttribute('aria-label',title);controls[key]=input;form.append(label);return input;};
    const select=(key,title,options)=>{const n=el('select');for(const [value,text] of options){const o=el('option',text);o.value=value;n.append(o);}n.value=p[key];add(key,title,n);};
    select('stance','邻域姿态',[['press','侵夺敌方'],['guard','守护自身'],['protect','庇护己方同伴'],['off','不展开邻域']]);
    select('burst','高消耗术式',[['auto','依战况发动'],['early','有余力即发动'],['never','不主动发动']]);
    for(const [key,title,max,step,value] of [['investment','每轮追加仙力',1000000,1,p.investment],['mp_reserve','爆发法力保留线（%）',100,1,Math.round(p.mp_reserve*100)]]){
      const n=el('input');n.type='number';n.min=0;n.max=max;n.step=step;n.value=value;add(key,title,n);
    }
    for(const [key,title] of [['transformations','使用已配置变身'],['support_guard','由护主单位承担普通攻击']]){const n=el('input');n.type='checkbox';n.checked=p[key];add(key,title,n);}
    form.append(el('p',`当前可追加仙力为邻域基础投入上限的 ${p.investment_multiplier} 倍，超出按上限处理；须留足展开和维持消耗。`));
    const submit=el('button','保存战斗预案');submit.type='submit';submit.disabled=!!data.pending_event||!data.player.alive||!!data.active_trial;form.append(submit);
    form.onsubmit=event=>{event.preventDefault();save({stance:controls.stance.value,burst:controls.burst.value,investment:Number(controls.investment.value),mp_reserve:Number(controls.mp_reserve.value)/100,transformations:controls.transformations.checked,support_guard:controls.support_guard.checked});};root.append(form);
  }
  window.CombatPlanPanel={render};
})();
