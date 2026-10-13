/* Free virtual trackball. Orientation has no yaw/pitch limits. */
(() => {
'use strict';
const multiply=(a,b)=>Array.from({length:9},(_,i)=>{const row=Math.floor(i/3),col=i%3;return a[row*3]*b[col]+a[row*3+1]*b[3+col]+a[row*3+2]*b[6+col];});
function initial(yaw=-.2,pitch=.64){const c=Math.cos(yaw),s=Math.sin(yaw),a=Math.sin(pitch),b=Math.cos(pitch);return [c,-s,0,s*a,c*a,-b,s*b,c*b,a];}
function matrix(camera){if(!Array.isArray(camera.orientation)||camera.orientation.length!==9||!camera.orientation.every(Number.isFinite))camera.orientation=initial(camera.yaw,camera.pitch);return camera.orientation;}
function vector(p,box){const size=Math.max(1,Math.min(box.width,box.height)),x=(2*(p.x-box.left)-box.width)/size,y=(2*(p.y-box.top)-box.height)/size,d=Math.hypot(x,y),z=d<Math.SQRT1_2?Math.sqrt(1-d*d):.5/Math.max(d,.001),n=Math.hypot(x,y,z);return [x/n,y/n,z/n];}
function fromTo(a,b){
 const x=a[1]*b[2]-a[2]*b[1],y=a[2]*b[0]-a[0]*b[2],z=a[0]*b[1]-a[1]*b[0],w=1+a[0]*b[0]+a[1]*b[1]+a[2]*b[2],n=Math.hypot(x,y,z,w);
 if(n<1e-8){const t=Math.abs(a[0])<.8?[1,0,0]:[0,1,0];return fromAxis([a[1]*t[2]-a[2]*t[1],a[2]*t[0]-a[0]*t[2],a[0]*t[1]-a[1]*t[0]],Math.PI);}
 return quaternion(x/n,y/n,z/n,w/n);
}
function quaternion(x,y,z,w){return [1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w),2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w),2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)];}
function fromAxis(axis,angle){const n=Math.hypot(...axis),s=Math.sin(angle/2)/n;return quaternion(axis[0]*s,axis[1]*s,axis[2]*s,Math.cos(angle/2));}
function start(camera,p,box){return {orientation:[...matrix(camera)],ball:vector(p,box),point:p,box,yaw:camera.yaw,pitch:camera.pitch};}
function drag(camera,gesture,p){camera.orientation=multiply(fromTo(gesture.ball,vector(p,gesture.box)),gesture.orientation);const size=Math.max(1,Math.min(gesture.box.width,gesture.box.height));camera.yaw=gesture.yaw+(p.x-gesture.point.x)*Math.PI/size;camera.pitch=gesture.pitch+(p.y-gesture.point.y)*Math.PI/size;}
function rotate(camera,angle){camera.orientation=multiply(fromAxis([0,1,0],angle),matrix(camera));camera.yaw+=angle;}
function reset(camera){Object.assign(camera,{yaw:-.2,pitch:.64,zoom:1,orientation:initial()});}
function project(camera,x,y,z=0){const m=matrix(camera);return {x:m[0]*x+m[1]*y+m[2]*z,y:m[3]*x+m[4]*y+m[5]*z,depth:m[6]*x+m[7]*y+m[8]*z};}
window.MapCamera={matrix,start,drag,rotate,reset,project};
})();
