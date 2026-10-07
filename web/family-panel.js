(() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = v => Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits:1});
  const button = (text, action, payload={}, disabled=false) => `<button type="button" data-family='${esc(JSON.stringify({action,...payload}))}' ${disabled?'disabled':''}>${esc(text)}</button>`;
  function member(row, family, registered) {
    const id={npc_id:row.id}, infusion=row.infusion || {};
    const acts=[];
    if(row.can_interact) {
      const techniques=(family.teaching_options || []).map(t=>`<option value="${esc(t.id)}">${esc(t.name)} · +${num(t.power)}战力</option>`).join('');
      const items=(family.equipment_options || []).map(i=>`<option value="${esc(i.id)}">${esc(i.name)} ×${i.quantity} · +${num(i.power)}战力</option>`).join('');
      if(techniques)acts.push(`<label>传授功法<select data-family-technique>${techniques}</select>${button('传授','teach',id)}</label>`);
      if(items)acts.push(`<label>赠与装备<select data-family-item>${items}</select>${button('赠与','gift_equipment',id)}</label>`);
      acts.push(button(row.in_party?'已在队伍':'邀请同行','invite',id,row.in_party));
      acts.push(button(`灌顶 · ${num(infusion.cost)}机缘`,'infuse',id,!infusion.allowed));
    }
    if(registered && family.can_manage && row.alive) {
      if(row.can_marry)acts.push(button('安排外聘婚配','marry',id));
      const sects=(family.diplomacy || []).filter(s=>s.kind!=='family' && ['alliance','vassal'].includes(s.status));
      if(!row.sect_name && row.age>=16 && sects.length)acts.push(`<label>安排入宗<select data-family-sect>${sects.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('')}</select>${button('入宗','send_sect',id)}</label>`);
      if(family.intrigue_enabled)acts.push(button('移出族籍','expel',id));
    }
    return `<article class="family-row family-member ${row.alive===false?'fallen':''}" data-family-member="${esc(row.id)}">
      <div class="family-member-heading"><b>${esc(row.name)}${registered?' · '+esc(row.member_type):''}</b><strong>${esc(row.realm_name)}</strong></div>
      <p>${esc(row.spirit_root_name)} · ${row.age}岁 · 战力 ${num(row.combat_power)}${row.spouse_name?' · 配偶 '+esc(row.spouse_name):''}${row.sect_name?' · 任职 '+esc(row.sect_name):''}</p>
      ${row.can_interact?`<small>灌顶上限：${esc(infusion.cap_name)}；须你的修为严格高于后代。</small>`:row.alive!==false && row.age<16?'<small>满16岁且拥有灵根后，可以同界互动。</small>':''}
      ${acts.length?`<div class="family-member-actions">${acts.join('')}</div>`:''}</article>`;
  }
  function render(root, family, act) {
    family=family || {};
    const sections=[];
    if(family.exists) sections.push(`<section class="family-overview"><strong>家族总战力 ${num(family.total_power)}</strong><p>立族底线：至少一位${esc(family.protection_realm || '结丹')}修士坐镇${family.pressure?` · 排挤 ${family.pressure}/3`:''}。</p>
      ${family.can_manage?button(family.reproduction_enabled?'暂停族内繁衍':'恢复族内繁衍','reproduction',{enabled:!family.reproduction_enabled}):''}
      <small>外聘婚配需支付本界礼仪费用；族人生育按双方较高境界结算，化神起自然概率为0。所生后代必有灵根。</small></section>`);
    const registered=new Set((family.roster || []).map(r=>r.id));
    const children=(family.offspring || []).filter(c=>!registered.has(c.id));
    sections.push(`<section><h3>血脉后代</h3>${children.map(c=>member(c,family,false)).join('') || '<p class="muted">暂无未入族籍的后代；已入族籍者见下方名册。</p>'}</section>`);
    if(family.exists)sections.push(`<section><h3>家族名册</h3>${(family.roster || []).map(c=>member(c,family,true)).join('') || '<p class="muted">当前没有可见的族人名册。</p>'}</section>`);
    const ledger=family.ledger;
    if(ledger)sections.push(`<section class="family-finances"><h3>家族内政</h3><div class="family-metrics">${[['资材',ledger.resources],['年度收入',ledger.income],['年度开支',ledger.expenses],['收支差额',ledger.balance],['资材缺口',ledger.shortfall],['本年分红',ledger.dividend],['宗门奉赠',ledger.office_income],['附属宗门上供',ledger.tribute]].map(([k,v])=>`<span><small>${k}</small><b>${num(v)}</b></span>`).join('')}</div>
      <p>人数增加会提高开支，高阶修士带来更多收入。盈余分红与宗门奉赠只在家族所在界面发放。</p>
      ${family.can_manage?`<div class="family-member-actions"><label>注入灵石<input data-family-funds type="number" min="1" step="1" value="1000">${button('注资','fund')}</label>${button(family.gather_used?'本年已经营':'组织经营采集（每年一次）','gather',{},family.gather_used)}</div>`:''}</section>`);
    sections.push(`<section><h3>本界其他修仙家族</h3>${(family.other_families || []).map(f=>`<div class="family-other"><b>${esc(f.name)}</b><span>${f.living_count}人在册 · 总战力 ${num(f.total_power)}</span><small>${esc(f.description)}</small></div>`).join('') || '<p class="muted">本界暂未出现其他存续的修仙家族。</p>'}</section>`);
    if(family.diplomacy?.length)sections.push(`<section><h3>家族外交</h3><p>依附主从按高阶修士数量及总战力判定。依附宗门且族内无人拥有其决策权时，可能遭到兼并。</p>${family.diplomacy.map(s=>`<div class="family-other"><b>${esc(s.name)} · ${esc(({alliance:'同盟',neutral:'中立',vassal:'依附',war:'交战',truce:'停战'})[s.status] || s.status)}${s.status==='vassal'?' · '+(s.overlord===family.id?'对方依附本族':'本族依附对方'):''}</b><span>总战力 ${num(s.total_power)}</span>${family.can_manage?`<div class="family-member-actions">${button('结盟','diplomacy',{target_id:s.id,status:'alliance'},s.status==='war')}${button('确立依附','diplomacy',{target_id:s.id,status:'vassal'},s.status==='war')}${button('恢复中立','diplomacy',{target_id:s.id,status:'neutral'},s.status==='war')}${button('宣战','diplomacy',{target_id:s.id,status:'war'},s.status==='war')}</div>`:''}</div>`).join('')}</section>`);
    const panel=document.createElement('div');panel.className='family-management';panel.innerHTML=sections.join('');root.appendChild(panel);
    window.renderOrganizationFinance?.(panel.querySelector('.family-finances') || panel, family.finance);
    panel.querySelectorAll('[data-family]').forEach(node=>node.addEventListener('click',()=>{
      const payload=JSON.parse(node.dataset.family),group=node.closest('.family-member');
      if(payload.action==='teach')payload.technique_id=group.querySelector('[data-family-technique]').value;
      if(payload.action==='gift_equipment')payload.item_id=group.querySelector('[data-family-item]').value;
      if(payload.action==='send_sect')payload.sect_id=group.querySelector('[data-family-sect]').value;
      if(payload.action==='fund')payload.amount=Number(panel.querySelector('[data-family-funds]').value);
      if(payload.action==='diplomacy' && payload.status==='war' && window.openGameConfirm) {
        openGameConfirm({title:'家族宣战',body:'将以家族身份向该势力宣战，确认后请前往战争界面指挥。',confirmText:'确认宣战',onConfirm:()=>act(payload)});
      } else if(payload.action==='expel' && window.openGameConfirm) {
        openGameConfirm({title:'移出族籍',body:'该族人将停止领取家族供养，并离开同行队伍。确认除名？',confirmText:'确认除名',onConfirm:()=>act(payload)});
      } else act(payload);
    }));
  }
  window.FamilyPanel={render};
})();
