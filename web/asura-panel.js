(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:1});
  let owner;
  const selected=new Set();
  function render(game,act,breakthrough){
    if(owner!==game.id){owner=game.id;selected.clear();}
    for(const id of selected)if(!(game.asura?.bodies||[]).some(b=>b.id===id))selected.delete(id);
    for(const tab of ['conversion','body','veins','route','domain','powers'])renderSection(game,act,breakthrough,tab);
  }
  function renderSection(game,act,breakthrough,tab){
    const s=game.asura||{},p=game.player,name=`asura-${tab}`;
    const card=document.getElementById(`${name}-card`),root=document.getElementById(`${name}-content`);
    card.classList.toggle('hidden',!s.available);
    document.querySelector(`[data-panel-target="${name}"]`).classList.toggle('hidden',!s.available);
    root.replaceChildren();
    if(!s.available){window.UtilityPanels?.close(name);return;}
    root.classList.add('asura-workbench');
    const blocked=!p.alive||!!game.pending_event||!!game.trial?.active||!!game.imprisonment||!!p.sealed_cultivation||!!p.cultivation_suppression||!s.can_cultivate;
    const converted=(s.conversion||0)>=5;
    const button=(label,action,payload={},disabled=false)=>{const b=el('button',label,'asura-action');b.type='button';b.dataset.asuraAction=action;b.disabled=blocked||disabled;b.onclick=()=>act({action,...payload});return b;};
    const note=text=>el('p',text,'asura-note');
    const section=(title,description)=>{const box=el('section',null,'asura-section');box.append(el('h3',title));if(description)box.append(el('p',description,'asura-description'));return box;};
    const metric=(label,value)=>{const box=el('div');box.append(el('small',label),el('strong',value));return box;};
    const hero=el('header',null,'asura-hero'),seal=el('div',s.route_name?.slice(0,1)||'煞','asura-sigil'),heading=el('div');
    seal.setAttribute('aria-hidden','true');heading.append(el('small','修罗显圣 · 无法无天','asura-eyebrow'),el('h3',s.route?`${s.route_name} · ${s.part}`:'凝身入道'),el('p',s.route?`${s.domain_name} · ${s.domain_label}`:'锻炼己身，凝练肉身，融合本命。'));hero.append(seal,heading);
    if(tab==='route')root.append(hero);
    const metrics=el('div',null,'asura-metrics');metrics.append(metric('精魂',fmt(s.souls)),metric('修罗之躯',`${s.body_level||0}/20 层`),metric('本境魔脉',`${s.opened||0}/27`));if(['body','route','domain','powers'].includes(tab))root.append(metrics);
    const handbook=el('button','八部条件与修炼规则 → 百科','asura-help');handbook.type='button';handbook.onclick=()=>window.TutorialGuide?.showChapter('dlc-asura');if(tab==='route')root.append(handbook);
    if(!s.can_cultivate){root.append(note('已炼化元神可在御傀面板提纯。登临修罗界、达到修罗境后开启此处修持。'));return;}
    const content=el('div',null,'asura-page');content.dataset.page=tab;root.append(content);
    if(tab==='conversion'){
      const conversion=section('煞元转化',converted?'五重转化已完成，可开脉、锻体和凝练煞元。':'按顺序完成五重转化事件，每重开放两成可用煞元。');
      const steps=el('ol',null,'asura-steps');['引煞','洗元','凝旋','通窍','归一'].forEach((title,i)=>{const n=el('li',`${i+1} · ${title}`);n.dataset.state=i<(s.conversion||0)?'done':i===(s.conversion||0)?'current':'locked';steps.append(n);});conversion.append(steps);
      if(!converted)conversion.append(button(`进行第 ${(s.conversion||0)+1} 重转化`,'convert'));
      content.append(conversion);
    }
    if(tab==='body'){
      const body=section('锻炼自己的修罗之躯',`玩家普通炼体 ${p.body_training}/100 层；普通炼体达到100层后，才能以机缘锻炼修罗之躯。修罗之躯单独计层，上限20层。`);
      const track=el('div',null,'asura-body-track');track.setAttribute('aria-label',`修罗之躯 ${s.body_level||0}/20 层`);for(let i=1;i<=20;i++){const n=el('span',String(i));n.classList.toggle('is-open',i<=(s.body_level||0));track.append(n);}body.append(track);
      body.append(note('达到修罗之躯20层后，可凝练外界肉身并融合本命。这里显示的是玩家己身，与俘虏、傀儡的炼体层数分开。'));
      if((s.body_level||0)<20)body.append(el('p',`下一层费用：${fmt(s.body_cost)} 机缘 · 当前 ${fmt(p.opportunity)}`),button('锻炼下一层修罗之躯','train_body',{},!converted||p.body_training<100||p.opportunity<s.body_cost));
      else body.append(note('修罗之躯已达20层，可前往「八部」选择凝练肉身。'));
      content.append(body);
    }
    if(tab==='veins'){
      const v=s.meridians, next=v.opened+1;
      const overview=section(`${v.realm} · 第${v.layer}层魔脉`,`本层需累计贯通 ${v.required} 条，已贯通 ${v.opened} 条；每层三脉，本境共二十七脉。`);
      const progress=el('progress');progress.max=27;progress.value=v.opened;progress.setAttribute('aria-label','本境魔脉');
      overview.append(progress,el('p',`机缘 ${fmt(v.opportunity)} · 精魂 ${fmt(v.souls)}`),el('p',`魔脉累计本源增益：气血 +${fmt(v.intrinsic_total.hp)} · 法力 +${fmt(v.intrinsic_total.mp)}`,'asura-benefit'));
      content.append(overview,window.AsuraMeridians.render(v));
      if(v.last_attempt){const r=v.last_attempt,feedback=note(`${r.realm}第${r.index}脉：${r.success?'贯通成功':'开辟失败，已积累保底'}。本次消耗 ${fmt(r.opportunity)} 机缘、${fmt(r.souls)} 精魂。`);feedback.setAttribute('role','status');content.append(feedback);}
      if(v.next_cost){
        const attempt=section(`开辟第 ${next} 条魔脉`, `成功后增加本源气血 ${fmt(v.intrinsic_per_vein.hp)}、本源法力 ${fmt(v.intrinsic_per_vein.mp)}。`);
        const quote=el('div',null,'asura-quote');quote.append(metric('所需机缘',fmt(v.next_cost.opportunity)),metric('所需精魂',fmt(v.next_cost.souls)),metric('本次成功率',`${fmt(v.chance*100)}%`));attempt.append(quote);
        attempt.append(el('p',`当前机缘 ${fmt(v.opportunity)} · 精魂 ${fmt(v.souls)}。本脉已失败 ${v.failures} 次；失败消耗上述资源，下次增加 ${fmt(v.pity_step*100)} 个百分点，成功后清除此脉保底。`,'asura-description'),button('尝试开辟下一条魔脉','open_vein',{},!v.can_open));
        if(v.reason)attempt.append(note(v.reason));content.append(attempt);
      }
      const advance=section('贯脉之后，手动冲关',`冲关另外消耗 ${fmt(v.breakthrough_cost)} 机缘；开脉不会自动提升境界。`);
      advance.append(note(!converted?'须先完成五重煞元转化。':!v.ready?`本层还需开辟 ${v.required-v.opened} 条魔脉。`:game.breakthrough?.reason||'本层三脉已贯通。'));
      const b=button(game.breakthrough?.kind==='major'?'开始大境界劫战':'手动突破下一层','',{},!game.breakthrough?.enabled);b.onclick=breakthrough;advance.append(b);
      if(v.ready&&p.opportunity<v.breakthrough_cost)advance.append(note(`还需积累 ${fmt(v.breakthrough_cost-p.opportunity)} 机缘。`));content.append(advance);
    }
    if(tab==='route'){
      if(!s.route){
        content.append(note(`凝练门槛：候选俘虏或傀儡自身的「普通炼体」至少 ${s.minimum_body_training}/100 层；玩家还须修罗之躯20层。两者分别判定。`));
        const candidates=section('可凝练肉身','只列出你实际持有的俘虏与傀儡。凝练消耗精魂，并将其移入待融合名录。');
        if(!s.candidates?.length)candidates.append(note('暂无可用肉身，可先获得俘虏或制作傀儡。路线材料条件见百科。'));
        for(const b of s.candidates||[]){const row=section(`${b.name} · ${b.source==='prisoner'?'俘虏':'傀儡'}`);row.append(el('p',`自身普通炼体 ${b.body_training}/100 层 · 高阶肉身 ${b.immortal_body_level} 层 · 炼体境界 ${b.body_realm}`),el('p',`可继承肉身战力 ${fmt(b.body_power)} · ${b.eligible?'普通炼体门槛已满足':'普通炼体不足，无法凝练'}`,'asura-description'),button(`凝练肉身 · ${fmt(b.condense_cost)} 精魂`,'condense',{target_id:b.id},!converted||!b.eligible||(s.body_level||0)<20||s.souls<b.condense_cost));candidates.append(row);}content.append(candidates);
        const fusion=section('待融合肉身','选择一至两具已凝练肉身。单具按身体条件匹配本命；两具合格肉身进入阿修罗。融合后本命永久确定。');
        const preview=note(''),fight=button('融合所选肉身（开始生死战）','fuse',{},true);
        const update=()=>{const rows=(s.bodies||[]).filter(b=>selected.has(b.id)),name=rows.length===2?'阿修罗':rows[0]?.matched_route;preview.textContent=rows.length?`已选 ${rows.length} 具 · ${name?`将进入${name}本命`:'此单具不符合本命条件，需搭配另一具肉身'}`:'尚未选择肉身';fight.disabled=blocked||!converted||(s.body_level||0)<20||!name||rows.length>2;};
        for(const b of s.bodies||[]){const row=el('label',null,'asura-body-choice'),box=el('input');box.type='checkbox';box.checked=selected.has(b.id);box.onchange=()=>{if(box.checked)selected.add(b.id);else selected.delete(b.id);update();};row.append(box,el('span',`${b.name} · 普通炼体 ${b.body_training}/100 · 高阶肉身 ${b.immortal_body_level||0} 层 · 肉身战力 ${fmt(b.power)}`));fusion.append(row);}
        fight.onclick=()=>act({action:'fuse',body_ids:[...selected]});fusion.append(preview,fight,note('融合战双方不可逃跑。须镇压或击杀全部凝练肉身；失败可能身死。只继承肉身炼体战力，不复制其装备与功法。'));update();content.append(fusion);
      }else{
        const route=section(`${s.route_name}本命 · ${s.part} ${s.level}/9级`,`融合所得永久肉身战力 ${fmt(s.inherited_power)}。本命已经确定。`);route.append(button(`修炼本体 · ${fmt(60*s.level)} 精魂`,'train_route',{},!converted||s.level>=9||s.souls<60*s.level));content.append(route);
        if(!s.branch&&(s.level<5||p.realm_index<10))content.append(note('本体达到5级，并进入非天境后，开放本命分支选择。'));
        else for(const b of s.branches?.[s.route]||[]){
          if(s.branch&&s.branch!==b.id)continue;
          const branch=section(`${b.name}${s.branch?` · ${s.branch_level}/9级`:''}`);b.descriptions.forEach((desc,i)=>branch.append(el('p',`${[1,4,7][i]}级：${desc}`,'asura-description')));
          branch.append(s.branch?button(`修炼分支 · ${fmt(80*s.branch_level)} 精魂`,'train_branch',{},!converted||s.branch_level>=9||s.souls<80*s.branch_level):button('确定此分支（不可更换）','choose_branch',{target_id:b.id},!converted));content.append(branch);
        }
      }
    }
    if(tab==='domain'){
      if(!s.route)content.append(note('完成肉身融合、确定本命后获得自己的魔域。'));
      else{
        const domain=section(s.domain_name,`${s.domain_label} · 威能滋养 ${s.domain_power||0}/99`),stats=el('div',null,'asura-quote');for(const [key,label] of [['stability','稳固'],['incursion','侵夺'],['authority','权能']])stats.append(metric(label,fmt(s.domain_stats[key])));domain.append(stats);
        const rankCost=50*((s.domain_rank||1)+1),powerCost=50*((s.domain_power||0)+1);
        domain.append(button(`提升境界 · ${fmt(rankCost)} 精魂`,'train_domain',{},!converted||s.domain_rank>=13||s.souls<rankCost),button(`滋养威能 · ${fmt(powerCost)} 精魂`,'nourish_domain',{},!converted||s.domain_power>=99||s.souls<powerCost));
        const naming=el('details',null,'asura-details');naming.append(el('summary','为魔域更名'));const input=el('input');input.maxLength=24;input.value=s.domain_name;input.setAttribute('aria-label','魔域名称');const rename=button('保存名称','rename');rename.onclick=()=>act({action:'rename',name:input.value});naming.append(input,rename);domain.append(naming);content.append(domain);
        const effects=section('当前生效的魔域能力');(s.rule_descriptions||[]).forEach(rule=>effects.append(el('p',rule,'asura-description')));if(!s.rule_descriptions?.length)effects.append(note('本命2级起逐步解锁基础能力。'));content.append(effects);
      }
    }
    if(tab==='powers'){
      if(!s.route)content.append(note('先完成肉身融合，确定本命后开放神通槽位。'));
      else{
        const quote=s.power_reroll,locked=new Set(quote.locked_ids);
        const powers=section(`神通属性 ${(s.powers||[]).length}/${s.slots}`,'洗练一次重置所有未锁定属性，锁定属性完整保留。基础费用100精魂，每锁定一条费用翻倍；不随洗练次数上涨。');
        powers.append(button('获取随机神通（100精魂）','learn_power',{},!converted||(s.powers||[]).length>=s.slots||s.souls<100));
        for(const rule of s.powers||[]){
          const row=section(rule.name,rule.description),isLocked=locked.has(rule.id);
          row.dataset.powerId=rule.id;
          const toggle=button(isLocked?'已锁定 · 点击解锁':'锁定此属性','lock_power',{target_id:rule.id},!converted);
          toggle.setAttribute('aria-pressed',String(isLocked));row.append(toggle);powers.append(row);
        }
        powers.append(el('p',`已锁定 ${locked.size} 条 · 本次洗练 ${quote.unlocked} 条 · 费用 ${fmt(quote.cost)} 精魂`),button(`洗练全部未锁定属性（${fmt(quote.cost)}精魂）`,'reroll_power',{},!converted||!quote.unlocked||s.souls<quote.cost));
        if(!quote.unlocked)powers.append(note((s.powers||[]).length?'全部属性均已锁定，请先解除部分锁定。':'请先获取神通。'));
        content.append(powers);
      }
    }
  }
  window.AsuraPanel={render};
})();
