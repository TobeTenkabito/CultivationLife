(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1});
  function render(data, act, options={}) {
    for(const [name,visible] of [['immortal-aperture',data.available],['spirit-voisinage',data.available&&data.lower&&data.field]]) {
      document.getElementById(name+'-card').classList.toggle('hidden',!visible);
      document.querySelector(`[data-panel-target="${name}"]`).classList.toggle('hidden',!visible);
      if(!visible)window.UtilityPanels?.close(name);
    }
    if(!data.available)return;
    const root=document.getElementById('immortal-aperture-content');root.replaceChildren();
    const figure=el('figure',null,'aperture-reservoir');
    figure.style.setProperty('--reservoir-fill',`${Math.max(0,Math.min(100,data.current/data.capacity*100))}%`);
    const pool=el('div',null,'aperture-orb');pool.setAttribute('role','img');pool.setAttribute('aria-label',`${data.name} ${fmt(data.current)} / ${fmt(data.capacity)}`);
    pool.append(el('div',null,'aperture-water'),el('strong',`${fmt(data.current)} / ${fmt(data.capacity)}`),el('span',data.name));
    figure.append(pool,el('figcaption','仙窍 · 邻域所用的独立储量'));root.append(figure);
    root.append(el('p',data.lower?'下界无法维持完整仙域。凝练本源，仅得少量仿仙灵力；灵域威能为原域的 4%，同样经过邻域阶段结算。':'仙窍存储斗法所需仙灵力。展开、维持和施展邻域权能都会消耗储量，战后不会自动补满。'));
    if(data.lower)root.append(el('p',`封存仙灵力 ${fmt(data.sealed_reserve)}；回到三级界面才可使用。`,'muted'));
    root.append(el('p',`本源气血 ${fmt(data.origin_hp)} / ${fmt(data.max_hp)} · 本源法力 ${fmt(data.origin_mp)} / ${fmt(data.max_mp)}`),
      el('p',`每次凝练 ${fmt(data.refine_gain)} ${data.name}，消耗本源气血 ${fmt(data.hp_cost)}、本源法力 ${fmt(data.mp_cost)}。接近满储时按实际凝练量扣除。`));
    const refine=el('button',`凝练${data.name}`);refine.type='button';refine.disabled=options.pending||!options.alive||data.current>=data.capacity||(!data.lower&&data.conversion<1)||data.origin_hp<=data.hp_cost||data.origin_mp<data.mp_cost;
    refine.onclick=()=>act({action:'refine'});root.append(refine);
    root.append(el('p',`转化完成度 ${fmt(data.conversion*100)}%。仙窍圆池显示可消耗的储量，转化程度不会随战斗消耗降低。`,'muted'));
    const fields=document.getElementById('spirit-voisinage-content');fields.replaceChildren();
    if(!data.field)return;
    const f=data.field;fields.append(el('h3',f.name),el('p',`稳固 ${fmt(f.stability)} · 侵夺 ${fmt(f.incursion)} · 权能 ${fmt(f.authority)}`),
      el('p',`展开 ${fmt(f.opening_cost)} / 每轮维持 ${fmt(f.upkeep_cost)} / 施权 ${fmt(f.effect_cost)} 仿仙灵力。储量不足时领域消散。`));
    for(const book of data.spirit_fields||[]){const b=el('button',`${book.name} · Lv${book.level}${(data.active_manual||data.spirit_fields[0]?.id)===book.id?'（当前）':''}`);b.disabled=options.pending||!options.alive;b.onclick=()=>act({action:'select',manual_id:book.id});fields.append(b);}
    fields.append(el('p','灵域残解合参至 Lv4 即可运用，无需参悟道统。继续合参可强化灵域。下界残解仅在黑市、交换会、商盟寻访委托或修士遗物中出现。','muted'));
  }
  window.ImmortalAperturePanel={render};
})();
