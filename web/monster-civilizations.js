/* Lazy, discovery-limited visual atlas. All commands submit a server revision. */
(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const worlds={human:'人界',monster_realm:'妖界',phantom_underworld:'幻冥界',nether:'幽冥界'};
  const labels={observe:'考察当地',protect:'约束猎取',guide:'疏导猛兽',found:'立下氏族',join:'加入此族',leave:'退出氏族',contest:'按族约争取继位',branch:'建立分支',law:'修订族约',alliance:'缔结盟约',merge:'并入本族',revive:'重续族约',regime:'提交政体议案',invite:'邀请族员'};
  let game,view,query,act,tab='ecology',world='',selectedRegion='',page=0,search='',generation=0,pending=false,owner=null;
  const root=()=>document.getElementById('civilizations-content');
  const svg=(tag,attrs={})=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n;};
  const visible=()=>document.getElementById('civilizations-card')?.classList.contains('panel-open');
  const note=text=>el('p',text,'mc-note');
  async function load(){
    if(!query||!visible())return;
    const seq=++generation,id=game.id;
    root().setAttribute('aria-busy','true');
    if(!view)root().replaceChildren(note('正在展开万灵图卷…'));
    try{
      const next=await query({world:world||game.player.world,page,query:search});
      if(seq!==generation||id!==game.id||!visible())return;
      view=next;draw();
    }catch(error){if(seq===generation){root().replaceChildren(note(error.message));const retry=el('button','重新载入');retry.onclick=load;root().append(retry);}}
    finally{if(seq===generation)root().removeAttribute('aria-busy');}
  }
  async function submit(action,target_id='',name=''){
    if(pending||!view)return;
    pending=true;draw();
    const revision=view.revision;
    try{await act({action,target_id,name,expected_revision:revision,expected_world:view.world,expected_location:view.location});}
    finally{pending=false;await load();}
  }
  function button(action,target='',name=''){
    const amount=view.costs[action]||0,b=el('button',`${labels[action]}${amount?` · ${amount}机缘`:''}`);
    b.type='button';b.dataset.civilizationAction=action;
    b.disabled=pending||view.actions_blocked||(game.player.opportunity||0)<amount;
    if(view.cooldowns[action]>0){b.disabled=true;b.title=`尚需 ${view.cooldowns[action]}年筹备`;}
    if(['protect','guide'].includes(action)&&view.effect_years>0){b.disabled=true;b.title=`现有护育安排尚余 ${view.effect_years}年`;}
    b.onclick=()=>submit(action,target,typeof name==='function'?name():name);
    return b;
  }
  function map(){
    const compact=innerWidth<620;
    const graph=svg('svg',{viewBox:compact?'0 0 360 275':'0 0 660 210',role:'group','aria-label':'选择栖地，查阅原地图道路与考察记录'});
    const positions=new Map(view.regions.map((r,i)=>[r.id,compact?[75+i%2*210,35+Math.floor(i/2)*85]:[75+i%3*250,45+Math.floor(i/3)*110]]));
    view.edges.forEach(e=>{const a=positions.get(e.source),b=positions.get(e.target);if(a&&b)graph.append(svg('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],class:'mc-road'}));});
    view.regions.forEach(r=>{const [x,y]=positions.get(r.id),g=svg('g',{'class':`mc-map-node${r.current?' current':''}${r.known?' known':''}${r.id===selectedRegion?' selected':''}`,role:'button',tabindex:0,'aria-label':`查阅${r.name}`,'aria-pressed':String(r.id===selectedRegion),'data-civilization-region':r.id});
      g.onclick=()=>{selectedRegion=r.id;draw();};g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectedRegion=r.id;draw();root().querySelector(`[data-civilization-region="${r.id}"]`)?.focus();}};
      g.append(svg('circle',{cx:x,cy:y,r:12}));const t=svg('text',{x,y:y+30,'text-anchor':'middle'});t.textContent=r.name;g.append(t);graph.append(g);});
    return graph;
  }
  function trend(points,name){
    const chart=svg('svg',{viewBox:'0 0 320 68',role:'img','aria-label':`${name}历次考察趋势`});
    const max=Math.max(1,...points.map(p=>p.value)),low=Math.min(...points.map(p=>p.value));
    chart.append(svg('line',{x1:6,y1:59,x2:314,y2:59,class:'mc-road'}));
    const coords=points.map((p,i)=>`${points.length===1?160:6+i*308/(points.length-1)},${55-(p.value-low)/Math.max(1,max-low)*44}`);
    if(coords.length>1)chart.append(svg('polyline',{points:coords.join(' '),class:'mc-trend'}));
    points.forEach((p,i)=>{const [x,y]=coords[i].split(',');chart.append(svg('circle',{cx:x,cy:y,r:3,class:'mc-point'}));});
    return chart;
  }
  function ecology(container){
    const selected=view.regions.find(r=>r.id===selectedRegion)||view.regions.find(r=>r.current)||view.regions.find(r=>r.known)||view.regions[0];
    selectedRegion=selected?.id||'';
    container.append(note('点选栖地查阅考察记录。连线沿用已有道路；图志不会代你移动。旧图请以新考察核实，护育不向行囊赠送材料。'),map());
    if(selected){const form=el('div',null,'mc-form'),picker=el('select');picker.setAttribute('aria-label','栖地记录');view.regions.forEach(r=>{const option=el('option',`${r.name} · ${r.current?'所在栖地':r.known?'已考察':'未考察'}`);option.value=r.id;picker.append(option);});picker.value=selectedRegion;picker.onchange=()=>{selectedRegion=picker.value;draw();};form.append(picker);container.append(form);}
    const grid=el('div',null,'mc-grid');
    (selected?[selected]:[]).forEach(r=>{
      const card=el('article',null,`mc-region${r.current?' current':''}`);card.dataset.region=r.id;
      const top=el('header');top.append(el('h3',r.name),el('span',r.current?'所在栖地':r.known?'已考察':'未考察','mc-pill'));card.append(top);
      if(!r.known)card.append(note('尚无考察记录。沿原地图前往此地后，可认识当地生灵。'));
      else{
        card.append(el('p',`纪年 ${r.year} 考察${view.year>r.year?` · 距今 ${view.year-r.year}年，数量或已改变`:' · 当年记录'}`,'mc-date'),el('p',r.case_text,'mc-case'));
        Object.entries(r.populations).forEach(([id,p])=>{const row=el('div',null,'mc-species'),symbol={grazer:'◇',predator:'◆',plant:'❋'}[p.role];
          const label=el('div');label.append(el('span',`${symbol} ${p.name}`),el('small',`${p.min}–${p.max}`));
          const bar=el('div',null,'mc-bar'),fill=el('span',null,`mc-fill ${p.role}`);fill.style.width=`${Math.min(100,p.min/Math.max(1,p.capacity)*100)}%`;bar.append(fill);row.append(label,bar);card.append(row);});
        card.append(trend(r.trend,r.name));
      }
      if(r.current){const actions=el('div',null,'mc-actions');const observe=button('observe');observe.disabled ||= r.year===view.year;actions.append(observe);
        if(r.known){actions.append(button('protect'),button('guide'));if(view.effect_years>0)card.append(note(`现有护育安排尚余 ${view.effect_years}年。`));}card.append(actions);}
      grid.append(card);
    });container.append(grid);
  }
  function clans(container){
    container.append(note('氏族承载祖源与族约；族籍可与现有宗门、家族身份并存。立分支与并族转移原有族众，不能重复认领。'));
    if(view.world==='human'){container.append(note('人界以生态考察为主。妖修氏族可在妖界、幻冥界及幽冥界认识。'));return;}
    if(!view.player_clan){const create=el('div',null,'mc-form'),input=el('input');input.maxLength=12;input.placeholder='氏族名称（至多12字）';input.setAttribute('aria-label','新氏族名称');const b=button('found','',()=>input.value.trim()||game.player.name+'氏');create.append(input,b);container.append(create);}
    const names=new Map(view.clans.map(c=>[c.id,c.name]));
    const tree=el('div',null,'mc-clan-tree');
    [...view.clans].sort((a,b)=>Number(b.id===view.player_clan)-Number(a.id===view.player_clan)).forEach(c=>{const own=c.id===view.player_clan,card=el('article',null,`mc-clan${own?' current':''}`);card.dataset.clan=c.id;
      card.append(el('small',c.parent_id?`${names.get(c.parent_id)||'尚未考察的祖族'} → 分支`:'创始祖族','mc-ancestry'),el('h3',c.name),el('p',`${c.home_name} · ${c.law_name}`),el('span',({active:'传承中',dormant:'沉寂',merged:'已并族'})[c.status]||c.status,'mc-pill'));
      card.append(el('p',c.lineage,'mc-date'));if(c.important_members!=null)card.append(el('p',`重要族员 ${c.important_members} · 族众份额 ${(c.share/100).toFixed(1)}%${c.leader_self?' · 你为族长':c.vacant?' · 族长空缺':''}`));
      const actions=el('div',null,'mc-actions');
      if(!own&&!view.player_clan&&c.status==='active')actions.append(button('join',c.id));
      if(!view.player_clan&&c.status==='dormant'&&(c.member_self||c.founder_self))actions.append(button('revive',c.id));
      if(own){if(!c.leader_self)actions.append(button('contest'));actions.append(button('leave'));const form=el('div',null,'mc-form'),name=el('input');name.placeholder='分支名称';name.maxLength=12;name.setAttribute('aria-label','分支名称');form.append(name,button('branch','',()=>name.value.trim()||game.player.name+'支'));card.append(form);
        if(c.leader_self){const laws=el('select');laws.setAttribute('aria-label','继承族约');Object.entries({eldest_eligible:'长幼传承',strongest_eligible:'强者继位',council_election:'族议推举'}).forEach(([id,n])=>{const option=el('option',n);option.value=id;laws.append(option);});laws.value=c.law;const change=button('law');change.onclick=()=>submit('law',laws.value);const form=el('div',null,'mc-form');form.append(laws,change);card.append(form);
          change.disabled=true;laws.onchange=()=>{change.disabled=pending||view.actions_blocked||laws.value===c.law||view.cooldowns.law>0||(game.player.opportunity||0)<view.costs.law;};
          if(view.invitees.length){const select=el('select');select.setAttribute('aria-label','可邀请的相识妖修');view.invitees.forEach(n=>{const o=el('option',n.name);o.value=n.id;select.append(o);});const invite=button('invite');invite.onclick=()=>submit('invite',select.value);const f=el('div',null,'mc-form');f.append(select,invite);card.append(f);}}}
      if(!own&&view.player_clan&&c.status==='active'){actions.append(button('alliance',c.id),button('merge',c.id));}
      card.append(actions);tree.append(card);
    });if(!view.clans.length)tree.append(note('尚未认识当地氏族。考察祖地，或亲自立下族约。'));container.append(tree);
  }
  function court(container){
    const c=view.court;
    if(!c){container.append(note('王庭依托幽冥界原万妖宫。须在幽冥界完成一次栖地考察，再查看当地政治。'));return;}
    const banner=el('div',null,'mc-court-banner');banner.append(el('h3',c.regime_name),el('p',`正统承认 ${c.legitimacy}/100 · ${({stable:'局势稳定',succession:'继承审议',disputed:'正统未定'})[c.phase]}`),el('small',`本界政治纪历 ${c.clock} · ${c.ruler_self?'你获承认为王庭正统':'诸族按族约审议王庭继承'}`));container.append(banner);
    container.append(note('王庭正统不授予万妖宫席位。五门阀仍以十五议权议事，议案至少需要八议权。离开本界后政治纪历暂停。'));
    const votes=el('div',null,'mc-vote-track');c.blocs.forEach(b=>{const n=el('span',`${b.name} ${b.weight}`);n.style.flex=String(b.weight);n.className=b.present?'':'vacant';votes.append(n);});container.append(votes);
    c.blocs.forEach(b=>{const row=el('div',null,'mc-bloc');row.append(el('b',`${b.name} · ${b.weight}议权`),el('small',b.present?`原议席支持 ${b.support}/100`:'原议席空缺'));const bar=el('div',null,'mc-bar'),fill=el('span',null,'mc-fill');fill.style.width=`${b.support}%`;bar.append(fill);row.append(bar);container.append(row);});
    const form=el('div',null,'mc-form'),select=el('select');select.setAttribute('aria-label','王庭政体');Object.entries(c.regimes).forEach(([id,n])=>{const o=el('option',n);o.value=id;select.append(o);});select.value=c.regime;
    const b=button('regime');b.onclick=()=>submit('regime',select.value);b.disabled ||= !game.upper_institution?.seat_active;form.append(select,b);container.append(form);
    const palace=el('button','前往万妖宫政务');palace.onclick=()=>window.UtilityPanels.open('upper-institution');container.append(palace);
  }
  function journal(container){
    const form=el('form',null,'mc-form'),input=el('input');input.placeholder='检索已知史事';input.maxLength=40;input.value=search;input.setAttribute('aria-label','万灵志检索');const b=el('button','检索');b.type='submit';form.append(input,b);form.onsubmit=e=>{e.preventDefault();search=input.value;page=0;load();};container.append(form);
    const list=el('ol',null,'mc-timeline');view.facts.forEach(f=>{const item=el('li');item.append(el('small',`纪年 ${f.year}`),el('p',f.text));list.append(item);});
    if(!view.facts.length)container.append(note('尚无符合条件的已知史事。考察与参与会留下可追溯的记录。'));container.append(list);
    const nav=el('div',null,'mc-actions'),prev=el('button','上一页'),next=el('button','下一页');prev.disabled=page===0;next.disabled=(page+1)*12>=view.total;prev.onclick=()=>{page--;load();};next.onclick=()=>{page++;load();};nav.append(prev,el('span',`${page+1}页 · ${view.total||0}条近事`),next);container.append(nav);
    if(view.summaries.length){const old=el('details'),title=el('summary','往年史略');old.append(title);view.summaries.slice().reverse().forEach(s=>old.append(el('p',`纪年 ${s.start}–${s.end}：已知史事 ${s.count}件，传承与生息仍有迹可循。`)));container.append(old);}
  }
  function draw(){
    if(!view||!root())return;
    const r=root();r.replaceChildren();
    const heading=document.querySelector('#civilizations-card > .section-title');
    r.style.setProperty('--mc-tabs-top',`${Math.max(0,heading.offsetHeight+(parseFloat(getComputedStyle(heading).top)||0))}px`);
    const head=el('div',null,'mc-atlas-head');head.append(el('p','观山川生息，续诸族传承。'));
    const select=el('select');select.setAttribute('aria-label','已知界面');view.worlds.forEach(id=>{const o=el('option',worlds[id]);o.value=id;select.append(o);});select.value=view.world;select.onchange=()=>{world=select.value;selectedRegion='';page=0;view=null;load();};head.append(select);r.append(head);
    const tabs=el('div',null,'mc-tabs');tabs.setAttribute('role','tablist');[['ecology','生息图'],['clans','氏族谱'],['court','王庭'],['journal','万灵志']].forEach(([id,text])=>{const b=el('button',text);b.type='button';b.setAttribute('role','tab');b.setAttribute('aria-selected',String(tab===id));b.dataset.civilizationTab=id;b.onclick=()=>{tab=id;draw();};tabs.append(b);});r.append(tabs);
    if(!view.supported){r.append(note('此万灵记录版本暂不支持。原记录已保留，请启用对应版本后继续。'));return;}
    const content=el('div',null,'mc-tab-content');content.setAttribute('role','tabpanel');({ecology,clans,court,journal})[tab](content);r.append(content);
    if(view.actions_blocked)r.append(note('当前可查阅图志。当地事务须亲临栖地，并先处理事件、试炼或拘禁。'));
  }
  function render(data,fetchView,perform){
    if(owner!==data.id){owner=data.id;world='';selectedRegion='';page=0;view=null;generation++;tab='ecology';}
    else if(game?.player.world!==data.player.world||game?.player.location_id!==data.player.location_id)selectedRegion='';
    game=data;query=fetchView;act=perform;
    const available=!!data.monster_civilizations?.available;
    document.getElementById('civilizations-card')?.classList.toggle('hidden',!available);
    document.querySelector('[data-panel-target="civilizations"]')?.classList.toggle('hidden',!available);
    if(!available){window.UtilityPanels?.close('civilizations');view=null;generation++;return;}
    if(visible())load();
  }
  function open(which='ecology'){tab=which;world=game?.player.world||'';selectedRegion='';window.UtilityPanels?.open('civilizations');}
  window.addEventListener('game:panel-open',e=>{if(e.detail.name==='civilizations')load();else generation++;});
  window.MonsterCivilizationsPanel={render,open};
})();
