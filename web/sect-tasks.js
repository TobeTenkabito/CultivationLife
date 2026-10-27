(() => {
  const node=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const num=n=>Number(n||0).toLocaleString('zh-CN');
  let selected='tasks';
  window.SectTasks={render(root,d,submit){
    if(!d)return;
    const section=node('section',null,'sect-board');section.id='sect-task-board';
    const head=node('header');head.append(node('small','执事堂 · 宗门事务'),node('h3','宗门任务栏'));
    const stats=node('div',null,'sect-board-stats');
    for(const [label,value] of [['我的贡献',num(d.contribution)],['宗门影响力',num(d.influence)],['府库灵石',num(d.treasury)],['门内不满',Number(d.unrest).toFixed(0)+'/100']]){
      const card=node('div');card.append(node('small',label),node('strong',value));stats.append(card);
    }
    section.append(head,stats);
    if(d.blocked)section.append(node('p',d.blocked,'sect-board-warning'));
    if(!d.local)section.append(node('p','府库与治理请亲赴山门办理；战争动员须先沿地图抵达对应战场。','muted'));
    const tabs=node('nav',null,'sect-board-tabs'),body=node('div',null,'sect-board-body');
    const send=(action,p={})=>submit({action,owner_id:d.owner_id,revision:d.revision,...p});
    const btn=(text,action,p={},disabled=false)=>{const b=node('button',text);b.type='button';b.dataset.sectAction=action;b.disabled=!!d.blocked||disabled||(!d.local&&action!=='complete');b.onclick=()=>send(action,p);return b;};
    const select=(label,options)=>{const n=node('select');n.setAttribute('aria-label',label);for(const r of options){const o=node('option',r.name);o.value=r.id;n.append(o);}return n;};
    const amount=(label,value,max)=>{const n=node('input');n.type='number';n.min='1';n.max=String(max);n.value=String(value);n.setAttribute('aria-label',label);return n;};
    const form=(...children)=>{const n=node('div',null,'sect-board-form');n.append(...children);return n;};
    const draw=()=>{
      body.replaceChildren();tabs.querySelectorAll('button').forEach(b=>{b.classList.toggle('selected',b.dataset.tab===selected);b.setAttribute('aria-selected',String(b.dataset.tab===selected));});
      if(selected==='tasks'){
        body.append(node('p','每行动单位可完成1项、发布3项任务。NPC每单位最多完成3项；发布者不能完成自己的任务。影响力由年度履职、完成任务及捐献获得。','muted'));
        if(!d.tasks.length)body.append(node('p','暂无任务。年度结算后，达到发布境界的门人会在此发布委托；你也可以消耗影响力发布。','sect-board-empty'));
        const list=node('div',null,'sect-task-list');
        for(const t of [...d.tasks].reverse()){
          const card=node('article',null,'sect-task');card.append(node('b',t.title),node('small',`发起者 ${t.issuer_name} · 完成者 ${t.completer_name||'待领取'}`));
          card.append(node('p',`${num(t.reward)} 贡献 · ${{open:'待完成',completed:'已完成',failed:'未完成',cancelled:'已失效'}[t.status]}`));
          if(t.kind==='mobilize')card.append(node('small',t.issuer==='player'?'门人完成后，下一场会战战力加成2%，最多10%，使用一次。':'亲自迎战敌宗修士，修为差在三个小境界内；胜利获得贡献。'));
          if(t.kind==='mobilize'&&t.issuer!=='player')card.append(node('small',`战场：${t.battle_location_name}。请沿地图抵达后出战；战败有陨落风险。`));
          if(t.status==='open'&&t.issuer!=='player')card.append(btn(t.kind==='mobilize'?'出战':'交付材料','complete',{task_id:t.id},!t.available));
          if(t.status==='open'&&t.issuer==='player')card.append(btn('撤销任务','cancel',{task_id:t.id}));
          list.append(card);
        }body.append(list);
      }else if(selected==='publish'){
        body.append(node('p',`最低发布境界：${d.realms[d.minimum_realm].name}。每人最多3项待办，仅征集普通材料。每项消耗10＋数量点影响力。`));
        const goods=select('征集材料',d.materials.map(r=>({id:r.key,name:r.name}))),qty=amount('征集数量',1,100);
        const post=btn('发布材料任务','publish',{},!d.can_publish||!d.materials.length);
        post.onclick=()=>send('publish',{kind:'material',item:goods.value,quantity:Number(qty.value)});
        body.append(form(goods,qty,post));
        if(d.wars.length){const wars=select('动员战役',d.wars);const b=btn('发布战争动员 · 11影响力','publish',{},!d.can_publish);b.onclick=()=>send('publish',{kind:'mobilize',war_id:wars.value});body.append(form(wars,b));}
      }else if(selected==='treasury'){
        body.append(node('p',`本行动单位剩余额度 ${num(Math.max(0,d.limit-d.used))} / ${num(d.limit)} 灵石折值。每1贡献兑换10灵石。额度未使用时也可单领一件高价实物，本单位不再领取；与原府库申领共用额度。`));
        const qty=amount('兑换灵石数量',10,10000),cash=btn('兑换灵石','redeem');cash.onclick=()=>send('redeem',{item:'spirit_stone',quantity:Number(qty.value)});body.append(form(qty,cash));
        const list=node('div',null,'sect-task-list');
        for(const r of d.stock){const card=node('article',null,'sect-task');card.append(node('b',r.name),node('small',`库存 ${num(r.quantity)} · 单件 ${num(r.cost)}贡献`),btn('兑换一件','redeem',{item:r.key,quantity:1},d.contribution<r.cost||(d.used>0&&d.limit-d.used<r.value)));list.append(card);}body.append(list);
        const gift=amount('捐献灵石数量',100,1000000000),b=btn('捐献府库','donate');b.onclick=()=>send('donate',{amount:Number(gift.value)});
        body.append(node('h4','捐献'),node('p','每100灵石获得5贡献与1点影响力；捐献入原府库。'),form(gift,b));
      }else if(selected==='finance'){
        body.append(node('p',`本年你的最低薪俸 ${num(d.minimum_salary)} 灵石。按境界从高到低发放；全员最低薪俸与养护储备充足时额外加发。`));
        body.append(node('p',d.salary_year==null?'尚未进行年度薪俸结算':`最近结算：${d.salary_year}岁 · 未付最低薪俸 ${num(d.arrears)} 灵石`,d.arrears?'sect-board-warning':''));
        const list=node('div',null,'sect-salary-list');for(const r of d.salaries){const card=node('div');card.append(node('b',r.name),node('span',`${d.realms[r.realm].name} · 实领 ${num(r.paid)} / 最低 ${num(r.minimum)}`));list.append(card);}body.append(list);
        body.append(node('p','本次新增结算仅在你仍属本宗且身处同界时运行；退出或离界后停止，不追补离开期间薪俸与任务。','muted'));
      }else if(selected==='governance'){
        body.append(node('p',`当前${d.recruitment_open?'正常招新':'暂停招新'} · 已罢免止怨 ${d.dismissals} 次`));
        if(d.permissions.policy){const ranks=select('最低任务发布境界',d.realms);ranks.value=String(d.minimum_realm);const b=btn('设置发布境界','minimum');b.onclick=()=>send('minimum',{realm:Number(ranks.value)});body.append(form(ranks,b));}
        if(d.permissions.recruit)body.append(btn(d.recruitment_open?'暂停招新':'恢复招新','recruitment',{enabled:!d.recruitment_open}));
        if(d.permissions.dismiss){body.append(node('p','欠薪且不满达到20时可罢免掌门：不满−25，每年限一次；此后每次欠薪额外＋2不满，累积叠加。'));
          const next=select('继任掌门',d.successors),b=btn('罢免掌门并任命继任者','dismiss',{},!d.can_dismiss||!d.successors.length);b.onclick=()=>send('dismiss',{successor:next.value});body.append(form(next,b));}
        if(d.permissions.expel){const who=select('开除弟子',d.members.filter(r=>r.id!=='player'&&r.id!==d.leader)),b=btn('开除弟子 · 不满＋5','expel',{},!who.options.length);b.onclick=()=>send('expel',{npc_id:who.value});body.append(form(who,b));}
        if(!Object.values(d.permissions).some(Boolean))body.append(node('p','当前没有宗门治理权限。'));
      }else{
        for(const r of [...d.history].reverse())body.append(node('p',`${r.year}岁 · ${r.text}`));
      }
    };
    for(const [key,label] of [['tasks','任务'],['publish','发布'],['treasury','兑换与捐献'],['finance','薪俸'],['governance','治理'],['history','记录']]){const b=node('button',label);b.type='button';b.dataset.tab=key;b.onclick=()=>{selected=key;draw();};tabs.append(b);}
    section.append(tabs,body);root.append(section);draw();
  }};
})();
