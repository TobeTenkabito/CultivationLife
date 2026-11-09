/* DLC terms within existing destinations. No new navigation buttons. */
(() => {
 const e=(...a)=>window.GameUi.element(...a),f=n=>Number(n||0).toLocaleString('zh-CN');
 function contracts(root,data,send,filter='garden'){
   if(!data)return null;
   const offers=data.offers.filter(o=>o.id===filter),active=data.active,r=active&&(filter==='free')===(active.source_kind==='inventory')?active:null;
   const history=data.history.filter(h=>(filter==='free')===(h.source_kind==='inventory'));
   if(!offers.length&&!r&&!history.length)return null;
   const box=e('section',null,'institution-sheet');box.append(e('h3',filter==='free'?'散仙合作契约':'长期供货'));
   const button=(label,action,value='')=>{const b=e('button',label);b.type='button';b.dataset.contractAction=action;b.dataset.dlc='yaochi-westward';b.onclick=()=>send({action,target_id:data.token+'|'+value});return b;};
   if(r){const deliver=button('交付本期实货','contract_deliver');deliver.disabled=!!data.delivery_reason;box.append(e('strong',r.name),e('p',`已交 ${r.completed}/${r.periods} 期 · 每期 ${r.quantity} 件 · 货款 ${f(r.price)}`),e('p',`下一交付年 ${r.next} · 截止 ${r.deadline}`),e('small',data.delivery_reason||'本期实货可交付','muted'),deliver,button('交接余款','contract_cancel'));}
   else for(const o of offers){const b=button('签订分期契约','contract_open',o.id),reason=active?'请先交接已有供货契约':o.reason;b.disabled=!!reason;box.append(e('p',`${o.name}：${o.item_name}，每期 ${o.quantity} 件，共 ${o.periods} 期，间隔 ${o.interval} 年；每期 ${f(o.price)} 灵石。`),e('small',reason||'采购方预留全部实际货款；未交付部分可交接退回原款。','muted'),b);}
   if(history.length){const past=e('details');past.append(e('summary','近期履约'));for(const h of [...history].reverse())past.append(e('p',`${h.name} · 已交 ${h.completed}/${h.periods} 期 · 实付 ${f(h.paid)} · 退原款 ${f(h.refunded)}`));box.append(past);}
   root.append(box);return box;
 }
 function strategy(root,d,send){
   if(!d?.strategy)return;
   const s=d.strategy,box=e('details',null,'institution-sheet');box.append(e('summary','施政安排与原天官提案'));
   const policy=e('select');for(const [id,name] of Object.entries({balanced:'均衡施政',repair:'司土修缮',procurement:'天工补缺',training:'公共修持',service:'地方护民'})){const o=e('option',name);o.value=id;policy.append(o);}policy.value=s.priority;policy.setAttribute('aria-label','施政优先序');
   const cap=e('input');cap.type='number';cap.min='0';cap.value=s.cap;cap.setAttribute('aria-label','单项议案预算上限');
   const batch=e('input');batch.type='number';batch.min='1';batch.max='20';batch.value=s.batch;batch.setAttribute('aria-label','采购批量上限');
   const save=e('button','保存下一批施政安排');save.type='button';save.dataset.dlc='yaochi-westward';save.disabled=!!d.authority||!!d.current;save.onclick=()=>send({action:'council_strategy',target_id:d.token+'|'+policy.value+':'+Number(cap.value)+':'+Number(batch.value)});
   const field=(name,input)=>{const l=e('label',name,'institution-field');l.append(input);return l;};
   const controls=e('div',null,'institution-controls');controls.append(field('施政优先序',policy),field('单项预算上限',cap),field('采购批量上限',batch),save);box.append(controls,e('p','预算上限填0表示沿原府库额度；所有项目仍须逐案听议表决。','muted'));
   for(const p of s.proposals){const offer=d.offers.find(o=>o.key===p.key),b=e('button','采纳并开始听议');b.type='button';b.dataset.dlc='yaochi-westward';b.disabled=!!d.authority||!!d.current||!offer||!!offer.reason;b.onclick=()=>send({action:'council_propose',target_id:d.token+'|'+offer.token});box.append(e('p',`${p.proposer} 提议：${p.name} · 原预算 ${f(p.budget)}`),e('small',p.reason,'muted'),b);}
   if(!s.proposals.length)box.append(e('p','在玉京经过实际年份后，空闲原天官会根据当地真实需求提出有限事项。','muted'));
   root.append(box);
 }
 function benefits(root,rows){if(!rows?.length)return;const box=e('section',null,'institution-sheet');box.append(e('h3','获奖待遇'));for(const r of rows)box.append(e('p',r.label+` · 截止 ${r.until} 年`));root.append(box);}
 window.WestwardDevelopment={contracts,strategy,benefits};
})();
