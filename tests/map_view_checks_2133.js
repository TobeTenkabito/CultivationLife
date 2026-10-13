const assert=require('node:assert/strict');
global.window=global;require('../web/map-camera.js');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,a+' != '+b);
const box={left:30,top:70,width:400,height:600},camera={yaw:-.2,pitch:.64,zoom:1,panX:0,panY:0};
const orientation=[...MapCamera.matrix(camera)];
MapCamera.pan(camera,80,-40,box);near(camera.panX*box.width/1600,80);near(camera.panY*box.width/1600,-40);assert.deepEqual(MapCamera.matrix(camera),orientation);
MapCamera.pan(camera,-80,40,box);near(camera.panX,0);near(camera.panY,0);
// A world point at the wheel/pinch anchor stays under that exact screen point.
const anchor={x:170,y:280},anchorX=(anchor.x-box.left)*1600/box.width,anchorY=(anchor.y-box.top)*1600/box.width;
const local={x:anchorX-800,y:anchorY-box.height*1600/box.width/2};
for(const z of [1.6,2.4,.65,1]){
 MapCamera.zoomAt(camera,z,anchor,box);
 near(800+camera.panX+local.x*camera.zoom,anchorX);
 near(box.height*1600/box.width/2+camera.panY+local.y*camera.zoom,anchorY);
}
MapCamera.zoomAt(camera,100,anchor,box);near(camera.zoom,2.4);
MapCamera.zoomAt(camera,0,anchor,box);near(camera.zoom,.65);
MapCamera.twist(camera,.6);assert.notDeepEqual(MapCamera.matrix(camera),orientation);
MapCamera.reset(camera);near(camera.panX,0);near(camera.panY,0);near(camera.zoom,1);assert.deepEqual(MapCamera.matrix(camera),orientation);
console.log('View controls passed: pixel pan, preserved orientation, anchored zoom, limits and complete reset');
