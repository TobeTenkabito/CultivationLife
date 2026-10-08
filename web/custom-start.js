/* Initial-life editor. All selections are validated by the creation endpoint. */
(() => {
  const el=(tag,text,cls='')=>{const n=document.createElement(tag);n.textContent=text??'';n.className=cls;return n;};
  window.CustomStart={render(config,submit){
    document.querySelector('#custom-start')?.remove();
    const c=config.custom_start;if(!c)return;
    const root=el('details',null,'custom-start');root.id='custom-start';
    root.append(el('summary','自定义开局 · 写下你的前尘'),el('p','自由设定这一世的起点。年龄随修为生成，进入游戏后沿用正常修炼、经济与战斗规则。','muted'));
    const form=el('form');form.id='custom-start-form';root.append(form);
    const group=title=>{const d=el('fieldset');d.append(el('legend',title));const grid=el('div',null,'custom-start-grid');d.append(grid);form.append(d);return grid;};
    const select=(parent,label,options,id)=>{const l=el('label',label),s=el('select');s.id='custom-'+id;s.setAttribute('aria-label',label);Object.entries(options).forEach(([v,t])=>s.add(new Option(t,v)));l.append(s);parent.append(l);return s;};
    const input=(parent,label,id,value,min,max)=>{const l=el('label',label),n=el('input');n.id='custom-'+id;n.setAttribute('aria-label',label);n.type=max==null?'text':'number';n.value=value;if(max!=null){n.min=min;n.max=max;n.step=1;}l.append(n);parent.append(l);return n;};
    const identity=group('根骨与修行');
    const rootSelect=select(identity,'自定义灵根',config.spirit_roots,'root'),path=select(identity,'自定义道途',config.paths,'path');
    const species=select(identity,'妖修种属',Object.fromEntries(Object.entries(config.monster_species).map(([k,v])=>[k,v.name])),'species');
    const world=select(identity,'出生界面',c.worlds,'world'),realm=select(identity,'修为境界',Object.fromEntries(c.realms.map(r=>[r.id,r.name])),'realm');realm.value='1';
    const layer=select(identity,'修为层数',{},'layer');
    const body=input(identity,'普通炼体等级','body',0,0,100),higher=input(identity,'高阶肉身等级','higher-body',0,0,100),sense=input(identity,'神识等级','sense',4,0,1000);
    const roots=el('div',null,'custom-roots');roots.append(el('span','补全灵根'));
    for(const [id,name] of Object.entries({metal:'金',wood:'木',water:'水',fire:'火',earth:'土'})){const l=el('label',name),check=el('input');check.type='checkbox';check.value=id;check.dataset.additionalRoot='1';l.append(check);roots.append(l);}identity.append(roots);
    const org=group('宗门与家族');const sect=select(org,'所属宗门',{},'sect'),sectName=input(org,'自建宗门名称','sect-name','',null,null),family=select(org,'所属家族',{},'family'),familyName=input(org,'自建家族名称','family-name','',null,null);
    const domain=group('邻域与温养');const tendency=select(domain,'邻域倾向',{'':'不携带',...c.tendencies},'tendency'),rank=input(domain,'邻域境界等级','domain-rank',1,1,13),warming=input(domain,'额外温养','warming',0,0,99),route=select(domain,'八部本命',{'':'按倾向选择',...c.asura_routes},'route');
    const domainNote=el('p',null,'muted');domain.append(domainNote);
    const bag=group('行囊与本命');const inventory=[],manuals=[];
    const search=input(bag,'搜索物品','item-search','',null,null),items=select(bag,'添加行囊物品',{},'item'),quantity=input(bag,'物品数量','quantity',1,1,1000000000000);
    const add=el('button','加入行囊');add.type='button';add.id='custom-add-item';bag.append(add);
    const list=el('div',null,'custom-inventory');list.id='custom-inventory';bag.append(list);
    const natal=select(bag,'本命法宝（从行囊选择）',{'':'不携带'},'natal');
    const bookSearch=input(bag,'搜索功法','book-search','',null,null),books=select(bag,'携带功法',{},'book'),addBook=el('button','加入功法');addBook.type='button';bag.append(addBook);const bookList=el('div',null,'custom-inventory');bag.append(bookList);
    const filter=(source,text,target)=>{const old=target.value;target.replaceChildren();source.filter(r=>!text||r.name.includes(text)||r.id.toLowerCase().includes(text.toLowerCase())).slice(0,150).forEach(r=>target.add(new Option(r.name,r.id)));if([...target.options].some(o=>o.value===old))target.value=old;};
    search.oninput=()=>filter(c.items,search.value.trim(),items);bookSearch.oninput=()=>filter(c.techniques,bookSearch.value.trim(),books);search.oninput();bookSearch.oninput();
    const refreshBag=()=>{list.replaceChildren();const old=natal.value;natal.replaceChildren(new Option('不携带',''));for(const row of inventory){const item=c.items.find(i=>i.id===row.id),line=el('div'),remove=el('button','移除');remove.type='button';remove.onclick=()=>{inventory.splice(inventory.indexOf(row),1);refreshBag();};line.append(el('span',`${item.name} × ${row.quantity.toLocaleString('zh-CN')}`),remove);list.append(line);if(item.natal)natal.add(new Option(item.name,item.id));}natal.value=[...natal.options].some(o=>o.value===old)?old:'';};
    add.onclick=()=>{if(!items.value||!quantity.reportValidity())return;const existing=inventory.find(r=>r.id===items.value);if(existing)existing.quantity=Math.min(1e12,existing.quantity+Number(quantity.value));else inventory.push({id:items.value,quantity:Number(quantity.value)});refreshBag();};
    const refreshBooks=()=>{bookList.replaceChildren();for(const id of manuals){const line=el('div'),remove=el('button','移除');remove.type='button';remove.onclick=()=>{manuals.splice(manuals.indexOf(id),1);refreshBooks();};line.append(el('span',c.techniques.find(t=>t.id===id).name),remove);bookList.append(line);}};
    addBook.onclick=()=>{if(books.value&&!manuals.includes(books.value)){manuals.push(books.value);refreshBooks();}};
    let machine=null;
    if(c.tianji_enabled){const section=group('巧夺天工');machine=select(section,'携带神机名次',{'0':'不携带',...Object.fromEntries(Array.from({length:c.tianji_brackets},(_,i)=>[i+1,`第 ${i*20+1}—${(i+1)*20} 名中随机一件`]))},'tianji');}
    const footer=el('div',null,'custom-start-footer'),start=el('button','以此前尘，踏入仙途');start.type='submit';start.id='custom-start-submit';footer.append(start);form.append(footer);
    const updateOrgs=()=>{for(const [kind,target] of [['sect',sect],['family',family]]){target.replaceChildren(new Option('无所属',''),new Option('自行建立','new'));c.factions.filter(f=>f.kind===kind&&f.world===world.value).forEach(f=>target.add(new Option(f.name,f.id)));}update();};
    const update=()=>{species.parentElement.hidden=path.value!=='monster';sectName.parentElement.hidden=sect.value!=='new';familyName.parentElement.hidden=family.value!=='new';const asura=c.asura_enabled&&path.value==='demonic'&&world.value==='asura';const celestial=world.value==='celestial';const supported=celestial||asura;rank.max=supported?13:9;rank.value=Math.min(Number(rank.value),Number(rank.max));warming.disabled=!supported||!tendency.value;if(!supported)warming.value=0;rank.disabled=!tendency.value;route.parentElement.hidden=!asura;domainNote.textContent=asura?'本命魔域：初成至至臻，共 13 级，支持额外温养。':celestial?'仙域：按倾向匹配本存档生成的道统，初成至至臻共 13 级；额外温养作用于稳定、侵夺与权能。':'上界本体邻域或二级界面灵域残解：1—9 级，沿用相应道途体系；无独立温养轴。';};
    realm.onchange=()=>{layer.replaceChildren();for(let i=1;i<=c.realms.find(r=>r.id===Number(realm.value)).layers;i++)layer.add(new Option(`${i} 层`,i));update();};
    path.onchange=tendency.onchange=sect.onchange=family.onchange=update;world.onchange=updateOrgs;realm.onchange();updateOrgs();
    form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity())return;const base=new FormData(document.querySelector('#new-game-form'));const payload={name:base.get('name')||'',gender:base.get('gender')||'male',spirit_root:rootSelect.value,path:path.value,monster_species_id:path.value==='monster'?species.value:null,custom_start:{world:world.value,realm_index:Number(realm.value),layer:Number(layer.value),body_training:Number(body.value),immortal_body_level:Number(higher.value),divine_sense_rank:Number(sense.value),additional_roots:[...roots.querySelectorAll('input:checked')].map(n=>n.value),inventory,techniques:manuals,natal_artifact:natal.value,sect:sect.value,sect_name:sectName.value,family:family.value,family_name:familyName.value,domain_rank:tendency.value?Number(rank.value):0,tendency:tendency.value||'strike',warming:Number(warming.value),asura_route:route.value,tianji_bracket:Number(machine?.value||0)}};if(base.get('seed'))payload.seed=Number(base.get('seed'));submit(payload);};
    document.querySelector('.quick-start').append(root);
  },setBusy(busy){document.querySelectorAll('#custom-start-form button').forEach(b=>b.disabled=busy);}};
})();
