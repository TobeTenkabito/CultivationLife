/* A small, paged view over already-presented NPCs; no polling or population generation. */
window.NpcContacts = (() => {
  let data, people = [], send, saveId, selected = '', query = '', filter = 'all', page = 0;
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const labels = {party:'组队同行',companion:'结为道侣',friend:'结为道友',master:'拜师',disciple:'收徒',concubine:'收为侍妾',improve:'改善关系',worsen:'破坏关系',slay:'截杀',capture:'生擒'};
  const relation = n => {
    const name = {master:'师父',companion:'道侣',disciple:'弟子',friend:'道友',concubine:'侍妾',party:'同行'}[n.contact_relation];
    if(name) return name;
    const p = data.player;
    if (p.master?.id === n.id) return '师父';
    if (p.dao_companion?.id === n.id) return '道侣';
    if (p.disciples?.some(r=>r.id===n.id)) return '弟子';
    if (p.dao_friends?.some(r=>r.id===n.id)) return '道友';
    if (p.concubines?.some(r=>r.id===n.id)) return '侍妾';
    return n.in_party ? '同行' : n.attitude;
  };
  function drawDetail(target) {
    target.replaceChildren();
    const n = people.find(r=>r.id===selected);
    if (!n) { target.append(el('p','点选人物，展开交往。','empty')); return; }
    const header = el('div',undefined,'contact-hero');
    header.append(el('span',n.name.slice(0,1),'contact-seal'));
    const title = el('div'); title.append(el('small',n.contact_source==='institution'?`机构往来 · ${n.institution_name||'机构'}`:n.contact_source==='fixed'?'世间留名 · 重要人物':n.contact_source==='sect'?'同门问道 · 宗门同道':n.contact_source==='important'?'故人留名 · 重要人物':'萍水相逢 · 一面之缘'),el('h3',n.name),el('p',`${n.realm_name} · ${n.path_name} · ${n.gender_name}`));header.append(title);target.append(header);
    target.append(el('p',`${relation(n) || '相识'} · 好感 ${Number(n.affinity || 0).toFixed(0)} · ${n.status}`,'contact-standing'));
    if(n.cultivation_ranks) target.append(el('p',`炼体 ${n.cultivation_ranks.body.name} · 神识 ${n.cultivation_ranks.sense.name}`,'muted'));
    const tools = el('div',undefined,'contact-actions');
    for (const [action,label] of Object.entries(labels)) {
      const reason = n.contact_actions?.[action] ?? '暂不可交往';
      const danger = ['slay','capture','worsen'].includes(action);
      const button = el('button',undefined,`contact-action${danger?' danger':''}`); button.type='button';button.dataset.contactAction=action;
      button.append(el('b',action==='party'&&n.in_party?'离开队伍':label));
      const hint = reason || (action==='improve'||action==='worsen'?'本行动单位共一次':action==='slay'||action==='capture'?'立即交锋，后果自负':'依双方状况回应');
      button.append(el('small',hint));button.title=hint;button.dataset.available=reason?'0':'1';
      button.disabled=!!reason || !!data.pending_event || !data.player.alive;
      button.onclick=()=>{
        if(danger && !confirm(`对${n.name}执行「${label}」？${action==='worsen'?'这会降低好感。':'将按现有交锋与背叛规则结算，可能危及性命。'}`)) return;
        send({npc_id:n.id,action});
      };tools.append(button);
    }
    target.append(tools);
  }
  function render(value, callback) {
    if(saveId!==value.id){saveId=value.id;selected='';query='';filter='all';page=0;}
    data=value;send=callback;
    const roster=(data.faction?.roster||[]).filter(n=>!n.is_player);
    const sectIds=new Set(roster.map(n=>n.id));
    people=[...new Map([...roster,...(data.world_npcs||[])].map(n=>[n.id,n])).values()].map(n=>({...n,contact_sect:sectIds.has(n.id)}));
    const root=document.getElementById('npc-contacts'); if(!root)return;
    const focused=root.contains(document.activeElement)&&document.activeElement.type==='search';
    root.replaceChildren();
    const head=el('div',undefined,'contact-heading');head.append(el('h3','故人笺'),el('span','重要人物 · 当面交往'));root.append(head);
    root.append(el('p','重要人物、游历相识、宗门同道与机构人物尽收此笺。同一人可见于多个分类；灰色操作会说明缘由，更多亲随事务可在下方名册办理。','muted'));
    const search=el('input');search.type='search';search.placeholder='寻姓名、称号、境界…';search.setAttribute('aria-label','搜索重要人物');search.value=query;search.className='contact-search';root.append(search);
    const tabs=el('div',undefined,'contact-filters');
    for(const [key,label] of [['all','全部'],['important','重要人物'],['pool','一面之缘'],['sect','宗门同道'],['institution','机构人物'],['close','亲近之人'],['absent','去向已远']]){
      const b=el('button',label);b.type='button';b.setAttribute('aria-pressed',String(filter===key));b.onclick=()=>{filter=key;page=0;render(data,send);};tabs.append(b);
    }root.append(tabs);
    const layout=el('div',undefined,'contact-layout'),directory=el('div',undefined,'contact-directory'),detail=el('div',undefined,'contact-detail');layout.append(directory,detail);root.append(layout);
    function list(){
      const rows=people.filter(n=>(filter==='absent'?!n.perceived_alive:n.perceived_alive)&&
        (filter!=='important'||['fixed','important'].includes(n.contact_source))&&
        (filter!=='pool'||n.contact_source==='pool')&&
        (filter!=='sect'||n.contact_sect)&&
        (filter!=='institution'||n.contact_source==='institution')&&
        (filter!=='close'||n.in_party||['师父','道侣','弟子','道友','侍妾'].includes(relation(n)))&&
        `${n.name} ${n.title||''} ${n.realm_name}`.includes(query.trim()));
      directory.replaceChildren(); page=Math.min(page,Math.max(0,Math.ceil(rows.length/12)-1));
      const slice=rows.slice(page*12,page*12+12);
      if(!rows.some(n=>n.id===selected))selected=slice[0]?.id||'';
      for(const n of slice){
        const b=el('button',undefined,'contact-person');b.type='button';b.dataset.npcId=n.id;b.setAttribute('aria-pressed',String(n.id===selected));
        b.append(el('b',n.name),el('small',`${n.realm_name} · ${relation(n)||'相识'}`));
        b.onclick=()=>{selected=n.id;list();if(innerWidth<=600)detail.scrollIntoView({block:'start',behavior:'instant'});};directory.append(b);
      }
      if(!rows.length)directory.append(el('p','此页尚无相应人物。','empty'));
      const nav=el('div',undefined,'contact-pagination');
      for(const [delta,label] of [[-1,'上一页'],[1,'下一页']]){const b=el('button',label);b.type='button';b.disabled=delta<0?page===0:(page+1)*12>=rows.length;b.onclick=()=>{page+=delta;list();};nav.append(b);}
      nav.append(el('small',`${rows.length} 位 · ${page+1}/${Math.max(1,Math.ceil(rows.length/12))} 页`));directory.append(nav);drawDetail(detail);
    }
    search.oninput=()=>{query=search.value;page=0;list();};list();if(focused)search.focus();
  }
  function open(identity) {
    const person=people.find(n=>n.id===identity);if(!data||!person)return false;
    selected=identity;query=person.name;filter=person.perceived_alive?'all':'absent';page=0;
    render(data,send);return true;
  }
  return {render,open};
})();
