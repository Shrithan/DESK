'use strict';
const $=id=>document.getElementById(id);
const roles=['front','top'];
const cameras={};
let inventory=[],world=null,mapMode='top',worldBusy=false,topTrail=[],worldTrail=[],lastTopId=null,lastAnchor=null;
let discoveryBusy=false;
for(const role of roles)cameras[role]={role,video:$(`video-${role}`),stream:null,active:false,epoch:0,timer:null,inFlight:null,lastVideoTime:-1,lastCompletion:null,result:null,failures:0,canvas:document.createElement('canvas')};
function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
async function api(path,body={},role='front',type='application/json',sample=null){
 const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),15000);
 try{
  const headers={'Content-Type':type,'X-Camera-Id':role};
  if(sample!==null)headers['X-Capture-Sample-Ms']=String(sample);
  const response=await fetch(path,{method:'POST',headers,body:type==='application/json'?JSON.stringify(body):body,signal:abort.signal});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed');return result;
 }finally{clearTimeout(timeout);}
}
function state(role,text){$(`state-${role}`).textContent=text;}
function cameraOptions(){
 const visible=inventory.filter(d=>d.kind==='videoinput'&&!/desk view/i.test(d.label));
 const phones=visible.filter(d=>/iphone|continuity/i.test(d.label));
 for(const role of roles){
  const select=$(`camera-${role}`),current=select.value;
  select.replaceChildren(new Option('Choose a distinct camera…',''));
  visible.forEach((d,i)=>select.append(new Option(d.label||`Camera ${i+1}`,d.deviceId)));
  if(visible.some(d=>d.deviceId===current))select.value=current;
  else if(phones[roles.indexOf(role)])select.value=phones[roles.indexOf(role)].deviceId;
 }
 const count=phones.length;
 $('notice').textContent=count>=2?`${count} iPhone camera sources found. Assign the front phone and the overhead phone, then connect both.`:
  `The Mac currently exposes ${count} iPhone camera source${count===1?'':'s'}. A second phone must appear separately before two-phone mapping can run. Desk View is not a second phone.`;
}
async function discover(){
 if(discoveryBusy)return;discoveryBusy=true;$('discover').disabled=true;error();
 let temporary=null;
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Use Safari or Chrome on this Mac at http://localhost:8765.');
  inventory=await navigator.mediaDevices.enumerateDevices();
  if(!inventory.some(d=>d.kind==='videoinput'&&d.label)&&!roles.some(r=>cameras[r].active)){
   temporary=await navigator.mediaDevices.getUserMedia({video:true,audio:false});
   inventory=await navigator.mediaDevices.enumerateDevices();
  }
  cameraOptions();
 }catch(err){error(err.message);}finally{temporary?.getTracks().forEach(t=>t.stop());discoveryBusy=false;$('discover').disabled=false;}
}
async function focus(role){
 const camera=cameras[role],track=camera.stream?.getVideoTracks()[0];if(!track)return;
 const caps=typeof track.getCapabilities==='function'?track.getCapabilities():{};
 const modes=caps.focusMode||[];
 const status=$(`focus-status-${role}`);
 try{
  const mode=modes.includes('continuous')?'continuous':modes.includes('single-shot')?'single-shot':null;
  if(mode){
   await track.applyConstraints({advanced:[{focusMode:mode}]});
   status.textContent=track.getSettings().focusMode===mode?`${mode} autofocus enabled`:`${mode} autofocus requested; driver has not reported its state`;
  }else status.textContent='Focus managed by iPhone · browser control unavailable';
  $(`focus-${role}`).disabled=!mode;
  if(caps.exposureMode?.includes('continuous')){
   try{await track.applyConstraints({advanced:[{exposureMode:'continuous'}]});}catch(_){}
  }
  const manual=modes.includes('manual')&&caps.focusDistance;
  $(`manual-${role}`).hidden=!manual;
  if(manual){const range=$(`distance-${role}`);range.min=caps.focusDistance.min;range.max=caps.focusDistance.max;range.step=caps.focusDistance.step||.01;range.value=track.getSettings().focusDistance??caps.focusDistance.min;}
 }catch(err){status.textContent=`Camera did not accept the focus request: ${err.message}`;}
}
async function stop(role,reset=true){
 const camera=cameras[role];camera.active=false;camera.epoch++;clearTimeout(camera.timer);
 camera.stream?.getTracks().forEach(t=>t.stop());camera.stream=null;camera.video.srcObject=null;
 if(camera.inFlight){try{await camera.inFlight;}catch(_){}}
 camera.inFlight=null;camera.result=null;
 state(role,'Not connected');$(`empty-${role}`).hidden=false;
 $(`connect-${role}`).disabled=false;$(`stop-${role}`).disabled=true;$(`focus-${role}`).disabled=true;
 $(`detection-${role}`).textContent='No object yet';$(`stats-${role}`).textContent='—';
 if(reset)try{await api('/api/reset',{},role);}catch(_){}
}
async function connect(role){
 const camera=cameras[role],id=$(`camera-${role}`).value;
 if(!id){error(`Choose the ${role} camera first. If it is missing, enable Continuity Camera on that phone and find cameras again.`);return;}
 const other=cameras[role==='front'?'top':'front'];
 const chosen=inventory.find(d=>d.deviceId===id),otherSettings=other.stream?.getVideoTracks()[0].getSettings();
 if(other.active&&(otherSettings.deviceId===id||(chosen?.groupId&&chosen.groupId===otherSettings.groupId))){error('Choose a different physical camera for each view.');return;}
 $(`connect-${role}`).disabled=true;error();await stop(role);$(`connect-${role}`).disabled=true;
 const epoch=++camera.epoch;let opened=null;
 try{
  opened=await navigator.mediaDevices.getUserMedia({audio:false,video:{deviceId:{exact:id},width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30,max:30}}});
  if(epoch!==camera.epoch){opened.getTracks().forEach(t=>t.stop());return;}
  camera.stream=opened;camera.video.srcObject=opened;await camera.video.play();
  if(epoch!==camera.epoch)return;
  await api('/api/auto',{enabled:$('auto').checked},role);
  camera.active=true;camera.lastVideoTime=-1;camera.lastCompletion=null;camera.failures=0;
  const track=opened.getVideoTracks()[0];
  track.addEventListener('ended',()=>{if(camera.active&&epoch===camera.epoch)stop(role);});
  $(`empty-${role}`).hidden=true;$(`stop-${role}`).disabled=false;
  state(role,'Live · learning scene');await focus(role);schedule(role,epoch,0);
 }catch(err){opened?.getTracks().forEach(t=>t.stop());await stop(role);error(`${role}: ${err.message}. Keep this phone locked and close other apps using its camera.`);}
 finally{if(epoch===camera.epoch)$(`connect-${role}`).disabled=false;}
}
function schedule(role,epoch,delay=16){const camera=cameras[role];clearTimeout(camera.timer);if(camera.active&&epoch===camera.epoch)camera.timer=setTimeout(()=>pump(role,epoch),delay);}
async function pump(role,epoch){
 const camera=cameras[role],video=camera.video;
 if(!camera.active||epoch!==camera.epoch)return;
 if(document.hidden||video.readyState<2||camera.lastVideoTime===video.currentTime){schedule(role,epoch);return;}
 const start=performance.now(),sample=performance.timeOrigin+start;
 camera.lastVideoTime=video.currentTime;
 const scale=Math.min(1,800/Math.max(video.videoWidth,video.videoHeight));
 const canvas=camera.canvas;canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
 canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
 camera.inFlight=(async()=>{
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.85));
  if(!blob)throw new Error('Camera frame unavailable');
  const result=await api('/api/frame',blob,role,'image/jpeg',sample);
  if(epoch!==camera.epoch||!camera.active)return;
  camera.result=result;camera.failures=0;
  const messages={learning_background:'Live · learning scene',waiting_for_motion:'Ready · move an object',confirming_motion:'Movement detected',hold_camera_still:'Keep camera still',need_more_texture:'Need clearer object details'};
  state(role,result.observation?(result.observation.tracking_state==='tracked'?`Tracking ${result.object_label||'object'}`:'Searching for same object'):messages[result.auto_status]||'Waiting for movement');
  const method=result.selection_source==='semantic_motion'?'AI object mask':result.selection_source==='automatic_motion'?'Motion fallback':result.detector;
  $(`detection-${role}`).textContent=`${method} · detail ${result.focus_sharpness??'—'}`;
  const now=performance.now(),fps=camera.lastCompletion?1000/(now-camera.lastCompletion):0;
  $(`stats-${role}`).textContent=`${fps.toFixed(1)} analysis fps · ${result.processing_ms.toFixed(0)} ms`;
  camera.lastCompletion=now;
 })();
 try{await camera.inFlight;}catch(err){if(epoch!==camera.epoch)return;camera.failures++;state(role,'Analysis interrupted');if(camera.failures>=3){await stop(role);error(`${role}: ${err.message}`);return;}}
 finally{camera.inFlight=null;}
 schedule(role,epoch,Math.max(0,1000/24-(performance.now()-start)));
}
for(const role of roles){
 $(`connect-${role}`).addEventListener('click',()=>connect(role));$(`stop-${role}`).addEventListener('click',()=>stop(role));$(`focus-${role}`).addEventListener('click',()=>focus(role));
 $(`distance-${role}`).addEventListener('change',async event=>{const track=cameras[role].stream?.getVideoTracks()[0];if(track)try{await track.applyConstraints({advanced:[{focusMode:'manual',focusDistance:Number(event.target.value)}]});$(`focus-status-${role}`).textContent='Manual focus · press Autofocus to restore';}catch(err){error(err.message);}});
}
$('discover').addEventListener('click',discover);
$('clear').addEventListener('click',async()=>{error();for(const role of roles)try{await api('/api/clear',{},role);}catch(err){error(err.message);}await api('/api/map/reset');topTrail=[];worldTrail=[];});
$('auto').addEventListener('change',async()=>{for(const role of roles)try{await api('/api/auto',{enabled:$('auto').checked},role);}catch(err){error(err.message);}});
$('reset-anchor').addEventListener('click',async()=>{try{await api('/api/map/reset');worldTrail=[];}catch(err){error(err.message);}});
$('calibration').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{const payload=JSON.parse(await file.text());await api('/api/calibration',payload);error();}catch(err){error(`Calibration: ${err.message}`);}});
$('top-map').addEventListener('click',()=>setMap('top'));
$('world-map').addEventListener('click',()=>setMap('world'));
function setMap(mode){mapMode=mode;$('top-map').setAttribute('aria-pressed',String(mode==='top'));$('world-map').setAttribute('aria-pressed',String(mode==='world'));drawMap();}
const map=$('map'),context=map.getContext('2d');
function drawMap(){
 const bounds=map.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
 if(!bounds.width||!bounds.height)return;
 map.width=Math.round(bounds.width*dpr);map.height=Math.round(bounds.height*dpr);context.scale(dpr,dpr);
 const w=bounds.width,h=bounds.height,pad=46;
 context.clearRect(0,0,w,h);context.font='12px system-ui';context.lineWidth=1;
 const line=(a,b,color='#334238')=>{context.strokeStyle=color;context.beginPath();context.moveTo(...a);context.lineTo(...b);context.stroke();};
 const dot=(p,color='#c5ef9b')=>{context.fillStyle=color;context.beginPath();context.arc(...p,7,0,Math.PI*2);context.fill();};
 if(mapMode==='top'){
  const project=uv=>[pad+uv[0]*(w-2*pad),h-pad-uv[1]*(h-2*pad)];
  for(let i=0;i<=10;i++){line(project([i/10,0]),project([i/10,1]));line(project([0,i/10]),project([1,i/10]));}
  context.fillStyle='#aab8aa';context.fillText('Image left → right',pad,h-15);context.fillText('Far edge of overhead picture',pad,24);
  const top=world?.views?.top;
  if(top?.tracked&&top.center_uv){
   if(top.contour_uv.length>2){context.beginPath();top.contour_uv.forEach((p,i)=>i?context.lineTo(...project(p)):context.moveTo(...project(p)));context.closePath();context.fillStyle='#c5ef9b20';context.fill();context.strokeStyle='#c5ef9b';context.stroke();}
   if(topTrail.length>1){context.beginPath();topTrail.forEach((p,i)=>i?context.lineTo(...project(p)):context.moveTo(...project(p)));context.strokeStyle='#9dcaeb';context.stroke();}
   const p=project(top.center_uv);dot(p);context.fillStyle='#edf2e9';context.fillText(top.label||'Moving region',Math.min(w-120,p[0]+13),Math.max(48,p[1]-13));
  }else{context.fillStyle='#aab8aa';context.textAlign='center';context.fillText(top?.connected?'Waiting for a moving object overhead':'Connect the overhead camera to start mapping',w/2,h/2);context.textAlign='left';}
 }else{
  const points=worldTrail.length?worldTrail:[[0,0,0]];
  const extent=Math.max(.25,...points.flat().map(Math.abs))*1.3,scale=Math.min(w*.35,h*.33)/extent;
  const project=([x,y,z])=>[w*.5+(x-y)*.866*scale,h*.62+(x+y)*.5*scale-z*scale];
  const origin=project([0,0,0]);
  for(let i=-4;i<=4;i++){const t=i*extent/4;line(project([t,-extent,0]),project([t,extent,0]));line(project([-extent,t,0]),project([extent,t,0]));}
  for(const [label,p,color] of [['X',[extent,0,0],'#f1b4a3'],['Y',[0,extent,0],'#c5ef9b'],['Z',[0,0,extent],'#a9d6fa']]){const q=project(p);line(origin,q,color);context.fillStyle=color;context.fillText(label+' (m)',q[0]+6,q[1]);}
  if(world?.world){if(worldTrail.length>1){context.beginPath();worldTrail.forEach((p,i)=>i?context.lineTo(...project(p)):context.moveTo(...project(p)));context.strokeStyle='#9dcaeb';context.stroke();}const p=world.world.position_m;dot(project([p.x,p.y,p.z]));}
  else{context.fillStyle='#aab8aa';context.textAlign='center';context.fillText(world?.calibration_loaded?'Waiting for matched surface features':'Load calibration to measure XYZ',w/2,35);context.textAlign='left';}
 }
 $('map-units').textContent=mapMode==='top'?'TOP CAMERA · IMAGE COORDINATES':'WORLD AXES · METERS';
 $('map-title').textContent=mapMode==='top'?'Overhead movement map':'Calibrated 3D surface point';
 $('map-status').textContent=mapMode==='top'?'Shows the overhead object’s silhouette and path. This is a 2D image map; height is unknown.':world?.status||'Waiting for camera data';
}
async function pollWorld(){
 if(worldBusy)return;worldBusy=true;
 try{
  const response=await fetch('/api/world',{cache:'no-store'});if(!response.ok)throw new Error('Mapping service unavailable');world=await response.json();
  for(const role of roles){const view=world.views[role];$(`${role}-target`).textContent=view.tracked?(view.label||'moving region'):view.connected?'Searching':'Not connected';}
  const top=world.views.top;
  if(top.tracked&&top.center_uv){if(top.object_id!==lastTopId)topTrail=[];lastTopId=top.object_id;topTrail.push(top.center_uv);if(topTrail.length>100)topTrail.shift();}else topTrail=[];
  if(world.world){if(lastAnchor!==world.world.anchor_id)worldTrail=[];lastAnchor=world.world.anchor_id;const p=world.world.position_m;worldTrail.push([p.x,p.y,p.z]);if(worldTrail.length>100)worldTrail.shift();$('xyz').textContent=[p.x,p.y,p.z].map(v=>v.toFixed(3)).join(', ');}
  else{$('xyz').textContent=world.calibration_loaded?'Unresolved':'Not calibrated';}
  drawMap();
 }catch(err){$('map-status').textContent=err.message;}finally{worldBusy=false;}
}
new ResizeObserver(drawMap).observe(map.parentElement);
setInterval(pollWorld,250);pollWorld();
window.addEventListener('pagehide',()=>{for(const role of roles){const camera=cameras[role];camera.active=false;clearTimeout(camera.timer);camera.stream?.getTracks().forEach(t=>t.stop());}});
if(navigator.mediaDevices)navigator.mediaDevices.addEventListener('devicechange',()=>{navigator.mediaDevices.enumerateDevices().then(devices=>{inventory=devices;cameraOptions();}).catch(()=>{});});
