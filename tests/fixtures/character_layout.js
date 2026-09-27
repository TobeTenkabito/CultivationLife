/* Shared by Chromium and the separate Android instrumentation APK. No save writes. */
window.CharacterLayoutProbe = (() => {
  const npc = {
    id:'layout-test-npc', name:'闻宁', title:'外门弟子', gender_name:'男', race_name:'人族',
    path_name:'佛修', spirit_root_name:'伪灵根（金 · 木 · 水 · 火 · 土）', age:43, lifespan:117,
    realm_name:'练气2层', combat_power:126, breakthrough_chance:.01, affinity:-12,
    attitude:'冷淡', wounds:2, treasure_name:'九转玲珑护身宝塔', perceived_alive:true, status:'宗门内修行',
    can_request_master:true, can_accept_disciple:true, can_invite_party:true,
    can_propose_companion:true, can_befriend:true, can_recruit_concubine:true, can_intercept:true
  };
  function mount(panel) {
    if (panel==='faction') {
      renderFaction({member:true,name:'菩提寺',role:'宗门弟子',description:'同门修士',join_age:18,
        contribution:12,reward_options:{},fallen_count:0,roster:[
          {...npc,is_player:true,name:'独孤惊鸿',affinity:null,breakthrough_chance:null,wounds:0,treasure_name:null,
            can_request_master:false,can_accept_disciple:false,can_invite_party:false,
            can_propose_companion:false,can_befriend:false,can_recruit_concubine:false,can_intercept:false},
          npc,{...npc,name:'司徒长风临江听雨问道真人',realm_name:'大乘后期圆满',combat_power:1000000000000}
        ]});
    } else if (panel==='world-npc') renderWorldNpcs([npc,{...npc,name:'司徒长风临江听雨问道真人'}]);
    else if (panel==='family') renderFamily({exists:true,name:'独孤氏',description:'家族成员',same_world:true,living_count:1,offspring:[npc],roster:[{...npc,alive:true,member_type:'族人'}]});
    else if (panel==='relationship') renderParty([{...npc,can_interact:true,can_cross_spirit:true}]);
    else if (panel==='sage') renderSageSystem({available:true,teaching_available:true,doctrines:[
      {id:'layout',name:'经世学说',members:[{...npc,name:'司徒长风临江听雨问道真人',rank:1,role_name:'执掌者',inner:123456,combat_power:1000000000000}]}]});
    UtilityPanels.open(panel);
  }
  function check(panel) {
    const failures=[];
    const expect=(ok,msg)=>{if(!ok)failures.push(msg);};
    const card=document.getElementById(panel+'-card');
    expect(getComputedStyle(card).visibility==='visible','panel not visible');
    expect(card.scrollWidth<=card.clientWidth+2,'panel overflow');
    const bounds=card.getBoundingClientRect();
    for(const button of document.querySelectorAll('.brand .theme-open,.brand .text-button')) {
      const b=button.getBoundingClientRect(),x=(b.left+b.right)/2,y=(b.top+b.bottom)/2;
      if(x>bounds.left&&x<bounds.right&&y>bounds.top&&y<bounds.bottom)
        expect(document.elementFromPoint(x,y)!==button,'background toolbar covers panel');
    }
    const rowSelector={faction:'.roster-row','world-npc':'.world-npc-row',family:'.family-row',relationship:'.party-row',sage:'.sage-member-row'}[panel];
    const rows=[...card.querySelectorAll(rowSelector)];
    expect(rows.length>0,'missing rows');
    rows.forEach((row,i)=>{
      const r=row.getBoundingClientRect();
      expect(row.scrollWidth<=row.clientWidth+2,'row overflow '+i);
      const info=row.querySelector('.roster-identity,.party-member-info')||row.firstElementChild;
      if(panel!=='family')expect(info.getBoundingClientRect().width>r.width*(panel==='sage'?.45:.65),'identity squeezed '+i);
      for(const button of row.querySelectorAll('button')){
        const b=button.getBoundingClientRect();
        expect(b.left>=r.left-1&&b.right<=r.right+1,'button outside card '+i);
        if(panel==='faction')expect(b.top>=info.getBoundingClientRect().bottom-1,'actions overlap identity');
      }
    });
    if(panel==='faction') {
      const fields=[...rows[1].querySelectorAll('dt')].map(n=>n.textContent);
      expect(['年龄','寿元','战力','突破','好感','伤势','重宝'].every(n=>fields.includes(n)),'missing status');
      expect(rows[1].querySelectorAll('button').length===7,'missing actions');
      expect(rows[0].querySelectorAll('button').length===0,'player has NPC actions');
      expect(rows[1].getBoundingClientRect().height<650,'single-character column');
    }
    return failures;
  }
  return {mount,check};
})();
