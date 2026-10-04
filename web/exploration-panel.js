/* Base-game spatial travel and talismans; all writes use named engine actions. */
(() => {
  'use strict';
  const node = (tag, text) => { const e=document.createElement(tag); if(text!=null)e.textContent=text; return e; };
  const select = (label, rows) => { const e=node('select'); e.setAttribute('aria-label',label); rows.forEach(r=>e.append(new Option(r.name,r.id))); return e; };
  const section = (id,parent,title) => {
    let e=document.getElementById(id);
    if(!e){ e=node('section'); e.id=id; e.className='exploration-section'; document.querySelector(parent)?.append(e); }
    e.replaceChildren(node('h3',title)); return e;
  };
  function render(game, mutate) {
    const locked=!game.player.alive || !!game.pending_event || !!game.trial?.active;
    const button=(title,kind,action,payload={},disabled=false)=>{
      const b=node('button',title); b.type='button'; b.disabled=locked||disabled;
      b.onclick=()=>mutate(`/api/games/${game.id}/${kind}-action`,{action,...payload}); return b;
    };
    const t=game.talismans;
    if(t){
      const root=section('talisman-panel','#inventory-card','符箓');
      root.append(node('p','符箓只有威力、防护、辅助、次数四个维度。每调用一个非零属性，扣除一次；战斗开始按威力→防护→辅助调用，单项加成最多 8%。'));
      t.methods.forEach(m=>root.append(button(m.learned?`已学：${m.name}`:`学习${m.name} · ${m.cost}灵石`,'talisman','learn',{method_id:m.id},m.learned)));
      const form=node('div'); form.className='exploration-grid';
      const method=select('制符法',t.methods.filter(m=>m.learned));
      const materials=t.materials.map(m=>({...m,name:`${m.name} × ${m.quantity}`}));
      const first=select('材料一',materials), second=select('材料二',materials);
      const elements={metal:'金',wood:'木',water:'水',fire:'火',earth:'土',wind:'风',thunder:'雷',yin:'阴',yang:'阳'};
      const element=select('法术灵力',t.elements.map(id=>({id,name:elements[id]||id})));
      const helper=select('注灵修士',[{id:'',name:'自行注灵'},...t.helpers.map(n=>({...n,name:`${n.name}（${n.elements.map(k=>elements[k]||k).join('、')}）`}))]);
      const make=button('合成符箓','talisman','craft',{},!method.options.length);
      make.onclick=()=>mutate(`/api/games/${game.id}/talisman-action`,{action:'craft',method_id:method.value,material1:first.value,material2:second.value,element:element.value,npc_id:helper.value});
      form.append(method,first,second,element,helper,make); root.append(form);
      t.rows.forEach(row=>{
        const card=node('div'); card.className='exploration-row';
        card.append(node('p',`${row.name} · 威力 ${row.power} · 防护 ${row.protection} · 辅助 ${row.assistance} · 剩余 ${row.uses} 次`),
          button(row.enabled?'停用':'启用','talisman','toggle',{talisman_id:row.id},row.uses<=0),
          button('弃去','talisman','discard',{talisman_id:row.id})); root.append(card);
      });
    }
    const s=game.spatial; if(!s)return;
    document.querySelectorAll('[data-panel-target]').forEach(dock=>{
      const local=['map','inventory','settings','secret-art','formation','combat-plan'];
      dock.classList.toggle('spatial-unavailable',s.inside && !local.includes(dock.dataset.panelTarget));
      if(s.inside && !local.includes(dock.dataset.panelTarget)) window.UtilityPanels?.close(dock.dataset.panelTarget);
    });
    const root=section('spatial-panel','#map-card',s.scene?s.scene.name:'空间裂缝');
    const maps=document.getElementById('map-locations'); if(maps)maps.hidden=s.inside;
    document.getElementById('map-view-tabs')?.classList.toggle('spatial-unavailable',s.inside);
    document.getElementById('map-directory')?.classList.toggle('spatial-unavailable',s.inside);
    if(s.scene){
      document.getElementById('map-title').textContent=`${s.scene.name}地图`;
      document.getElementById('map-current').textContent=`当前：${game.player.location_name}`;
      document.getElementById('map-description').textContent='独立空间内移动、探索及人物交流各消耗一年；外界入口暂不可用。';
    }
    root.append(node('p',`护持评分 ${s.protection.score.toFixed(1)} = 符箓防护 ${s.protection.talisman_protection.toFixed(1)} × ${s.weights.protection} + 阵法生势 ${s.protection.formation_growth.toFixed(1)} × ${s.weights.growth}。进入才消耗符箓；不足则身死道消。裂缝是单程通道。`));
    if(s.can_open)root.append(button('消耗四分之一法力开辟裂缝','spatial','open'));
    s.rifts.forEach(r=>{
      const location=(s.scene?.locations||game.map?.locations||[]).find(m=>m.id===r.location_id)?.name || r.location_id;
      const card=node('div'); card.className='exploration-row';
      card.append(node('p',`${location} · 护持要求 ${r.requirement} · 尚存 ${r.expires_age-game.player.age} 年`),
        button(s.protection.score<r.requirement?'进入裂缝（护持不足，必死）':'进入裂缝','spatial','enter',{target_id:r.id},r.location_id!==(s.scene?.location_id||game.player.location_id)));root.append(card);
    });
    if(!s.rifts.length)root.append(node('p','当前未发现仍开放的裂缝。裂缝随时间刷新。'));
    if(s.scene){
      const scene=s.scene;
      root.append(node('p',`界面等级 ${scene.tier}。${scene.kind==='secluded'?'此地修炼收益为普通地图的六倍，魔修不受自然修炼折损；只能等待裂缝或于化神后期自行开辟。':'本界容纳至大乘九层，九阶道果将被排斥。此界人物仍会老去并经历雷劫。'} 外界交互暂停；此地专属产物不会进入外界货源。`),
        button('探索 · 一年','spatial','explore'));
      scene.locations.forEach(l=>root.append(button(l.id===scene.location_id?`所在：${l.name}`:`前往${l.name}`,'spatial','move',{target_id:l.id},l.id===scene.location_id)));
      scene.sects.forEach(f=>root.append(button(scene.joined_sect===f.id?`已加入${f.name}`:`拜入${f.name}`,'spatial','join',{target_id:f.id},f.location_id!==scene.location_id || scene.joined_sect===f.id)));
      scene.npcs.forEach(n=>root.append(button(`${n.name} · ${n.realm_index}阶${n.layer}层 · ${n.alive?'交流':n.death_reason}`,'spatial','talk',{target_id:n.id},!n.alive)));
    }
    if(!s.inside && (game.secret_arts?.suppression?.active || (game.player.realm_index>=6) || s.visited.length)){
      const panel=node('details');panel.append(node('summary','秘法下界至失落界面'));
      panel.append(node('p','须有九阶真实道果，并先用压制秘法将显露修为降至大乘九层以内。可定向重访，或生成一个新界面。'),button('随机新界面','spatial','descend'));
      s.visited.forEach(v=>panel.append(button(`重访${v.name}`,'spatial','descend',{target_id:v.id})));root.append(panel);
    }
  }
  window.ExplorationPanel={render};
})();
