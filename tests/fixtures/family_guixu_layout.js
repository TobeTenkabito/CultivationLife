/* Renderer contracts run in Chromium and Android's release WebView; no save mutation. */
window.FamilyGuixuProbe=(()=>{
  let last;
  const child={id:'heir',name:'独孤惊鸿临江听雨',alive:true,age:20,realm_name:'筑基后期',
    spirit_root_name:'变异灵根（风）',combat_power:12345678,can_interact:true,can_marry:true,member_type:'本家',
    infusion:{allowed:true,cost:1300,cap_name:'结丹后期'}};
  const family={exists:true,id:'family-test',name:'独孤氏',same_world:true,living_count:2,can_manage:true,
    total_power:123456789012,protection_realm:'元婴',pressure:1,reproduction_enabled:true,intrigue_enabled:true,
    roster:[child,{...child,id:'elder',name:'司徒长风',sect_name:'太一仙宗',spouse_name:'顾清',can_marry:false}],offspring:[],
    teaching_options:[{id:'book',name:'玄天九霄御雷真诀',power:1350}],equipment_options:[{id:'sword',name:'九转玲珑护身法宝',quantity:1,power:10000}],
    ledger:{resources:12345678,income:159000,expenses:79000,balance:80000,dividend:12000,office_income:25000,tribute:32000,shortfall:0},
    diplomacy:[{id:'sect',name:'太一仙宗',kind:'sect',status:'alliance',total_power:123456789},
      {id:'rival',name:'南宫修仙世家',kind:'family',status:'neutral',total_power:150000}],
    other_families:[{id:'rival',name:'南宫修仙世家',living_count:33,total_power:150000,description:'镇守商路的修仙世家。'}]};
  function mount(kind) {
    last=null;
    if(kind==='family'){
      renderFamily(family);
      const root=document.querySelector('#family-content');
      root.innerHTML='';FamilyPanel.render(root,family,p=>last=p);
    } else {
      const session={dungeon_name:'人界归墟',layer_id:'outer',remaining_days:25,return_days:2,
        player_ever_claimed:true, pending_team_offer:kind==='offer'?{name:'临江散人'}:null,
        layers:[{id:'outer',name:'外层',current:true},{id:'middle',name:'中层'}],actors:[],treasures:[],
        companions:kind==='offer'?[]:[{actor_id:'ally',name:'临江散人',has_treasure:false,empty_intervals:2}],
        transferable_treasures:[{pool_entry_id:'treasure',name:'玄水潮生万象镜'}]};
      GuixuPanel.render({available:true,session},p=>last=p);
    }
    UtilityPanels.open(kind==='family'?'family':'guixu');
  }
  function check(kind) {
    const failures=[],card=document.querySelector('#'+(kind==='family'?'family':'guixu')+'-card');
    const expect=(ok,text)=>{if(!ok)failures.push(text);};
    expect(getComputedStyle(card).visibility==='visible','panel hidden');
    expect(card.scrollWidth<=card.clientWidth+2,'panel overflow');
    for(const node of card.querySelectorAll('.family-member,.family-other,.family-metrics,.guixu-actor,.guixu-threat')){
      expect(node.scrollWidth<=node.clientWidth+2,'content overflow: '+node.className);
    }
    if(kind==='family'){
      expect(card.querySelectorAll('.family-member').length===2,'missing family members');
      for(const action of ['teach','gift_equipment','invite','infuse','marry','send_sect','expel','reproduction','fund','gather','diplomacy']){
        const button=[...card.querySelectorAll('[data-family]')].find(b=>JSON.parse(b.dataset.family).action===action);
        expect(!!button,'missing '+action);
        if(button && action!=='expel'){
          button.click();expect(last?.action===action,'wrong callback '+action);
          if(action==='teach')expect(last.technique_id==='book','missing technique');
          if(action==='gift_equipment')expect(last.item_id==='sword','missing equipment');
          if(action==='send_sect')expect(last.sect_id==='sect','missing sect');
        }
      }
    } else {
      const action=kind==='offer'?'team_accept':'gift_treasure';
      const button=[...card.querySelectorAll('[data-guixu]')].find(b=>JSON.parse(b.dataset.guixu).action===action);
      expect(!!button,'missing '+action);if(button){button.click();expect(last?.action===action,'wrong callback');}
      if(kind==='offer')expect([...card.querySelectorAll('[data-guixu]')].find(b=>JSON.parse(b.dataset.guixu).action==='search').disabled,'offer did not lock exploration');
    }
    return failures;
  }
  return {mount,check};
})();
