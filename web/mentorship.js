/* Personal school controls stay inside the existing relationship window. */
window.Mentorship = (() => {
  'use strict';
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  let owner='',preferences=new Map();
  function render(host,game,mutate){
    const data=game.mentorship;if(!data)return;
    if(owner!==game.id){owner=game.id;preferences=new Map();}
    function remember(details,key){
      details.dataset.schoolSection=key;details.open=preferences.get(key)===true;
      details.addEventListener('toggle',()=>{if(details.isConnected)preferences.set(key,details.open);});
      return details;
    }
    function heading(card,name,badge,portrait){
      const head=node('header');head.className='mentorship-person';
      const text=node('div');text.append(node('b',name));const label=node('span',badge);label.className='mentorship-badge';text.append(label);head.append(text);
      window.NpcArt?.avatar(head,portrait);card.append(head);
    }
    function stats(card,items){const grid=node('dl');grid.className='mentorship-stats';
      for(const [label,value] of items){const cell=node('div');cell.append(node('dt',label),node('dd',String(value)));grid.append(cell);}card.append(grid);}
    const root=node('details');root.id='mentorship-panel';root.open=true;
    root.append(node('summary','师门名册 · 位次与日常事务'));
    const intro=node('p','同门问道，薪火相传。记名无福利与义务，培养仍在独立窗口办理。');intro.className='mentorship-intro';root.append(intro);
    const act=payload=>mutate(`/api/games/${game.id}/mentorship-action`,payload);
    function advancedTools(row,own){
      const details=remember(node('details'),`advanced:${row.id}`);details.className='mentorship-actions';details.append(node('summary',own?'传承契约':'同门谋议'));
      const options=own?[
        ['pact_possession',`商议自愿夺舍契约（机缘${row.honor_cost}）`],['pact_avatar',`商议自愿化身契约（机缘${row.honor_cost}）`],['revoke_pacts','撤销契约'],
        ['possess_heir','神游夺舍（有失败风险，原神魂消散）'],['refine_avatar','炼化身外化身（不可逆）']
      ]:[['sow_discord','游说离心（消耗机缘，有被察觉风险）'],['plot','结为夺位同盟']];
      const select=node('select');select.setAttribute('aria-label',`${row.name}传承事务`);
      for(const [value,label] of options){const o=node('option',label);o.value=value;select.append(o);}
      const b=button('办理传承事务',{},row.reason);
      b.onclick=()=>{
        if(['possess_heir','refine_avatar'].includes(select.value)&&!window.confirm(select.value==='refine_avatar'?
          '将原弟子永久炼为唯一化身，结束在籍关系，消耗自身阶段10%突破机缘。继承原培养和寿命；永久飞升会解除控制。确定炼化？':
          '夺舍仍有融合失败风险；成功会消耗夺舍次数，原弟子神魂永久消散。确定履约？'))return;
        act({action:select.value,npc_id:row.id});
      };
      details.append(select,b);
      const a=row.advanced||{};
      details.append(node('small',own?`契约：夺舍${a.pact_possession?'已同意':'未同意'} / 化身${a.pact_avatar?'已同意':'未同意'}。需忠诚85商议，低于60、降位或离门即不能履行。亲传每周期精修1次，嫡传3次，前往独立培养窗口。`:
        `对师父忠诚低于30、对你好感至少30才能结盟；最多三名同场盟友。${a.plot?'已结盟，开战时重新核验条件。':''}`));
      return details;
    }
    function button(label,payload,reason=''){
      const b=node('button',label);b.type='button';b.disabled=Boolean(reason);b.title=reason;b.onclick=()=>act(payload);return b;
    }
    function peerTools(row){
      const details=remember(node('details'),`peer:${row.id}`);details.className='mentorship-actions';details.append(node('summary',`${row.kinship}交流 · 好感 ${row.affinity}`));
      const tools=node('div');tools.className='relationship-tools';
      const select=node('select');select.setAttribute('aria-label',`${row.name}同门交流`);
      for(const item of row.interactions||[]){const opt=node('option',item.label);opt.value=item.action;select.append(opt);}
      const choiceKey=`choice:${row.id}`;if([...select.options].some(o=>o.value===preferences.get(choiceKey)))select.value=preferences.get(choiceKey);
      const help=node('small'),submit=button('办理同门事务',{});help.className='mentorship-feedback';help.setAttribute('aria-live','polite');
      const refresh=()=>{const item=row.interactions.find(i=>i.action===select.value);
        submit.disabled=!item||Boolean(item.reason);submit.title=item?.reason||'';
        help.dataset.blocked=Boolean(item?.reason);
        const hints={peer_consult:'请教修行：获得当前阶段1%机缘（至少1点）。',peer_spar:'非致命单人切磋：胜败均得1%机缘（至少1点），实际消耗HP／MP与战斗耗材。',peer_item:'好感需20；转交对方实际持有的宝物。',peer_technique:'好感需30；传授对方已学、适合你修习的新功法。'};
        help.textContent=item?.reason||hints[select.value]||'';};
      select.onchange=()=>{preferences.set(choiceKey,select.value);refresh();};submit.onclick=()=>act({action:select.value,npc_id:row.id});refresh();
      tools.append(select,submit);details.append(tools,help,node('small','每人每项每师门周期一次 · 不占师父指导额度'));
      return details;
    }
    if(data.master){
      const m=data.master,card=node('div');card.className='mentorship-row mentorship-master';
      heading(card,`${m.teacher_name}门下`,m.rank_name,m.teacher_portrait);
      stats(card,[['师父好感',m.teacher_affinity],['师门不满',`${m.discontent}/100`],['履约资历',m.merit],['指导余额',`${m.support_remaining}/${m.support_limit}`]]);
      card.append(node('small',`本周期截止 · ${m.due} 年`));
      if(m.warned)card.append(node('p','师门已发出警告：请及时履约，不满达到100且警告未解除会被逐出。'));
      const tools=node('div');tools.className='relationship-tools mentorship-duties';
      if(!m.initialized)tools.append(button('登记已有师承',{action:'register'},m.reason));
      tools.append(button(`自愿呈交心得 · 机缘 ${m.honor_cost} · 好感+10`,{action:'honor'},m.reason||(m.honored===m.cycle?'本周期已呈交':'')));
      tools.append(button('申请出师',{action:'graduate'},m.graduation_reason));
      if(m.rank!=='registered')tools.append(button(`呈交心得 · 机缘 ${m.duty_cost}`,{action:'fulfill'},m.reason||(m.fulfilled===m.cycle?'本周期已履约':'')));
      if(m.rank!=='heir'){
        const promotion=remember(node('details'),'promotion');promotion.className='mentorship-actions';promotion.append(node('summary','晋位与比试'));
        const keys=Object.keys(data.ranks),next=keys[keys.indexOf(m.rank)+1];
        const select=node('select');select.setAttribute('aria-label','晋位比试同门');
        const empty=node('option','有空位直接晋位；满额时选择比试同门');empty.value='';select.append(empty);
        for(const peer of data.peers.filter(p=>p.rank===next)){const opt=node('option',peer.name);opt.value=peer.id;select.append(opt);}
        const promote=button('申请晋位',{},m.reason||(m.promoted===m.cycle?'本周期已申请':''));
        promote.onclick=()=>act({action:'promote',rival_id:select.value});
        promotion.append(select,promote,node('small','逐级晋位：师父好感20/45/75，履约资历0/2/5；满额须胜出，失败保留位次。'));tools.append(promotion);
      }
      card.append(tools);if(m.reason)card.append(node('small',m.reason));root.append(card);
      if(m.rank!=='registered'){
        const challenge=button('联合同门挑战师父',{},m.reason);
        challenge.onclick=()=>{if(window.confirm('这是致命战斗，需要至少一名符合条件的同场盟友。失败将断绝师承；成功仅接掌个人师承，不取得宗门职位和财产。确定挑战？'))act({action:'challenge_master'});};
        const danger=remember(node('details'),'challenge');danger.className='mentorship-actions mentorship-danger';danger.append(node('summary','师门争端'),node('small','联合同门挑战师父将进行致命战斗。'),challenge);card.append(danger);
      }
    }
    for(const [title,list,own] of [['同门',data.peers,false],['门下弟子',data.disciples,true]]){
      if(!list.length)continue;const titleNode=node('h3',`${title} · ${list.length}`);titleNode.className='mentorship-section-title';root.append(titleNode);
      const roster=node('div');roster.className='mentorship-roster';root.append(roster);
      for(const row of list){
        const card=node('div');card.className='mentorship-row';card.dataset.mentorshipNpc=row.id;
        card.dataset.rank=row.rank;heading(card,row.name,`${row.rank_name}${own?'':` · ${row.kinship}`}`,row.portrait);
        stats(card,own?[['忠诚',`${row.loyalty}/100`],['周期截止',`${row.due} 年`]]:[['对你好感',row.affinity],['对师父忠诚',`${row.loyalty}/100`]]);
        if(own){
          const tools=node('div');tools.className='relationship-tools';
          const select=node('select');select.setAttribute('aria-label',`${row.name}位次`);
          for(const [key,label] of Object.entries(data.ranks)){const opt=node('option',label);opt.value=key;opt.selected=key===row.rank;select.append(opt);}
          const appoint=button('任命',{},row.reason);appoint.onclick=()=>act({action:'appoint',npc_id:row.id,rank:select.value});
          tools.append(select,appoint,button('领取实际贡物',{action:'collect',npc_id:row.id},row.reason||(row.rank==='registered'?'记名无义务':row.collected===row.cycle?'本周期已领取':'')),
            button('准予出师',{action:'graduate',npc_id:row.id},row.reason));
          window.NpcDevelopment?.link(tools,row.id);card.append(tools);
          if(row.rank==='heir')card.append(advancedTools(row,true));
        }
        if(!own){
          card.append(peerTools(row));
          if(data.master?.rank!=='registered'&&row.rank!=='registered')card.append(advancedTools(row,false));
        }
        if(row.reason){const reason=node('small',row.reason);reason.className='mentorship-feedback';reason.dataset.blocked='true';card.append(reason);}roster.append(card);
      }
    }
    root.append(node('small',`名额：嫡传1、亲传3、真传${data.capacity.true}、记名不限。NPC 师父只建立少量同门，不自动招满。`));
    const advanced=game.mentorship_advanced;
    if(advanced?.rebellion?.ids?.length)root.append(node('p','门下曾出现串联预警：请留意低忠诚门人，在场合力足够且经过预警周期后会触发叛师事件。'));
    if(advanced?.avatar){
      const a=advanced.avatar,card=node('div');card.className='mentorship-row';
      card.append(node('b',`身外化身 · ${a.name} · ${a.consented?'自愿契合（战力+20%）':'强制炼化'}`));
      window.NpcArt?.avatar(card,a.portrait);
      card.append(button(a.enabled?'停止化身出战':'启用化身出战',{action:'avatar_toggle'},a.reason));
      window.NpcDevelopment?.link(card,a.id);
      card.append(node('small',a.reason||'不占同行名额，使用原人物功法、邻域、资源及伤势。'));root.append(card);
    }
    if(data.history.length){const history=node('details');history.append(node('summary',`师承履历 (${data.history.length})`));
      const labels={graduated:'已出师',departed:'已离门',expelled:'已逐出',active:'关系已结束'};
      for(const row of data.history)history.append(node('p',`${row.id==='player'?'你':row.name} · ${row.teacher_name}门下 · ${row.rank_name} · ${labels[row.status]||row.status}`));root.append(history);}
    host.prepend(root);
  }
  return {render};
})();
