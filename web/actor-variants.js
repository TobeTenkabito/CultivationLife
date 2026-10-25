/* Derivative pixels only: never change source atlases, identities or combat rules. */
(() => {
  'use strict';
  const styles=Object.freeze({
    heart_demon:{color:'#c65073',opacity:.68,halo:'#e07d9c',label:'心魔'},
    heavenly_demon:{color:'#63519c',opacity:.76,halo:'#af92e3',label:'天魔'},
    corpse_self:{color:'#61b9c2',opacity:.54,halo:'#97e4e0',label:'自我尸'},
    corpse_primal:{color:'#b24d3a',opacity:.66,halo:'#efa477',label:'本我尸'},
    corpse_superego:{color:'#d4c181',opacity:.58,halo:'#f1e5b0',label:'超我尸'},
  });
  function create(){
    const layer=document.createElement('canvas'),c=layer.getContext('2d');
    function draw(target,render,variant,time=0){
      const style=styles[variant];if(!style){render(target);return;}
      const w=target.canvas.width,h=target.canvas.height;
      if(layer.width!==w||layer.height!==h){layer.width=w;layer.height=h;}
      c.clearRect(0,0,w,h);c.imageSmoothingEnabled=false;render(c);
      c.save();c.globalCompositeOperation='source-atop';c.globalAlpha=style.opacity;c.fillStyle=style.color;c.fillRect(0,0,w,h);c.restore();
      target.save();target.globalAlpha=.17;target.drawImage(layer,-3,0);target.drawImage(layer,3,0);target.globalAlpha=.92;target.drawImage(layer,0,0);target.restore();
      c.save();c.globalCompositeOperation='source-atop';c.fillStyle=style.halo;c.globalAlpha=.27;
      for(let y=(Math.floor(time*10)%20);y<h;y+=20)c.fillRect(0,y,w,2);
      c.restore();target.save();target.globalAlpha=.32;target.drawImage(layer,0,0);target.restore();
    }
    return {draw,dispose(){layer.width=layer.height=0;}};
  }
  window.ActorVariants=Object.freeze({styles,valid:id=>Object.prototype.hasOwnProperty.call(styles,id),create});
})();
