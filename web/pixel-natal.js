/* Presentation of real natal shape and existing, unbounded slot controls. */
(() => {
  'use strict';
  function item(system){return {id:system.item_id,crafted_artifact_id:system.crafted_artifact_id};}
  function decorate(system,state){
    if(!PixelLibrary.active())return;
    const root=document.getElementById('natal-artifact-content');root.classList.add('pixel-natal-content');
    const visual=root.querySelector('.natal-artifact-visual');
    if(visual&&system.bound){const art=document.createElement('figure');art.className='pixel-natal-art';art.append(PixelLibrary.image(item(system),state,160));visual.prepend(art);}
    root.querySelectorAll('.natal-slot').forEach((button,index)=>{
      const slot=system.slots[index];if(!slot)return;
      if(slot.material_id){button.querySelector('span')?.replaceWith(PixelLibrary.image({id:slot.material_id},state));}
    });
  }
  function material(button,material,state){if(PixelLibrary.active())button.prepend(PixelLibrary.image({id:material.item_id},state));}
  window.PixelNatal=Object.freeze({decorate,material});
})();
