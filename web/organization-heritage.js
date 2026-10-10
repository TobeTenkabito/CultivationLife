(() => {
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  const num=n=>Number(n||0).toLocaleString('zh-CN');
  window.OrganizationHeritage={render(root,d,submit){
    if(!d)return;
    const section=el('details');section.className='organization-heritage';
    section.append(el('summary',`本门绝学 · ${d.books.length}部`),el('p',`本界最高收录${d.ceiling}功法。成员首次参悟免费；再次领取Lv.1玉简须缴费入府库。配置功法仍须满足灵根、肉身与元力要求。`));
    const send=(action,technique_id)=>submit({action,technique_id,owner_id:d.owner_id,revision:d.revision});
    for(const r of d.books){const card=el('article');card.className='depot-good';
      card.append(el('b',r.name),el('small',`${r.grade} · ${r.learned?'已领悟':'尚未领悟'}`));
      const b=el('button',r.learned?`领取玉简 · ${num(r.price)}灵石`:'免费参悟');b.type='button';b.disabled=!d.local;
      b.dataset.heritageAction=r.learned?'heritage_copy':'heritage_learn';b.dataset.techniqueId=r.id;
      b.onclick=()=>send(b.dataset.heritageAction,r.id);card.append(b);section.append(card);
    }
    if(!d.local)section.append(el('p','请亲赴组织驻地参悟、领取或收录绝学。'));
    if(d.can_add&&d.add_options.length){const form=el('form'),select=el('select');select.setAttribute('aria-label','收录本门绝学');
      for(const r of d.add_options){const o=el('option',r.name);o.value=r.id;select.append(o);}
      const b=el('button','收录已悟功法');b.type='submit';b.dataset.heritageAction='heritage_add';b.disabled=!d.local;form.append(select,b);
      form.onsubmit=e=>{e.preventDefault();send('heritage_add',select.value);};section.append(form);
    }
    if(d.history.length){const log=el('details');log.append(el('summary','传承记录'));for(const r of [...d.history].reverse())log.append(el('p',`${r.year}岁：${r.text}`));section.append(log);}
    root.append(section);
  }};
})();
