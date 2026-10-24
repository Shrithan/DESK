'use strict';
function canStick(value,origin,gain=30,flip={}){
 const x=(value.x-origin[0])*gain*(flip.x?-1:1),y=(value.y-origin[1])*gain*(flip.y?-1:1),length=Math.max(1,Math.hypot(x,y));
 // Camera mounting correction: former D → W, A → S, W → A, S → D.
 const output={x:(-y/length)||0,y:(x/length)||0};
 return {...output,direction:Math.hypot(output.x,output.y)>.1?Math.atan2(output.x,output.y)*180/Math.PI:null};
}
function stickKeys(stick,previous={},active=true){
 if(!active||!stick)return {W:false,A:false,S:false,D:false};
 const pressed=(key,value)=>value>(previous[key] ? .12 : .18);
 return {W:pressed('W',stick.y),A:pressed('A',-stick.x),S:pressed('S',-stick.y),D:pressed('D',stick.x)};
}

// Hold a measured input briefly, then ease to zero; never extrapolate off-screen motion.
function stickContinuity(state,target,now,sample=now){
 if(target){state.last={...target};state.seen=sample;}
 const age=now-(state.seen??-Infinity);
 const scale=age<=130?1:Math.max(0,1-(age-130)/170);
 if(!state.last||!scale)return null;
 const x=state.last.x*scale,y=state.last.y*scale;
 return {x,y,direction:Math.hypot(x,y)>.1?Math.atan2(x,y)*180/Math.PI:null};
}
function tiltStick(input,side,stamp){
 const s=side.skeleton;
 if(input.sideId!==side.observation.object_id){input.sideId=side.observation.object_id;input.leanZero=s.projected_lean_degrees;input.baseZero=s.base_px;input.tiltFilter=null;}
 const height=Math.hypot(s.top_px[0]-s.base_px[0],s.top_px[1]-s.base_px[1]);
 if(Math.hypot(s.base_px[0]-input.baseZero[0],s.base_px[1]-input.baseZero[1])>height*.3)return null;
 const raw=Math.max(-1,Math.min(1,(s.projected_lean_degrees-input.leanZero)/12));
 if(input.tiltFilter?.stamp!==stamp)input.tiltFilter=euroStep(input.tiltFilter,raw,stamp,{minCutoff:3,beta:2});
 // Side image horizontal lean controls the forward/back axis after mounting rotation.
 return input.tiltFilter.value;
}
