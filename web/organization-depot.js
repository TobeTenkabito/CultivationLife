(() => {
  const node=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const num=n=>Number(n||0).toLocaleString('zh-CN');
  window.OrganizationDepot={render(root,d,submit){
    if(!d)return;
    const section=node('details',null,'organization-depot');
    section.append(node('summary',`府库实物 · ${num(d.value)} 灵石折值`));
    section.append(node('p','申请须提前一个行动单位；任一高层批准后，物资预留待领。战备只征用未预留库存。','muted'));
    if(d.contribution!=null)section.append(node('p',`宗门贡献 ${num(d.contribution)}；申请时扣除，驳回或撤销后退还，同次入宗期间有效。`,'muted'));
    if(!d.local)section.append(node('p','请到组织驻地办理采购、审批及领取。','muted'));
    const send=(action,payload={})=>submit({action,owner_id:d.owner_id,revision:d.revision,...payload});
    const button=(text,action,payload={},disabled=false)=>{const b=node('button',text);b.type='button';b.dataset.depotAction=action;b.disabled=!d.local||disabled;b.onclick=()=>send(action,payload);return b;};
    const goods=node('div',null,'depot-goods');
    for(const r of d.stock){const card=node('article',null,'depot-good');card.append(node('b',r.name),node('small',`库存 ${num(r.quantity)} · 单件现值 ${num(r.value)}`));
      card.append(button(`申请一件${r.contribution_cost?' · '+num(r.contribution_cost)+'贡献':''}`,'depot_request',{item:r.key,quantity:1},!r.requestable));goods.append(card);}
    section.append(goods);
    if(!d.stock.length)section.append(node('p','暂无实物储备；年度经营有盈余时会从本地市场采购。','muted'));
    if(d.can_manage){const form=node('form',null,'depot-purchase'),select=node('select'),qty=node('input');
      select.setAttribute('aria-label','采购物资');for(const r of d.offers){const o=node('option',`${r.name} · 参考 ${num(r.price)}`);o.value=r.key;select.append(o);}
      qty.type='number';qty.min='1';qty.max='1000';qty.value='1';qty.setAttribute('aria-label','采购数量');
      const b=node('button','从本地市场采购');b.type='submit';b.disabled=!d.local||!d.offers.length;
      form.append(select,qty,b);form.onsubmit=e=>{e.preventDefault();send('depot_purchase',{item:select.value,quantity:Number(qty.value)});};section.append(form);}
    const requests=node('div',null,'depot-requests');
    for(const r of [...d.requests].reverse()){
      const card=node('article',null,'depot-request'),name=[...d.stock,...d.offers].find(i=>i.key===r.item)?.name||r.item;
      card.append(node('b',`${name} ×${r.quantity}`),node('small',({pending:'等待审批',approved:'已批准 · 留存待领',collected:'已领取',cancelled:'已取消',rejected:'已驳回'})[r.status]));
      const p={request_id:r.id};
      if(r.status==='pending'){
        const ready=d.unit>=r.ready_unit;
        if(!ready)card.append(node('small','尚需推进一个行动单位后审批。'));
        if(d.can_manage)card.append(button('批准申请','depot_approve',p,!ready));
        if(d.seniors.length){const select=node('select');select.setAttribute('aria-label','请求批准的高层');
          d.seniors.forEach(s=>{const o=node('option',s.name);o.value=s.id;select.append(o);});
          const b=button('请高层审批','depot_review',{},!ready);b.onclick=()=>send('depot_review',{...p,approver_id:select.value});card.append(select,b);}
      }
      if(r.status==='approved')card.append(button('领取物资','depot_collect',p));
      if(['approved','pending'].includes(r.status))card.append(button('撤销申请','depot_cancel',p));
      requests.append(card);
    }
    section.append(requests);root.append(section);
  }};
})();
