/* Evidence-only view. Commands always carry the revision shown on the page. */
(() => {
  let game, send, expandedPerson = null, busy = () => false, activeTab='journal', workspaceKey='';
  let atlasRevision='',atlasSelection=null,atlasObserver=null;
  let mailDraft={topic:'ask_location',recipient:'',site:''};
  const compactQuery=window.matchMedia('(max-width:959px), (max-height:540px)');
  const qualities={'普通':['ordinary','谨慎探行'],'稀有':['rare','险中藏珍'],'史诗':['epic','群雄逐宝'],'传奇':['legendary','凶险争夺']};
  const el = (tag,text,cls='') => {const n=document.createElement(tag);n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  function button(label,action,payload={},enabled=true) {
    const choice=payload.choice;
    const tone=choice==='fight'||action==='slay'?'danger':
      ['exit','decline_invite'].includes(action)||['bypass','decline','flee'].includes(choice)?'quiet':
      ['discover','enter','learn','study','continue_study'].includes(action)||['seize','accept'].includes(choice)?'primary':'secondary';
    const b=el('button',label,`dungeon-button dungeon-button--${tone}`);b.type='button';b.dataset.dungeonAction=action;
    if(choice)b.dataset.choice=choice;
    b.dataset.enabled=String(enabled);b.disabled=!enabled||busy();
    const id=game.id;b.onclick=()=>send(`/api/games/${id}/dungeon-action`,{action,...payload});return b;
  }
  const box=(title)=>{const n=el('section',undefined,'dungeon-box');n.append(el('h3',title));return n;};
  function floorMap(session,token) {
    const map=session.map, pane=box('境内舆图');
    pane.classList.add('dungeon-floor');
    const stamp=workspaceKey+':'+session.revision;
    if(atlasRevision!==stamp){atlasRevision=stamp;atlasSelection=null;}
    atlasObserver=window.DungeonAtlas.render(pane,map,el,(direction,open)=>
      button((map.chasing?'遁向':'前往')+direction,'move',{...token,choice:direction},open),
      atlasSelection,coord=>{atlasSelection=coord;});
    const tools=el('div',undefined,'atlas-formation');
    pane.append(tools);
    const formations=game.formation_system;
    if(map.array_name){
      tools.append(button('收回'+map.array_name,'withdraw_ward',token,map.can_withdraw));
    }else if(formations?.loadouts.length){
      const stock=new Map();
      for(const material of formations.materials){
        if(!material.locked)stock.set(material.definition_id,(stock.get(material.definition_id)||0)+1);
      }
      const select=el('select');
      select.setAttribute('aria-label','选择九宫阵');
      for(const row of formations.loadouts){
        const need=new Map();
        row.slots.filter(Boolean).forEach(id=>need.set(id,(need.get(id)||0)+1));
        const ready=[...need].every(([id,n])=>(stock.get(id)||0)>=n);
        const option=el('option',row.name+(ready?'':'（缺阵材）'));
        option.value=row.id;
        option.disabled=!ready;
        select.append(option);
      }
      const options=[...select.options];
      const selected=options.find(o=>o.value===formations.active_formation_id&&!o.disabled)||options.find(o=>!o.disabled);
      if(selected)select.value=selected.value;
      const payload={...token,loadout_id:select.value};
      select.onchange=()=>{payload.loadout_id=select.value;};
      tools.append(select,button('在此布阵','ward',payload,map.can_ward&&Boolean(selected)));
    }else{
      tools.append(el('p','可在阵法栏保存九宫阵，再携阵材入境布置。','dungeon-map-caption'));
    }
    if(map.readings.length)pane.append(el('p',map.readings.join('。')+'。','dungeon-sense'));
    return pane;
  }
  function metric(row) {
    const n=el('div',undefined,'dungeon-metric'),caption=el('div',undefined,'dungeon-caption');
    caption.append(el('span',row.label),el('b',row.display));
    const track=el('div',undefined,'dungeon-track'),fill=el('i');
    track.setAttribute('aria-label',row.label);track.setAttribute('role','meter');
    track.setAttribute('aria-valuemin',row.min);track.setAttribute('aria-valuemax',row.max);
    track.setAttribute('aria-valuetext',row.display);
    if(row.value!==null){track.setAttribute('aria-valuenow',row.value);fill.style.width=`${Math.min(100,Math.max(0,100*(row.value-row.min)/(row.max-row.min)))}%`;}
    else track.classList.add('unknown');
    track.append(fill);n.append(caption,track,el('small',row.source));return n;
  }
  function journalRows(root,logs) {
    const filters=el('select');filters.setAttribute('aria-label','筛选境中见闻');
    ['全部','实证','据说','听说','纠正与后证'].forEach(k=>{const o=el('option',k);o.value=k;filters.append(o);});
    const subjects=el('select');subjects.setAttribute('aria-label','筛选见闻对象');
    const all=el('option','全部人物与势力');all.value='';subjects.append(all);
    const known=new Map();logs.forEach(l=>(l.subjects||[]).forEach(s=>known.set(s.id,s.label)));
    known.forEach((label,id)=>{const o=el('option',label);o.value=id;subjects.append(o);});
    const controls=el('div',undefined,'dungeon-log-filters'),rows=el('div',undefined,'dungeon-log-rows');controls.append(filters,subjects);root.append(controls,rows);
    function draw(){rows.replaceChildren();[...logs].reverse().filter(l=>(filters.value==='全部'||l.kind===filters.value||filters.value==='纠正与后证'&&l.supersedes)&&(!subjects.value||(l.subjects||[]).some(s=>s.id===subjects.value))).forEach(l=>{
      const item=el('article',undefined,'dungeon-log');item.id=l.id;
      item.append(el('small',`${l.kind} · ${l.place} · ${l.source}`),el('p',l.text));
      if(l.received_step!==undefined)item.append(el('small',`发生于第 ${l.occurred_step} 处附近 · 第 ${l.received_step} 处收到`));
      if(l.supersedes){const link=el('a','查看此前说法');link.href='#'+l.supersedes;link.onclick=()=>{filters.value='全部';subjects.value='';draw();};item.append(link);}
      rows.append(item);
    });}filters.onchange=draw;subjects.onchange=draw;draw();
  }
  function render() {
    atlasObserver?.disconnect();
    const view=game.dungeons,root=document.querySelector('#dungeon-panel');root.replaceChildren();
    const shell=document.querySelector('#dungeon-card');
    const titleBar=shell.querySelector('.section-title');
    titleBar.querySelector('.dungeon-hero')?.remove();
    if(!view){shell.classList.remove('dungeon-active');return;}
    const session=view.session;
    const key=game.id+':'+(session?.id||'lobby');
    if(workspaceKey!==key){workspaceKey=key;activeTab=session?.map?'map':'journal';expandedPerson=null;}
    shell.classList.toggle('dungeon-active',!!session);
    shell.dataset.quality=qualities[session?.quality]?.[0]||'neutral';
    let workspace,teamPane,journalPane;
    if(!session){
      const intro=box('寻访当地隐境');intro.classList.add('dungeon-discovery');
      intro.append(el('p',`已探寻 ${view.used} / ${view.limit} 处 · 入境不耗岁月，撤离后须间隔一个完整行动单位。`));
      if(view.reason)intro.append(el('p',view.reason,'dungeon-warning'));
      if(view.ready_in)intro.append(el('p',`再次入境还需 ${view.ready_in} 年。`));
      intro.append(button('探寻一处入口','discover',{world:view.world,location_id:view.location_id,slot:view.used},view.available&&view.used<view.limit));root.append(intro);
      const list=el('div',undefined,'dungeon-grid');
      const closed=view.sites.filter(site=>site.status==='closed');
      view.sites.filter(site=>site.status!=='closed').forEach(s=>{const b=box(s.name);b.append(el('p',s.quality+' · '+({open:'入口尚在',active:'正在探索',closed:'入口已封'}[s.status])));
        b.append(button('进入副本','enter',{dungeon_id:s.id,revision:s.revision},s.can_enter));
        if(s.status==='open'&&view.invitees.length){
          const select=el('select');select.setAttribute('aria-label','选择当地同行修士');
          view.invitees.forEach(n=>{const option=el('option',n.name);option.value=n.id;select.append(option);});
          const invite=button('邀请同行','invite',{},view.available);
          invite.onclick=()=>send(`/api/games/${game.id}/dungeon-action`,{action:'invite',dungeon_id:s.id,revision:s.revision,actor_id:select.value});
          const invitation=el('div',undefined,'dungeon-invite');invitation.append(select,invite);b.append(invitation);
        }
        list.append(b);});
      if(list.childElementCount)root.append(list);
      if(closed.length){
        const past=el('details',undefined,'dungeon-closed-sites');
        past.append(el('summary',`已封入口 · ${closed.length} 处`));
        const names=el('ul');
        closed.forEach(site=>names.append(el('li',site.name+' · '+site.quality)));
        past.append(names);root.append(past);
      }
    }else{
      const token={dungeon_id:session.id,revision:session.revision},hero=el('header',undefined,'dungeon-hero');
      const identity=el('div',undefined,'dungeon-identity');
      identity.append(el('small',`${session.quality} · ${qualities[session.quality]?.[1]||session.place}`,'dungeon-quality'),el('h2',session.name));
      hero.append(identity,el('p',`${session.place}　·　同行 ${session.party_count} / ${session.team_limit}　·　机缘 ${session.acquired} 份`));titleBar.prepend(hero);
      const grid=el('div',undefined,'dungeon-grid'),left=el('div',undefined,'dungeon-column'),right=el('div',undefined,'dungeon-column');
      workspace=grid;grid.classList.add('dungeon-workspace');
      const scene=box('眼前局势'),reading=el('div',undefined,'dungeon-scene-reading');scene.classList.add('dungeon-scene');reading.append(el('p',session.text,'dungeon-narrative'));scene.append(reading);const actions=el('div',undefined,'dungeon-actions');
      session.choices.forEach(c=>actions.append(button(c.label,'choose',{...token,choice:c.id},c.enabled)));
      const heading=el('div',undefined,'dungeon-scene-heading'),retreat=el('div',undefined,'dungeon-retreat');
      retreat.append(button('撤离副本','exit',token,session.can_exit));
      heading.append(scene.querySelector('h3'),retreat);
      scene.prepend(heading);scene.append(actions);left.append(scene);
      const team=box('同行名册');teamPane=team;team.classList.add('dungeon-team');
      if(session.people.length){
        const compare=el('details',undefined,'dungeon-compare'),a=el('select'),b=el('select'),values=el('div');compare.append(el('summary','双方交锋对照'));

        a.setAttribute('aria-label','对照一方');b.setAttribute('aria-label','对照另一方');
        const choices=[{id:'player',name:'你',comparison:session.player_comparison},...session.people,
          ...session.people.filter(p=>p.squad).map(p=>({id:'squad:'+p.id,name:p.name+'一方（已见 '+p.squad.count+' 人）',comparison:p.squad}))];
        [a,b].forEach(select=>choices.forEach(p=>{const o=el('option',p.name);o.value=p.id;select.append(o);}));b.selectedIndex=1;
        function drawComparison(){const x=choices.find(p=>p.id===a.value),y=choices.find(p=>p.id===b.value);values.replaceChildren();const gap=x.comparison.rank-y.comparison.rank,ratio=x.comparison.power/Math.max(1,y.comparison.power);values.append(metric({label:'显露境界差距',value:gap,min:Math.min(-36,gap),max:Math.max(36,gap),display:`${gap>=0?'+':''}${gap} 阶`,source:`${x.name} 对 ${y.name}`}),metric({label:'战力估计',value:Math.round(ratio*100),min:0,max:Math.max(200,Math.round(ratio*100)),display:`约 ${(ratio<.1?ratio.toPrecision(2):ratio.toFixed(1))} 倍`,source:'来自交锋表现与外显气息'}));
          const target=y.id==='player'?x:y,desire=target.bars?.find(m=>m.label.startsWith('夺宝意向'));
          if(desire)values.append(metric({...desire,label:target.name+' · '+desire.label}));
        }
        a.onchange=b.onchange=drawComparison;compare.append(a,b,values);drawComparison();team.append(compare);
      }
      team.append(metric({label:'己方地势准备',value:session.preparation,min:0,max:100,display:`${session.preparation} / 100`,source:'已完成勘察与已履行的向导交易'}));
      session.people.forEach(p=>{const card=el('details',undefined,'dungeon-person');const body=el('div',undefined,'dungeon-person-body');card.open=expandedPerson===p.id;card.ontoggle=()=>{if(card.open){expandedPerson=p.id;team.querySelectorAll('.dungeon-person').forEach(other=>{if(other!==card)other.open=false;});}else if(expandedPerson===p.id)expandedPerson=null;};card.dataset.personId=p.id;
        const head=el('summary',undefined,'dungeon-person-head');head.append(el('b',p.name),el('span',p.status,'dungeon-state'),el('small',`${p.sect} · ${p.realm}`));if(p.clues.length)head.append(el('small',p.clues[p.clues.length-1].text,'dungeon-last-clue'));card.append(head,body);
        if(p.exposed)body.append(el('p','已亲见其敌对行动','dungeon-warning'));
        if(p.representative)body.append(el('p','以本宗身份在场','muted'));
        p.bars.forEach(m=>body.append(metric(m)));
        if(p.treasure_bars?.length){const select=el('select'),observed=el('div');select.setAttribute('aria-label','查看'+p.name+'对已知宝物的表现');p.treasure_bars.forEach(m=>{const o=el('option',m.label.replace('夺宝意向 · ',''));o.value=m.id;select.append(o);});const show=()=>observed.replaceChildren(metric(p.treasure_bars.find(m=>m.id===select.value)));select.onchange=show;show();body.append(select,observed);}
        p.clues.forEach(c=>body.append(el('p','实证 · '+c.text,'dungeon-clue')));
        if(p.can_pact)body.append(button('约定互相掩护','pact',{...token,actor_id:p.id}));
        if(p.can_slay)body.append(button('出手灭杀','slay',{...token,actor_id:p.id}));
        if(p.contract)body.append(el('p','交药换取辨阵：'+({promised:'待交付',fulfilled:'已当面履行',broken:'已撤回约定'}[p.contract.state])));
        if(p.can_trade){const deal=el('div',undefined,'dungeon-mail-actions');
          if(!p.contract)deal.append(button('商议交药换取辨阵','bargain',{...token,actor_id:p.id,choice:'promise'}));
          else if(p.contract.state==='promised'){deal.append(button('交付一份恢复药物','bargain',{...token,actor_id:p.id,choice:'deliver'},p.can_deliver),button('撤回交付约定','bargain',{...token,actor_id:p.id,choice:'break'}));}body.append(deal);}
        team.append(card);});
      if(!session.people.length)team.append(el('p','尚未接触其他修士。'));left.append(team);
      const journal=box('境中见闻');journalPane=journal;journal.classList.add('dungeon-journal');journal.setAttribute('aria-live','polite');
      if(!session.logs.length)journal.append(el('p','一切尚待探索。'));
      journalRows(journal,session.logs);right.append(journal);
      grid.append(left,right);root.append(grid);
    }
    if(!session&&view.archives?.length){const archive=box('往次探境见闻');[...view.archives].reverse().forEach(s=>{const details=el('details'),summary=el('summary',s.name);details.append(summary);journalRows(details,s.logs);archive.append(details);});root.append(archive);}
    const manuals=box('所得传承');manuals.classList.add('dungeon-manuals');
    view.manuals.forEach(m=>{const row=el('article',undefined,'dungeon-person');row.append(el('h4',m.name),el('p',`${m.grade} · ${m.fused?'完整合练传承':'完整功法'} · Lv${m.level}`),el('p',m.description));if(!m.learned)row.append(button('依法研习','learn',{manual_id:m.id},!!m.can_learn));else {row.append(el('p','已收入已悟功法，可在功法界面配置。'));if(m.study){row.append(el('p',`参悟 ${m.study.elapsed} / ${m.study.required} 年`));const continueButton=button('继续参悟一个行动单位','continue_study',{},!view.active&&view.available);continueButton.onclick=()=>send(`/api/games/${game.id}/advance`,{action:'dungeon_study',years:1});row.append(continueButton);}else if(m.level<9){row.append(el('p',`参悟代价：${m.quote.opportunity} 机缘、${m.quote.traces} 仙痕；需 ${m.quote.years} 年。`),button('准备参悟','study',{manual_id:m.id},!view.active&&view.available));}}manuals.append(row);});
    if(session){
      if(!view.manuals.length)manuals.append(el('p','行囊中尚无探境传承。','muted'));
      workspace.append(manuals);
      const tabs=el('nav',undefined,'dungeon-view-tabs');tabs.setAttribute('aria-label','探境资料');
      const panels={team:teamPane,journal:journalPane,manuals};
      if(session.map){panels.map=floorMap(session,{dungeon_id:session.id,revision:session.revision});workspace.append(panels.map);}
      if(session.map?.chasing && compactQuery.matches)activeTab='map';
      if(activeTab==='map'&&!session.map)activeTab='journal';
      const teamTab=Boolean(session.map)||compactQuery.matches;
      const fixedMap=Boolean(session.map)&&!compactQuery.matches;
      const selected=(activeTab==='team'&&!teamTab)||(activeTab==='map'&&fixedMap)?'journal':activeTab;
      function select(tab){activeTab=tab;workspace.dataset.view=tab;Object.entries(panels).forEach(([id,pane])=>{pane.hidden=id!==tab&&(id!=='team'||teamTab)&&(id!=='map'||!fixedMap);});tabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.dungeonView===tab)));}
      [...(session.map&&!fixedMap?[['map','舆图']]:[]),['team',`队伍 ${session.party_count}/${session.team_limit}`],['journal',`见闻 ${session.logs.length}`],['manuals',`传承 ${view.manuals.length}`]].forEach(([id,label])=>{
        const tab=el('button',label,'dungeon-button dungeon-button--quiet');tab.type='button';tab.dataset.dungeonView=id;
        panels[id].id='dungeon-view-'+id;tab.setAttribute('aria-controls',panels[id].id);tab.onclick=()=>select(id);tabs.append(tab);
      });
      workspace.prepend(tabs);select(selected);
    }else if(view.manuals.length)root.append(manuals);
  }
  function composeLetter() {
    const form=box('写信'), fields=el('div',undefined,'mail-fields'), actions=el('div',undefined,'dungeon-mail-actions');
    const field=(name)=>{
      const label=el('label',name),select=el('select');
      label.append(select);fields.append(label);return select;
    };
    const topic=field('事由'),site=field('副本入口'),recipient=field('收信人');
    const option=(value,label)=>new Option(label,value);
    topic.add(option('ask_location','询问行踪'));topic.add(option('invite','邀请同行'));
    topic.value=mailDraft.topic;
    const view=game.dungeons;
    const known=[...new Map([...(game.faction?.roster||[]),...(game.world_npcs||[])]
      .filter(n=>n.perceived_alive&&!n.is_player).map(n=>[n.id,n])).values()];
    const open=view.sites.filter(s=>s.status==='open');
    function draw(){
      const inviting=topic.value==='invite';
      site.parentElement.hidden=!inviting;
      site.replaceChildren(...open.map(s=>option(s.id,s.name)));
      if(open.some(s=>s.id===mailDraft.site))site.value=mailDraft.site;
      const selectedSite=open.find(s=>s.id===site.value);
      const people=inviting?view.invitees:known;
      recipient.replaceChildren(option('','请选择修士'),...people.map(n=>option(n.id,n.realm_name?n.name+' · '+n.realm_name:n.name)));
      recipient.value=people.some(n=>n.id===mailDraft.recipient)?mailDraft.recipient:'';
      const person=people.find(n=>n.id===recipient.value);
      let reason=person?.letter_reason||'';
      if(inviting){
        reason=view.reason||'';
        if(!reason&&view.active)reason='待出境后再寄邀约';
        if(!reason&&!selectedSite)reason='先寻得一处副本入口';
        if(!reason&&person&&view.mail.some(m=>m.dungeon_id===selectedSite.id&&m.sender_id===person.id&&m.status==='reply'))
          reason='这处副本的邀约已有回信';
      }
      if(!reason&&!people.length)reason=inviting?'当地尚无可邀约的修士':'暂无可通信的修士';
      const payload=inviting?{dungeon_id:selectedSite?.id,revision:selectedSite?.revision,actor_id:recipient.value}:
        {actor_id:recipient.value,expected_age:game.player.age,world:game.player.world};
      actions.replaceChildren(button('寄出',topic.value,payload,!!person&&!reason));
      if(reason)actions.append(el('small',reason));
    }
    topic.onchange=()=>{mailDraft.topic=topic.value;draw();};
    site.onchange=()=>{mailDraft.site=site.value;draw();};
    recipient.onchange=()=>{mailDraft.recipient=recipient.value;draw();};
    form.append(fields,actions);draw();return form;
  }
  function mailbox() {
    const root=document.querySelector('#mailbox-panel');root.replaceChildren();
    const mail=game.dungeons?.mail||[];
    if(game.dungeons)root.append(composeLetter());
    if(!mail.length)root.append(el('p','尚无修士来信。'));
    [...mail].reverse().forEach(m=>{const row=box(m.title);row.append(el('p',`${m.sender} · ${m.unread?'未读':'已读'}`),el('p',m.body));
      const actions=el('div',undefined,'dungeon-mail-actions');
      if(m.unread)actions.append(button('读过此信','read_mail',{mail_id:m.id}));
      if(m.status==='whereabouts'){row.append(el('small',`于你 ${m.age} 岁时收到`),actions);root.append(row);return;}
      const s=game.dungeons.sites.find(s=>s.id===m.dungeon_id);
      if(s&&s.status==='open'){actions.append(button(m.status==='reply'?'前往副本':'赴约入境','enter',{dungeon_id:s.id,revision:s.revision},s.can_enter));if(m.status==='pending')actions.append(button('谢绝邀约','decline_invite',{dungeon_id:s.id,revision:s.revision},game.dungeons.available&&!game.dungeons.active));}
      else row.append(el('p',m.status==='pending'?'请抵达来信所述地图后赴约。':'邀约已处理。'));row.append(actions);root.append(row);});
  }
  window.DungeonPanel={
    update(data,mutate,isBusy){
      if(game?.id!==data.id)mailDraft={topic:'ask_location',recipient:'',site:''};
      game=data;send=mutate;busy=isBusy;
      document.querySelectorAll('.mailbox-dot').forEach(dot=>{dot.hidden=!data.dungeons?.unread;});
      document.querySelector('#mailbox-main-open').onclick=()=>window.UtilityPanels.open('mailbox');
      window.UtilityPanels.schedule('dungeon',render);window.UtilityPanels.schedule('mailbox',mailbox);
    },
    lock(){document.querySelectorAll('[data-dungeon-action]').forEach(b=>b.disabled=busy()||b.dataset.enabled!=='true');}
  };
  compactQuery.addEventListener('change',()=>{if(game)window.UtilityPanels.schedule('dungeon',render);});
})();
