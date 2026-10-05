/* Base-game spatial travel and talismans; all writes use named engine actions. */
(() => {
  'use strict';
  const node = (tag, text) => { const e=document.createElement(tag); if(text!=null)e.textContent=text; return e; };
  const select = (label, rows) => { const e=node('select'); e.setAttribute('aria-label',label); rows.forEach(r=>e.append(new Option(r.name,r.id))); return e; };
  let selectedTier=null;
  function render(game, mutate) {
    const locked=!game.player.alive || !!game.pending_event || !!game.trial?.active;
    const button=(title,kind,action,payload={},disabled=false)=>{
      const b=node('button',title); b.type='button'; b.disabled=locked||disabled;
      b.className='exploration-action';b.dataset.unavailable=disabled?'1':'0';b.onclick=()=>mutate(`/api/games/${game.id}/${kind}-action`,{action,...payload}); return b;
    };
    const t=game.talismans;
    if(t){
      const root=document.getElementById('talisman-content'); root.replaceChildren();
      root.append(node('p',`制符 Lv.${t.skill.level} · 经验 ${t.skill.experience.toFixed(1)}。成功率随制符经验、等级与目标阶数变化；失败仍耗符材、注灵并获得经验。`));
      root.append(node('p','仅可使用本界同阶制符法与两份符材。每调用一个非零属性扣除一次；战斗按威力→防护→辅助调用，单项加成最多 8%。'));
      const tier=select('符箓阶数',[...new Set(t.methods.map(m=>m.tier))].map(id=>({id,name:`${id}阶符箓`}))), workspace=node('div');
      const remembered=selectedTier;
      tier.value=String([...tier.options].some(o=>o.value===remembered)?remembered:Math.max(...t.methods.filter(m=>m.available).map(m=>m.tier),Number(tier.options[0]?.value)||1));
      root.append(tier,workspace);
      const draw=()=>{
        workspace.replaceChildren();selectedTier=tier.value;
        const methods=t.methods.filter(m=>m.tier===Number(tier.value));
        const learning=node('details'),summary=node('summary',`本阶制符法 · ${methods.filter(m=>m.learned).length}/${methods.length} 已学`);learning.append(summary);
        methods.forEach(m=>learning.append(button(m.learned?`已学 ${m.name}`:`学习 ${m.name} · ${m.cost}灵石`,'talisman','learn',{method_id:m.id},m.learned||!m.available)));
        if(!methods.some(m=>m.learned))learning.open=true;
        workspace.append(learning);
        const form=node('div');form.className='exploration-grid';
        const field=(label,input)=>{const wrap=node('label',label);wrap.append(input);form.append(wrap);return input;};
        const method=field('制符法',select('制符法',methods.filter(m=>m.learned&&m.available)));
        const materials=t.materials.filter(m=>m.tier===Number(tier.value)).map(m=>({...m,name:`${m.name} × ${m.quantity}`}));
        const first=field('材料一',select('材料一',materials)),second=field('材料二',select('材料二',materials));
        if(second.options.length>1)second.selectedIndex=1;
        const elements={metal:'金',wood:'木',water:'水',fire:'火',earth:'土',wind:'风',thunder:'雷',yin:'阴',yang:'阳'};
        const element=field('法术灵力',select('法术灵力',t.elements.map(id=>({id,name:elements[id]||id}))));
        const helper=field('注灵修士',select('注灵修士',[{id:'',name:'自行注灵'},...t.helpers.map(n=>({...n,name:`${n.name}（${n.elements.map(k=>elements[k]||k).join('、')}）`}))]));
        const hint=node('p');const update=()=>{const m=methods.find(r=>r.id===method.value);hint.textContent=m?`炼制成功率 ${(m.success_chance*100).toFixed(1)}% · 基础威力 ${m.power} / 防护 ${m.protection} / 辅助 ${m.assistance} / 次数 ${m.uses}；品级与符材影响最终四维及估值。`:'先学习本阶制符法。';};method.onchange=update;update();
        const make=button('炼制符箓','talisman','craft',{},!method.options.length);
        make.onclick=()=>mutate(`/api/games/${game.id}/talisman-action`,{action:'craft',method_id:method.value,material1:first.value,material2:second.value,element:element.value,npc_id:helper.value});
        form.append(make);workspace.append(form,hint);
      };tier.onchange=draw;draw();
      root.append(node('h3','持有符箓'));
      t.rows.forEach(row=>{
        const card=node('div');card.className='exploration-row';
        card.append(node('strong',`${row.name} · ${row.quality_name}`),node('p',`威力 ${row.power} · 防护 ${row.protection} · 辅助 ${row.assistance} · 剩余 ${row.uses} 次 · 估值 ${row.value} 灵石`),button(row.enabled?'停用':'启用','talisman','toggle',{talisman_id:row.id},row.uses<=0),button('弃去','talisman','discard',{talisman_id:row.id}));root.append(card);
      });
      if(!t.rows.length)root.append(node('p','尚未持有符箓。符材可从本界坊市或商盟取得。'));
    }
    const s=game.spatial; if(!s)return;
    document.querySelectorAll('[data-panel-target]').forEach(dock=>{
      const local=[...(s.panels || []),'heavens'];
      dock.classList.toggle('spatial-unavailable',s.inside && !local.includes(dock.dataset.panelTarget));
      if(s.inside && !local.includes(dock.dataset.panelTarget)) window.UtilityPanels?.close(dock.dataset.panelTarget);
    });
    const maps=document.getElementById('map-locations'); if(maps)maps.hidden=false;
    document.querySelectorAll('.spatial-map-tools,.spatial-rift').forEach(e=>e.remove());
    let root=document.getElementById('spatial-panel');root?.remove();
    root=node('section');root.id='spatial-panel';root.className='spatial-map-tools';
    if(s.visible || s.scene)maps.prepend(root);
    document.getElementById('map-view-tabs')?.classList.toggle('spatial-unavailable',s.inside);
    document.getElementById('map-directory')?.classList.toggle('spatial-unavailable',s.inside);
    if(s.scene){
      maps.replaceChildren(root);
      document.getElementById('map-title').textContent=`${s.scene.name}地图`;
      document.getElementById('map-current').textContent=`当前：${game.player.location_name}`;
      document.getElementById('map-description').textContent='独立空间内移动、探索及人物交流各消耗一年；外界入口暂不可用。';
    }
    if(s.scene?.heavens_target){
      document.getElementById('map-description').textContent='镜律场域保留三处机关与稳定返程入口。';
      const ruins=s.scene.heavens_target==='causal_ruins';
      root.append(node('h3',ruins?'回潮阵室':'三镜回廊'),node('p',ruins?'请在诸天面板调查两端关联、读取、替换或取走唯一阵芯，也可沿原路退出。阵眼与记录均保留，遗址不刷新随机所得。':'请在诸天面板试探、破解、隔断或强攻，也可沿原路退出。普通修炼使用正常倍率，场域不刷新随机所得。'));
      const open=node('button','查看诸天机关与返程');open.type='button';open.onclick=()=>{window.HeavensPanel?.openTarget(s.scene.heavens_target);document.querySelector('[data-panel-target="heavens"]')?.click();};root.append(open);return;
    }
    if(s.visible){
      root.append(node('p',`护持评分 ${s.protection.score.toFixed(1)} = 符箓防护 × ${s.weights.protection} + 阵法生势 × ${s.weights.growth}。裂缝越接近崩溃，护持要求越高；不足则身死道消。`));
      if(s.can_open)root.append(button('消耗四分之一法力开辟裂缝','spatial','open'));
      if(!s.rifts.length)root.append(node('small','当前未发现仍开放的裂缝。'));
    }
    const appendRifts=(parent,locationId)=>{
      s.rifts.filter(r=>r.location_id===locationId).forEach(r=>{
        const card=node('section');card.className='spatial-rift';card.dataset.riftId=r.id;
        const left=r.expires_age-game.player.age,dying=left/(r.expires_age-r.created_age)<.25;
        card.append(node('strong',`${r.name}${dying?' · 濒临崩溃':''}`),node('p',`护持要求 ${r.requirement} · 尚存 ${left} 年 · 跨界概率 ${(r.passage_chance*100).toFixed(0)}%`),button(s.protection.score<r.requirement?'进入（护持不足，必死）':`进入${r.name}`,'spatial','enter',{target_id:r.id},locationId!==(s.scene?.location_id||game.player.location_id)));parent.append(card);
      });
    };
    if(!s.scene)maps.querySelectorAll('.map-location').forEach(row=>appendRifts(row,row.dataset.location));
    if(s.scene){
      const scene=s.scene;
      root.append(node('p',`界面等级 ${scene.tier}。${scene.kind==='secluded'?'此地修炼收益为普通地图的六倍，魔修不受自然修炼折损；只能等待裂缝或于化神后期自行开辟。':`${scene.resource_description||'本界修炼资源可支持至大乘后期。'} ${scene.power_description||'界面之力承载至大乘后期，九阶道果将被排斥。'} 本界人物仍会老去并经历雷劫。`} 外界交互暂停；此地专属产物不会进入外界货源。`),
        button('探索 · 一年','spatial','explore'));
      if(scene.population_rules){const r=scene.population_rules;root.append(node('p',`本界${r.abundance==='barren'?'资源匮乏':'资源寻常'}，修炼收益 ×${r.cultivation_multiplier}；初始修士最高 ${r.npc_realm_ceiling}阶后期。此为人口生成状况，并非界面修炼上限。`));}
      scene.locations.forEach(l=>{const card=node('article');card.className='map-location';card.dataset.location=l.id;card.append(node('h3',l.name),node('p',l.description||'独立空间内的地域。'),node('small',`气经验：${Object.entries(l.qi_gain_efficiencies).map(([key,value])=>`${({spirit:'灵气',demon:'魔气',monster:'妖气',yin:'阴气'})[key]} ×${value.toFixed(2)}`).join(' · ')}`),button(l.id===scene.location_id?'所在地':'前往 · 一年','spatial','move',{target_id:l.id},l.id===scene.location_id));appendRifts(card,l.id);root.append(card);});
      scene.sects.forEach(f=>root.append(button(scene.joined_sect===f.id?`已加入${f.name}`:`拜入${f.name}`,'spatial','join',{target_id:f.id},f.location_id!==scene.location_id || scene.joined_sect===f.id)));
      scene.npcs.forEach(n=>root.append(button(`${n.name} · ${n.realm_index}阶${n.layer}层 · ${n.alive?'交流':n.death_reason}`,'spatial','talk',{target_id:n.id},!n.alive)));
    }
    if(s.visible && !s.inside && (game.secret_arts?.suppression?.active || (game.player.realm_index>=6) || s.visited.length)){
      const panel=node('details');panel.append(node('summary','秘法下界至失落界面'));
      panel.append(node('p','须有九阶真实道果，并先用压制秘法将显露修为降至大乘九层以内。可定向重访，或生成一个新界面。'),button('随机新界面','spatial','descend'));
      s.visited.forEach(v=>panel.append(button(`重访${v.name}`,'spatial','descend',{target_id:v.id})));root.append(panel);
    }
  }
  window.ExplorationPanel={render};
})();
