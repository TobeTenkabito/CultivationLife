/* View controls only. No gameplay state or time is read or written. */
(() => {
'use strict';
function frame(viewport){const box=viewport.getBoundingClientRect();return {box,width:1600,height:1600*Math.max(1,box.height)/Math.max(1,box.width)};}
function mount(viewport,drawing,camera,options){
 const pointers=new Map();let gesture=null,skipClick=false,tappedId=null,disposed=false;
 const point=e=>({x:e.clientX,y:e.clientY});
 function capture(id){try{drawing.setPointerCapture(id);}catch(_){}}
 function clear(){gesture=null;pointers.clear();drawing.classList.remove('dragging');}
 function start(){
  const list=[...pointers.values()];
  if(!list.length){gesture=null;drawing.classList.remove('dragging');return;}
  const box=viewport.getBoundingClientRect();
  if(list.length>=2){const a=list[0].p,b=list[1].p;gesture={mode:'multi',center:{x:(a.x+b.x)/2,y:(a.y+b.y)/2},distance:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),angle:Math.atan2(b.y-a.y,b.x-a.x)};skipClick=true;tappedId=null;for(const id of pointers.keys())capture(id);}
  else{const a=list[0];gesture={mode:a.touch||a.button===1||!options.rotate?'pan':'rotate',last:a.p,origin:a.p,rotation:MapCamera.start(camera,a.p,box),moved:skipClick};}
 }
 function down(e){
  if(disposed||(!['touch','pen'].includes(e.pointerType)&&![0,1].includes(e.button)))return;
  if(!pointers.size){skipClick=false;tappedId=e.target.closest('[data-atlas-location]')?.dataset.atlasLocation||null;}
  if(e.button===1)e.preventDefault();
  pointers.set(e.pointerId,{p:point(e),touch:['touch','pen'].includes(e.pointerType),button:e.button});start();
 }
 function move(e){
  const p=pointers.get(e.pointerId);if(!p||!gesture)return;
  p.p=point(e);const box=viewport.getBoundingClientRect();
  if(gesture.mode==='multi'){
   const list=[...pointers.values()],a=list[0].p,b=list[1].p,center={x:(a.x+b.x)/2,y:(a.y+b.y)/2},distance=Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),angle=Math.atan2(b.y-a.y,b.x-a.x);
   if(options.rotate){MapCamera.drag(camera,MapCamera.start(camera,gesture.center,box),center);MapCamera.twist(camera,Math.atan2(Math.sin(angle-gesture.angle),Math.cos(angle-gesture.angle)));}
   else MapCamera.pan(camera,center.x-gesture.center.x,center.y-gesture.center.y,box);
   MapCamera.zoomAt(camera,camera.zoom*distance/gesture.distance,center,box);
   gesture={mode:'multi',center,distance,angle};
  }else{
   if(!gesture.moved&&Math.hypot(p.p.x-gesture.origin.x,p.p.y-gesture.origin.y)<=5)return;
   gesture.moved=true;capture(e.pointerId);
   if(gesture.mode==='pan')MapCamera.pan(camera,p.p.x-gesture.last.x,p.p.y-gesture.last.y,box);
   else MapCamera.drag(camera,gesture.rotation,p.p);
   gesture.last=p.p;
  }
  e.preventDefault();skipClick=true;tappedId=null;drawing.classList.add('dragging');options.changed();
 }
 function end(e){if(!pointers.has(e.pointerId))return;pointers.delete(e.pointerId);if(e.type!=='pointerup'){skipClick=true;tappedId=null;}start();}
 function lost(e){if(e.target===drawing&&!drawing.hasPointerCapture(e.pointerId))end(e);}
 function click(e){
  if(skipClick){skipClick=false;tappedId=null;e.preventDefault();e.stopImmediatePropagation();return;}
  const id=e.target.closest('[data-atlas-location]')?.dataset.atlasLocation||tappedId;tappedId=null;
  if(id&&options.onSelect){e.preventDefault();e.stopImmediatePropagation();options.onSelect(id);}
 }
 function wheel(e){
  e.preventDefault();const unit=e.deltaMode===1?16:e.deltaMode===2?viewport.clientHeight:1;
  MapCamera.zoomAt(camera,camera.zoom*Math.exp(-Math.max(-400,Math.min(400,e.deltaY*unit))*.0015),point(e),viewport.getBoundingClientRect());options.changed();
 }
 const aux=e=>{if(e.button===1)e.preventDefault();};
 drawing.addEventListener('pointerdown',down);drawing.addEventListener('pointermove',move);drawing.addEventListener('click',click,true);drawing.addEventListener('auxclick',aux);drawing.addEventListener('wheel',wheel,{passive:false});
 window.addEventListener('pointerup',end,true);window.addEventListener('pointercancel',end,true);drawing.addEventListener('lostpointercapture',lost);
 const observer=new ResizeObserver(()=>{if(!disposed)options.changed();});observer.observe(viewport);
 return {pause:clear,dispose:()=>{disposed=true;observer.disconnect();clear();drawing.removeEventListener('pointerdown',down);drawing.removeEventListener('pointermove',move);drawing.removeEventListener('click',click,true);drawing.removeEventListener('auxclick',aux);drawing.removeEventListener('wheel',wheel);window.removeEventListener('pointerup',end,true);window.removeEventListener('pointercancel',end,true);drawing.removeEventListener('lostpointercapture',lost);}};
}
function plane(viewport,drawing,camera){
 const layer=document.createElementNS('http://www.w3.org/2000/svg','g');layer.classList.add('atlas-flat-layer');layer.append(...drawing.childNodes);drawing.append(layer);
 let disposed=false,queued=0;
 function paint(){if(disposed)return;const f=frame(viewport),scale=Math.min(f.width*.88/1000,f.height*.84/710)*camera.zoom;drawing.setAttribute('viewBox','0 0 '+f.width+' '+f.height);layer.setAttribute('transform','translate('+(800+(camera.panX||0))+' '+(f.height/2+(camera.panY||0))+') scale('+scale+') translate(-500 -355)');drawing.dataset.panX=camera.panX||0;drawing.dataset.panY=camera.panY||0;drawing.dataset.zoom=camera.zoom;}
 function schedule(){if(disposed||queued||viewport.closest('.hidden'))return;queued=requestAnimationFrame(()=>{queued=0;paint();});}
 const input=mount(viewport,drawing,camera,{changed:schedule});paint();
 return {pause:()=>{input.pause();if(queued)cancelAnimationFrame(queued);queued=0;},dispose:()=>{disposed=true;input.dispose();if(queued)cancelAnimationFrame(queued);},reset:()=>{MapCamera.reset(camera);paint();}};
}
window.MapInput={mount,frame,plane};
})();
