/* Theme-native landscape plates: decorative SVG, never a second gameplay map. */
window.HeavensAtlas = (() => {
  const motifs={human:['烽','山川故道'],spirit:['雷','长虹渡霆'],demon:['契','赤髓余烬'],true_demon:['日','黑日沉渊'],monster_realm:['山','万兽归径'],phantom_underworld:['梦','月下重影'],hell:['灯','忘川引魂'],celestial:['阙','玉京云阙'],asura:['旗','无生战痕'],nether:['根','太初幽脉'],reincarnation:['渡','彼岸因果']};
  const stages={unseen:'待求证',surveying:'求证中',surveyed:'待赴现场',treated:'待复核',closed:'已留录'};
  const landmarks={
    human:'M206 185v-37h32v37m-44-36 28-17 28 17m-51 0h46m-37-17 14-15 14 15m-14-15v-12',
    spirit:'m246 82-28 43h25l-29 49m69-78-16 25h16l-19 30',
    demon:'M207 185v-40h38v40m-45-39 26-24 26 24m-29 29 7-19 7 19m-34 17h61',
    true_demon:'M206 192q30-35 65 0m-53-8 12-25 8 17 9-32 13 40',
    monster_realm:'m169 192 27-40 15 16 26-55 34 56 13-19 30 42m-90-18 13-21 15 30',
    phantom_underworld:'M221 104a29 29 0 1 0 29 29 22 22 0 0 1-29-29M189 183q36-22 73 0m-59 9q28-15 56 0',
    hell:'M225 186v-65m-16 16h32l-5 26h-22Zm-10-4 21-12 21 12m-21 26v13m-32 23q31-10 65 0',
    celestial:'M190 176v-32h28v32m-37-32 23-18 23 18m4 32v-50h30v50m-40-50 25-20 25 20m-93 63q47-17 95 0',
    asura:'M223 190V92m1 4 43 12-43 21m-24 66 43-11m-30-42-14 48m45-45 17 41',
    nether:'M226 105v43m-32-29 32 29 34-41m-34 41-5 21-29 18m29-18 12 31m-6-47 19 21 27 8m-68-13-29 5',
    reincarnation:'M172 189q62-79 125 0m-114 0q51-59 103 0m-102-16v-21m103 22v-22m-110 17q58-66 116 0',
  };
  function plate(world,node){
    const wrap=node('div',null,'heavens-landscape');wrap.dataset.world=world;wrap.setAttribute('aria-hidden','true');
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 480 240');svg.setAttribute('focusable','false');
    const shape=(tag,attrs)=>{const s=document.createElementNS(svg.namespaceURI,tag);for(const [k,v] of Object.entries(attrs))s.setAttribute(k,v);svg.append(s);};
    shape('circle',{cx:352,cy:72,r:42,class:'atlas-halo'});
    shape('circle',{cx:352,cy:72,r:52,class:'atlas-orbit'});
    shape('path',{d:'M0 171 63 124 102 152 183 61 252 133 293 111 370 162 421 115 480 154V240H0Z',class:'atlas-far'});
    shape('path',{d:'m0 205 95-54 60 30 103-76 82 72 62-30 78 44v49H0Z',class:'atlas-near'});
    shape('path',{d:'M0 218Q95 172 210 214T480 212M0 232Q170 198 284 227T480 223',class:'atlas-water'});
    shape('path',{d:'M51 71h103m-73 8h90m169 75h118m-75 8h100',class:'atlas-cloud'});
    shape('path',{d:landmarks[world]||landmarks.human,class:'atlas-pavilion'});
    wrap.append(svg,node('span',(motifs[world]||motifs.human)[0],'heavens-world-seal'));
    return wrap;
  }
  function feature(row,node,onOpen){
    const article=node('article',null,'heavens-feature');article.dataset.world=row.world;
    const copy=node('div',null,'heavens-feature-copy');
    copy.append(node('small',`${row.world_name} · ${(motifs[row.world]||motifs.human)[1]}`),node('h3',row.name,'heavens-title'),node('p',row.glimpse));
    const foot=node('div',null,'heavens-feature-footer');foot.append(node('span',stages[row.stage],'heavens-badge'));
    if(onOpen){const b=node('button','查阅本界事务 ›');b.type='button';b.onclick=onOpen;foot.append(b);}
    else foot.append(node('small',row.current?'足迹所在':'诸界远览 · 亲临后办理'));
    copy.append(foot);article.append(copy,plate(row.world,node));return article;
  }
  function docket(host,row,node){
    const header=node('header',null,'heavens-dossier-heading');header.dataset.world=row.world;
    const stamp=node('span',(motifs[row.world]||motifs.human)[0],'heavens-dossier-seal');stamp.setAttribute('aria-hidden','true');
    const copy=node('div');const h=node('h3',row.name,'heavens-title');h.tabIndex=-1;
    copy.append(node('small',`${row.world_name} / ${({anomaly:'异象档案',conflict:'战地档案'})[row.category]||'地方行录'}`),h);header.append(stamp,copy,node('span',stages[row.stage],'heavens-badge'));host.append(header);
  }
  return {feature,docket,plate};
})();
