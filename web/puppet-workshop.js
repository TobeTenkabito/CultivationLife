(() => {
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  let owner,draft={},generation=0;
  function render(game,preview,craft){
    const root=document.getElementById('puppet-workshop');root.replaceChildren();
    const system=game.demonic_system?.puppet_crafting;
    for(const selector of ['#puppet-workshop-card','[data-panel-target=puppet-workshop]'])document.querySelector(selector).classList.toggle('hidden',!system);
    if(!system){window.UtilityPanels?.close('puppet-workshop');return;}
    const token=++generation;
    if(owner!==game.id){owner=game.id;draft={};}
    root.append(el('h3','机关工坊'),el('p',system.description));
    const grid=el('div');grid.className='puppet-component-grid';root.append(grid);
    const selects={};
    for(const [key,title] of [['form','成品形态'],['core','傀儡核心 · 神识'],['shell','傀儡外材 · 炼体'],['energy','傀儡能源 · 修为']]){
      const label=el('label',title),select=el('select');select.setAttribute('aria-label',title);selects[key]=select;label.append(select);grid.append(label);
    }
    function options(key,rows){const node=selects[key];node.replaceChildren();for(const row of rows)node.add(new Option(`${row.name}${row.quantity?' ×'+row.quantity:''}`,row.id));
      if(!rows.length)node.add(new Option('暂无对应材料，请前往坊市',''));
      if(rows.some(r=>r.id===draft[key]))node.value=draft[key];draft[key]=node.value;
    }
    options('form',system.forms);options('core',system.materials.filter(r=>r.slot==='core'));options('energy',system.materials.filter(r=>r.slot==='energy'));
    const output=el('p','选定三类材料后，自动推演成品。');output.className='puppet-result';output.setAttribute('aria-live','polite');root.append(output);
    const button=el('button','打造所选傀儡');button.id='craft-puppet';button.type='button';button.dataset.unavailable='1';button.disabled=true;root.append(button);
    const help=el('p','各材料消耗一份；无需青锋灵剑。低阶材料不会因玩家境界高而自动升阶。成品可以继续培养修为、炼体、神识。');help.className='muted';root.append(help);
    let request=0,approved=null;
    async function update(){
      const current=++request;approved=null;button.dataset.unavailable='1';button.disabled=true;
      const payload=Object.fromEntries(Object.entries(selects).map(([k,n])=>[k,n.value]));draft={...payload};
      if(!payload.core||!payload.shell||!payload.energy){output.textContent='请在坊市购买对应核心、外材和能源；三项齐全后可查看成品预览。';return;}
      output.textContent='正在推演成品……';
      try{const q=await preview(payload);if(generation!==token||request!==current)return;
        output.textContent=`${q.form_name} · 修为 ${q.cultivation_name} · 炼体 ${q.body_name}（普通 ${q.body_training}/100层，高阶肉身 ${q.immortal_body_level}层） · 神识 ${q.sense_name}（${q.divine_sense_rank}阶） · 总战力 ${q.combat_power.toLocaleString('zh-CN')}。${q.reason||'成功率100%，消耗所选材料各一份。'}`;
        approved=payload;button.dataset.unavailable=q.can_craft?'0':'1';
        button.disabled=!q.can_craft||!!game.pending_event||!!game.trial?.active||!!game.imprisonment||!!game.player.sealed_cultivation;
      }catch(error){if(generation===token&&request===current)output.textContent=error.message;}
    }
    selects.form.onchange=()=>{draft.form=selects.form.value;options('shell',system.materials.filter(r=>r.slot==='shell'&&r.form===draft.form));update();};
    for(const key of ['core','shell','energy'])selects[key].onchange=update;
    options('shell',system.materials.filter(r=>r.slot==='shell'&&r.form===draft.form));
    button.onclick=()=>{if(approved&&!button.disabled)craft(approved);};update();
  }
  window.PuppetWorkshop={render};
})();
