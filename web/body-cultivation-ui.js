(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN');
  const families={
    immortal:{sigil:'仙',eyebrow:'仙躯 · 五炁归元',step:'神光'},
    demonic:{sigil:'煞',eyebrow:'魔躯 · 五蕴铸身',step:'蕴'},
    monster:{sigil:'妖',eyebrow:'妖躯 · 五蜕返祖',step:'蜕'},
    ghost:{sigil:'冥',eyebrow:'鬼躯 · 生灭轮转',step:'法'}
  };
  function hero(root,{family,title,titleClass='',description,level=0,max=50,names=[]}){
    const theme=families[family];root.classList.add('body-cultivation');root.dataset.bodyFamily=family;
    const header=el('header',null,'body-cultivation-hero');
    const sigil=el('div',null,'body-cultivation-sigil');sigil.setAttribute('aria-hidden','true');
    sigil.append(el('span',theme.sigil));
    const copy=el('div',null,'body-cultivation-heading');copy.append(el('small',theme.eyebrow,'body-cultivation-eyebrow'),el('h3',title,titleClass),el('p',description));
    header.append(sigil,copy);root.append(header);
    const journey=el('section',null,'body-cultivation-journey');journey.setAttribute('aria-label',`${theme.step}解锁进度`);
    const line=el('div',null,'body-cultivation-progress-label');line.append(el('strong',`高阶炼体 ${level} / ${max} 层`),el('small',`已解锁 ${names.filter((_,i)=>level>=(i+1)*10).length} / ${names.length}`));journey.append(line);
    const steps=el('ol',null,'body-cultivation-stages');
    names.forEach((name,i)=>{const step=el('li');step.dataset.step=i;step.classList.toggle('is-open',level>=(i+1)*10);
      step.append(el('span',String((i+1)*10),'body-stage-number'),el('strong',name),el('small',level>=(i+1)*10?'已解锁':`${(i+1)*10}层解锁`));steps.append(step);});
    journey.append(steps);root.append(journey);
  }
  function card(node,{index,name,level=0,unlocked=true,unlockLevel}){
    node.classList.add('body-cultivation-card');node.classList.toggle('locked',!unlocked);
    const cap=el('div',null,'body-card-caption');cap.append(el('span',String(index+1).padStart(2,'0')),el('small',unlocked?'已启 · 独立修持':`${unlockLevel}层开启`));node.prepend(cap);
    const heading=node.querySelector('h3,h4');
    if(heading){const seal=el('span',name.slice(0,1),'body-card-seal');seal.setAttribute('aria-hidden','true');heading.prepend(seal);}
    const meter=el('div',null,'body-cultivation-rank');meter.setAttribute('role','meter');meter.setAttribute('aria-label',`${name}修炼重数`);
    meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax','10');meter.setAttribute('aria-valuenow',String(level));
    for(let i=1;i<=10;i++){const tick=el('span');tick.classList.toggle('is-open',unlocked&&i<=level);meter.append(tick);}
    if(heading)heading.after(meter);else node.append(meter);
  }
  function material(parent,row,cls=''){
    const box=el('div',null,`body-cultivation-material ${cls}`);box.dataset.material=row.id;
    const missing=Math.max(0,row.needed-row.owned);box.classList.toggle('is-short',missing>0);
    if(window.PixelLibrary?.active()){
      const picture=el('div',null,'body-material-picture'),img=el('img');img.alt=row.name;img.width=img.height=64;img.loading='lazy';picture.append(img);box.append(picture);
      window.PixelLibrary.ensure().then(c=>{const asset=c?.assets[row.asset+'.portrait'];if(img.isConnected&&asset)img.src=asset.file;});
    }
    const info=el('div',null,'body-material-copy');info.append(el('strong',row.name),el('p',row.needed?`持有 ${fmt(row.owned)} / 本次所需 ${fmt(row.needed)}`:`持有 ${fmt(row.owned)} · 培养圆满`),el('small',`仅${row.origin_name}产出${missing?` · 尚缺 ${fmt(missing)}`:''}`));
    box.append(info);parent.append(box);return box;
  }
  window.BodyCultivationUI=Object.freeze({hero,card,material});
})();
