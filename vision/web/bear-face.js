'use strict';
// The talking Cal bear: the voxel portrait with a jaw that drops along the smile line, blocky pupils that
// follow the pointer, blinks, and a head that turns toward where it looks. window.setBearMouth(level)
// is driven by the Cartesia reply audio (mascot.js connectBearAudio); the springs make it move naturally.
(()=>{
 const canvas=document.getElementById('bear-canvas'),fallback=document.getElementById('bear-fallback');
 if(!canvas)return;
 const ctx=canvas.getContext('2d'),img=new Image();
 const IW=1214,IH=1296,W=1296,H=1296,OX=(W-IW)/2; // square canvas, portrait centered
 canvas.width=W;canvas.height=H;
 img.src='/cal-bear-talking.png';
 img.onerror=()=>{canvas.hidden=true;if(fallback)fallback.hidden=false;};
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');

 // ---------- face geometry, in image pixels ----------
 // centre line of the black smile stroke: the mouth opens along it
 const SMILE=[[428,787],[440,799],[450,805],[460,816],[470,829],[480,838],[490,847],[500,852],[510,854],[520,855],[530,857],[560,859],
  [600,860],[640,859],[680,857],[700,855],[710,853],[720,849],[730,842],[740,833],[750,823],[760,808],[770,801],[780,796],[790,790]];
 const MOUTH_X0=428,MOUTH_X1=790,MOUTH_CX=609,MOUTH_HALF=181,JAW_L=398,JAW_R=818,CHIN=962,MAX_DROP=82;
 const EYES=[[381,476,136,170],[697,476,136,170]];
 // the head is cut from the body just above the collar, stepping around the shoulder tops
 const HEAD=[[0,0],[1214,0],[1214,916],[945,916],[935,945],[855,972],[365,972],[280,945],[268,916],[0,916]];
 const BODY=[[0,914],[270,914],[282,935],[930,935],[947,914],[1214,914],[1214,1296],[0,1296]];
 const PIVOT_X=607,PIVOT_Y=980;
 function cutY(x){
  if(x<=SMILE[0][0])return SMILE[0][1];
  for(let i=1;i<SMILE.length;i++){const [x1,y1]=SMILE[i];if(x<=x1){const [x0,y0]=SMILE[i-1];return y0+(y1-y0)*(x-x0)/(x1-x0);}}
  return SMILE[SMILE.length-1][1];
 }
 function lipShape(x,round){const a=Math.abs((x-MOUTH_CX)/MOUTH_HALF);return a>=1?0:Math.pow(1-Math.pow(a,2.2),.45+round*.9);}
 function poly(points){ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();}

 function drawFace(open,round){
  ctx.save();poly(HEAD);ctx.clip();ctx.drawImage(img,0,0);ctx.restore();
  const drop=open*MAX_DROP;if(drop<.6)return;
  ctx.save();ctx.beginPath();
  for(let x=MOUTH_X0;x<=MOUTH_X1;x+=2)ctx.lineTo(x,cutY(x));
  for(let x=MOUTH_X1;x>=MOUTH_X0;x-=2)ctx.lineTo(x,cutY(x)+drop*lipShape(x,round)+1);
  ctx.closePath();ctx.clip();
  const lipY=cutY(MOUTH_CX),g=ctx.createLinearGradient(0,lipY,0,lipY+drop);
  g.addColorStop(0,'#120405');g.addColorStop(1,'#4a1210');ctx.fillStyle=g;ctx.fillRect(MOUTH_X0,760,MOUTH_X1-MOUTH_X0,220);
  const tw=MOUTH_HALF*(1.05-round*.35),th=16+drop*.42,ty=lipY+drop-th*.55;
  ctx.fillStyle='#b8434b';ctx.beginPath();ctx.roundRect(MOUTH_CX-tw/2,ty,tw,th+20,[26,26,0,0]);ctx.fill();
  ctx.fillStyle='#d4646b';ctx.fillRect(MOUTH_CX-tw*.3,ty+6,tw*.6,7);
  const sh=ctx.createLinearGradient(0,lipY,0,lipY+22);sh.addColorStop(0,'rgba(10,2,2,.85)');sh.addColorStop(1,'rgba(10,2,2,0)');
  ctx.fillStyle=sh;ctx.fillRect(MOUTH_X0,lipY-40,MOUTH_X1-MOUTH_X0,62);ctx.restore();
  // jaw: each 1px column of the lower muzzle is redrawn from its smile cut down to the dropped chin
  const chinY=CHIN+drop;
  for(let x=JAW_L;x<JAW_R;x++){const top=cutY(x+.5),dy=top+drop*lipShape(x+.5,round);ctx.drawImage(img,x,top,1,CHIN-top,x,dy,1,chinY-dy);}
  const cs=ctx.createLinearGradient(0,chinY,0,chinY+34);cs.addColorStop(0,'rgba(40,12,0,.55)');cs.addColorStop(1,'rgba(40,12,0,0)');
  ctx.fillStyle=cs;ctx.fillRect(JAW_L+10,chinY,JAW_R-JAW_L-20,34);
 }
 function drawEyes(lx,ly){
  const pw=58,ph=74;
  for(const [x,y,w,h] of EYES){
   const px=x+w/2-pw/2+lx*(w/2-pw/2-12),py=y+h/2-ph/2+4+ly*(h/2-ph/2-14);
   ctx.save();ctx.beginPath();ctx.rect(x+4,y+2,w-8,h-4);ctx.clip();
   ctx.fillStyle='#21140c';ctx.beginPath();ctx.roundRect(px,py,pw,ph,7);ctx.fill();
   ctx.fillStyle='#3a2618';ctx.fillRect(px+5,py+4,pw-10,6);ctx.fillStyle='#0f0805';ctx.fillRect(px+5,py+ph-9,pw-10,6);
   ctx.fillStyle='#fffaf0';ctx.fillRect(px+10,py+13,17,17);ctx.globalAlpha=.8;ctx.fillRect(px+pw-19,py+ph-24,8,8);ctx.restore();
  }
 }
 function drawLids(c){
  if(c<.03)return;
  for(const [x,y,w,h] of EYES){
   const lh=Math.round(h*Math.min(1,c)),g=ctx.createLinearGradient(0,y,0,y+h);
   g.addColorStop(0,'#8f4a16');g.addColorStop(1,'#a8591c');ctx.fillStyle=g;ctx.fillRect(x,y,w,lh);
   ctx.fillStyle='#3d1c06';ctx.fillRect(x,y+lh-9,w,9);
  }
 }

 // ---------- springs ----------
 const spring=(k,zeta)=>({x:0,v:0,t:0,k,c:2*zeta*Math.sqrt(k)});
 const step=(s,dt)=>{s.v+=((s.t-s.x)*s.k-s.v*s.c)*dt;s.x+=s.v*dt;};
 const jaw=spring(900,.8),rnd=spring(500,.9),lid=spring(2600,1),lookX=spring(700,.85),lookY=spring(700,.85),headX=spring(45,.8),headY=spring(45,.8);
 let mouthLevel=0,lastMouth=0,talk=0;
 // The audio envelope already rises fast and falls slower; the jaw spring adds weight and a little overshoot.
 window.setBearMouth=(level=0)=>{mouthLevel=Math.max(0,Math.min(1,+level||0));lastMouth=performance.now();};

 let pointer={x:0,y:0},pointerIdle=99,nextGlance=1,nextBlink=1.2,blinkHold=0,time=0,last=performance.now();
 window.addEventListener('pointermove',e=>{
  const r=canvas.getBoundingClientRect();if(!r.width)return;
  pointer.x=Math.max(-1,Math.min(1,(e.clientX-(r.left+r.width/2))/(r.width*.6)));
  pointer.y=Math.max(-1,Math.min(1,(e.clientY-(r.top+r.height*.43))/(r.height*.6)));pointerIdle=0;
 });
 document.addEventListener('pointerleave',()=>{pointerIdle=99;});

 function frame(now){
  const dt=Math.min(.05,(now-last)/1000);last=now;time+=dt;
  const body=document.body.classList,calm=reduced.matches;
  // mouth: follow the voice; a small live wobble keeps held vowels from freezing
  const level=now-lastMouth<250?mouthLevel:0;
  jaw.t=level>.06?level*(1+.06*Math.sin(time*23)*Math.sin(time*7.3)):0;
  rnd.t=.15+.5*Math.max(0,Math.sin(time*2.7))*(level>.1?1:0);
  // gaze: the pointer while it moves; up and aside while thinking; at you while listening or speaking
  pointerIdle+=dt;nextGlance-=dt;
  if(body.contains('va-thinking')){lookX.t=.55;lookY.t=-.7;}
  else if(pointerIdle<3){lookX.t=pointer.x;lookY.t=pointer.y;}
  else if(body.contains('va-listening')||body.contains('va-hearing')||body.contains('va-speaking')||talk>.05){lookX.t=0;lookY.t=.1;}
  else if(nextGlance<=0){const away=Math.random()<.35;lookX.t=away?(Math.random()*2-1)*.9:(Math.random()-.5)*.3;lookY.t=away?(Math.random()*2-1)*.6:(Math.random()-.5)*.2;nextGlance=away?.8+Math.random():1.5+Math.random()*2.5;}
  // blinks, sometimes doubled
  nextBlink-=dt;
  if(!calm&&nextBlink<=0&&blinkHold<=0){lid.t=1;blinkHold=.075;}
  if(blinkHold>0){blinkHold-=dt;if(blinkHold<=0){lid.t=0;nextBlink=Math.random()<.18?.18:2+Math.random()*4;}}
  for(let h=dt;h>0;h-=.004){const s=Math.min(.004,h);step(jaw,s);step(rnd,s);step(lid,s);step(lookX,s);step(lookY,s);}
  if(jaw.x<0){jaw.x=0;jaw.v=Math.max(0,jaw.v);}
  headX.t=lookX.t;headY.t=lookY.t;step(headX,dt);step(headY,dt);
  talk+=(jaw.x-talk)*Math.min(1,dt*4);

  if(img.complete&&img.naturalWidth){
   ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,W,H);ctx.translate(OX,0);
   const motion=calm?.35:1,breathe=calm?0:Math.sin(time*1.7)*.004+talk*.006;
   ctx.save();ctx.translate(IW/2,IH);ctx.scale(1,1+breathe);ctx.translate(-IW/2,-IH);
   ctx.save();poly(BODY);ctx.clip();ctx.drawImage(img,0,0);ctx.restore();
   ctx.fillStyle='#3c1a04';ctx.fillRect(370,900,480,30);
   const hx=Math.max(-1.2,Math.min(1.2,headX.x))*motion,hy=Math.max(-1.2,Math.min(1.2,headY.x))*motion;
   const tilt=(hx*4+(calm?0:Math.sin(time*.6)*.5+Math.sin(time*2.1)*talk*.8))*Math.PI/180;
   ctx.translate(PIVOT_X+hx*20,PIVOT_Y+hy*10+talk*3);ctx.rotate(tilt);ctx.scale(1,1-hy*.025);ctx.translate(-PIVOT_X,-PIVOT_Y);
   drawFace(Math.min(1.08,jaw.x),Math.min(1,Math.max(0,rnd.x)));
   drawEyes(lookX.x-hx*.4,lookY.x-hy*.4);drawLids(lid.x);
   ctx.restore();
  }
  requestAnimationFrame(frame);
 }
 requestAnimationFrame(frame);
})();
