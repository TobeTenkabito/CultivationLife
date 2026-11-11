/* Provincial affairs live inside original court and building navigation. */
(() => {
  const el=(...a)=>window.GameUi.element(...a),fmt=n=>Number(n||0).toLocaleString('zh-CN');
  const labels={vacant:'待授',appointed:'待赴任',active:'在任',handover:'待交接'};
  function render(host,game,dispatch,selected=null){
    const d=game.upper_institution?.court?.governorship;if(!d)return;
    const root=el('section',null,'asura-governorship');root.dataset.dlcScope='asura-manifestation';
    const blocked=!!game.pending_event||!!game.trial?.active||!game.player.alive||!!game.imprisonment||!!game.map_journey;
    const send=(action,data={})=>dispatch({action:'governorship',target_id:JSON.stringify({action,token:d.token,...data})});
    const button=(label,action,data={},disabled=false)=>{const b=el('button',label,'court-button');b.type='button';b.dataset.governorAction=action;b.dataset.dlc='asura-manifestation';b.disabled=blocked||disabled;b.onclick=()=>send(action,typeof data==='function'?data():data);return b;};
    const fold=(title,description)=>{const box=el('details',null,'governor-section');box.append(el('summary',title));if(description)box.append(el('p',description,'court-description'));return box;};
    const choose=(label,rows)=>{const s=el('select');s.setAttribute('aria-label',label);for(const r of rows){const o=el('option',r.name);o.value=r.id;s.append(o);}return s;};
    const headline=el('div',null,'governor-heading');headline.append(el('span','府','governor-seal'),el('div'));
    headline.lastChild.append(el('h3',selected?'地方府务':'总督外任'),el('p',d.enabled?'任期五百年 · 原址接任 · 公私分账':'扩展已停用 · 保留原款与交接责任','court-description'));root.append(headline);
    if(!selected){
      const request=fold(d.king?'地方任命':'申请外任','战将以上、累计功绩100、恩宠20可在王庭申请。受任后沿原地图赴任，设府及工程另付原款。');
      const cities=choose('外任城市',d.cities.filter(c=>c.eligible)),people=choose('总督人选',d.candidates);
      request.append(cities);if(d.king)request.append(people);
      request.append(button(d.king?'颁发任命':'申请外任',d.king?'appoint':'request',()=>({city:cities.value,person:people.value}),!d.enabled||!d.capital||!d.cities.length||(!d.king&&!d.qualified)||(d.king&&!d.candidates.length)));
      root.append(request);
    }
    const rows=d.offices.filter(r=>!selected||[r.id,r.city_id,r.building_id].includes(selected));
    for(const r of rows){
      const box=el('article',null,'governor-office');box.dataset.governorOffice=r.id;
      const place=game.map?.locations?.find(p=>p.id===r.location)?.name||r.location;
      box.append(el('h4',r.name),el('p',`${labels[r.status]} · ${r.holder_name} · ${place}`),el('p',`任期至 ${r.expires} 年${r.cash!==undefined?' · 公款 '+fmt(r.cash)+' 灵石':''}`,'court-description'));
      if(!selected){
        box.append(el('p','赴当地建筑办理府务；设府前从原城市的「总督府」进入。','court-note'));
        if(d.king){
          const funds=el('input');funds.type='number';funds.min='1';funds.max='1000000000000000';funds.value='1000000';funds.setAttribute('aria-label',r.name+'拨款');
          const actions=fold('拨款与撤任');actions.append(funds,button('拨付公款','fund',()=>({office:r.id,amount:Number(funds.value)}),!d.enabled||!d.capital),button('撤销任命','revoke',{office:r.id},!d.enabled||!d.capital||!['active','appointed'].includes(r.status)));box.append(actions);
        }
      }else if(r.mine){
        if(r.status==='appointed')box.append(button('验收接任','assume',{office:r.id},!d.enabled||!r.local));
        if(r.active){
          const budget=fold('公款与府署','自愿资助进入本府公账，不能取回个人行囊。营造采购原市场实货，府署保留王庭产权。');
          const funds=el('input');funds.type='number';funds.min='1';funds.max='1000000000000000';funds.value=String(Math.max(1000000,r.quote?.total||0));funds.setAttribute('aria-label','资助本府金额');
          budget.append(funds,button('资助本府','donate',()=>({office:r.id,amount:Number(funds.value)}),!d.enabled));
          if(r.building_status!=='intact'&&r.quote){const q=r.quote;budget.append(el('p',`营造总价 ${fmt(q.total)} 灵石 · 其中工费 ${fmt(q.coins)}`),el('p',q.reason||'工料及施工全额实付，原址恢复。','court-description'),button(r.building_status==='unbuilt'?'营造府署':'公费原址重建','build',{office:r.id,quote:q.token,total:q.total},!d.enabled||!!q.reason));}
          box.append(budget);
          const staff=fold('属员与履约','从原址自由修士中聘任执事。项目沿原机构系统托管预算，按真实年份执行；离场和失去资格会暂停。');
          const person=choose('地方执事',[{id:'',name:'暂不聘任'},...(r.candidates||[])]);person.value=r.people?.[0]||'';
          staff.append(person,button('登记属员','staff',()=>({office:r.id,person:person.value}),!d.enabled||!!r.agenda?.job));
          window.InstitutionGovernance?.render(staff,d.management.filter(m=>m.id===r.id),payload=>send('management',{office:r.id,payload}),'asura-manifestation');box.append(staff);
        }
        const handover=fold('任职交接','上缴只将未耗公款交回王庭。辞任解除原任职，建筑、公款与历史留在原址；已耗工程与劳务不退款。');
        handover.append(button('上缴未耗公款','return',{office:r.id},!r.local||r.controller!=='player'),button('交接辞任','resign',{office:r.id},!r.local));box.append(handover);
      }
      if(r.history?.length){const history=fold('任职与收支记录');for(const h of [...r.history].reverse())history.append(el('p',`${h.year}年 · ${h.text}`));box.append(history);}
      root.append(box);
    }
    if(!rows.length&&!selected)root.append(el('p','尚无已授地方任职。','court-description'));
    host.append(root);
  }
  window.AsuraGovernorship={render};
})();
