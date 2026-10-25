'use strict';
// Reusable game profiles. Runtime object IDs and output tokens are deliberately session-only.
const FLIGHT_DEADZONE=.35;
const GAME_MODULES=Object.freeze({
 'flight-stick':{label:'Flight simulator · joystick',slide:true,flight:true,bindings:{up:'a',down:'d',left:'w',right:'s'},help:'First detection locks the reference point. Move the can top relative to this point. Pull back for W, push forward for S, left for A and right for D. Keys stay held while deflected; return to neutral to release. Diagonal deflection holds both axes.'},
 'subway-slide':{label:'Subway City · flick detector',slide:true,movement:true,bindings:{up:'left',down:'right',left:'down',right:'up'},help:'Move left/right to change lanes, forward to jump, back to roll. One swipe per deliberate flick. Continued motion does not repeat. Settle briefly to prepare the next flick, or reverse clearly to dodge back.'},
 'subway-tilt':{label:'Subway City · can tilt',slide:false,bindings:{up:'up',down:'down',left:'left',right:'right'},help:'Keep the can base fixed. Tilt for arrow-key swipes: left/right change lanes, up jumps, down rolls. Return upright between gestures.'},
 'can-slide-wasd':{label:'Can D-pad · WASD',slide:true,bindings:{up:'a',down:'d',left:'s',right:'w'},help:'First detection fixes the center permanently. Move the object into W/A/S/D boxes to hold a key. Center, outside all five boxes, or lost tracking releases it. Reset first-scan anchor is the only way to move the center.'}
});
function fixedZoneBoxes(origin,width,height){
 return Object.entries({center:[0,0],up:[0,1],down:[0,-1],left:[-1,0],right:[1,0]}).map(([name,[dx,dy]])=>({name,x:origin[0]+(dx-.5)*width,y:origin[1]+(dy-.5)*height,width,height}));
}
function fixedZoneAt(value,origin,width,height){
 if(!value||!origin||![value.x,value.y,...origin,width,height].every(Number.isFinite)||width<=0||height<=0)return null;
 return fixedZoneBoxes(origin,width,height).find(b=>value.x>=b.x&&value.x<b.x+b.width&&value.y>=b.y&&value.y<b.y+b.height)?.name||null;
}
function movementSwipeVector(value,state,now,sample){
 const zero={x:0,y:0,direction:null};
 if(!value||![value.x,value.y,now,sample].every(Number.isFinite)){state.motion=null;state.phase='lost';state.zone=null;return null;}
 const tx=state.thresholdX||.024,ty=state.thresholdY||.024;
 let m=state.motion;
 if(!m||sample-m.sample>250||sample<m.sample){m=state.motion={sample,history:[{...value,t:sample}],phase:'ready',until:0,next:0,x:0,y:0,peak:{...value}};}
 else if(sample!==m.sample){
  m.sample=sample;m.history.push({...value,t:sample});
  while(m.history.length>1&&sample-m.history[0].t>180)m.history.shift();
  const first=m.history[0],dx=(value.x-first.x)/tx,dy=(value.y-first.y)/ty;
  const settle=m.history.filter(p=>sample-p.t<=150);
  const quiet=settle.length>=3&&sample-settle[0].t>=110&&
   (Math.max(...settle.map(p=>p.x))-Math.min(...settle.map(p=>p.x)))/tx<.15&&
   (Math.max(...settle.map(p=>p.y))-Math.min(...settle.map(p=>p.y)))/ty<.15;
  let fire=null;
  if(m.phase==='ready'){
   if(Math.max(Math.abs(dx),Math.abs(dy))>=1)fire=Math.abs(dx)>Math.abs(dy)?[Math.sign(dx),0]:[0,Math.sign(dy)];
  }else{
   // Follow the furthest point of the current flick. A deliberate reverse flick
   // must travel a full threshold back from that peak, not just jitter backwards.
   if((value.x-m.peak.x)/tx*m.x+(value.y-m.peak.y)/ty*m.y>0)m.peak={...value};
   const reverse=-((value.x-m.peak.x)/tx*m.x+(value.y-m.peak.y)/ty*m.y);
   const sideways=Math.abs((value.x-m.peak.x)/tx*m.y-(value.y-m.peak.y)/ty*m.x);
   if(now>=m.next&&reverse>=1&&reverse>sideways*1.3)fire=[-m.x,-m.y];
   else if(quiet&&now>=m.next){m.phase='ready';m.history=[{...value,t:sample}];}
   else m.phase=quiet?'settling':'moving';
  }
  if(fire){[m.x,m.y]=fire;m.until=now+80;m.next=now+160;m.peak={...value};m.phase='moving';state.strokes=(state.strokes||0)+1;}
 }
 state.phase=m.phase;
 const active=now<m.until,x=active?m.x*(state.flipX?-1:1):0,y=active?m.y*(state.flipY?-1:1):0;
 state.zone=x>0?'right':x<0?'left':y>0?'up':y<0?'down':null;
 return {x,y,direction:x||y?Math.atan2(x,y)*180/Math.PI:null};
}
let flightAnchor=null;
function flightTopPoint(item,width,height){
 const point=item?.skeleton?.top_px|| (item?.control_features?[item.control_features.cx,item.control_features.cy]:item?.motion?.center_px);
 return point&&point.every(Number.isFinite)?{x:point[0]/width,y:1-point[1]/height}:null;
}
function captureFlightAnchor(item){
 const camera=$('camera-top').value;
 if(flightAnchor?.camera===camera)return flightAnchor;
 const c=cameras.top,point=flightTopPoint(item,c.canvas.width,c.canvas.height);if(!point)return null;
 const [x,y,x2,y2]=item.observation.bbox_xyxy;
 flightAnchor={camera,origin:[point.x,point.y],width:Math.max(.03,(x2-x)/c.canvas.width),height:Math.max(.03,(y2-y)/c.canvas.height)};
 return flightAnchor;
}
function drawFlightOverlay(ctx,canvas){
 if(!$('game-overlay').checked||!flightAnchor)return;
 const item=objects('top').find(o=>o.observation.object_id===gameModuleObject&&o.observation.tracking_state==='tracked');
 const fresh=item&&performance.timeOrigin+performance.now()-cameras.top.acceptedSample<250;
 const top=fresh?flightTopPoint(item,canvas.width,canvas.height):null;
 const input=flatInputs.get(gameModuleObject),scale=Number($('game-travel').value)/100;
 const settings=input?.gameSlide||{width:flightAnchor.width*scale,height:flightAnchor.height*scale};
 const vector=top?flightStickVector(top,flightAnchor.origin,settings):null;
 const cx=flightAnchor.origin[0]*canvas.width,cy=(1-flightAnchor.origin[1])*canvas.height;
 ctx.save();ctx.setLineDash([]);ctx.lineWidth=3;ctx.strokeStyle='#ffdc64';ctx.fillStyle='#ffdc64';ctx.font='bold 16px sans-serif';
 ctx.beginPath();ctx.arc(cx,cy,6,0,Math.PI*2);ctx.fill();ctx.fillText('FIXED FIRST POINT',cx+10,cy-12);
 ctx.strokeRect(cx-settings.width*canvas.width*FLIGHT_DEADZONE,cy-settings.height*canvas.height*FLIGHT_DEADZONE,settings.width*canvas.width*FLIGHT_DEADZONE*2,settings.height*canvas.height*FLIGHT_DEADZONE*2);
 if(top){const x=top.x*canvas.width,y=(1-top.y)*canvas.height;ctx.strokeStyle='#67ffa7';ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x,y);ctx.stroke();ctx.fillStyle='#ff75d2';ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();ctx.fillText('CAN TOP',x+10,y);}
 const bindings=GAME_MODULES['flight-stick'].bindings,keys=vector?[vector.x>FLIGHT_DEADZONE?bindings.right:vector.x< -FLIGHT_DEADZONE?bindings.left:null,vector.y>FLIGHT_DEADZONE?bindings.up:vector.y< -FLIGHT_DEADZONE?bindings.down:null].filter(Boolean):[];
 ctx.fillStyle='#fff';ctx.fillText('FLIGHT · '+(top?(keys.join(' + ').toUpperCase()||'NEUTRAL'):'TRACKING LOST · RELEASED'),12,24);
 if(top)ctx.fillText('Top displacement: '+Math.round(Math.hypot(top.x*canvas.width-cx,(1-top.y)*canvas.height-cy))+' px',12,46);
 ctx.restore();
}
function flightStickVector(value,origin,settings){
 if(!value||!origin)return null;
 const x=(value.x-origin[0])/(settings.width||.05),y=(value.y-origin[1])/(settings.height||.05);
 const magnitude=Math.max(Math.abs(x),Math.abs(y));if(!Number.isFinite(magnitude))return null;
 return {x:Math.max(-1,Math.min(1,x)),y:Math.max(-1,Math.min(1,y)),direction:magnitude>FLIGHT_DEADZONE?Math.atan2(x,y)*180/Math.PI:null};
}
function gameSlideVector(value,origin,settings,now=0,sample=now){
 if(settings.flight)return flightStickVector(value,origin,settings);
 if(settings.movement)return movementSwipeVector(value,settings,now,sample);
 const zone=fixedZoneAt(value,settings.origin||origin,settings.width||settings.travel,settings.height||settings.travel);
 settings.zone=zone;
 const [x,y]=({up:[0,1],down:[0,-1],left:[-1,0],right:[1,0]})[zone]||[0,0];
 return value?{x:x*(settings.flipX?-1:1),y:y*(settings.flipY?-1:1),direction:x||y?Math.atan2(x,y)*180/Math.PI:null}:null;
}
let fixedGameAnchor=null;
function captureGameAnchor(item){
 const c=cameras.top,camera=$('camera-top').value;
 if(fixedGameAnchor?.camera===camera)return fixedGameAnchor;
 try{const saved=JSON.parse(sessionStorage.getItem('fixed-game-anchor'));if(saved?.camera===camera&&saved.origin?.length===2){fixedGameAnchor=saved;return saved;}}catch(_){}
 if(!item?.motion||!c.canvas.width||!c.canvas.height)return null;
 const [x,y,x2,y2]=item.observation.bbox_xyxy;
 fixedGameAnchor={camera,origin:[item.motion.center_px[0]/c.canvas.width,1-item.motion.center_px[1]/c.canvas.height],width:Math.max(.03,(x2-x)/c.canvas.width*1.3),height:Math.max(.03,(y2-y)/c.canvas.height*1.3)};
 sessionStorage.setItem('fixed-game-anchor',JSON.stringify(fixedGameAnchor));
 return fixedGameAnchor;
}
function drawGameZones(ctx,canvas){
 if(GAME_MODULES[$('game-module').value].flight){drawFlightOverlay(ctx,canvas);return;}
 if(!$('game-overlay').checked||!fixedGameAnchor||fixedGameAnchor.camera!==$('camera-top').value)return;
 const input=flatInputs.get(gameModuleObject),anchor=fixedGameAnchor;
 const scale=Number($('game-travel').value)/100;
 const width=anchor.width*scale,height=anchor.height*scale;
 const current=objects('top').find(o=>o.observation.object_id===gameModuleObject&&o.observation.tracking_state==='tracked');
 const fresh=current&&performance.timeOrigin+performance.now()-cameras.top.acceptedSample<250;
 const value=fresh?{x:current.motion.center_px[0]/canvas.width,y:1-current.motion.center_px[1]/canvas.height}:null;
 const active=input?.gameSlide?.movement?input.gameSlide.zone:fixedZoneAt(value,anchor.origin,width,height);
 const bindings=GAME_MODULES[$('game-module').value].bindings;
 ctx.save();ctx.setLineDash([]);ctx.lineWidth=3;ctx.font='bold 18px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
 for(const box of fixedZoneBoxes(anchor.origin,width,height)){
  const x=box.x*canvas.width,y=(1-box.y-box.height)*canvas.height,w=box.width*canvas.width,h=box.height*canvas.height;
  ctx.fillStyle=active===box.name?'rgba(80,255,160,.48)':'rgba(12,24,38,.28)';ctx.fillRect(x,y,w,h);ctx.strokeStyle=box.name==='center'?'#ffdc64':'#78cfff';ctx.strokeRect(x,y,w,h);
  ctx.fillStyle='#fff';ctx.fillText(box.name==='center'?'CENTER':bindings[box.name].toUpperCase(),x+w/2,y+h/2);
 }
 const cx=anchor.origin[0]*canvas.width,cy=(1-anchor.origin[1])*canvas.height;
 ctx.strokeStyle='#ffdc64';ctx.beginPath();ctx.moveTo(cx-8,cy);ctx.lineTo(cx+8,cy);ctx.moveTo(cx,cy-8);ctx.lineTo(cx,cy+8);ctx.stroke();
 if(value){ctx.fillStyle='#ff75d2';ctx.beginPath();ctx.arc(value.x*canvas.width,(1-value.y)*canvas.height,6,0,Math.PI*2);ctx.fill();}
 if(input?.gameSlide?.movement){ctx.textAlign='left';ctx.fillStyle='#fff';ctx.fillText('FLICK · '+(input.gameSlide.phase||'ready').toUpperCase()+' · '+$('game-threshold').value+'px · '+(input.gameSlide.strokes||0)+' swipes',12,24);}
 ctx.restore();
}
function gameModulePlan(profile,id){
 const module=GAME_MODULES[profile];if(!module)throw new Error('Choose a game module.');
 if(!id)throw new Error('Choose the currently visible can.');
 return {object_id:id,controller:'joystick',output:'keyboard',bindings:{...module.bindings},mode:'game',deadzone:module.flight?FLIGHT_DEADZONE:.25};
}
let gameModuleObject=null;
function gameModuleMessage(message){$('game-module-status').textContent=message;}
function gameModuleOptions(){
 const select=$('game-object'),selected=select.value;
 const now=performance.timeOrigin+performance.now();
 const items=running&&!studioDemo&&now-cameras.top.acceptedSample<250?objects('top').filter(o=>o.motion&&o.observation.tracking_state==='tracked'):[];
 const signature=items.map(o=>o.observation.object_id+o.number+o.object_label).join('|');
 if(select.dataset.items!==signature){select.replaceChildren(new Option('Choose visible can…',''),...items.map(o=>new Option(`#${o.number} ${o.object_label}`,o.observation.object_id)));select.dataset.items=signature;if(items.some(o=>o.observation.object_id===selected))select.value=selected;else if(items.length===1)select.value=items[0].observation.object_id;}
 const first=items.find(o=>o.observation.object_id===select.value);if(first){if(GAME_MODULES[$('game-module').value].flight)captureFlightAnchor(first);else if(GAME_MODULES[$('game-module').value].slide)captureGameAnchor(first);}
 const padInput=flatInputs.get(gameModuleObject),pad=padInput?.gameSlide?padInput.joystick:null;
 for(const [direction,on] of Object.entries({up:pad?.y>0,down:pad?.y<0,left:pad?.x<0,right:pad?.x>0,center:!!pad&&padInput?.gameSlide?.zone==='center'})){const cell=$('game-pad-'+direction);cell.classList.toggle('pressed',!!on);if(direction!=='center')cell.textContent=(GAME_MODULES[$('game-module').value].bindings[direction]||direction).toUpperCase();}
 if(gameModuleObject){const input=flatInputs.get(gameModuleObject),visible=items.some(o=>o.observation.object_id===gameModuleObject),armed=keyboardObject===gameModuleObject&&!!keyboardToken;
 gameModuleMessage(!visible?'Can track unavailable. Output is released; choose its current track and map again.':!armed?'Module configured · output disarmed. Click Map and arm game module to resume.':`Armed · ${input?.label} · ${$('keyboard-status').textContent}`);}
}
async function mapGameModule(fromAgent=false){
 if(!running||studioDemo)throw new Error('Start the real overhead camera first.');
 const profile=$('game-module').value,module=GAME_MODULES[profile],id=$('game-object').value;
 const threshold=Number($('game-threshold').value);if(!Number.isFinite(threshold)||threshold<3||threshold>80)throw new Error('Movement threshold must be 3–80 camera pixels.');
 const travel=Number($('game-travel').value)/100;
 if(!Number.isFinite(travel)||travel<.5||travel>3)throw new Error('Zone size must be between 50% and 300%.');
 const item=objects('top').find(o=>o.observation.object_id===id&&o.observation.tracking_state==='tracked');
 const anchor=module.flight?captureFlightAnchor(item):module.slide?captureGameAnchor(item):null;
 if(module.slide&&!anchor)throw new Error('Show an object to capture its first position.');
 if(!fromAgent)commandVersion++;
 const plan=gameModulePlan(profile,id);
 if(module.flight)plan.mode=$('keyboard-mode').value;
 await activateMorph(plan,module.help,false);
 const input=flatInputs.get(id);input.label=module.label;input.gameModule=profile;
 if(module.slide){input.pivot=false;input.poseMode=false;input.gameSlide={flight:!!module.flight,movement:!!module.movement,thresholdX:Number($('game-threshold').value)/cameras.top.canvas.width,thresholdY:Number($('game-threshold').value)/cameras.top.canvas.height,origin:[...anchor.origin],travel,width:anchor.width*travel,height:anchor.height*travel,flipX:$('game-flip-x').checked,flipY:$('game-flip-y').checked};input.origin=[...anchor.origin];input.continuity={};}
 renderFlatInputs();syncCommandTargets();$('keyboard-target').value=id;
 gameModuleObject=id;
 await armRealKeys(id);
 await sendRealKeys();
 gameModuleOptions();
}
$('game-map').addEventListener('click',()=>void mapGameModule().catch(e=>gameModuleMessage(e.message)));
$('game-stop').addEventListener('click',()=>void stopRealKeys('Game module stopped').then(()=>gameModuleMessage('Game controls stopped.')));
$('game-center').addEventListener('click',async()=>{
 await stopRealKeys('Reset fixed zones');fixedGameAnchor=null;flightAnchor=null;sessionStorage.removeItem('fixed-game-anchor');gameModuleObject=null;
 for(const input of flatInputs.values())if(input.gameSlide){input.gameSlide=null;input.joystick=null;input.controlActive=false;}
 gameModuleMessage('Anchor reset. The next detected object sets the fixed center. Map and arm to resume.');
});
for(const id of ['game-module','game-object','game-travel','game-flip-x','game-flip-y','game-threshold'])$(id).addEventListener('change',()=>{
 void stopRealKeys('Game module settings changed');$('game-module-help').textContent=GAME_MODULES[$('game-module').value].help;gameModuleMessage('Settings changed · map and arm to apply.');
});
$('game-module-help').textContent=GAME_MODULES[$('game-module').value].help;
setInterval(gameModuleOptions,200);
