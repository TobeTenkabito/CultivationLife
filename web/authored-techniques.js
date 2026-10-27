/* A compact authoring desk; every price and effect is validated by the server. */
window.AuthoredTechniques = (() => {
  let game, send, preview, draft, quote, pending=false, generation=0, timer;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const root=()=>document.querySelector('#authored-content');
  const categories={main:'主修 · 悟道',support:'辅修 · 调息',combat:'杀伐 · 斗法',body:'炼体',divine_sense:'神识',transformation:'变化'};
  function label(text,input){const n=el('label');n.append(el('span',text),input);return n;}
  function number(value,min,max,change,name){const n=el('input');n.type='number';n.min=min;n.max=max;n.step=1;n.value=value;if(name)n.dataset.authoredInput=name;n.oninput=()=>{change(Number(n.value));schedule();};return n;}
  function select(options,value,change,name){const n=el('select');if(name)n.dataset.authoredInput=name;for(const [key,text]of Object.entries(options)){const o=el('option',text);o.value=key;n.append(o);}n.value=value;n.onchange=()=>{change(n.value);schedule();};return n;}
  function schedule(){quote=null;document.querySelector('[data-author-create]')?.setAttribute('disabled','');clearTimeout(timer);const token=++generation;timer=setTimeout(()=>estimate(token),250);}
  async function estimate(token){
    if(!draft||!game)return;
    const node=document.querySelector('#authored-estimate');if(node)node.textContent='正在推演…';
    try{const data=await preview({action:'preview',design:draft});if(token!==generation)return;quote=data;paintEstimate();}
    catch(error){if(token===generation){quote=null;if(node)node.textContent=error.message;document.querySelector('[data-author-create]')?.setAttribute('disabled','');}}
  }
  function paintEstimate(){
    const node=document.querySelector('#authored-estimate');if(!node||!quote)return;
    node.replaceChildren(el('p',draft.name||'未题名','at-book-name'));
    const list=el('dl',undefined,'at-values');
    for(const [key,title]of Object.entries(game.authored_techniques.stats)){list.append(el('dt',title),el('dd','+'+Number(quote.technique[key]).toLocaleString()));}
    node.append(list);
    for(const text of quote.buffs)node.append(el('p',text,'at-effect-text'));
    node.append(el('p',`属性 ${quote.attribute_cost} 点 · 效果 ${quote.buff_cost} 点`,'muted'),el('strong',`定稿消耗 ${quote.cost.toLocaleString()} 点`));
    document.querySelector('[data-author-create]').disabled=pending||!game.authored_techniques.can_operate||quote.cost>game.authored_techniques.points.available;
  }
  function drawBuffs(){
    const holder=document.querySelector('#authored-buffs');holder.replaceChildren();
    draft.buffs.forEach((b,index)=>{
      const row=el('section',undefined,'at-buff');const header=el('div',undefined,'at-buff-heading');
      const remove=el('button','移除');remove.type='button';remove.onclick=()=>{draft.buffs.splice(index,1);drawBuffs();schedule();};header.append(el('strong',`效果 ${index+1}`),remove);row.append(header);
      const grid=el('div',undefined,'at-buff-fields');
      const all=game.authored_techniques.slots;
      const slots=['main','support','combat'].includes(draft.category)?Object.fromEntries(['main','support','combat'].map(k=>[k,all[k]])):Object.fromEntries([[{body:'body',divine_sense:'sense',transformation:'transformation'}[draft.category],all[{body:'body',divine_sense:'sense',transformation:'transformation'}[draft.category]]]]);
      grid.append(label('生效栏目',select(slots,b.slot,v=>b.slot=v)),
        label('触发条件',select({always:'战斗中始终生效',from_round:'从指定轮次起',at_round:'仅指定轮次'},b.condition,v=>{b.condition=v;if(v==='always')b.round=1;drawBuffs();})),
        label('效果',select(Object.fromEntries(Object.entries(game.authored_techniques.effects).map(([k,v])=>[k,v.name])),b.effect,v=>{b.effect=v;b.value=Math.min(b.value,game.authored_techniques.effects[v].maximum);drawBuffs();})),
        label('数值（%）',number(b.value,1,game.authored_techniques.effects[b.effect].maximum,v=>b.value=v)),
        label('解锁等级',number(b.level,1,9,v=>b.level=v)));
      if(b.condition!=='always')grid.append(label('指定轮次',number(b.round,1,8,v=>b.round=v)));
      row.append(grid);holder.append(row);
    });
    document.querySelector('[data-author-add-buff]').disabled=draft.buffs.length>=4;
  }
  async function command(payload){if(pending)return;pending=true;draw();try{await send(payload);}finally{pending=false;draw();schedule();}}
  function draw(){
    const state=game.authored_techniques,host=root();host.replaceChildren();
    const hero=el('header',undefined,'at-intro');const intro=el('div');intro.append(el('p','著经立道 · 所学皆可成章','at-eyebrow'),el('h3','写下你的传承'),el('p','参悟已学功法，分配点数，留下只属于你的修行之书。'));
    const balance=el('div',undefined,'at-balance');balance.append(el('span','可用创法点'),el('strong',state.points.available.toLocaleString()),el('small',`累计 ${state.points.earned.toLocaleString()} · 已用 ${state.points.spent.toLocaleString()}`));hero.append(intro,balance);host.append(hero);
    const help=el('details',undefined,'at-rules');help.append(el('summary','点数与传承规则'),el('p','每部普通已学功法按 10 × 品阶² × 等级² 计点；未装备也计入，升级仅补差额。自创与继承功法不返还点数。'),el('p','本世作品只在此处获得与刻录；玉简沿原有合参方式升级。下一世可选一个前世存档，只继承该档亲自创作的作品，进入黑市与交易集会。'));host.append(help);
    const tabs=el('div',undefined,'at-section-title');tabs.append(el('span','01'),el('h3','编撰新卷'));host.append(tabs);
    const desk=el('div',undefined,'at-desk'),form=el('div',undefined,'at-form'),fields=el('div',undefined,'at-fields');
    const name=el('input');name.value=draft.name;name.maxLength=24;name.placeholder='为功法题名';name.dataset.authoredInput='name';name.oninput=()=>{draft.name=name.value;schedule();};
    fields.append(label('功法名称',name),label('功法类型',select(categories,draft.category,v=>{draft.category=v;const slot={body:'body',divine_sense:'sense',transformation:'transformation'}[v]||v;draft.buffs.forEach(b=>b.slot=slot);drawBuffs();},'category')),
      label('功法境界',select(Object.fromEntries(Array.from({length:Math.max(1,state.max_grade)},(_,i)=>[i+1,configData.combat_benchmarks[i]?.name||`${i+1}阶`])),String(draft.grade),v=>draft.grade=Number(v),'grade')),
      label('灵根属性',select({neutral:'无属性',metal:'金',wood:'木',water:'水',fire:'火',earth:'土',wind:'风',thunder:'雷',yin:'阴',yang:'阳'},draft.element,v=>draft.element=v,'element')));
    form.append(fields,el('h4','属性投入'));
    const allocations=el('div',undefined,'at-allocations');for(const [key,title]of Object.entries(state.stats))allocations.append(label(title,number(draft.allocations[key],1,1000000,v=>draft.allocations[key]=v,key)));form.append(allocations);
    const effects=el('div',undefined,'at-section-title'),add=el('button','＋ 添加效果');add.type='button';add.dataset.authorAddBuff='';add.onclick=()=>{const slot={body:'body',divine_sense:'sense',transformation:'transformation'}[draft.category]||draft.category;draft.buffs.push({slot,effect:'might',value:5,level:1,condition:'always',round:1});drawBuffs();schedule();};effects.append(el('h4','功法效果'),add);form.append(effects);const buffs=el('div');buffs.id='authored-buffs';form.append(buffs);
    const side=el('aside',undefined,'at-preview');side.append(el('p','成书预览 · Lv.1','at-eyebrow'));const estimate=el('div');estimate.id='authored-estimate';side.append(estimate);
    const create=el('button','定稿并学会','primary');create.type='button';create.dataset.authorCreate='';create.disabled=true;create.onclick=()=>command({action:'create',design:draft,revision:state.revision});side.append(create,el('small','定稿后保存为独立作品；已有点数投入不退回。'));desk.append(form,side);host.append(desk);
    const shelfTitle=el('div',undefined,'at-section-title');shelfTitle.append(el('span','02'),el('h3','我的书架'));host.append(shelfTitle);
    const shelf=el('div',undefined,'at-shelf');
    for(const book of state.books){const card=el('article',undefined,'at-book');card.append(el('small',book.own?'本世所著':`前世传承 · ${book.author}`),el('h4',book.name),el('p',book.level?`已掌握 Lv.${book.level}`:'尚未获得 · 黑市与交易集会寻访'));book.buffs.forEach(t=>card.append(el('p',t,'at-effect-text')));
      if(book.own&&book.level<9){const buy=el('button',`刻录 Lv.${book.level||1} 玉简 · ${book.manual_cost.toLocaleString()}点`);buy.type='button';buy.dataset.authorManual=book.id;buy.disabled=pending||!state.can_operate||state.points.available<book.manual_cost;buy.onclick=()=>command({action:'manual',id:book.id,level:book.level||1,revision:state.revision});card.append(buy);}
      if(book.level>0&&book.level<9){const upgrade=el('button','使用玉简合参升级');upgrade.type='button';upgrade.dataset.authorUpgrade=book.id;upgrade.disabled=pending||!book.can_upgrade;upgrade.title=book.can_upgrade?'消耗一份同级玉简':'需要一份同名同级玉简，并结束当前事件';upgrade.onclick=()=>command({action:'upgrade',id:book.id});card.append(upgrade);}shelf.append(card);
    }
    if(!state.books.length)shelf.append(el('p','书架尚空。从你已学会的功法中，写下第一部作品。','empty'));host.append(shelf);drawBuffs();paintEstimate();
    if(pending)host.querySelectorAll('button,input,select').forEach(n=>n.disabled=true);
  }
  async function lineages(){
    const label=document.querySelector('#authored-lineage-field'),select=document.querySelector('#authored-lineage');
    try{const response=await fetch('/api/authored-lineages');if(!response.ok)return;const data=await response.json();label.classList.toggle('hidden',!data.available);const previous=select.value;select.replaceChildren();const none=el('option','不继承 · 从此世开始');none.value='';select.append(none);for(const row of data.lineages){const o=el('option',`${row.name} · 本世著作 ${row.books} 部`);o.value=row.id;select.append(o);}select.value=[...select.options].some(o=>o.value===previous)?previous:'';}catch(_){label.classList.add('hidden');}
  }
  return {lineages,ready:()=>!pending&&!!quote,render(data,query,action){const changed=game?.id!==data.id;game=data;preview=query;send=action;const available=!!data.authored_techniques?.available;document.querySelector('#authored-card').classList.toggle('hidden',!available);document.querySelector('[data-panel-target=authored]').classList.toggle('hidden',!available);if(!available){window.UtilityPanels?.close('authored');return;}if(changed||!draft){draft={name:'',grade:1,category:'main',element:'neutral',allocations:{opportunity_bonus:1,hp_bonus:1,mp_bonus:1,combat_bonus:1},buffs:[]};quote=null;}window.UtilityPanels.schedule('authored',()=>{draw();schedule();});}};
})();
