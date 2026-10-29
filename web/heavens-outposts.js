/* Civilian frontier details reuse the existing heavens navigation and command. */
(() => {
  const status={unregistered:'尚未授权',authorized:'已获开拓许可',building:'施工中',active:'正常运营',suspended:'暂停经营',withdrawing:'撤回中',closed:'已关闭'};
  const phase={gathering:'沿路集结',outbound:'跨界去程',stationed:'已在驻地',returning:'跨界返程',homeward:'沿路返乡',home:'已归返结清',lost:'原人物陨落'};
  function render(host, projects, ui, api) {
    const {node,title,tile,back,subview,renderActions,empty,go}=api;
    const selected=projects.find(row=>row.id===ui.target);
    if(!selected){
      back(host,'返回诸界','worlds');title(host,'跨界开拓','保留原总部，以原门人、原钱货经营异界分驻地。');
      const directory=node('div',null,'heavens-directory');
      for(const row of projects)tile(directory,{name:row.name,description:`${row.source_name} · ${row.gateway} → ${row.destination_name} · ${row.location_name}`,status:status[row.status],glyph:'驻',onClick:()=>go('worlds',row.id)});
      host.append(directory);
      if(!projects.length)empty(host,'尚无可开拓的势力','首期支持人界或魔界的原宗门、家族。取得实际控制权后，在原总部批准开拓；结丹至炼虚可申请个人往返。');
      return;
    }
    const returnLink=node('button','‹ 返回开拓目录','heavens-back');returnLink.type='button';returnLink.onclick=()=>go('worlds','outpost_network');host.append(returnLink);
    title(host,selected.name,`${selected.source_name} → ${selected.destination_name} · ${selected.location_name} · ${status[selected.status]}`);
    if(selected.notice)host.append(node('p',selected.notice,'muted'));
    subview(host,[['permit','授权与往返'],['staff','派驻与补给'],['local','驻地与仓储'],['records','开拓纪要']],'permit',(body,section)=>{
      let actions=[];
      if(section==='permit'){
        body.append(node('p',`在原总部批准开拓，到${selected.gateway}申请个人通行。本人去返程各8年，各800灵石；首次启程同时预留返程款。`),node('p','民用开拓许可只用于派驻、施工和补给，不附带征服或宣战权。'));
        if(selected.visit_status)body.append(node('p',`个人行程：${({preparing:'启程中',visiting:'异界停留',returned:'已经返乡',cancelled:'启程已取消',failed:'行程结束'})[selected.visit_status]} · 保留返程款 ${selected.return_fare} 灵石`));
        actions=selected.actions.filter(r=>['outpost_authorize','outpost_depart','outpost_return','outpost_wait'].includes(r.action));
      }else if(section==='staff'){
        body.append(node('p','原门人先沿地图道路集结，再跨界8年。施工另需当地10年；随行预留往返费用。每处最多3人在途或驻守。'),node('p','派驻携带原府库二阶构材6、导灵矿2、储能矿2；补给使者携款抵达后循路返乡。'));
        for(const unit of selected.units)body.append(node('p',`${unit.name}${unit.courier?' · 补给使者':''}：${phase[unit.phase]}${unit.duration?` · ${unit.progress}/${unit.duration}年`:''}${unit.notice?' · '+unit.notice:''}`));
        actions=selected.actions.filter(r=>['outpost_dispatch','outpost_supply','outpost_recall'].includes(r.action));
      }else if(section==='local'){
        body.append(node('p',`施工进度 ${selected.progress||0}/${selected.duration||10} 年；运营养护每当地年100灵石。暂停后保留库存与人员，停止经营养护。`));
        if(selected.balance!=null){
          body.append(node('p',`当地经费：${selected.balance.toLocaleString()} 灵石`));
          for(const row of selected.stock_rows||[])body.append(node('p',`${row.name} × ${row.quantity}`));
          const governor=selected.residents.find(p=>p.id===selected.governor_id);body.append(node('p',`在场负责人：${governor?.name||'暂无可履职负责人'}`));
        }else body.append(node('p','库存与现任负责人须亲自抵达驻地核实。'));
        actions=selected.actions.filter(r=>['outpost_appoint','outpost_suspend','outpost_activate','outpost_withdraw'].includes(r.action));
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
