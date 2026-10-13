const assert=require('node:assert/strict');
global.window=global;require('../web/map-camera.js');
const near=(a,b,e=1e-9)=>assert.ok(Math.abs(a-b)<e,a+' != '+b);
const box={left:20,top:30,width:900,height:650};
let camera={yaw:-.2,pitch:.64,zoom:1};const before=[...MapCamera.matrix(camera)];
const start={x:470,y:355};const g=MapCamera.start(camera,start,box);
MapCamera.drag(camera,g,{x:670,y:535});
const m=MapCamera.matrix(camera);
for(let i=0;i<3;i++)for(let j=0;j<3;j++)near(m[i*3]*m[j*3]+m[i*3+1]*m[j*3+1]+m[i*3+2]*m[j*3+2],i===j?1:0);
near(m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6]),1);
assert.ok(camera.pitch>.92,'Vertical drag must cross the old pitch ceiling');
MapCamera.drag(camera,g,start);MapCamera.matrix(camera).forEach((x,i)=>near(x,before[i]));
MapCamera.rotate(camera,2*Math.PI);MapCamera.matrix(camera).forEach((x,i)=>near(x,before[i]));
// The virtual sphere point follows the pointer in screen coordinates.
MapCamera.reset(camera);const original=MapCamera.matrix(camera);const gesture=MapCamera.start(camera,start,box);
const delta={x:650,y:475};MapCamera.drag(camera,gesture,delta);
const sphere=point=>{const x=(2*(point.x-box.left)-box.width)/650,y=(2*(point.y-box.top)-box.height)/650,d=Math.hypot(x,y),z=d<Math.SQRT1_2?Math.sqrt(1-d*d):.5/d,n=Math.hypot(x,y,z);return [x/n,y/n,z/n];};
const a=sphere(start),b=sphere(delta),world=[0,1,2].map(i=>original[i]*a[0]+original[3+i]*a[1]+original[6+i]*a[2]);
const projected=MapCamera.project(camera,...world);[projected.x,projected.y,projected.depth].forEach((x,i)=>near(x,b[i]));
// Repeated turns reach upside-down views; there is no fixed interval.
MapCamera.reset(camera);MapCamera.rotate(camera,Math.PI);assert.ok(MapCamera.project(camera,0,0,1).depth<0);
MapCamera.reset(camera);assert.deepEqual(MapCamera.matrix(camera),before);
console.log('Trackball invariants passed: pointer following, reversible gesture, full turns, orthonormal projection and reset');
