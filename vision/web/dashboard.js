'use strict';
let studioFilter='all',studioDemo=false,demoTimer=null;
if(location.pathname.endsWith('/fusion.html')){$('start').disabled=true;$('start').textContent='Static preview · cameras off';$('start').title='Run python -m vision.live and open localhost:8765 for live capture.';}
const studioCards=new Map();
function registryItems(){
 const now=performance.timeOrigin+performance.now(),overhead=objects('top');
 const inputs=[...flatInputs].map(([id,input])=>{const item=overhead.find(o=>o.observation.object_id===id);return {key:'input:'+id,id,type:input.controlKind==='cover_button'?'button':input.mode==='xy'?'joystick':'slider',name:input.label,input,item,active:input.controlKind==='cover_button'?['ready','covering','pressed'].includes(input.actionState?.phase):input.mode==='xy'?!!input.controlActive:!!(item?.motion&&item.observation.tracking_state==='tracked'&&now-cameras.top.acceptedSample<250),yaw:input.filteredYaw??item?.orientation?.rotation_degrees??null};});
 const spatial=pairs.map(pair=>({key:'pair:'+pair.number,type:'object',name:`Object ${pair.number} · ${pair.label}`,pair,active:!!(pair.position&&pair.visual),yaw:find('top',pair.top)?.orientation?.rotation_degrees??null}));
 const used=new Set([...flatInputs.keys(),...pairs.map(p=>p.top)]);
 const possible=overhead.filter(item=>!used.has(item.observation.object_id)&&item.observation.tracking_state==='tracked').map(item=>({key:'candidate:'+item.observation.object_id,id:item.observation.object_id,item,type:'candidate',name:`${item.object_label} #${item.number}`,active:true,yaw:item.orientation?.rotation_degrees??null}));
 return [...inputs,...spatial,...possible];
}
function createStudioCard(key){
 const el=document.createElement('article');el.className='studio-card';
 el.innerHTML='<div class="card-top"><span class="card-type"></span><span class="card-state"></span></div><h3></h3><div class="card-visuals"><canvas class="control-visual" width="260" height="200"></canvas><canvas class="proxy-visual" width="160" height="150" aria-label="Object proxy representation"></canvas></div><span class="proxy-caption">3D proxy · not a reconstructed scan</span><div class="card-values"></div><p class="rotation-value"></p><div class="key-display" aria-label="Virtual joystick key states"><kbd data-key="W">W</kbd><div><kbd data-key="A">A</kbd><kbd data-key="S">S</kbd><kbd data-key="D">D</kbd></div></div><div class="card-actions"></div>';
 const card={el,type:el.querySelector('.card-type'),state:el.querySelector('.card-state'),title:el.querySelector('h3'),control:el.querySelector('.control-visual'),proxy:el.querySelector('.proxy-visual'),values:el.querySelector('.card-values'),rotation:el.querySelector('.rotation-value'),actions:el.querySelector('.card-actions'),item:null};
 studioCards.set(key,card);$('control-registry').append(el);return card;
}
function action(card,label,fn,disabled=false){if(!card.rebuild){const existing=card.actions.children[card.actionIndex++];if(existing)existing.disabled=disabled;return;}card.actionIndex++;const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.addEventListener('click',()=>fn(card.item));card.actions.append(b);}
function assignInput(entry,mode){if(mode==='xy'&&typeof useOverheadJoystick==='function')void useOverheadJoystick();flatInputs.set(entry.id,{mode,pivot:mode==='xy',label:entry.name,range:null});const p=pairs.find(p=>p.top===entry.id);if(p)pairs.splice(pairs.indexOf(p),1);candidates.clear();renderFlatInputs();updateStudio();}
function updateStudio(){
 const items=registryItems(),keys=new Set(items.map(x=>x.key));
 for(const [key,card] of studioCards)if(!keys.has(key)){card.el.remove();studioCards.delete(key);}
 $('count-sliders').textContent=items.filter(x=>x.type==='slider').length;
 $('count-joysticks').textContent=items.filter(x=>x.type==='joystick').length;
 $('count-objects').textContent=items.filter(x=>x.type==='object').length;
 if($('count-buttons'))$('count-buttons').textContent=items.filter(x=>x.type==='button').length;
 $('count-active').textContent=items.filter(x=>x.active&&x.type!=='candidate').length;
 $('studio-stop').disabled=!running;
 if(!running)$('model-info').textContent=studioDemo?'Simulated layout preview · no vision model running':'YOLOE Extra Large · offline';
 $('studio-state').textContent=studioDemo?'DEMO · SIMULATED':running?'LIVE':'CAMERAS OFF';
 $('studio-state').classList.toggle('is-live',running&&!studioDemo);
 for(const entry of items){
  const card=studioCards.get(entry.key)||createStudioCard(entry.key);card.item=entry;
  card.el.hidden=studioFilter!=='all'&&entry.type!==studioFilter;
  card.type.textContent={button:'COVER BUTTON',slider:'LINEAR INPUT',joystick:'JOYSTICK / 2D INPUT',object:'SPATIAL OBJECT',candidate:'AVAILABLE OVERHEAD TRACK'}[entry.type];
  card.state.textContent=entry.active?(entry.input?.bridging?'Brief gap · easing':'Active'):running?'Waiting for object':'Offline';card.state.className='card-state '+(entry.active?'active':'');
  card.title.textContent=entry.name;
  if(entry.input?.poseMode&&!entry.active)card.state.textContent=entry.input.poseCalibration?.phase==='ready'?'Waiting for can':'Calibrating upright / directions';
  const keyPanel=card.el.querySelector('.key-display');keyPanel.hidden=entry.type!=='joystick';
  for(const key of keyPanel.querySelectorAll('[data-key]')){const down=!!(entry.active&&entry.input?.keys?.[key.dataset.key]);key.classList.toggle('pressed',down);key.setAttribute('aria-label',`${key.dataset.key} ${down?'pressed':'released'}`);}
  card.rotation.textContent=entry.yaw!==null&&entry.active?`YAW / ROTATION  ${entry.yaw.toFixed(1)}° CW`:'YAW / ROTATION  —  Needs visible texture or a mark';
  const yaw=entry.active?entry.yaw:null;
  drawObjectProxy(card.proxy,{kind:entry.type==='object'?'bottle':'disk',yaw,active:entry.active,color:entry.type==='slider'?'#efca90':'#a9e9cf'});
  const ctx=card.control.getContext('2d'),w=260,h=200;ctx.clearRect(0,0,w,h);
  ctx.fillStyle='#101a1c';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#2b4447';ctx.lineWidth=1;
  card.rebuild=card.kind!==entry.type;card.actionIndex=0;if(card.rebuild)card.actions.replaceChildren();card.kind=entry.type;
  if(entry.type==='button'){
   const state=entry.input.actionState||{},pressed=state.phase==='pressed';
   ctx.fillStyle=pressed?'#f2dd83':'#344037';ctx.beginPath();ctx.arc(130,100,65,0,Math.PI*2);ctx.fill();
   ctx.fillStyle=pressed?'#101512':'#edf2e9';ctx.font='18px sans-serif';ctx.textAlign='center';ctx.fillText(pressed?'PRESSED':'COVER',130,106);ctx.textAlign='start';
   card.values.textContent=`${state.phase||'waiting'} · ${state.presses||0} presses`;
   card.rotation.textContent='Hand-confirmed cover → one key press. Uncover the stationary target to reset.';
   action(card,'Re-arm / learn clear view',()=>void armRealKeys(entry.id).catch(err=>keyStatus(err.message)));
  }else if(entry.type==='joystick'){
   const i=entry.input,value=i.current,stick=i.joystick;
   ctx.beginPath();ctx.arc(130,100,74,0,Math.PI*2);ctx.moveTo(45,100);ctx.lineTo(215,100);ctx.moveTo(130,15);ctx.lineTo(130,185);ctx.stroke();
   if(entry.active&&stick){const x=130+stick.x*74,y=100-stick.y*74;ctx.strokeStyle='#a9e9cf';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(130,100);ctx.lineTo(x,y);ctx.stroke();ctx.fillStyle='#a9e9cf';ctx.beginPath();ctx.arc(x,y,12,0,Math.PI*2);ctx.fill();}
   if(yaw!==null){const a=(yaw-90)*Math.PI/180;ctx.strokeStyle='#9dcfff';ctx.lineWidth=3;ctx.beginPath();ctx.arc(130,100,87,-Math.PI/2,a,a< -Math.PI/2);ctx.stroke();ctx.fillStyle='#9dcfff';ctx.beginPath();ctx.arc(130+Math.cos(a)*87,100+Math.sin(a)*87,4,0,Math.PI*2);ctx.fill();}
   card.values.textContent=entry.active&&stick?`X ${stick.x.toFixed(2)}     Y ${stick.y.toFixed(2)}${stick.direction!=null?' · stick heading '+stick.direction.toFixed(0)+'°':''}`:'X —     Y —';
   if(i.pivot){const sides=objects('front').filter(o=>o.skeleton&&compatible(o.object_label,entry.item?.object_label||'can'));const lean=sides.length===1?sides[0].skeleton.projected_lean_degrees:null;card.rotation.textContent=`BASE → TOP PIVOT${lean!=null?' · side lean '+lean.toFixed(1)+'°':''} · ${yaw!=null?'twist '+yaw.toFixed(1)+'°':'twist not visible'}`;}
   if(i.poseMode)card.rotation.textContent=`${i.calibrationStatus||'Calibrate upright'} · ${yaw!=null?'twist '+yaw.toFixed(1)+'°':'twist unavailable'}`;
   const canPose=i.pivot&&['can','bottle','cup'].includes(entry.item?.object_label)&&!studioDemo;
   const visible=!!entry.item?.control_features&&entry.item.observation.tracking_state==='tracked';
   action(card,'Calibrate upright (1s)',e=>{beginStickNeutral(e.input);renderFlatInputs();},!canPose||!visible);
   action(card,'Learn W',e=>{beginStickDirection(e.input,'W');renderFlatInputs();},!canPose||!i.neutralPose||!visible||i.poseCalibration?.phase!=='ready');
   action(card,'Learn D',e=>{beginStickDirection(e.input,'D');renderFlatInputs();},!canPose||!i.neutralPose||!i.directionBasis?.W||!visible||i.poseCalibration?.phase!=='ready');
   action(card,'Use pivot / WASD',e=>{e.input.pivot=true;if(e.input.current)e.input.origin=[e.input.current.x,e.input.current.y];if(e.input.poseMode)beginStickNeutral(e.input);e.input.sideId=null;e.input.continuity={};e.input.keys=stickKeys(null,{},false);renderFlatInputs();});
   action(card,'Center & zero yaw',async e=>{if(e.input.current)e.input.origin=[e.input.current.x,e.input.current.y];if(studioDemo)e.input.demoYawZero=e.item.orientation?.rotation_degrees||0;else try{await api('/api/rotation/reset',{object_id:e.id},'top');}catch(err){error(err.message);}if(e.input.poseMode)beginStickNeutral(e.input);e.input.sideId=null;e.input.continuity={};e.input.yawFilter=null;e.input.yawStamp=null;renderFlatInputs();},!entry.active);
   action(card,'Make slider',e=>assignInput(e,'x'));
  }else if(entry.type==='slider'){
   const value=entry.input.current?.value;ctx.strokeStyle='#3c4546';ctx.lineWidth=10;ctx.beginPath();ctx.moveTo(25,100);ctx.lineTo(235,100);ctx.stroke();
   for(let j=0;j<=10;j++){ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(25+j*21,116);ctx.lineTo(25+j*21,123);ctx.stroke();}
   if(entry.active&&value!=null){ctx.strokeStyle='#efca90';ctx.lineWidth=10;ctx.beginPath();ctx.moveTo(25,100);ctx.lineTo(25+value*210,100);ctx.stroke();ctx.fillStyle='#efca90';ctx.fillRect(18+value*210,80,14,40);}
   card.values.textContent=entry.active&&value!=null?`${(value*100).toFixed(1)}% · ${entry.input.mode==='x'?'horizontal':'vertical'}`:'— · input inactive';
   for(const end of [0,1])action(card,`Set ${end*100}%`,e=>{const raw=flatValue(e.item.motion.center_px,[cameras.top.canvas.width,cameras.top.canvas.height],'xy');e.input.range=e.input.range||[0,1];e.input.range[end]=e.input.mode==='y'?raw.y:raw.x;e.input.filters={};e.input.filterStamp=null;renderFlatInputs();},!entry.active);
   action(card,'X ↔ Y',e=>{e.input.mode=e.input.mode==='x'?'y':'x';e.input.range=null;});
   action(card,'Make joystick',e=>assignInput(e,'xy'));
  }else if(entry.type==='object'){
   drawObjectProxy(card.control,{kind:'bottle',yaw,active:entry.active,color:colors[(entry.pair.number-1)%colors.length]});
   card.values.textContent=entry.active?formatSpatialPosition(entry.pair):'Waiting for both camera views';
   action(card,'Use as joystick',e=>assignInput({id:e.pair.top,name:e.name},'xy'));
   action(card,'Unpair',e=>{pairs.splice(pairs.indexOf(e.pair),1);candidates.clear();updateStudio();});
  }else{
   drawObjectProxy(card.control,{kind:entry.item.object_label==='disk'?'disk':'object',yaw,active:true});
   card.values.textContent='Choose how this object behaves';
   action(card,'Add joystick',e=>assignInput(e,'xy'));action(card,'Add slider',e=>assignInput(e,'x'));
  }
  if(['joystick','slider','button'].includes(entry.type))action(card,'Remove',e=>{flatInputs.delete(e.id);dismissedFlatInputs.add(e.id);updateStudio();});
 }
 let empty=$('registry-empty');if(!empty){empty=document.createElement('div');empty.id='registry-empty';empty.className='registry-empty';$('control-registry').append(empty);}
 empty.hidden=items.some(e=>studioFilter==='all'||e.type===studioFilter);
 empty.textContent=studioFilter!=='all'?`No ${studioFilter==='object'?'3D objects':studioFilter==='slider'?'sliders':'joysticks'} configured yet. Choose All controls to assign a tracked object.`:running?'Move an object briefly under the overhead camera. New tracks appear here.':'Your controls will appear here. Start cameras when ready, or preview the layout without camera access.';
}
for(const button of document.querySelectorAll('[data-filter]'))button.addEventListener('click',()=>{studioFilter=button.dataset.filter;for(const b of document.querySelectorAll('[data-filter]'))b.setAttribute('aria-pressed',String(b===button));updateStudio();});
function clearStudioDemo(){
 if(!studioDemo)return;clearInterval(demoTimer);studioDemo=false;flatInputs.clear();pairs.length=0;candidates.clear();for(const role of roles)cameras[role].result=null;$('preview-layout').textContent='Demo controls';updateStudio();draw();
}
$('studio-stop').addEventListener('click',()=>stop());
$('start').addEventListener('click',clearStudioDemo,{capture:true});
$('preview-layout').addEventListener('click',()=>{
 if(running){const panel=document.querySelector('.camera-drawer');panel.open=true;panel.scrollIntoView({behavior:'smooth',block:'start'});error('Your live cameras are below. Demo controls are simulated; stop cameras first if you want the demo.');return;}if(studioDemo){clearStudioDemo();return;}
 studioDemo=true;$('preview-layout').textContent='Exit preview';const began=performance.now();
 for(let i=1;i<=3;i++)flatInputs.set('demo'+i,{mode:i===1?'x':i===2?'y':'xy',label:['','Travel slider','Vertical slider','Rotary joystick'][i],range:null});
 const pair={front:'demo-side',top:'demo4',number:1,label:'Spatial object',confirmed:true,position:[0,0,0],visual:[0,0,0],points:[],state:'tracked'};pairs.push(pair);
 const tick=()=>{const t=(performance.now()-began)/1000;const make=(id,n,x,y)=>({number:n,object_label:'disk',observation:{object_id:id,tracking_state:'tracked'},motion:{center_px:[x,y]},orientation:{rotation_degrees:Math.sin(t*.7)*90}});
 cameras.top.canvas.width=640;cameras.top.canvas.height=480;cameras.top.acceptedSample=performance.timeOrigin+performance.now();
 cameras.top.result={objects:[make('demo1',1,320+Math.sin(t)*220,240),make('demo2',2,300,240+Math.sin(t*.7)*160),make('demo3',3,320+Math.cos(t)*70,240+Math.sin(t)*70),make('demo4',4,320,240)]};
 pair.position=[Math.sin(t)*15,Math.cos(t)*12,Math.sin(t*.7)*10];pair.visual=pair.position;pair.points.push(pair.position);if(pair.points.length>120)pair.points.shift();renderFlatInputs();updateStudio();draw();};tick();demoTimer=setInterval(tick,100);
});
setInterval(updateStudio,33);updateStudio();
