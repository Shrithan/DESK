import * as THREE from './vendor/three.module.js';

const canvas=document.getElementById('bear-canvas');
const fallback=document.getElementById('bear-fallback');
const host=document.getElementById('bear-avatar');
const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');

try{
 const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
 renderer.outputColorSpace=THREE.SRGBColorSpace;
 renderer.shadowMap.enabled=true;
 renderer.shadowMap.type=THREE.PCFSoftShadowMap;
 const scene=new THREE.Scene();
 const camera=new THREE.OrthographicCamera(-3.05,3.05,3.05,-3.05,.1,40);
 camera.position.set(3.8,3.25,11.5);
 camera.lookAt(0,.05,0);
 scene.add(new THREE.HemisphereLight(0xffffff,0x86a9a2,2.1));
 const sun=new THREE.DirectionalLight(0xffffff,2.65);
 sun.position.set(-3.5,7,6);sun.castShadow=true;
 sun.shadow.mapSize.set(1024,1024);
 sun.shadow.camera.left=-5;sun.shadow.camera.right=5;sun.shadow.camera.top=6;sun.shadow.camera.bottom=-5;
 sun.shadow.normalBias=.025;sun.shadow.radius=3;scene.add(sun);

 const mat=(front,side,top)=>[
  new THREE.MeshLambertMaterial({color:side}),new THREE.MeshLambertMaterial({color:side}),
  new THREE.MeshLambertMaterial({color:top}),new THREE.MeshLambertMaterial({color:side}),
  new THREE.MeshLambertMaterial({color:front}),new THREE.MeshLambertMaterial({color:side})
 ];
 const fur=mat('#b97b46','#9c6135','#cf9258');
 const furDark=mat('#945a34','#784627','#aa6d3e');
 const honey=mat('#e9ba78','#d6a15f','#f5cc8e');
 const belly=mat('#dfad70','#c28b53','#f0c289');
 const nose=mat('#302725','#211b1b','#403331');
 const eyeMat=mat('#211b1b','#161313','#302828');
 const mouthMat=mat('#402628','#2b191a','#4d3030');
 const earInner=mat('#d29361','#b8794d','#e2a674');
 const shadow=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.ShadowMaterial({opacity:.18}));
 shadow.rotation.x=-Math.PI/2;shadow.position.y=-2.09;shadow.receiveShadow=true;scene.add(shadow);

 const root=new THREE.Group();scene.add(root);
 const body=new THREE.Group();root.add(body);
 const headPivot=new THREE.Group();headPivot.position.y=.12;root.add(headPivot);
 function block(parent,w,h,d,x,y,z,material,casts=true){
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material);
  mesh.position.set(x,y,z);mesh.castShadow=casts;mesh.receiveShadow=true;parent.add(mesh);return mesh;
 }
 // A few deliberately large blocks make the character read like the duck reference.
 block(body,1.52,1.36,1.03,0,-.87,0,fur);
 block(root,.84,.72,.74,0,.02,-.07,furDark);
 block(body,.91,.91,.08,0,-.88,.56,belly,false);
 for(const side of [-1,1]){
  block(body,.48,.86,.7,side*1.04,-.9,.03,fur);
  block(body,.56,.4,.82,side*.43,-1.65,.22,furDark);
  block(body,.69,.24,1.04,side*.43,-1.96,.43,furDark);
 }
 block(headPivot,2.18,1.85,1.55,0,1.06,0,fur);
 block(headPivot,1.91,.46,1.56,0,.34,0,furDark);
 for(const side of [-1,1]){
  block(headPivot,.54,.56,.55,side*.84,2.14,-.05,fur);
  block(headPivot,.31,.31,.035,side*.84,2.15,.245,earInner,false);
 }
 block(headPivot,1.15,.46,.47,0,.67,.98,honey);
 block(headPivot,.22,.18,.19,0,.84,1.27,nose);
 const eyes=[];
 for(const side of [-1,1]){
  const eye=block(headPivot,.105,.14,.075,side*.43,1.43,.82,eyeMat,false);
  eyes.push(eye);
 }
 const mouth=block(headPivot,.34,.038,.035,0,.44,1.225,mouthMat,false);
 const mouthOpen=block(headPivot,.33,.01,.036,0,.38,1.231,mouthMat,false);
 mouthOpen.visible=false;

 let targetX=0,targetY=0,activePointer=false;
 function point(event){
  targetX=THREE.MathUtils.clamp((event.clientX/window.innerWidth-.5)*2,-1,1);
  targetY=THREE.MathUtils.clamp((event.clientY/window.innerHeight-.5)*2,-1,1);
  activePointer=true;
 }
 window.addEventListener('pointermove',point,{passive:true});
 window.addEventListener('pointerdown',point,{passive:true});
 window.addEventListener('pointerup',event=>{if(event.pointerType==='touch')activePointer=false},{passive:true});
 window.addEventListener('pointerout',event=>{if(!event.relatedTarget)activePointer=false});
 window.addEventListener('blur',()=>{activePointer=false});
 const state={headX:0,headY:0,headZ:0,bodyY:0,vx:0,vy:0,vz:0,vBody:0,mouth:0,mouthTarget:0};
 function spring(key,velocity,target,dt,stiffness=46,damping=11){
  state[velocity]+=(target-state[key])*stiffness*dt;
  state[velocity]*=Math.exp(-damping*dt);
  state[key]+=state[velocity]*dt;
 }
 window.setBearMouth=(level=0)=>{state.mouthTarget=THREE.MathUtils.clamp(level,0,1)};
 function size(){
  const w=host.clientWidth,h=host.clientHeight;
  if(!w||!h)return;
  renderer.setSize(w,h,false);
  const aspect=w/h,halfHeight=3.05;
  camera.left=-halfHeight*aspect;camera.right=halfHeight*aspect;
  camera.top=halfHeight;camera.bottom=-halfHeight;camera.updateProjectionMatrix();
 }
 new ResizeObserver(size).observe(host);size();
 const clock=new THREE.Clock();let elapsed=0,blinkAt=3.8;
 function draw(){
  requestAnimationFrame(draw);
  if(document.hidden)return;
  const dt=Math.min(clock.getDelta(),.05);elapsed+=dt;
  const x=activePointer?targetX:0,y=activePointer?targetY:0;
  if(reduced.matches){
   state.headY=.22+x*.18;state.headX=-.05-y*.1;state.headZ=0;state.bodyY=0;
  }else{
   spring('headY','vy',.22+x*.25,dt);
   spring('headX','vx',-.05-y*.15,dt);
   spring('headZ','vz',-x*.035,dt);
   spring('bodyY','vBody',x*.055,dt,20,9);
  }
  headPivot.rotation.set(state.headX,state.headY,state.headZ);
  body.rotation.y=state.bodyY;
  if(!reduced.matches){
   body.scale.y=1+Math.sin(elapsed*1.5)*.005;
   if(elapsed>blinkAt){blinkAt=elapsed+4.3+Math.random()*2.5;eyes.forEach(eye=>eye.userData.blinkUntil=elapsed+.115)}
   for(const eye of eyes)eye.scale.y=elapsed<(eye.userData.blinkUntil||0)?.12:1;
  }else{body.scale.y=1;eyes.forEach(eye=>eye.scale.y=1)}
  state.mouth+=(state.mouthTarget-state.mouth)*Math.min(1,dt*17);
  mouth.visible=state.mouth<.1;
  mouthOpen.visible=state.mouth>=.1;
  mouthOpen.scale.y=Math.max(.1,state.mouth*18);
  renderer.render(scene,camera);
 }
 draw();
}catch(error){
 console.error('3D bear could not start',error);
 canvas.hidden=true;fallback.hidden=false;
}
