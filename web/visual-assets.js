/* Local, bounded bitmap cache. This layer has no gameplay or random-number ports. */
(() => {
  'use strict';
  const catalog = window.PixelAssetCatalog || {assets:{}, frames:[], base:'/assets/pixel/v1/'}, cache = new Map();
  function load(id) {
    const entry = Object.prototype.hasOwnProperty.call(catalog.assets, id) ? catalog.assets[id] : null;
    if (!entry) return Promise.resolve(null);
    if (!cache.has(id)) cache.set(id, new Promise(resolve => {
      const bitmap = new Image();
      bitmap.onload = () => resolve(bitmap.naturalWidth === entry.size[0] && bitmap.naturalHeight === entry.size[1] ? bitmap : null);
      bitmap.onerror = () => resolve(null);
      bitmap.src = catalog.base + entry.file;
    }));
    return cache.get(id);
  }
  function actor(player) {
    if (!player || player.race !== 'human' || !['dao', 'demonic'].includes(player.path) || player.ghost_host_body ||
        player.ghost_attachment || (player.lineage_race && player.lineage_race !== 'human') ||
        player.transformation_loadouts?.[player.transformation_technique?.id]?.active?.length ||
        !['male', 'female'].includes(player.gender)) return null;
    return `actor.human.${player.path}.${player.gender}`;
  }
  function frame(context, bitmap, name) {
    const i = catalog.frames.indexOf(name);
    context.clearRect(0, 0, 96, 96);
    if (!bitmap || i < 0) return;
    context.imageSmoothingEnabled = false;
    context.drawImage(bitmap, i % 4 * 96, Math.floor(i / 4) * 96, 96, 96, 0, 0, 96, 96);
  }
  // Unmodified Lucide 0.468.0 icon nodes; see assets/pixel/LUCIDE-LICENSE.
  const icons = {
    replay: [['path',{d:'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8'}],['path',{d:'M3 3v5h5'}]],
    pause: [['rect',{x:'14',y:'4',width:'4',height:'16',rx:'1'}],['rect',{x:'6',y:'4',width:'4',height:'16',rx:'1'}]],
    play: [['polygon',{points:'6 3 20 12 6 21 6 3'}]],
    panel: [['rect',{width:'18',height:'18',x:'3',y:'3',rx:'2'}],['path',{d:'M9 3v18'}],['path',{d:'m14 9 3 3-3 3'}]],
    close: [['path',{d:'M18 6 6 18'}],['path',{d:'m6 6 12 12'}]],
    plus: [['path',{d:'M5 12h14'}],['path',{d:'M12 5v14'}]],
    minus: [['path',{d:'M5 12h14'}]],
    locate: [['line',{x1:'2',x2:'5',y1:'12',y2:'12'}],['line',{x1:'19',x2:'22',y1:'12',y2:'12'}],['line',{x1:'12',x2:'12',y1:'2',y2:'5'}],['line',{x1:'12',x2:'12',y1:'19',y2:'22'}],['circle',{cx:'12',cy:'12',r:'7'}]],
  };
  function icon(name) {
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    for (const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'2','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'})) svg.setAttribute(key,value);
    for (const [tag,attributes] of icons[name] || []) {
      const node = document.createElementNS(ns,tag);
      for (const [key,value] of Object.entries(attributes)) node.setAttribute(key,value);
      svg.append(node);
    }
    return svg;
  }
  window.VisualAssets = Object.freeze({load, actor, frame, icon});
})();
