import * as THREE from './vendor/three.module.js';

const canvas=document.getElementById('bear-canvas');
const fallback=document.getElementById('bear-fallback');
const host=document.getElementById('bear-avatar');
const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');

try{
 const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
 renderer.outputColorSpace=THREE.SRGBColorSpace;
 const scene=new THREE.Scene();
 const camera=new THREE.OrthographicCamera(-2.6,2.6,2.6,-2.6,.1,40);
 camera.position.set(1.7,2.75,12);
 camera.lookAt(0,.9,0);
 scene.add(new THREE.HemisphereLight(0xffffff,0x86a9a2,2.1));
 const sun=new THREE.DirectionalLight(0xffffff,2.65);
 sun.position.set(-3.5,7,6);scene.add(sun);

 const mat=(front,side,top)=>[
  new THREE.MeshLambertMaterial({color:side}),new THREE.MeshLambertMaterial({color:side}),
  new THREE.MeshLambertMaterial({color:top}),new THREE.MeshLambertMaterial({color:side}),
  new THREE.MeshLambertMaterial({color:front}),new THREE.MeshLambertMaterial({color:side})
 ];
 const fur=mat('#bd814d','#a46a3b','#d59b61');
 const furDark=mat('#9d6339','#804a2b','#b57946');
 const honey=mat('#ebbd7c','#d6a05e','#f7cf91');
 const navy=mat('#173457','#0e2745','#27486e');
 const navyFold=mat('#102b4d','#0b203b','#1b3b61');
 const gold=mat('#e6b546','#bf8e2e','#f1ca62');
 const nose=mat('#302725','#211b1b','#403331');
 const eyeMat=mat('#211b1b','#161313','#302828');
 const mouthMat=mat('#402628','#2b191a','#4d3030');
 const earInner=mat('#d29361','#b8794d','#e2a674');

 const root=new THREE.Group();scene.add(root);
 const body=new THREE.Group();root.add(body);
 const headPivot=new THREE.Group();headPivot.position.y=-.06;root.add(headPivot);
 function block(parent,w,h,d,x,y,z,material,casts=true){
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material);
  mesh.position.set(x,y,z);mesh.castShadow=casts;mesh.receiveShadow=true;parent.add(mesh);return mesh;
 }
 // The sweatshirt continues below the camera crop; the head is almost twice its width.
 block(body,1.42,1.9,.86,0,-1.11,-.05,navy);
 block(root,.78,.55,.65,0,-.28,-.06,furDark);
 block(body,1.28,.23,.95,0,-.29,.04,navyFold);
 block(body,1.12,.27,.19,0,-.42,.55,navyFold,false);
 block(body,.91,.085,.1,0,-.54,.67,gold,false);
 for(const side of [-1,1])block(body,.12,.24,.11,side*.5,-.37,.67,gold,false);
 for(const side of [-1,1]){
  block(body,.31,.92,.77,side*.77,-.85,-.07,navy);
  block(body,.11,.52,.79,side*.89,-.88,-.04,gold,false);
  block(body,.17,.5,.09,side*.56,-.64,.43,navyFold,false);
 }
 block(headPivot,3.28,2.72,1.68,0,1.23,0,fur);
 block(headPivot,2.7,.43,1.67,0,.12,0,furDark);
 for(const side of [-1,1]){
  block(headPivot,.52,.55,.59,side*1.39,2.5,-.05,fur);
  block(headPivot,.3,.32,.035,side*1.39,2.51,.265,earInner,false);
 }
 block(headPivot,1.55,.64,.51,0,.56,1.055,honey);
 block(headPivot,.23,.18,.2,0,.87,1.365,nose);
 const eyes=[];
 for(const side of [-1,1]){
  const eye=block(headPivot,.115,.14,.075,side*.61,1.55,.875,eyeMat,false);
  eyes.push(eye);
 }
 const mouth=block(headPivot,.35,.038,.035,0,.38,1.32,mouthMat,false);
 const mouthOpen=block(headPivot,.34,.01,.036,0,.34,1.33,mouthMat,false);
 mouthOpen.visible=false;

 // A stepped cap keeps its brim and lettering attached to the rotating head.
 block(headPivot,2.19,.69,1.53,0,2.89,-.045,navy);
 block(headPivot,2.35,.14,.83,0,2.52,.6,navyFold);
 block(headPivot,1.96,.11,.39,0,2.51,1.16,navy);
 block(headPivot,1.56,.1,.2,0,2.5,1.44,navy);
 const logoCanvas=document.createElement('canvas');logoCanvas.width=1024;logoCanvas.height=512;
 const ctx=logoCanvas.getContext('2d');
 ctx.clearRect(0,0,1024,512);
 ctx.textAlign='center';ctx.textBaseline='middle';
 ctx.font='italic 900 340px "Brush Script MT", "Snell Roundhand", "Apple Chancery", cursive';
 ctx.lineJoin='round';ctx.lineWidth=18;ctx.strokeStyle='#8c6124';ctx.strokeText('Cal',512,282);
 ctx.fillStyle='#f6c74f';ctx.fillText('Cal',512,282);
 const logoTexture=new THREE.CanvasTexture(logoCanvas);logoTexture.colorSpace=THREE.SRGBColorSpace;
 const logo=new THREE.Mesh(new THREE.PlaneGeometry(1.45,.71),new THREE.MeshBasicMaterial({map:logoTexture,transparent:true,depthWrite:false}));
 logo.position.set(0,2.92,.727);headPivot.add(logo);

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
  const aspect=w/h,halfHeight=2.6;
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
   state.headY=.14+x*.14;state.headX=-.04-y*.08;state.headZ=0;state.bodyY=0;
  }else{
   spring('headY','vy',.14+x*.19,dt);
   spring('headX','vx',-.04-y*.11,dt);
   spring('headZ','vz',-x*.026,dt);
   spring('bodyY','vBody',x*.035,dt,20,9);
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
