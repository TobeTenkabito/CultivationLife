/* Original three-headed, six-armed Asura diagram; all 27 nodes use live vein state. */
(() => {
  function render(v) {
    const node=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,value] of Object.entries(attrs))n.setAttribute(k,value);if(text)n.textContent=text;return n;};
    const figure=document.createElement('figure');figure.className='asura-meridian-figure';
    const svg=node('svg',{viewBox:'0 0 480 600',role:'img','aria-label':`三头六臂魔身经络图：已贯通 ${v.opened}/27 条魔脉`});
    svg.append(node('title',{},'三首六臂 · 二十七魔脉'));
    // A flame aureole surrounds the independent silhouette, armor and six hands.
    svg.append(node('path',{class:'asura-aureole',d:'M240 18 Q264 55 291 38 Q290 72 331 64 Q320 100 366 100 Q350 133 399 145 Q376 173 426 200 Q397 218 445 258 Q414 268 453 306 Q412 321 435 363 Q399 366 411 414 Q375 408 375 457 Q336 440 327 487 Q292 461 270 501 L240 535 L210 501 Q188 461 153 487 Q144 440 105 457 Q105 408 69 414 Q81 366 45 363 Q68 321 27 306 Q66 268 35 258 Q83 218 54 200 Q104 173 81 145 Q130 133 114 100 Q160 100 149 64 Q190 72 189 38 Q216 55 240 18Z'}));
    const armPaths=[
      'M193 174 Q160 144 134 127 L105 83 L92 67 L80 71 L80 92 L103 110 L112 157 L171 207Z',
      'M178 207 L123 206 L84 190 L68 173 L50 177 L52 198 L72 207 L120 242 L175 239Z',
      'M180 243 Q143 258 118 291 L87 312 L71 313 L64 328 L76 340 L95 335 L139 314 L191 280Z'
    ];
    for(const flip of [false,true])for(const d of armPaths)svg.append(node('path',{class:'asura-anatomy asura-arm',d,transform:flip?'translate(480 0) scale(-1 1)':''}));
    svg.append(node('path',{class:'asura-anatomy',d:'M212 158 Q187 158 174 193 L181 251 L200 310 L194 355 L173 473 L171 535 L145 553 L147 569 L206 569 L217 536 L240 404 L263 536 L274 569 L333 569 L335 553 L309 535 L307 473 L286 355 L280 310 L299 251 L306 193 Q293 158 268 158Z'}));
    // Three separate crowned faces, each with fierce brow and tusks.
    for(const [x,y,scale] of [[193,130,.84],[287,130,.84],[240,110,1]]){
      const face=node('g',{class:'asura-head',transform:`translate(${x} ${y}) scale(${scale})`});
      face.append(node('path',{class:'asura-anatomy',d:'M-26 -24 L-34 -44 L-14 -36 L0 -61 L14 -36 L34 -44 L26 -24 Q40 -3 26 21 L0 40 L-26 21 Q-40 -3 -26 -24Z'}));
      face.append(node('path',{class:'asura-engraving',d:'M-25 -9 L-7 -3 M7 -3 L25 -9 M-23 -1 L-10 3 M10 3 L23 -1 M0 -10 L-4 12 L4 12 M-18 18 Q0 28 18 18 M-15 19 L-13 10 L-6 23 M15 19 L13 10 L6 23 M-20 -27 L0 -35 L20 -27'}));
      svg.append(face);
    }
    for(const d of ['M185 192 L211 207 L240 182 L269 207 L295 192 M188 223 L217 243 L240 221 L263 243 L292 223','M196 267 L222 282 L240 260 L258 282 L284 267 M199 307 Q240 322 281 307','M198 328 L240 341 L282 328 L303 392 L270 377 L240 408 L210 377 L177 392Z','M185 452 L216 461 M264 461 L295 452 M177 501 L210 510 M270 510 L303 501','M115 134 L132 124 M104 215 L96 229 M113 297 L125 311 M365 134 L348 124 M376 215 L384 229 M367 297 L355 311'])svg.append(node('path',{class:'asura-engraving',d}));
    const center=[[240,169],[240,209],[240,249],[240,289],[240,329],[240,369],[240,409],[240,449],[240,489]];
    const left=[[121,145],[157,180],[90,208],[148,223],[105,316],[162,281],[204,396],[197,456],[187,525]];
    const right=left.map(([x,y])=>[480-x,y]);
    for(const points of [center,...[left,right].flatMap(a=>[a.slice(0,2),a.slice(2,4),a.slice(4,6),a.slice(6)])])svg.append(node('polyline',{class:'asura-channel',points:points.map(p=>p.join(',')).join(' ')}));
    for(let i=0;i<9;i++)for(let side=0;side<3;side++){
      const index=i*3+side+1,[x,y]=[center,left,right][side][i];
      const state=v.nodes.find(n=>n.index===index)?.status||'locked';
      const label=`第 ${index} 条魔脉 · ${{open:'已贯通',next:'下一脉',locked:'未贯通'}[state]}`;
      const g=node('g',{class:'asura-vein-node','data-state':state,'data-vein':index,'aria-label':label});
      g.append(node('title',{},label),node('circle',{cx:x,cy:y,r:13}),node('text',{x,y:y+4,'text-anchor':'middle'},String(index)));svg.append(g);
    }
    const caption=document.createElement('figcaption');caption.textContent='三首六臂 · 魔身经络示意（各本命共用）\n实心为已贯通，重环为下一脉，空心为未贯通；每层三脉，贯通后手动冲关。';
    figure.append(svg,caption);return figure;
  }
  window.AsuraMeridians={render};
})();
