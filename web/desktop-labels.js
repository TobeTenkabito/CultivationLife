/* The original buttons stay authoritative; this is a mouse/keyboard label only. */
(() => {
  const tip=document.createElement('div');tip.id='desktop-dock-tooltip';tip.className='desktop-dock-tooltip';tip.role='tooltip';tip.hidden=true;document.body.append(tip);
  let active=null;
  document.querySelectorAll('.strategy-dock button').forEach(b=>{const name=b.querySelector('small')?.textContent;if(name&&!b.hasAttribute('aria-label'))b.setAttribute('aria-label',name);});
  const hide=()=>{tip.hidden=true;if(active)active.removeAttribute('aria-describedby');active=null;};
  function show(button){
    if(!button||document.documentElement.dataset.compactDocks!=='true'||document.body.classList.contains('navigation-compact'))return hide();
    const text=button.querySelector('small')?.textContent;if(!text)return;
    if(active!==button)hide();
    active=button;tip.textContent=text;tip.hidden=false;button.setAttribute('aria-describedby',tip.id);
    const r=button.getBoundingClientRect(),w=tip.offsetWidth,h=tip.offsetHeight;
    tip.style.left=Math.max(4,Math.min(innerWidth-w-4,r.left<innerWidth/2?r.right+12:r.left-w-12))+'px';
    tip.style.top=Math.max(4,Math.min(innerHeight-h-4,r.top+(r.height-h)/2))+'px';
  }
  const target=e=>e.target.closest('.strategy-dock[data-desktop-dock] button');
  document.addEventListener('mouseover',e=>show(target(e)));
  document.addEventListener('focusin',e=>show(target(e)));
  document.addEventListener('mouseout',e=>{if(active&&!active.contains(e.relatedTarget))hide();});
  document.addEventListener('focusout',hide);document.addEventListener('click',hide);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});
  window.addEventListener('resize',hide);window.addEventListener('scroll',hide,true);window.addEventListener('game:theme-change',hide);
})();
