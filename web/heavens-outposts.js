/* Civilian frontier details reuse the existing heavens navigation and command. */
(() => {
  const status={unregistered:'尚未授权',authorized:'已获开拓许可',building:'施工中',active:'正常运营',suspended:'暂停经营',withdrawing:'撤回中',closed:'已关闭'};
  const phase={gathering:'沿路集结',outbound:'跨界去程',stationed:'已在驻地',returning:'跨界返程',homeward:'沿路返乡',home:'已归返结清',lost:'原人物陨落',local_outbound:'前往经营地点',local_work:'在当地办事',local_return:'返回异界驻地',campaign:'当地军令出征'};
  function render(host, projects, ui, api) {
    const {node,title,tile,back,subview,renderActions,empty,go}=api;
    const selected=projects.find(row=>row.id===ui.target);
    if(!selected){
      back(host,'返回诸界','worlds');title(host,'跨界开拓','保留原总部，以原门人、原钱货经营异界分驻地。');
      const directory=node('div',null,'heavens-directory');
      for(const row of projects)tile(directory,{name:row.name,description:`${row.source_name} · ${row.gateway} → ${row.destination_name} · ${row.location_name}`,status:status[row.status],glyph:'驻',onClick:()=>go('worlds',row.id)});
      host.append(directory);
      if(!projects.length)empty(host,'尚无可开拓的势力','支持普通三层界面的同层双界开拓。取得原宗门或家族实际控制权后，在原总部为指定目的界批准开拓。');
      return;
    }
    const returnLink=node('button','‹ 返回开拓目录','heavens-back');returnLink.type='button';returnLink.onclick=()=>go('worlds','outpost_network');host.append(returnLink);
    title(host,selected.name,`${selected.source_name} → ${selected.destination_name} · ${selected.location_name} · ${status[selected.status]}`);
    if(selected.notice)host.append(node('p',selected.notice,'muted'));
    const terms=selected.terms,annual=terms.annual,fare=annual*8;
    subview(host,[['permit','授权与往返'],['staff','派驻与补给'],['local','驻地与仓储'],['development','地方经营'],['conquest','征战与归附'],['records','开拓纪要']],'permit',(body,section)=>{
      let actions=[];
      if(section==='permit'){
        body.append(node('p',`在原总部批准前往${selected.destination_name}的开拓，到${selected.gateway}申请个人通行。去返程各8年，各${fare.toLocaleString()}灵石；首次启程同时预留返程款。`),node('p','每组双界独立使用一条单人通道。民用许可用于派驻、施工和补给；当地征战须另行取得军令。'));
        if(selected.visit_status)body.append(node('p',`个人行程：${({preparing:'启程中',visiting:'异界停留',returned:'已经返乡',cancelled:'启程已取消',failed:'行程结束'})[selected.visit_status]} · 保留返程款 ${selected.return_fare} 灵石`));
        actions=selected.actions.filter(r=>['outpost_authorize','outpost_depart','outpost_return','outpost_wait'].includes(r.action));
      }else if(section==='staff'){
        body.append(node('p',`原门人沿道路集结，再跨界8年。施工另需当地10年、劳务${terms.build_cost.toLocaleString()}灵石；每处最多3人在途或驻守。`),node('p',`派驻携带原府库${terms.grade}阶构材6、导灵矿2、储能矿2；往返每行旅年${annual.toLocaleString()}灵石，补给使者实付送款${terms.working_cash.toLocaleString()}灵石。`));
        for(const unit of selected.units)body.append(node('p',`${unit.name}${unit.courier?' · 补给使者':''}：${phase[unit.phase]}${unit.duration?` · ${unit.progress}/${unit.duration}年`:''}${unit.notice?' · '+unit.notice:''}`));
        actions=selected.actions.filter(r=>['outpost_dispatch','outpost_supply','outpost_recall'].includes(r.action));
      }else if(section==='local'){
        body.append(node('p',`施工进度 ${selected.progress||0}/${selected.duration||10} 年；运营养护每当地年${annual.toLocaleString()}灵石。暂停后保留库存与人员，停止经营养护。`));
        if(selected.balance!=null){
          body.append(node('p',`当地经费：${selected.balance.toLocaleString()} 灵石`));
          for(const row of selected.stock_rows||[])body.append(node('p',`${row.name} × ${row.quantity}`));
          const governor=selected.residents.find(p=>p.id===selected.governor_id);body.append(node('p',`在场负责人：${governor?.name||'暂无可履职负责人'}`));
        }else body.append(node('p','库存与现任负责人须亲自抵达驻地核实。'));
        actions=selected.actions.filter(r=>['outpost_appoint','outpost_suspend','outpost_activate','outpost_withdraw'].includes(r.action));
      }else if(section==='development'){
        const dev=selected.development;
        body.append(node('p','负责人留守驻地，另派已到场门人沿道路往返。联络地方5年；外驻点施工10年，使用驻地实有资材。'));
        if(dev?.reason){body.append(node('p',dev.reason,'muted'));return;}
        if(dev?.registered)body.append(node('p',`经营收入 ${dev.income.toLocaleString()} · 实付支出 ${dev.expense.toLocaleString()} · 当地结余 ${dev.balance.toLocaleString()} 灵石`),node('p','收入来自当地实际成交手续费的分成。运回总部须门人实际返乡交款；全处撤回也会撤去外围影响。'));
        for(const job of dev?.jobs||[])body.append(node('p',`${job.name} · ${job.location_name} · ${job.label}：${phase[job.phase]}${job.duration?' '+job.progress+'/'+job.duration+'年':''} · ${({active:'进行中',done:'已经结清',cancelled:'取消并结清',lost:'行程损失'})[job.status]}`));
        const selector=node('select');selector.setAttribute('aria-label','经营地点');
        const main=node('option','驻地经营总览');main.value='';selector.append(main);
        for(const place of dev?.locations||[]){const option=node('option',`${place.name} · 影响 ${place.value}${place.outpost?' · 已有驻点':''}`);option.value=place.id;selector.append(option);}
        selector.value=ui.developmentLocation||'';
        if(selector.selectedIndex<0)selector.value='';
        const details=node('div');
        const show=()=>{
          ui.developmentLocation=selector.value;details.replaceChildren();
          const place=dev?.locations.find(p=>p.id===selector.value);
          const choices=place?.actions||dev?.actions||[];
          const select=node('select');select.setAttribute('aria-label','选择经营事务');
          for(const action of choices){const option=node('option',action.label);option.value=action.action;select.append(option);}
          const remembered=ui.developmentAction;if(choices.some(a=>a.action===remembered))select.value=remembered;
          const actionBody=node('div');const showAction=()=>{ui.developmentAction=select.value;actionBody.replaceChildren();const action=choices.find(a=>a.action===select.value);if(!action)return;
            const people=action.action==='outpost_cancel_local'?(dev.jobs||[]).filter(j=>j.status==='active').map(j=>({id:j.person_id,name:j.name})):dev.workers;
            renderActions(actionBody,[{...action,policies:action.action==='outpost_policy'?place?.policies:null,rivals:action.action==='outpost_spar'?place?.rivals:null}],[],action.people||people);
          };select.onchange=showAction;details.append(select,actionBody);showAction();
        };selector.onchange=show;body.append(selector,details);show();return;
      }else if(section==='conquest'){
        const data=selected.conquest||{actions:[],rivals:[]};
        body.append(node('p',data.authorized?'原总部已签发本目的界当地征战军令。':'须先由本人返回原总部，为本目的界单独批准当地征战。'),node('p',`先在目标或相邻地区经营出影响50的驻点，再派原门人循路出征。负责人留守，军费实付${terms.war_budget.toLocaleString()}灵石及往返路费；民用通道不额外输送军队。`));
        const war=data.war;
        if(war){
          body.append(node('p',`${war.enemy_name} · ${war.location_name} · ${({marching:'循路开拔',engaged:'交战与控制总部',returning:'循路撤军',home:'已归返结清'})[war.phase]} · 会战 ${war.battles} 场 · 战争分数 ${war.score}`),node('p',`实际控制总部 ${war.occupation}/5 年；部众每十年会战一次。本人亲征须沿地图到战场，每十年一次。真实胜利且分数达标后，回主驻地签订原依附和约。`));
          for(const troop of war.troops)body.append(node('p',`${troop.name} · ${({outbound:'赴战途中',stationed:'已抵战场',returning:'返回主驻地',home:'已归返',lost:'原人物陨落'})[troop.phase]}${troop.duration?' '+troop.progress+'/'+troop.duration+'年':''}`));
          for(const log of war.logs)body.append(node('p',`${log.age}岁 · ${log.title} · ${log.text}`));
        }
        const select=node('select');select.setAttribute('aria-label','选择征战事务');
        for(const action of data.actions){const option=node('option',action.label);option.value=action.action;select.append(option);}
        if(data.actions.some(a=>a.action===ui.conquestAction))select.value=ui.conquestAction;
        const details=node('div');const show=()=>{ui.conquestAction=select.value;details.replaceChildren();let action=data.actions.find(a=>a.action===select.value);if(!action)return;
          if(action.action==='outpost_war_start'&&data.rivals.length){
            const target=node('select');target.setAttribute('aria-label','征战目标');
            for(const rival of data.rivals){const option=node('option',`${rival.name} · ${rival.location_name}`);option.value=rival.id;target.append(option);}
            target.value=ui.conquestRival||data.rivals.find(r=>r.command.enabled)?.id||data.rivals[0].id;
            if(target.selectedIndex<0)target.selectedIndex=0;
            const controls=node('div');const draw=()=>{ui.conquestRival=target.value;controls.replaceChildren();const rival=data.rivals.find(r=>r.id===target.value);renderActions(controls,[rival.command],[],rival.people);};
            target.onchange=draw;details.append(target,controls);draw();
          }else renderActions(details,[action]);
        };select.onchange=show;body.append(select,details);show();return;
      }else{
        for(const row of selected.history)body.append(node('p',`${row.year}岁 · ${row.text}`));
        if(!selected.history.length)body.append(node('p','正式授权后开始记录原人员、实际建设和往返结果。'));
      }
      if(actions.length){
        const select=node('select');select.setAttribute('aria-label','选择开拓事务');
        const details=node('div');
        for(const action of actions){const option=node('option',action.label);option.value=action.action;select.append(option);}
        const show=()=>{details.replaceChildren();const action={...actions.find(a=>a.action===select.value)};
          const people=['outpost_dispatch','outpost_supply'].includes(action.action)?selected.candidates:action.action==='outpost_appoint'?selected.residents:selected.units.filter(u=>['gathering','outbound','stationed'].includes(u.phase)&&u.free);
          renderActions(details,[action],[],people);
        };
        select.onchange=show;body.append(select,details);show();
      }
    });
  }
  window.HeavensOutposts={render};
})();
