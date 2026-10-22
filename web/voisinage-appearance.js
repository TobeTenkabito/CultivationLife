/* Presentation-only choices; encounter colors are sampled once, not from NPC IDs. */
(() => {
  'use strict';
  const palettes=['rose','peach','gold','lime','green','jade','cyan','blue','indigo','violet','lilac','pink'];
  const defaults=Object.freeze({outline:'mist',pattern:'mist',palette:'jade',control:'rings',density:65});
  function randomIndex(length){const limit=Math.floor(4294967296/length)*length,buffer=new Uint32Array(1);do{crypto.getRandomValues(buffer);}while(buffer[0]>=limit);return buffer[0]%length;}
  function createEncounter(npcs){
    if(!Array.isArray(npcs)||npcs.length>6)throw Error('邻域展示最多六个对照对象');
    return Object.freeze(npcs.map(row=>Object.freeze({...defaults,...row,palette:palettes[randomIndex(palettes.length)]})));
  }
  window.VoisinageAppearance=Object.freeze({defaults,palettes:Object.freeze(palettes),createEncounter});
})();
