/* Static art only: local SVG images, bounded cache, no game clocks or RNG. */
(() => {
'use strict';
const pending=new Map(),failed=new Set();
function get(world){return failed.has(world)?null:window.MapArtworkData?.[world]||null;}
function ready(world){
 const art=get(world);if(!art)return Promise.resolve(false);
 if(pending.has(world))return pending.get(world);
 const promise=new Promise(resolve=>{const img=new Image();img.onload=()=>resolve(true);img.onerror=()=>{failed.add(world);resolve(false);};img.src=art.url;});
 pending.set(world,promise);return promise;
}
function paint(world,view,project){
 const art=get(world);if(!art)return '';
 const origin=project(0,0,-15),u=project(1,0,-15),v=project(0,1,-15),matrix=[u.x-origin.x,u.y-origin.y,v.x-origin.x,v.y-origin.y,origin.x,origin.y];
 // The wall follows this world's authored coast, not a shared ellipse.
 let html='<g data-world-artwork="'+world+'" aria-hidden="true" pointer-events="none">';
 const faces=[];
 for(const ring of art.outlines||[art.outline]){
 for(let i=0;i<ring.length;i++){const a=ring[i],b=ring[(i+1)%ring.length],topA=project(...a,-15),topB=project(...b,-15),bottomA=project(a[0]*.96,a[1]*.96,-125),bottomB=project(b[0]*.96,b[1]*.96,-125);faces.push({depth:(topA.depth+topB.depth)/2,points:[topA,topB,bottomB,bottomA].map(p=>p.x.toFixed(2)+','+p.y.toFixed(2)).join(' '),tone:i%3});}
 }
 faces.sort((a,b)=>a.depth-b.depth);
 for(const f of faces)html+='<polygon points="'+f.points+'" fill="'+art.cliff+'" opacity="'+(.62+f.tone*.13)+'"/>';
 html+='<image class="scene-authored-landscape" href="'+art.url+'" x="'+art.x+'" y="'+art.y+'" width="'+art.width+'" height="'+art.height+'" transform="matrix('+matrix.join(' ')+')" preserveAspectRatio="none"/>';
 return html+'</g>';
}
window.MapArtwork={get,ready,paint};
})();
