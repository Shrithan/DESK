'use strict';
const $=id=>document.getElementById(id),video=$('source'),overlay=$('overlay'),context=overlay.getContext('2d');
const capture=document.createElement('canvas'),captureContext=capture.getContext('2d');
let stream=null,active=false,epoch=0,timer=null,inFlight=null,lastVideoTime=-1,lastCompleted=null;
const trails=new Map(),colors=['#c5ef9b','#9dcaeb','#f4ba8a','#dab4f5','#f2dd83'];
let expiry=null,failures=0,opening=false;
function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
async function api(path,body={},type='application/json'){
 const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),12000);
 try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':type,'X-Camera-Id':'front'},body:type==='application/json'?JSON.stringify(body):body,signal:abort.signal});const data=await response.json();if(!response.ok)throw new Error(data.error||'Tracker request failed');return data;}finally{clearTimeout(timeout);}
}
function wipe(){context.clearRect(0,0,overlay.width,overlay.height);$('objects').replaceChildren();}
function show(result){
 if(overlay.width!==capture.width||overlay.height!==capture.height){overlay.width=capture.width;overlay.height=capture.height;}
 clearTimeout(expiry);context.clearRect(0,0,overlay.width,overlay.height);
 const objects=result.objects||[],tracked=objects.filter(o=>o.observation.tracking_state==='tracked');
 $('state').textContent=objects.length?`${tracked.length} OBJECTS TRACKED · ${objects.length-tracked.length} RECOVERING`:'Looking for objects…';
 const cards=[];
 for(const item of objects){
  const obs=item.observation,id=obs.object_id,color=colors[(item.number-1)%colors.length];
  let history=trails.get(id);if(!history){history={points:[],state:null};trails.set(id,history);}
  const card=document.createElement('div');card.className='object-card';card.style.borderColor=color;
  const title=document.createElement('strong');title.textContent=`#${item.number} ${item.object_label}`;title.style.color=color;card.append(title);
  const detail=document.createElement('p');detail.className='small';card.append(detail);
  if(obs.tracking_state==='tracked'&&item.motion){
   if(history.state!=='tracked')history.points.push(null);
   history.points.push(item.motion.center_px);if(history.points.length>150)history.points.shift();
   const [dx,dy]=item.motion.displacement_px,speed=item.motion.speed_px_s;
   detail.textContent=`${Math.abs(dx).toFixed(0)} px ${dx<0?'left':'right'} · ${Math.abs(dy).toFixed(0)} px ${dy<0?'up':'down'} · ${speed==null?'Measuring speed':speed.toFixed(0)+' px/s'}`;
  }else detail.textContent=obs.tracking_state==='predicted'?'Brief blur · recovering…':'Out of view · looking for this object';
  history.state=obs.tracking_state;
  const plot=document.createElement('canvas');plot.width=220;plot.height=90;plot.setAttribute('aria-label',`Movement path for object ${item.number}`);
  const pc=plot.getContext('2d');pc.strokeStyle=color;pc.lineWidth=2;pc.beginPath();let pen=false;
  for(const point of history.points){if(!point){pen=false;continue;}const x=point[0]/overlay.width*220,y=point[1]/overlay.height*90;if(pen)pc.lineTo(x,y);else pc.moveTo(x,y);pen=true;}pc.stroke();card.append(plot);cards.push(card);
  if(!obs.bbox_xyxy||obs.tracking_state==='lost')continue;
  const [x,y,x2,y2]=obs.bbox_xyxy;context.strokeStyle=color;context.fillStyle=color;context.lineWidth=2;
  context.setLineDash(obs.tracking_state==='predicted'?[7,5]:[]);context.strokeRect(x,y,x2-x,y2-y);context.setLineDash([]);
  context.font='15px sans-serif';context.fillText(`#${item.number} ${item.object_label}`,x,Math.max(16,y-7));
  for(const point of obs.features){context.beginPath();context.arc(...point.pixel_xy,2,0,Math.PI*2);context.fill();}
 }
 $('objects').replaceChildren(...cards);
 expiry=setTimeout(()=>context.clearRect(0,0,overlay.width,overlay.height),350);
}
function schedule(g,delay=15){clearTimeout(timer);if(active&&g===epoch)timer=setTimeout(()=>pump(g),delay);}
async function pump(g){
 if(!active||g!==epoch)return;
 if(document.hidden||video.readyState<2||video.currentTime===lastVideoTime){schedule(g);return;}
 lastVideoTime=video.currentTime;const start=performance.now(),scale=Math.min(1,800/Math.max(video.videoWidth,video.videoHeight));
 capture.width=Math.round(video.videoWidth*scale);capture.height=Math.round(video.videoHeight*scale);captureContext.drawImage(video,0,0,capture.width,capture.height);
 inFlight=(async()=>{const blob=await new Promise(resolve=>capture.toBlob(resolve,'image/jpeg',.85));if(!blob)throw new Error('Camera frame unavailable');const result=await api('/api/frame',blob,'image/jpeg');if(g!==epoch||!active)return;show(result);const now=performance.now();$('stats').textContent=`${lastCompleted?(1000/(now-lastCompleted)).toFixed(1):'—'} tracking fps · ${result.processing_ms.toFixed(0)} ms analysis`;$('details').textContent=result.selection_source?.startsWith('semantic')?'AI object segmentation + tracking':(result.detector?.startsWith('YOLOE')?'AI object detection · no random-motion fallback':'Motion-only mode');lastCompleted=now;failures=0;})();
 try{await inFlight;}catch(err){if(g!==epoch)return;failures++;error(err.message);wipe();if(failures>=3){await stop();return;}}finally{inFlight=null;}
 schedule(g,Math.max(0,1000/24-(performance.now()-start)));
}
async function listCameras(current=''){
 const devices=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput'&&!/iphone|continuity|desk view|virtual|camo/i.test(d.label));
 $('cameras').replaceChildren(new Option('Auto-detect USB webcam',''));
 devices.forEach((d,i)=>$('cameras').append(new Option(d.label||`Webcam ${i+1}`,d.deviceId)));
 if(devices.some(d=>d.deviceId===current))$('cameras').value=current;
 return devices;
}
async function stop(){active=false;epoch++;clearTimeout(timer);clearTimeout(expiry);stream?.getTracks().forEach(t=>t.stop());stream=null;video.srcObject=null;if(inFlight)try{await inFlight;}catch(_){}inFlight=null;wipe();trails.clear();$('state').textContent='Stopped';$('stop').disabled=true;try{await api('/api/reset');}catch(_){} }
async function start(){
 if(opening)return;opening=true;$('connect').disabled=true;const selected=$('cameras').value;error();await stop();const g=++epoch;let opened=null;
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Open this page in Safari or Chrome on this Mac.');
  let choices=await listCameras(selected),id=selected||choices.find(d=>d.label&&!/macbook|facetime|built.in/i.test(d.label))?.deviceId||choices[0]?.deviceId;
  opened=await navigator.mediaDevices.getUserMedia({audio:false,video:{...(id?{deviceId:{exact:id}}:{}),width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30,max:30}}});
  choices=await listCameras(opened.getVideoTracks()[0].getSettings().deviceId);
  const external=!selected&&choices.find(d=>d.label&&!/macbook|facetime|built.in/i.test(d.label));
  if(external&&external.deviceId!==opened.getVideoTracks()[0].getSettings().deviceId){opened.getTracks().forEach(t=>t.stop());opened=await navigator.mediaDevices.getUserMedia({audio:false,video:{deviceId:{exact:external.deviceId},width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30,max:30}}});}
  if(g!==epoch){opened.getTracks().forEach(t=>t.stop());return;}
  stream=opened;video.srcObject=opened;await video.play();if(g!==epoch)return;
  await api('/api/auto',{enabled:true});
  const track=stream.getVideoTracks()[0];$('cameras').value=track.getSettings().deviceId||'';$('cameraLabel').textContent=track.label||'Live webcam';
  const caps=track.getCapabilities?.()||{};if(caps.focusMode?.includes('continuous'))try{await track.applyConstraints({advanced:[{focusMode:'continuous'}]});}catch(_){}
  track.addEventListener('ended',()=>{if(active&&g===epoch)stop();});
  active=true;failures=0;lastCompleted=null;lastVideoTime=-1;$('picture').hidden=false;$('empty').hidden=true;$('stop').disabled=false;$('connect').textContent='Reconnect';schedule(g,0);
 }catch(err){opened?.getTracks().forEach(t=>t.stop());error(err.name==='NotAllowedError'?'Allow camera access in the browser, then start the webcam again.':err.message);$('state').textContent='Camera not connected';}
 finally{opening=false;$('connect').disabled=false;}
}
$('connect').addEventListener('click',start);$('stop').addEventListener('click',stop);$('cameras').addEventListener('change',()=>{if(active)start();});
$('clear').addEventListener('click',async()=>{try{await api('/api/clear');wipe();trails.clear();error();}catch(err){error(err.message);}});
window.addEventListener('pagehide',()=>{active=false;clearTimeout(timer);clearTimeout(expiry);stream?.getTracks().forEach(t=>t.stop());});
if(navigator.mediaDevices)navigator.mediaDevices.addEventListener('devicechange',()=>listCameras(stream?.getVideoTracks()[0]?.getSettings().deviceId).catch(()=>{}));
