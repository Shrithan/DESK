'use strict';
function canStick(value,origin,gain=30,flip={}){
 const x=(value.x-origin[0])*gain*(flip.x?-1:1),y=(value.y-origin[1])*gain*(flip.y?-1:1),length=Math.max(1,Math.hypot(x,y));
 // Camera mounting correction: former D → W, A → S, W → A, S → D.
 const output={x:(-y/length)||0,y:(x/length)||0};
 return {...output,direction:Math.hypot(output.x,output.y)>.1?Math.atan2(output.x,output.y)*180/Math.PI:null};
}
// 8 sectors of 45 deg with magnitude hysteresis (press > .18, release < .12) and angle hysteresis:
// the held sector only changes once the stick is 10 deg past its edge. Checking each axis on its own
// (the old way) made diagonals flicker W -> W+D -> D -> W+D as the angle wobbled near 45 deg.
const STICK_SECTORS=[['W'],['W','D'],['D'],['S','D'],['S'],['S','A'],['A'],['W','A']];
function stickKeys(stick,previous={},active=true){
 const none={W:false,A:false,S:false,D:false};
 const mag=stick?Math.hypot(stick.x,stick.y):0;
 const held=previous&&typeof previous._sector==='number'?previous._sector:null;
 if(!active||!stick||!Number.isFinite(mag)||mag<(held===null?.18:.12)||(held===null&&mag<=.18))return none;
 const angle=((Math.atan2(stick.x,stick.y)*180/Math.PI)+360)%360;
 let sector=held;
 const off=held===null?Infinity:Math.abs(((angle-held*45)%360+540)%360-180);
 if(off>22.5+10)sector=Math.round(angle/45)%8;
 const keys={...none};for(const k of STICK_SECTORS[sector])keys[k]=true;
 Object.defineProperty(keys,'_sector',{value:sector,enumerable:false});
 return keys;
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
