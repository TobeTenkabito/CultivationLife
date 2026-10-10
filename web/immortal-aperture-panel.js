(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1});
  function render(data, act, options={}) {
    const studied=!!data.spirit_studies?.length;
    for(const [name,visible] of [['immortal-aperture',data.available],['spirit-voisinage',data.lower&&(data.field||studied)]]) {
      document.getElementById(name+'-card').classList.toggle('hidden',!visible);
      document.querySelector(`[data-panel-target="${name}"]`).classList.toggle('hidden',!visible);
      if(!visible)window.UtilityPanels?.close(name);
    }
    const fields=document.getElementById('spirit-voisinage-content');fields.replaceChildren();
    if(data.lower&&studied){
      fields.append(el('p','已得灵域传承，合参至 Lv4 后方能展开。未成域时仍可在这里查看进度；仿仙灵力和斗法资格按实际修持开放。','muted'));
      for(const book of data.spirit_studies){
        fields.append(el('p',`${book.name} · Lv${book.level}${book.level<4?' · 尚需合参':' · 已可展开'}`));
      }
      const bag=el('button','前往行囊合参玉简');bag.type='button';bag.onclick=()=>window.UtilityPanels.open('inventory');fields.append(bag);
    }
    if(!data.available)return;
    document.getElementById('immortal-aperture-card').dataset.energyKind=data.energy_kind;
    const title=data.title||'仙窍';
    document.querySelector('#immortal-aperture-card h2').textContent=title;
    document.querySelector('#immortal-aperture-card').setAttribute('aria-label',title);
    const dock=document.querySelector('[data-panel-target="immortal-aperture"]');dock.title=title;dock.querySelector('small').textContent=({'煞元府':'煞元','幽元府':'幽元','轮回元府':'轮元'})[title]||title;
    const root=document.getElementById('immortal-aperture-content');root.replaceChildren();
    const figure=el('figure',null,'aperture-reservoir');
    figure.style.setProperty('--reservoir-fill',`${Math.max(0,Math.min(100,data.current/Math.max(1,data.capacity)*100))}%`);
    const pool=el('div',null,'aperture-orb');pool.setAttribute('role','img');pool.setAttribute('aria-label',`${data.name} ${fmt(data.current)} / ${fmt(data.capacity)}`);
    pool.append(el('div',null,'aperture-water'),el('strong',`${fmt(data.current)} / ${fmt(data.capacity)}`),el('span',data.name));
    figure.append(pool,el('figcaption',`${title} · 邻域所用的独立储量`));root.append(figure);
    root.append(el('p',data.lower?'下界无法维持完整仙域。凝练本源，仅得少量仿仙灵力；灵域威能为原域的 4%，同样经过邻域阶段结算。':`${title}存储斗法所需${data.name}。展开、维持和施展邻域权能都会消耗储量，战后不会自动补满。`));
    if(data.lower)root.append(el('p',`封存${data.sealed_name || '元力'} ${fmt(data.sealed_reserve)}；回到三级界面才可使用。`,'muted'));
    root.append(el('p',`本源气血 ${fmt(data.origin_hp)} / ${fmt(data.max_hp)} · 本源法力 ${fmt(data.origin_mp)} / ${fmt(data.max_mp)}`),
      el('p',`每次凝练 ${fmt(data.refine_gain)} ${data.name}，消耗本源气血 ${fmt(data.hp_cost)}、本源法力 ${fmt(data.mp_cost)}。接近满储时按实际凝练量扣除。`));
    const refine=el('button',`凝练${data.name}`);refine.type='button';refine.disabled=options.pending||!options.alive||data.current>=data.capacity||(!data.lower&&data.conversion<1)||data.origin_hp<=data.hp_cost||data.origin_mp<data.mp_cost;
    refine.onclick=()=>act({action:'refine'});root.append(refine);
    root.append(el('p',data.asura_conversion?`煞元转化完成度 ${fmt(data.conversion*100)}%。请在八部面板完成五重转化，随后可凝练补充；战斗消耗不会倒退转化进度。`:data.native?`${data.name}可直接凝练。圆池显示实际储量；跨界不会凭空补充。`:`转化完成度 ${fmt(data.conversion*100)}%。仙窍圆池显示可消耗的储量，转化程度不会随战斗消耗降低。`,'muted'));
    if(!data.field)return;
    const f=data.field;fields.append(el('h3',f.name),el('p',`稳固 ${fmt(f.stability)} · 侵夺 ${fmt(f.incursion)} · 权能 ${fmt(f.authority)}`),
      el('p',`展开 ${fmt(f.opening_cost)} / 每轮维持 ${fmt(f.upkeep_cost)} / 施权 ${fmt(f.effect_cost)} 仿仙灵力。储量不足时领域消散。`));
    for(const book of data.spirit_fields||[]){const b=el('button',`${book.name} · Lv${book.level}${(data.active_manual||data.spirit_fields[0]?.id)===book.id?'（当前）':''}`);b.disabled=options.pending||!options.alive;b.onclick=()=>act({action:'select',manual_id:book.id});fields.append(b);}
    fields.append(el('p','灵域残解合参至 Lv4 即可运用，无需参悟道统。继续合参可强化灵域。下界残解仅在黑市、交换会、商盟寻访委托或修士遗物中出现。','muted'));
  }
  window.ImmortalAperturePanel={render};
})();
