'use strict';
// Learn the upright projection seen by THIS camera. An elongated neutral silhouette
// is allowed: neither a round lid nor a vertical image axis defines physical upright.
function beginStickNeutral(input){
 if(typeof stopRealKeys==='function'&&keyboardToken)void stopRealKeys('Recalibrating upright');
 input.neutralPose=null;input.poseCalibration={phase:'neutral',samples:[],lastStamp:null};
 input.calibrationStatus='Hold the can upright and still for 1 second';
 input.continuity={};input.keys=stickKeys(null,{},false);input.joystick=null;input.controlActive=false;input.poseFilter=null;
}
function beginStickDirection(input,key){
 if(!input.neutralPose)return;
 if(key==='W')input.directionBasis=null;
 input.poseCalibration={phase:key,samples:[],lastStamp:null};
 input.calibrationStatus=`Lean toward ${key}, keep the base fixed, and hold`;
 input.continuity={};input.keys=stickKeys(null,{},false);input.controlActive=false;
}
function validStickFeature(f){return !!f&&['cx','cy','area','cxx','cxy','cyy'].every(k=>Number.isFinite(f[k]))&&f.area>=30;}
function stickPoseRaw(pose,f){return [(f.cx-pose.cx)/pose.radius,(f.cy-pose.cy)/pose.radius];}
function basisStick(raw,basis,flip={}){
 let x,y;
 if(basis?.W&&basis?.D){
  const [wx,wy]=basis.W,[dx,dy]=basis.D,det=dx*wy-dy*wx;
  x=(raw[0]*wy-raw[1]*wx)/det;y=(dx*raw[1]-dy*raw[0])/det;
 }else{x=raw[1]/.45;y=raw[0]/.45;} // keep the user's corrected mounting orientation
 // Camera X reversal affects forward in the default mounting, Y reversal affects sideways.
 x*=flip.y?-1:1;y*=flip.x?-1:1;
 const length=Math.max(1,Math.hypot(x,y));x/=length;y/=length;
 return {x:x||0,y:y||0,direction:Math.hypot(x,y)>.1?Math.atan2(x,y)*180/Math.PI:null};
}
function stepStickPose(input,f,stamp,flip={}){
 if(!input.poseCalibration)beginStickNeutral(input);
 const c=input.poseCalibration;
 if(!validStickFeature(f)){input.calibrationStatus=c.phase==='neutral'?'Put the upright can clearly in view':c.phase==='ready'?'Can not visible · return it to the saved base':'Keep the can visible to calibrate';return null;}
 if(c.phase==='neutral'){
  if(c.lastStamp===stamp)return null;
  if(c.lastStamp!==null&&stamp-c.lastStamp>250)c.samples=[];
  c.lastStamp=stamp;
  const first=c.samples[0],r=Math.sqrt(f.area/Math.PI);
  if(first&&(Math.hypot(f.cx-first.cx,f.cy-first.cy)>.08*r||Math.abs(f.area/first.area-1)>.15||Math.hypot(f.cxx-first.cxx,f.cxy-first.cxy,f.cyy-first.cyy)/f.area>.08))c.samples=[];
  c.samples.push({...f,stamp});
  const elapsed=stamp-c.samples[0].stamp;
  input.calibrationStatus=`Hold upright and still · ${Math.min(100,Math.floor(elapsed/10))}%`;
  if(elapsed<1000||c.samples.length<8)return null;
  const mean=k=>c.samples.reduce((a,s)=>a+s[k],0)/c.samples.length;
  const pose=Object.fromEntries(['cx','cy','area','cxx','cxy','cyy'].map(k=>[k,mean(k)]));pose.radius=Math.sqrt(pose.area/Math.PI);
  const noise=Math.sqrt(c.samples.reduce((a,s)=>a+(s.cx-pose.cx)**2+(s.cy-pose.cy)**2,0)/c.samples.length)/pose.radius;
  pose.deadZone=Math.max(.025,noise*3);input.neutralPose=pose;c.phase='ready';c.samples=[];input.poseFilter=null;
  input.calibrationStatus=input.directionBasis?.W&&input.directionBasis?.D?'Upright saved · learned W/D directions active':'Upright saved · learn W/D if directions feel wrong';
  return {x:0,y:0,direction:null};
 }
 const pose=input.neutralPose,ratio=f.area/pose.area;
 if(ratio<.55||ratio>1.8){input.calibrationStatus='Can silhouette changed too much · keep hands clear or recalibrate';return null;}
 const raw=stickPoseRaw(pose,f);
 if(c.phase==='W'||c.phase==='D'){
  if(c.lastStamp===stamp)return null;
  if(c.lastStamp!==null&&stamp-c.lastStamp>250)c.samples=[];
  c.lastStamp=stamp;
  if(Math.hypot(...raw)<.15){c.samples=[];input.calibrationStatus=`Lean toward ${c.phase} farther and hold`;return null;}
  if(c.samples.length&&Math.hypot(raw[0]-c.samples[0].x,raw[1]-c.samples[0].y)>.12)c.samples=[];
  c.samples.push({x:raw[0],y:raw[1],stamp});
  if(stamp-c.samples[0].stamp<500||c.samples.length<6)return null;
  const vector=['x','y'].map(k=>c.samples.reduce((a,s)=>a+s[k],0)/c.samples.length),basis={...input.directionBasis,[c.phase]:vector};
  if(basis.W&&basis.D){const [wx,wy]=basis.W,[dx,dy]=basis.D;const sine=Math.abs(wx*dy-wy*dx)/(Math.hypot(wx,wy)*Math.hypot(dx,dy));
   if(sine<.3){c.samples=[];input.calibrationStatus='Directions too similar · return upright, then lean sideways for D';return null;}}
  input.directionBasis=basis;c.phase='return';input.calibrationStatus=basis.W&&basis.D?'Directions saved · return upright to start':'Direction saved · return upright, then learn the other direction';return null;
 }
 if(c.phase==='return'){
  if(Math.hypot(...raw)>Math.max(.08,pose.deadZone*2))return null;
  c.phase='ready';input.poseFilter=null;
 }
 if(Math.hypot(...raw)<=pose.deadZone){raw[0]=0;raw[1]=0;}
 let target=basisStick(raw,input.directionBasis,flip);
 if(input.poseFilter?.stamp!==stamp){const previous=input.poseFilter;input.poseFilter={stamp,x:euroStep(previous?.x,target.x,stamp,{minCutoff:3,beta:4}),y:euroStep(previous?.y,target.y,stamp,{minCutoff:3,beta:4})};}
 const x=input.poseFilter.x.value,y=input.poseFilter.y.value;
 input.calibrationStatus=input.directionBasis?.W&&input.directionBasis?.D?'Upright + W/D calibrated · relative lean / movement':'Upright calibrated · use Learn W/D to set your directions';
 return {x,y,direction:Math.hypot(x,y)>.1?Math.atan2(x,y)*180/Math.PI:null};
}
