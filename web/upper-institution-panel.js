(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN');
  const opened=new Set();let owner=null;
  function render(game,act){
    const d=game.upper_institution||{}, card=document.getElementById('upper-institution-card'),dock=document.querySelector('[data-panel-target="upper-institution"]');
    card.classList.toggle('hidden',!d.available);dock.classList.toggle('hidden',!d.available);
    if(!d.available){window.UtilityPanels?.close('upper-institution');return;}
    if(owner!==game.id){owner=game.id;opened.clear();}
    card.querySelector('h2').textContent=d.name;card.setAttribute('aria-label',d.name);dock.title=d.name;dock.querySelector('small').textContent=({asura:'王庭',nether:'妖宫',reincarnation:'轮殿'})[d.world];
    const root=document.getElementById('upper-institution-content');root.replaceChildren();
    root.classList.toggle('asura-court',d.world==='asura');
    if(d.world==='asura'&&d.court){window.AsuraCourtPanel.render(game,act,root);return;}
    const blocked=!d.local||!!game.pending_event||!!game.active_trial||!game.player.alive||!!game.imprisonment;
    const button=(text,action,target='',disabled=false)=>{const b=el('button',text);b.type='button';b.disabled=blocked||disabled;b.onclick=()=>act({action,target_id:target});return b;};
    const section=(id,title,detail)=>{const c=el('details',null,'doctrine-entry doctrine-compact');c.dataset.section=id;c.open=opened.has(id);c.addEventListener('toggle',()=>{if(c.isConnected){if(c.open)opened.add(id);else opened.delete(id);}});const s=el('summary'),text=el('span');text.append(el('b',title),el('small',detail));s.append(el('span',title[0],'doctrine-seal'),text);c.append(s);root.append(c);return c;};
    const oligarchy=d.world==='nether',religious=d.world==='reincarnation',regard=religious?'信望':'恩宠';
    const rank=oligarchy?(d.seat_active?'门阀代言人':'宫内客卿'):d.ranks[d.rank];
    const location=game.map?.locations?.find(x=>x.id===d.location)?.name||({asura:'万战魔城',nether:'祖兽神苑',reincarnation:'因果城'})[d.world];
    root.append(el('p',`${d.regime} · 驻地 ${location}`,'doctrine-lead'),el('p',d.description),el('p',`本界政历 ${d.unit} 单位 · 府库 ${fmt(d.treasury)} 灵石。政务随实际在本界度过的时间推进，短途余时会累计；读界面、投票和传送不推进政历。`,'muted'));
    window.renderOrganizationFinance?.(root, d.finance);
    if(!d.local)root.append(el('p',`须前往${location}办理事务。此处可查看政务；离开本界后身份和进度保留。`,'doctrine-note'));
    root.append(el('p',`现行${religious?'法旨':oligarchy?'门阀盟令':'王令'}：【${d.current_policy.name}】${d.current_policy.description}`,'doctrine-note'));
    const identity=section('identity','身份与供养',d.joined?rank:'尚未登记');
    if(!d.joined){identity.append(el('p','加入机构不占用宗门名额，不限制邻域入门；登记后方可享受政务与领取委托。'),button(religious?'登记奉愿':'登记效力','join'));}
    else{
      identity.append(el('p',`${rank} · 功勋 ${fmt(d.merit)} · 累计功绩 ${fmt(d.earned)}${oligarchy?'':` · ${regard} ${d.regard}/100`}`));
      identity.append(el('p','每在本界度过一年，成员基础供养 100 灵石，职阶每升一级另加 100；门阀代言人基础津贴为 200。政策可提高收益，实际支付以府库为限。'));
      if(!oligarchy&&d.rank<d.ranks.length-1){const next=d.rank+1;identity.append(el('p',`晋升 ${d.ranks[next]}：累计功绩 ${fmt(d.rank_merit[next])}，第 ${9+Math.floor(next/2)} 阶修为，${regard} ${next*20}。`),button('申请晋阶','promote'));}
      if(d.obligation)identity.append(el('p',`${d.obligation.name} · 最迟第 ${d.obligation.deadline} 单位交付；逾期 ${regard} −15。`,'doctrine-note'));
      identity.append(button('退出机构','leave','',!!d.job),el('small','有委托时须先交付或放弃；带未竟王命或誓愿退出会降低恩宠或信望。'));
    }
    const jobs=section('jobs','功勋与委托',d.job?`履约 ${d.job.progress}/${d.job.years} 年`:'驻地履约 · 筑域资材');
    jobs.append(el('p','每份委托须在驻地实际履约一个行动单位，基础 100 功勋，接取时按当前政务与赐福确定奖励；遇到事件可处理后续做。功勋消费不减少累计功绩。'));
    if(d.job)jobs.append(el('p',`本单报酬 ${d.job.reward} 功勋，当前 ${d.job.progress}/${d.job.years} 年。`),button('继续履约','work','',d.job.progress>=d.job.years),button('交付领取','claim','',d.job.progress<d.job.years),button('放弃委托','abandon'));
    else jobs.append(button('接取委托','accept','',!d.joined));
    jobs.append(el('p',`资材兑换需机构支付 ${fmt(d.material_stone_cost)} 灵石采购费；府库不足时暂缓兑换。`,'muted'));
    jobs.append(button('100 功勋 → 250,000 灵石','stones','',!d.joined||d.merit<100||d.treasury<250000),button(`${d.material_merit} 功勋 → 本界筑域材料一份`,'material','',!d.joined||d.merit<d.material_merit||d.treasury<d.material_stone_cost));
    if(oligarchy){
      const council=section('council','祖族议权',d.seat_active?'持有代言资格':'祖族授席，无定期选举');
      council.append(el('p','五门阀议权依次为 5、4、3、2、1，总计十五。取得代言资格后没有固定任期，但本族支持低于五十时失去资格。法令须至少八议权支持；空缺不赞成，玩家未主动提案时弃权。支持达到七十的门阀愿意支持你的政见。'));
      d.people.forEach((person,i)=>{const r=el('section',null,'doctrine-book');r.append(el('h3',`${person.title} · ${d.seat_active&&d.bloc===i?'你':person.present?person.name:'席位空缺'}`),el('p',`议权 ${d.weights[i]}/15 · 支持 ${d.support[i]}/100${d.bloc===i?' · 所选门阀':''}`),el('p',`授席条件：累计功绩 ${d.seat_merit[i]}、支持 ${d.seat_support[i]}、第 ${d.weights[i]>=4?10:9} 阶修为。`),button('选择依附此族','bloc',String(i),!d.joined||d.bloc===i||d.seat_active||!!d.job),button('争取支持 · 60 功勋','lobby',String(i),!d.joined||d.merit<60||d.support[i]>=100));council.append(r);});
      council.append(button('请求门阀授席','patronage','',!d.joined||d.seat_active||d.earned<d.seat_merit[d.bloc]||d.support[d.bloc]<d.seat_support[d.bloc]),button('辞去代言资格','resign','',!d.seat_active));
    }
    if(religious){const rites=section('rites','誓愿与祭仪',`信望 ${d.regard} · ${d.blessing_until>d.unit?`赐福余 ${d.blessing_until-d.unit} 单位`:'尚无赐福'}`);rites.append(el('p','自愿立誓后四单位内完成一份委托，除履约的 10 信望外再得 15；失约扣 15。祭仪花费 100 功勋增加 20 信望，四单位内新接委托的功勋报酬提高两成，不可重复叠加。'),button('立下济度誓愿','vow','',!d.joined||!!d.obligation),button('举行祭仪 · 100 功勋','rite','',!d.joined||d.merit<100||d.blessing_until>d.unit));}
    const politics=section('politics',religious?'奏请法旨':oligarchy?'门阀议政':'王命与请奏',`下次机构议政：第 ${d.agenda_at} 单位`);
    politics.append(el('p',oligarchy?'每次提案间隔至少四单位；投票不耗时间。未通过维持现政，不扣府库。提案通过后，与法令政见不合的门阀支持降低五点，本族降低十点。':`请奏须至少${d.ranks[2]}，${regard}达到 ${religious?60:80}，消耗 100 功勋。君主或祭议拥有最终裁定权，每次请奏间隔四单位。`),el('p',`每次施行消耗府库 ${fmt(d.policy_cost)} 灵石；同一时刻只有一项政务生效，新政替换旧政。每四单位会自行议政，不阻断修行。`));
    for(const p of d.policies){const row=el('section',null,'doctrine-book');row.append(el('h3',`${p.name}${p.id===d.policy?' · 生效中':''}`),el('p',p.description));if(oligarchy)row.append(el('p',`预计赞成：${d.tallies[p.id].filter(v=>v.yes).map(v=>`${v.name}(${v.weight})`).join('、')||'暂无'}`,'muted'));row.append(button(oligarchy?'提出议案':'奏请施行','policy',p.id,!d.joined||p.id===d.policy));politics.append(row);}
    const history=section('history','政务纪事',`${d.log.length} 条近况`);d.log.slice().reverse().forEach(l=>history.append(el('p',`第 ${l.unit} 单位 · ${l.text}`)));if(!d.log.length)history.append(el('p','尚无本界机构纪事。','muted'));
  }
  window.UpperInstitutionPanel={render};
})();
