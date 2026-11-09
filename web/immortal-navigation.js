/* Presentation only: each destination retains the authoritative API and quotes. */
(() => {
  const el=(...args)=>window.GameUi.element(...args);
  function render(game,dispatch) {
    const pool=game.yaochi||{},blocked=!!game.pending_event||!game.player.alive||!!game.active_trial;
    function panel(id,available,caption,description,draw) {
      document.getElementById(id+'-card').classList.toggle('hidden',!available);
      document.querySelector(`[data-panel-target="${id}"]`).classList.toggle('hidden',!available);
      if(!available)window.UtilityPanels.close(id);
      window.UtilityPanels.schedule(id,available?()=>{
        const root=document.getElementById(id+'-content');root.replaceChildren();
        const intro=el('header',null,'immortal-directory-intro');
        intro.append(el('small',caption,'yaochi-eyebrow'),el('p',description));root.append(intro);
        const groups=draw(root).filter(([,nodes])=>nodes.some(Boolean)).map(([name,nodes])=>[name,nodes.filter(Boolean)]);
        window.PanelPages.mount(id,root,groups);
      }:null);
    }
    panel('immortal-practice',!!(pool.identity||pool.westward?.available),'自身 · 仙途','仙籍与职责，师承与精进。办理仍遵循原地点和实际工时。',root=>[
      ['专修',[pool.westward?.available?window.YaochiWestward.render(root,game,dispatch):null]],
      ['仙籍与功德',[pool.identity?window.WestwardFinale.identity(root,game,dispatch):null]]]);
    panel('immortal-estate',!!(pool.antiquity?.enabled||pool.antiquity?.active||pool.purple_east),'外界 · 仙府','探访古仙府，参与紫气现世后的调查、公议与营建。',root=>[
      ['访古',[pool.antiquity?window.WestwardVentures.antiquity(root,game,dispatch,blocked):null]],
      ['紫气东来',[pool.purple_east?window.WestwardFinale.story(root,game,dispatch):null]]]);
  }
  window.ImmortalNavigation={render};
})();
