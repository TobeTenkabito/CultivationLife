/* Extensions of original local building rows; no separate navigation button. */
(() => {
  let game,dispatch,governorDispatch,selected=null,saveId=null;
  const el=(...args)=>window.GameUi.element(...args);
  const current=()=>game?.map?.locations?.find(p=>p.id===game.map.current);
  function kind(id) {
    const pool=game?.yaochi||{},row=current()?.buildings?.find(r=>r.id===id);
    if(!game?.buildings||['lost','rift'].includes(game.map?.world))return null;
    if(game.upper_institution?.court?.governorship?.offices.some(r=>r.local && (r.building_id===id||r.city_id===id&&r.building_status==='unbuilt')))return 'governor';
    if(pool.earth?.available && (pool.earth.temple?.id===id && pool.earth.local || pool.earth.cities?.some(c=>c.id===id)))return 'earth';
    if(pool.garden?.local && pool.garden.building_id && id===pool.garden.building_id)return 'garden';
    if(row && pool.relief?.offers?.some(r=>r.id===id))return 'relief';
    return null;
  }
  function draw() {
    const type=kind(selected),root=document.getElementById('building-affairs-content');root.replaceChildren();
    if(!type){window.UtilityPanels.close('building-affairs');return;}
    const pool=game.yaochi||{},row=current()?.buildings?.find(r=>r.id===selected);
    document.querySelector('#building-affairs-card h2').textContent=(row?.name||'当地建筑')+' · '+({earth:'庙务',garden:'经营',relief:'修缮',governor:'府务'}[type]);
    root.dataset.dlcScope=type==='governor'?'asura-manifestation':'yaochi-westward';
    const back=el('button','返回此地建筑','building-return');back.type='button';back.onclick=()=>{window.UtilityPanels.open('map');window.MapDirectory?.openTerritory('influence',game.map.current);};root.append(back);
    if(type==='earth')window.EarthTemple.render(root,game,dispatch);
    if(type==='governor')window.AsuraGovernorship.render(root,game,governorDispatch,selected);
    if(type==='earth')window.InstitutionGovernance?.render(root,(pool.management||[]).filter(r=>r.identity===selected||r.id==='temple:'+selected),payload=>dispatch({action:'management',target_id:JSON.stringify(payload)}),true);
    if(type==='garden')window.YaochiGathering.garden(root,game,dispatch,!!game.pending_event||!game.player.alive||!!game.active_trial);
    if(type==='garden')window.WestwardDevelopment?.contracts(root,pool.contracts,dispatch);
    if(pool.relief?.offers?.some(r=>r.id===selected))window.WestwardFinale.relief(root,game,dispatch,selected);
  }
  function open(id) {
    if(!kind(id))return;
    selected=id;document.getElementById('building-affairs-card').classList.remove('hidden');
    window.PixelHome?.closeDrawer();window.UtilityPanels.schedule('building-affairs',draw);window.UtilityPanels.open('building-affairs');
    if(kind(id)==='earth' && game.yaochi.earth.temple && !game.yaochi.earth.local)document.querySelector('#building-affairs-content [data-subpage="庙域名录"]')?.click();
  }
  function control(row,place) {
    const type=place?.current && kind(row.id);if(!type)return null;
    const b=el('button',type==='governor'?'总督府':{earth:game.yaochi?.earth?.temple?(game.yaochi.earth.local?'庙务':'分庙营建'):'奉建土地庙',garden:'仙圃经营',relief:'功德修缮'}[type],'building-command');
    b.type='button';b.dataset.buildingAffairs=row.id;b.dataset.dlc=type==='governor'?'asura-manifestation':'yaochi-westward';
    b.onclick=event=>{event.preventDefault();event.stopPropagation();open(row.id);};return b;
  }
  function foundation(host,place) {
    const garden=game?.yaochi?.garden,id=garden?.building_id;
    if(place.current && garden?.local && id && !place.buildings?.some(r=>r.id===id)){const b=control({id},place);if(b)host.append(b);}
  }
  function bind(data,send,governorSend) {
    if(saveId!==data.id){selected=null;saveId=data.id;window.UtilityPanels.close('building-affairs');}
    game=data;dispatch=send;governorDispatch=governorSend;
    const office=game.upper_institution?.court?.governorship?.offices.find(r=>r.city_id===selected&&r.building_status!=='unbuilt');
    if(office)selected=office.building_id;
    if(selected && game.yaochi?.earth?.local && game.yaochi.earth.temple?.city_id===selected)selected=game.yaochi.earth.temple.id;
    document.getElementById('building-affairs-card').classList.toggle('hidden',!kind(selected));
    if(!kind(selected))window.UtilityPanels.close('building-affairs');
    window.UtilityPanels.schedule('building-affairs',selected?draw:null);
  }
  window.BuildingAffairs={bind,control,foundation};
})();
