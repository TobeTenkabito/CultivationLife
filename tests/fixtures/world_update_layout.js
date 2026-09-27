/* Shared atlas/growth layout contract for Chromium and Android 12 WebView. */
window.WorldUpdateProbe = (() => {
  function mount(panel) {
    if (panel === 'map') {
      document.querySelector('#player-details-dialog').close();
      const map = JSON.parse(JSON.stringify(game.map));
      const place = map.locations[0];
      place.factions = [
        {id:'long-sect', name:'太元归墟九霄剑宗', kind:'sect', owned:true},
        {id:'long-clan', name:'独孤氏修仙世家', kind:'family'},
        {id:'race', name:'远古羽族', kind:'race'},
      ];
      place.wars = [{id:'war', attacker:'太元归墟九霄剑宗', defender:'玄海长生万象宫'}];
      place.ghost_parade = {status:'active', start_age:game.player.age};
      renderMap(map, {available:true, location_id:place.id, status:'scheduled', actions_until_open:2});
      UtilityPanels.open('map');
      const tabs = document.querySelectorAll('#map-view-tabs button');
      tabs[1].click();
      document.querySelector('#map-directory-filters');
      document.querySelectorAll('.map-directory-filters button')[0].click();
      document.querySelector('#map-card').scrollTop=0;
    } else {
      UtilityPanels.close('map');
      renderKnownTechniques(WorldUpdateProbe.techniques);
      const dialog=document.querySelector('#player-details-dialog');if(!dialog.open)dialog.showModal();
      const library = document.querySelector('#known-technique-list').closest('details');
      library.open=true;library.scrollIntoView({block:'start'});
    }
  }
  function check(panel) {
    const failures=[];
    const expect=(okay,message)=>{if(!okay)failures.push(message);};
    const card=document.querySelector(panel==='map'?'#map-card':'#known-technique-list');
    expect(card.getBoundingClientRect().width>100,'content is hidden');
    expect(card.scrollWidth<=card.clientWidth+2,'horizontal overflow');
    if(panel==='map') {
      expect(card.querySelectorAll('.map-directory-entry.faction').length>=3,'faction rows missing');
      expect(card.querySelectorAll('.map-directory-entry.war').length>=1,'war notice missing');
      expect(card.querySelectorAll('select').length===0,'native dropdown introduced');
    } else {
      expect(card.querySelectorAll('.technique-growth').length>=4,'growth previews missing');
      expect(card.textContent.includes('战斗倾向'),'combat preference missing');
    }
    card.querySelectorAll('.map-directory-entry,.known-technique').forEach((row,index)=>{
      expect(row.scrollWidth<=row.clientWidth+2,'row overflow '+index);
      const text=row.querySelector('strong,b');
      expect(text.getBoundingClientRect().width>80,'squeezed text '+index);
    });
    return failures;
  }
  return {mount,check,techniques:[]};
})();

WorldUpdateProbe.techniques=[{"id":"TECH_COMMON_GUI","path":"dao","name":"太元归墟剑","element":"neutral","grade":4,"level":5,"opportunity_bonus":0.31551999999999997,"hp_bonus":0.39168,"mp_bonus":0.8432,"combat_bonus":12783.999999999998,"karma_multiplier":1.0,"category":"spiritual","body_breakthrough_bonus":0.0,"body_bonus_max_layer":null,"sources":{"spirit":1.0},"combat_requirements":{"source":{"id":"spirit","op":">=","level":8}},"divine_sense_bonus":0.0,"transformation_capacity":0,"transformation_space":0,"initial_transformations":[],"requires_immortal_power":false,"immortal_power_cost":0.0,"required_body_training":0,"possession_limit_bonus":0,"ignore_possession_limit":false,"growth_preference":"combat","base_opportunity_bonus":0.2,"base_hp_bonus":0.24,"base_mp_bonus":0.5,"base_combat_bonus":5000.0,"base_divine_sense_bonus":0.0,"base_body_breakthrough_bonus":0.0,"base_transformation_capacity":0,"base_transformation_space":0,"next_level_gains":{"opportunity_bonus":0.010880000000000046,"hp_bonus":0.01631999999999996,"mp_bonus":0.04079999999999995,"combat_bonus":1496.0000000000018,"divine_sense_bonus":0.0,"body_breakthrough_bonus":0.0,"transformation_capacity":0,"transformation_space":0},"growth_name":"战斗","growth_multipliers":{"opportunity_bonus":1.16,"hp_bonus":1.2,"mp_bonus":1.24,"combat_bonus":1.88,"divine_sense_bonus":1.2799999999999998,"body_breakthrough_bonus":1.2799999999999998,"transformation_capacity":1.2799999999999998},"level_multiplier":1.4,"effect_multiplier":2.5567999999999995,"max_level":9,"upgrade_copies":0,"manuals_by_level":[],"can_upgrade":false,"effective_karma_multiplier":1.0,"source_names":["灵源"],"source_display":"灵源","environment_active":false,"environment_multiplier":null,"combat_requirement_display":"灵气 >= 8级","combat_requirement_met":false,"immortal_power_met":true,"body_requirement_met":true,"element_name":"无属性","compatible":true,"category_name":"修仙"},{"id":"TECH_BODY_MORTAL","path":"dao","name":"铁骨锻身诀","element":"neutral","grade":1,"level":5,"opportunity_bonus":0.045599999999999995,"hp_bonus":0.24672,"mp_bonus":0.034199999999999994,"combat_bonus":13.68,"karma_multiplier":1.0,"category":"body","body_breakthrough_bonus":0.37008,"body_bonus_max_layer":20,"sources":{"spirit":1.0},"combat_requirements":{"source":{"id":"spirit","op":">=","level":0}},"divine_sense_bonus":0.0,"transformation_capacity":0,"transformation_space":0,"initial_transformations":[],"requires_immortal_power":false,"immortal_power_cost":0.0,"required_body_training":0,"possession_limit_bonus":0,"ignore_possession_limit":false,"growth_preference":"main","base_opportunity_bonus":0.04,"base_hp_bonus":0.12,"base_mp_bonus":0.03,"base_combat_bonus":12.0,"base_divine_sense_bonus":0.0,"base_body_breakthrough_bonus":0.18,"base_transformation_capacity":0,"base_transformation_space":0,"next_level_gains":{"opportunity_bonus":0.0014000000000000056,"hp_bonus":0.04127999999999998,"mp_bonus":0.0010500000000000043,"combat_bonus":0.4200000000000017,"divine_sense_bonus":0.0,"body_breakthrough_bonus":0.061919999999999975,"transformation_capacity":0,"transformation_space":0},"growth_name":"炼体","growth_multipliers":{"opportunity_bonus":1.14,"hp_bonus":2.056,"mp_bonus":1.14,"combat_bonus":1.14,"divine_sense_bonus":1.14,"body_breakthrough_bonus":2.056,"transformation_capacity":1.14},"level_multiplier":1.4,"effect_multiplier":1.14,"max_level":9,"upgrade_copies":0,"manuals_by_level":[],"can_upgrade":false,"effective_karma_multiplier":1.0,"source_names":["灵源"],"source_display":"灵源","environment_active":false,"environment_multiplier":null,"combat_requirement_display":"灵气 >= 0级","combat_requirement_met":true,"immortal_power_met":true,"body_requirement_met":true,"element_name":"无属性","compatible":true,"category_name":"炼体"},{"id":"TECH_SPIRIT_SENSE","path":"dao","name":"凝神观想法","element":"neutral","grade":1,"level":5,"opportunity_bonus":0.056999999999999995,"hp_bonus":0.045599999999999995,"mp_bonus":0.11399999999999999,"combat_bonus":11.399999999999999,"karma_multiplier":1.0,"category":"divine_sense","body_breakthrough_bonus":0.0,"body_bonus_max_layer":null,"sources":{"spirit":1.0},"combat_requirements":{"source":{"id":"spirit","op":">=","level":0}},"divine_sense_bonus":0.2928,"transformation_capacity":0,"transformation_space":0,"initial_transformations":[],"requires_immortal_power":false,"immortal_power_cost":0.0,"required_body_training":0,"possession_limit_bonus":0,"ignore_possession_limit":false,"growth_preference":"main","base_opportunity_bonus":0.05,"base_hp_bonus":0.04,"base_mp_bonus":0.1,"base_combat_bonus":10.0,"base_divine_sense_bonus":0.12,"base_body_breakthrough_bonus":0.0,"base_transformation_capacity":0,"base_transformation_space":0,"next_level_gains":{"opportunity_bonus":0.0017500000000000072,"hp_bonus":0.0014000000000000056,"mp_bonus":0.0035000000000000144,"combat_bonus":0.3500000000000014,"divine_sense_bonus":0.05819999999999998,"body_breakthrough_bonus":0.0,"transformation_capacity":0,"transformation_space":0},"growth_name":"神识","growth_multipliers":{"opportunity_bonus":1.14,"hp_bonus":1.14,"mp_bonus":1.14,"combat_bonus":1.14,"divine_sense_bonus":2.44,"body_breakthrough_bonus":1.14,"transformation_capacity":1.14},"level_multiplier":1.4,"effect_multiplier":1.14,"max_level":9,"upgrade_copies":0,"manuals_by_level":[],"can_upgrade":false,"effective_karma_multiplier":1.0,"source_names":["灵源"],"source_display":"灵源","environment_active":false,"environment_multiplier":null,"combat_requirement_display":"灵气 >= 0级","combat_requirement_met":true,"immortal_power_met":true,"body_requirement_met":true,"element_name":"无属性","compatible":true,"category_name":"神识"},{"id":"TECH_BEAST_TRANSFORMATION","path":"monster","name":"百兽化形诀","element":"neutral","grade":4,"level":5,"opportunity_bonus":0.3720959999999999,"hp_bonus":0.434112,"mp_bonus":0.3720959999999999,"combat_bonus":3720.9599999999996,"karma_multiplier":1.0,"category":"transformation","body_breakthrough_bonus":0.0,"body_bonus_max_layer":null,"sources":{"monster":1.0},"combat_requirements":{"source":{"id":"monster","op":">=","level":8}},"divine_sense_bonus":0.0,"transformation_capacity":6,"transformation_space":4,"initial_transformations":[],"requires_immortal_power":false,"immortal_power_cost":0.0,"required_body_training":0,"possession_limit_bonus":0,"ignore_possession_limit":false,"growth_preference":"main","base_opportunity_bonus":0.24,"base_hp_bonus":0.28,"base_mp_bonus":0.24,"base_combat_bonus":2400.0,"base_divine_sense_bonus":0.0,"base_body_breakthrough_bonus":0.0,"base_transformation_capacity":3,"base_transformation_space":2,"next_level_gains":{"opportunity_bonus":0.011424000000000021,"hp_bonus":0.013328000000000026,"mp_bonus":0.011424000000000021,"combat_bonus":114.24000000000021,"divine_sense_bonus":0.0,"body_breakthrough_bonus":0.0,"transformation_capacity":1,"transformation_space":0},"growth_name":"变化","growth_multipliers":{"opportunity_bonus":1.14,"hp_bonus":1.14,"mp_bonus":1.14,"combat_bonus":1.14,"divine_sense_bonus":1.14,"body_breakthrough_bonus":1.14,"transformation_capacity":1.912},"level_multiplier":1.4,"effect_multiplier":1.5503999999999998,"max_level":9,"upgrade_copies":0,"manuals_by_level":[],"can_upgrade":false,"effective_karma_multiplier":1.0,"source_names":["妖源"],"source_display":"妖源","environment_active":false,"environment_multiplier":null,"combat_requirement_display":"妖气 >= 8级","combat_requirement_met":false,"immortal_power_met":true,"body_requirement_met":true,"element_name":"无属性","compatible":true,"category_name":"变身"}];
