'use strict';
// Constant-velocity estimate, with separate observation times for each axis.
function updatePrediction(previous,point,stamp,axisStamps=[stamp,stamp,stamp]){
 const velocity=[0,0,0];
 if(previous)for(let i=0;i<3;i++){
  const dt=(axisStamps[i]-previous.axisStamps[i])/1000;
  velocity[i]=dt===0?previous.velocity[i]:dt>0&&dt<=.25?Math.max(-180,Math.min(180,.65*(point[i]-previous.point[i])/dt+.35*previous.velocity[i])):0;
 }
 return {point:point.slice(),velocity,stamp,axisStamps:axisStamps.slice()};
}
function predictPosition(state,now,enabled=true){
 if(!state||state.axisStamps.some(stamp=>now-stamp>220))return null;
 let predicted=false;
 const point=state.point.map((v,i)=>{const age=Math.max(0,now-state.axisStamps[i]);if(enabled&&age>20&&Math.abs(state.velocity[i])>.2)predicted=true;return v+state.velocity[i]*(enabled?Math.min(age,80)/1000:0);});
 return {point,predicted,age:now-state.stamp};
}
