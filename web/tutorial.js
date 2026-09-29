(() => {
  const chapters=window.TutorialChapters, dialog=document.getElementById('tutorial-dialog');
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  let data=null,send=null,page=0,working=false,startEnabled=false,openedGame=null;
  try{startEnabled=localStorage.getItem('wendao-tutorial-next-life')==='true';}catch(_){}
  const bodyFor=chapter=>{const body=el('div',null,'tutorial-copy');body.append(el('p',chapter.lead,'tutorial-lead'));
    for(const [title,...paragraphs] of chapter.sections){const section=el('section');section.append(el('h3',title));paragraphs.forEach(p=>section.append(el('p',p)));body.append(section);}return body;};
  const manual=document.getElementById('tutorial-handbook');
  chapters.forEach((c,i)=>{const d=el('details');d.append(el('summary',`${i+1}. ${c.title}`),bodyFor(c));manual.append(d);});
  const status=document.getElementById('tutorial-status');
  async function act(action,step){if(working||!send)return;working=true;draw();try{await send({action,step});}finally{working=false;draw();}}
  function open(){status.textContent='';if(!dialog.open)dialog.showModal();draw();}
  function go(index){page=index;dialog.scrollTop=0;status.textContent='';if(data?.tutorial.enabled)act('navigate',index);else draw();}
  function draw(){
    const t=data?.tutorial, enabled=data?!!t?.enabled:startEnabled;
    if(!working)document.getElementById('tutorial-enabled').checked=enabled;
    document.getElementById('tutorial-enabled').disabled=working;
    document.getElementById('tutorial-toggle-description').textContent=data?'关闭会保留本角色的阅读进度与师缘；说明仍可随时查阅。':'开启后，新创建的角色会显示教程；已有角色保留各自的选择。';
    for(const b of document.querySelectorAll('[data-tutorial-open]'))b.textContent=`新手教程${data?(enabled?'：已开启':'：已关闭'):(startEnabled?'：新角色开启':'')}`;
    document.getElementById('tutorial-heading').textContent=chapters[page].title;
    document.getElementById('tutorial-progress').textContent=`${page+1} / ${chapters.length} · ${enabled?'引导中':'修行指南'}`;
    const select=document.getElementById('tutorial-chapter');select.value=String(page);select.disabled=working;
    const body=document.getElementById('tutorial-body');body.replaceChildren(bodyFor(chapters[page]));
    const c=chapters[page];
    if((c.panel||c.details)&&data){const b=el('button',c.panelLabel);b.type='button';b.className='tutorial-preview';
      b.disabled=!!c.panel&&!document.querySelector(`[data-panel-target="${c.panel}"]:not(.hidden)`);
      b.onclick=()=>{dialog.close();if(c.details){document.querySelector('#player-details-dialog').showModal();document.querySelectorAll('.compact-library').forEach(d=>d.open=true);}else window.UtilityPanels?.open(c.panel);};body.append(b,el('p','这里只打开窗口供你查看，不会自动修行、购买或推进年月。','muted'));}
    if(page===6){
      const event=el('section',null,'tutorial-mentor');event.append(el('h3','师缘事件 · 山道授业'));
      const button=(label,action,disabled=false)=>{const b=el('button',label);b.type='button';b.disabled=disabled||working;b.onclick=()=>act(action);event.append(b);};
      if(!data)event.append(el('p','创建角色并开启教程后，可在这里结下师缘。'));
      else if(t.mentor_result)event.append(el('p',t.mentor_result==='accepted'?'你已拜入沈照尘门下。这次师缘已经记入生平纪事。':'你已谢过这份师缘，可以在游历中另寻师承。'));
      else if(!enabled)event.append(el('p','开启教程后，可在这一课结下师缘。'));
      else if(t.mentor){event.append(el('p',`${t.mentor.name}停步讲道，向你递来入门的机会。执弟子礼会正式建立师徒关系；谢绝不会损及声望。`));
        if(t.blocked_reason)event.append(el('p',t.blocked_reason,'muted'));
        button('执弟子礼，拜入门下','accept_mentor',!t.can_accept);button('谢过好意，自行问道','decline_mentor');}
      else{event.append(el('p',t.blocked_reason||'这次相遇与拜师均已有定数，不消耗年月，也不收取灵石。'));
        button('开启师缘事件','offer_mentor',!t.can_offer);}
      body.append(event);
    }
    document.getElementById('tutorial-prev').disabled=working||page===0;
    document.getElementById('tutorial-next').disabled=working;
    document.getElementById('tutorial-next').textContent=page===chapters.length-1?'读完了，开始问道':'我已了解，下一课';
  }
  const select=document.getElementById('tutorial-chapter');chapters.forEach((c,i)=>{const o=el('option',`${i+1}. ${c.title}`);o.value=i;select.append(o);});
  select.onchange=()=>go(Number(select.value));
  document.getElementById('tutorial-prev').onclick=()=>go(Math.max(0,page-1));
  document.getElementById('tutorial-next').onclick=async()=>{if(page<chapters.length-1)go(page+1);else{if(data?.tutorial.enabled)await act('finish');dialog.close();}};
  document.getElementById('tutorial-close').onclick=()=>dialog.close();
  document.getElementById('tutorial-enabled').onchange=event=>{
    if(data)act(event.target.checked?'enable':'disable');
    else{startEnabled=event.target.checked;try{localStorage.setItem('wendao-tutorial-next-life',String(startEnabled));}catch(_){}draw();}
  };
  document.querySelectorAll('[data-tutorial-open]').forEach(b=>b.onclick=open);
  document.getElementById('setting-tutorial-open').onclick=open;
  window.TutorialGuide={
    enabledForNewGame:()=>startEnabled,
    reset(){data=null;send=null;page=0;openedGame=null;dialog.close();draw();},
    render(value,callback){const changed=data?.id!==value.id;data=value;send=callback;
      if(changed||data.tutorial.enabled)page=Math.max(0,Math.min(chapters.length-1,data.tutorial.step||0));draw();
      if(changed&&data.tutorial.enabled&&openedGame!==data.id){openedGame=data.id;open();}
    },open
  };
  draw();
})();
