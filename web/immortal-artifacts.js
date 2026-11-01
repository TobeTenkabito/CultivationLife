/* Independent equipment quality; the server owns all costs and grades. */
(() => {
  const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
  const ranks=['','一品','二品','三品','四品','五品'];
  const numeral=['','一','二','三','四','五'];
  function sectionHeading(title,note){
    const heading=make('div',null,'ia-section-heading');heading.append(make('h3',title),make('span',note));return heading;
  }
  function draw(state,send){
    const root=document.querySelector('#immortal-artifacts-content');root.replaceChildren();
    const intro=make('section',null,'ia-intro');
    const copy=make('div');copy.append(make('p','五品起炼 · 一品为极','ia-eyebrow'),make('h3','淬炼器质，温养仙锋'),make('p','品阶独立于本命温养，不直接增加战斗力。','immortal-artifact-lead'));
    const tally=make('div',null,'ia-tally');tally.append(make('strong',String(state.equipment.length)),make('span','在册'+state.title));intro.append(copy,tally);root.append(intro);
    root.append(sectionHeading('淬炼珍材','依次用于四次进阶'));
    const materials=make('section',null,'immortal-artifact-materials');
    materials.setAttribute('aria-label','培养材料');
    for(const [index,material] of state.materials.entries()){
      const card=make('figure');
      const art=make('div',null,'ia-material-art');
      if(window.PixelLibrary?.active()){
        const img=make('img');img.src=`/assets/pixel/immortal-refinement/${material.id}-portrait.png`;img.alt=material.name;img.width=img.height=64;img.loading='lazy';art.append(img);
      }else art.append(make('span',['铁','钢','银','金'][index],'ia-material-seal'));
      const caption=make('figcaption');caption.append(make('strong',material.name),make('small',index===0?'诸界可寻':'三级界面可寻'));
      const stock=make('span',null,'ia-stock');stock.append(make('small','持有'),make('b',String(material.quantity)));
      card.append(art,caption,stock,make('small',`${ranks[5-index]} → ${ranks[4-index]}`,'ia-material-use'));materials.append(card);
    }
    root.append(materials);
    root.append(sectionHeading(state.title+'名录','仅收录仙级伤害装备'));
    const list=make('section',null,'immortal-artifact-list');
    for(const item of state.equipment){
      const card=make('article',null,'immortal-artifact-entry');card.dataset.immortalArtifact=item.id;
      card.dataset.grade=String(item.grade);
      const header=make('div',null,'ia-item-heading');
      const seal=make('div',null,'ia-grade-seal');seal.setAttribute('aria-label',item.grade_name);seal.append(make('strong',numeral[item.grade]),make('small','品'));
      const name=make('div',null,'ia-item-name');name.append(make('h3',item.name),make('span',item.source==='natal'?'本命法宝':item.source==='crafted'?'炼器成品':'随身装备','ia-source'));
      header.append(seal,name,make('span','仙级伤害','ia-damage'));card.append(header);
      const progress=make('ol',null,'ia-grade-track');progress.setAttribute('aria-label',`当前${item.grade_name}，最高一品`);
      for(const rank of [5,4,3,2,1]){
        const step=make('li',ranks[rank]);step.className=rank===item.grade?'current':rank>item.grade?'complete':'pending';
        if(rank===item.grade)step.setAttribute('aria-current','step');progress.append(step);
      }
      card.append(progress);
      const footer=make('div',null,'ia-item-footer');
      if(item.next_grade){
        const cost=make('div',null,'ia-cost');cost.append(make('small','进阶所需'),make('strong',`${item.material_name} × ${item.cost}`));
        const held=state.materials.find(m=>m.id===item.material_id)?.quantity||0;
        cost.append(make('span',`持有 ${held} / 所需 ${item.cost}`,held>=item.cost?'ia-enough':'ia-short'));footer.append(cost);
        const action=make('div',null,'ia-action');
        const button=make('button',`培养至${ranks[item.next_grade]} →`);button.type='button';button.dataset.immortalRefine=item.id;button.dataset.unavailable=item.can_refine?'0':'1';button.disabled=!item.can_refine;button.title=item.reason||'消耗所列材料，原战力不变';
        button.onclick=()=>send({artifact_id:item.id,expected_grade:item.grade,expected_revision:state.revision});action.append(button);
        if(item.reason)action.append(make('small',item.reason));footer.append(action);
      }else footer.append(make('p','一品已成 · 已达培养上限','immortal-artifact-max'));
      card.append(footer);
      list.append(card);
    }
    if(!state.equipment.length){
      const empty=make('div',null,'ia-empty');empty.append(make('span','器','ia-empty-seal'),make('h3','仙器尚待入册'),make('p','取得仙级伤害装备后，即可在此培养。也可在本命页温养至少37次，再以三铸神魔铁进阶。'));list.append(empty);
    }
    root.append(list);
  }
  window.ImmortalArtifacts={render(data,send){
    const state=data.immortal_artifacts||{available:false};
    const panel=document.querySelector('#immortal-artifacts-card'),button=document.querySelector('[data-panel-target=immortal-artifacts]');
    panel.classList.toggle('hidden',!state.available);button.classList.toggle('hidden',!state.available);
    if(!state.available){window.UtilityPanels?.close('immortal-artifacts');return;}
    panel.querySelector('h2').textContent=state.title+'培养';panel.setAttribute('aria-label',state.title+'培养');button.querySelector('small').textContent=state.title;button.title=state.title+' · 五品至一品培养';
    window.UtilityPanels.schedule('immortal-artifacts',()=>draw(state,send));
  }};
})();
