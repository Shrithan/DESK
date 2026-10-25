'use strict';
function flatValue(center,size,mode,range=null){
 const x=Math.max(0,Math.min(1,center[0]/size[0])),y=Math.max(0,Math.min(1,1-center[1]/size[1]));
 if(mode==='xy')return {x,y};
 const position=mode==='y'?y:x;
 if(!range)return {value:position,calibrated:false};
 const delta=range[1]-range[0];
 if(Math.abs(delta)<.02)return null;
 return {value:Math.max(0,Math.min(1,(position-range[0])/delta)),calibrated:true};
}
function joystickValue(value,origin){return canStick(value,origin,30);}
const flatInputs=new Map(),dismissedFlatInputs=new Set();
// A previous session must never turn a newly detected object into a control.
let canJoystickArmed=false;
sessionStorage.removeItem('can-joystick-armed');
function renderFlatInputs(){
 const tracked=objects('top');
 if(canJoystickArmed){
  const containers=tracked.filter(o=>['can','bottle','cup'].includes(o.object_label)&&o.motion&&o.observation.tracking_state==='tracked').sort((a,b)=>{const area=o=>{const [x,y,x2,y2]=o.observation.bbox_xyxy;return (x2-x)*(y2-y);};return area(b)-area(a);});
  const area=o=>{const [x,y,x2,y2]=o.observation.bbox_xyxy;return (x2-x)*(y2-y);};
  if(containers.length&&(containers.length===1||area(containers[0])>area(containers[1])*1.5)){
   const item=containers[0],id=item.observation.object_id;flatInputs.set(id,{mode:'xy',label:'Can joystick',range:null,pivot:true});
   const pair=pairs.find(p=>p.top===id);if(pair)pairs.splice(pairs.indexOf(pair),1);
   canJoystickArmed=false;sessionStorage.removeItem('can-joystick-armed');$('can-status').textContent='Can assigned. Stand it upright and still for one second. Use Learn W and Learn D on its card to teach the tilted camera your directions.';
  }else $('can-status').textContent=containers.length?'Several similar objects are visible. Choose your can in Overhead input object, then Use as input.':'Waiting for your can under the overhead camera. Move it briefly to acquire it.';
 }
 const select=$('flat-object'),old=select.value;
 select.replaceChildren(new Option('Choose overhead object…',''),...tracked.filter(o=>o.observation.tracking_state==='tracked').map(o=>new Option(`#${o.number} ${o.object_label}`,o.observation.object_id)));
 if([...select.options].some(o=>o.value===old))select.value=old;
 const cards=[];
 for(const [id,input] of flatInputs){
  if(input.controlKind==='cover_button'){
   const card=document.createElement('div');card.className='track-card';
   const title=document.createElement('strong');title.textContent=input.label;
   const state=document.createElement('p');state.textContent=`Cover button · ${input.actionState?.phase||'waiting'} · ${input.actionState?.presses||0} presses · ${input.target}`;
   card.append(title,state);cards.push(card);continue;
  }
  const item=tracked.find(o=>o.observation.object_id===id),fresh=item?.observation.tracking_state==='tracked'&&item.motion&&performance.timeOrigin+performance.now()-cameras.top.acceptedSample<250;
  let value=fresh?flatValue(item.motion.center_px,[cameras.top.canvas.width,cameras.top.canvas.height],input.mode,input.range):null;
  if(value&&typeof euroStep==='function'){
   const stamp=cameras.top.acceptedSample;input.filters=input.filters||{};
   if(input.filterStamp!==stamp){for(const key of Object.keys(value))if(typeof value[key]==='number')input.filters[key]=euroStep(input.filters[key],value[key],stamp,{minCutoff:3,beta:25});input.filterStamp=stamp;}
   value={...value};for(const key of Object.keys(input.filters))if(key in value)value[key]=input.filters[key].value;
  }else if(performance.timeOrigin+performance.now()-(input.continuity?.seen||0)>1000){input.filters={};input.filterStamp=null;}
  input.current=value;
  if(value&&input.mode==='xy'&&!input.origin)input.origin=[value.x,value.y];
  let yaw=fresh?item.orientation?.rotation_degrees:null;
  if(yaw!=null)yaw-=input.demoYawZero||0;
  if(yaw!=null&&typeof euroStep==='function'){if(input.yawStamp!==cameras.top.acceptedSample){input.yawFilter=euroStep(input.yawFilter,yaw,cameras.top.acceptedSample,{minCutoff:2,beta:.1});input.yawStamp=cameras.top.acceptedSample;}yaw=input.yawFilter.value;}else input.yawFilter=null;
  input.filteredYaw=yaw;
  const now=performance.timeOrigin+performance.now();
  const card=document.createElement('div');card.className='track-card';card.style.borderColor='#f2dd83';
  const title=document.createElement('strong');title.textContent=`${input.label} · overhead-only ${input.mode==='xy'?'2D input':'slider'}`;
  const output=document.createElement('p');output.textContent=!value?'Not visible · input inactive':input.mode==='xy'?`X ${(value.x*100).toFixed(1)}% · Y ${(value.y*100).toFixed(1)}%`:`Value ${(value.value*100).toFixed(1)}%${value.calibrated?' · calibrated travel':' · full camera axis'}`;
  const gauge=document.createElement('canvas');gauge.width=240;gauge.height=input.mode==='xy'?220:34;
  const ctx=gauge.getContext('2d');ctx.fillStyle='#101b13';ctx.fillRect(0,0,gauge.width,gauge.height);ctx.strokeStyle='#536247';ctx.strokeRect(5,5,gauge.width-10,gauge.height-10);
  if(input.mode==='xy'){
   const cx=120,cy=110,radius=80;ctx.strokeStyle='#536247';ctx.lineWidth=2;ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);ctx.stroke();
   ctx.beginPath();ctx.moveTo(cx-radius,cy);ctx.lineTo(cx+radius,cy);ctx.moveTo(cx,cy-radius);ctx.lineTo(cx,cy+radius);ctx.stroke();
   let target=value?(input.pivot?canStick(value,input.origin,input.gain||30,{x:$('flip-top').checked,y:$('flip-y').checked}):joystickValue(value,input.origin)):null;
   if(input.gameSlide?.flight)target=gameSlideVector(fresh?flightTopPoint(item,cameras.top.canvas.width,cameras.top.canvas.height):null,input.gameSlide.origin,input.gameSlide,now,cameras.top.acceptedSample);
   else if(input.gameSlide)target=gameSlideVector(fresh?{x:item.motion.center_px[0]/cameras.top.canvas.width,y:1-item.motion.center_px[1]/cameras.top.canvas.height}:null,input.origin,input.gameSlide,now,cameras.top.acceptedSample);
   let sample=cameras.top.acceptedSample;
   input.poseMode=!!(input.pivot&&['can','bottle','cup'].includes(item?.object_label)&&!studioDemo);
   if(input.poseMode)target=stepStickPose(input,fresh?item.control_features:null,sample,{x:$('flip-top').checked,y:$('flip-y').checked});
   if(input.pivot&&item&&!input.poseMode){
    const sides=objects('front').filter(o=>o.skeleton&&o.observation.tracking_state==='tracked'&&compatible(o.object_label,item.object_label));
    const tops=tracked.filter(o=>o.observation.tracking_state==='tracked'&&compatible(o.object_label,item.object_label));
    if(sides.length===1&&tops.length<=1&&now-cameras.front.acceptedSample<150){
     const tilt=tiltStick(input,sides[0],cameras.front.acceptedSample);
     if(tilt!==null){sample=Math.max(sample,cameras.front.acceptedSample);const y=Math.abs(tilt)>Math.abs(target?.y||0)?tilt:(target?.y||0);target={x:target?.x||0,y};const len=Math.max(1,Math.hypot(target.x,target.y));target.x/=len;target.y/=len;target.direction=Math.hypot(target.x,target.y)>.1?Math.atan2(target.x,target.y)*180/Math.PI:null;}
    }
   }
   input.continuity=input.continuity||{};input.joystick=input.gameSlide?target:stickContinuity(input.continuity,target,now,sample);input.controlActive=!!input.joystick;input.bridging=!!input.joystick&&!target;
   if(input.joystick){
    const px=cx+input.joystick.x*radius,py=cy-input.joystick.y*radius;
    ctx.strokeStyle='#f2dd83';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(px,py);ctx.stroke();ctx.fillStyle='#f2dd83';ctx.beginPath();ctx.arc(px,py,12,0,Math.PI*2);ctx.fill();
    if(yaw!=null){const angle=yaw*Math.PI/180-Math.PI/2;ctx.strokeStyle='#9dcaeb';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.cos(angle)*(radius+14),cy+Math.sin(angle)*(radius+14));ctx.stroke();}
   }
  }else if(value){ctx.fillStyle='#f2dd83';ctx.beginPath();ctx.arc(8+value.value*224,17,5,0,Math.PI*2);ctx.fill();}
  const rotation=document.createElement('p');rotation.textContent=yaw==null?'Rotation unavailable · add a visible mark/texture; re-zero after a loss':`Relative yaw / rotation: ${yaw.toFixed(1)}° clockwise`;
  if(input.mode==='xy')input.keys=stickKeys(input.joystick,input.keys,input.controlActive);
  card.append(title,output,gauge,rotation);
  const recenter=document.createElement('button');recenter.textContent='Center stick / zero rotation';recenter.disabled=!fresh;recenter.addEventListener('click',async()=>{if(value&&input.mode==='xy')input.origin=[value.x,value.y];if(input.poseMode)beginStickNeutral(input);input.sideId=null;input.continuity={};try{await api('/api/rotation/reset',{object_id:id},'top');input.yawFilter=null;input.yawStamp=null;}catch(err){error(err.message);}renderFlatInputs();});card.append(recenter);
  if(input.mode!=='xy')for(const end of [0,1]){const button=document.createElement('button');button.textContent=`Set ${end?'100':'0'}% here`;button.disabled=!fresh;button.addEventListener('click',()=>{const center=item.motion.center_px,size=[cameras.top.canvas.width,cameras.top.canvas.height],raw=flatValue(center,size,'xy');input.range=input.range||[0,1];input.range[end]=input.mode==='y'?raw.y:raw.x;input.filters={};input.filterStamp=null;renderFlatInputs();});card.append(button);}
  const remove=document.createElement('button');remove.textContent='Remove input';remove.addEventListener('click',async()=>{if(typeof removeDJSource==='function')await removeDJSource(id);flatInputs.delete(id);dismissedFlatInputs.add(id);card.remove();});card.append(remove);cards.push(card);
 }
 $('flat-tracks').replaceChildren(...cards);
}
$('flat-add').addEventListener('click',async()=>{
 const id=$('flat-object').value,item=objects('top').find(o=>o.observation.object_id===id);if(!item)return;
 if($('flat-mode').value==='button'){void assignDetectedButton({id,name:`${item.object_label} #${item.number}`});return;}
 if(typeof removeDJSource==='function')await removeDJSource(id);
 flatInputs.set(id,{mode:$('flat-mode').value,pivot:$('flat-mode').value==='xy',label:`${item.object_label} #${item.number}`,range:null});
 if($('flat-mode').value==='xy'&&typeof useOverheadJoystick==='function')void useOverheadJoystick();
 const pair=pairs.find(p=>p.top===id);if(pair)pairs.splice(pairs.indexOf(pair),1);
 renderFlatInputs();
});

setInterval(()=>{if(running)renderFlatInputs();},33);

$('can-joystick').addEventListener('click',()=>{if(typeof useOverheadJoystick==='function')void useOverheadJoystick();canJoystickArmed=true;renderFlatInputs();canJoystickArmed=false;});
