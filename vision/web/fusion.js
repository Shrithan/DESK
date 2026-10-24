'use strict';
const $=id=>document.getElementById(id),roles=['front','top'],colors=['#c5ef9b','#9dcaeb','#f4ba8a','#dab4f5','#f2dd83'];
const candidates=new Map();
const cameras={},pairs=[],map=$('map');let running=false,opening=false,generation=0,busy=null,timer=null,pairNumber=0,lastCompleted=null,previewRequest=null,previewLast=0,previewCount=0,previewWindow=0,commonFps=30,analysisWindow=0,analysisCount=0;
for(const [index,role] of roles.entries()){
 const section=document.createElement('section');section.className='feed';
 section.innerHTML=`<div class="feed-title"><span>${index?'OVERHEAD / X + Y':'SIDE / HEIGHT Z'}</span><span id="state-${role}">Not connected</span></div><div class="feed-picture"><video id="video-${role}" autoplay muted playsinline></video><canvas id="preview-${role}" class="camera-preview"></canvas><canvas id="overlay-${role}"></canvas></div><div class="camera-controls"><select id="camera-${role}" aria-label="Camera ${index+1}"></select><div class="axis-controls"><label><input id="flip-${role}" type="checkbox">Reverse ${index?'X':'Z'} direction</label>${index?'<label><input id="flip-y" type="checkbox">Reverse Y direction</label>':''}<button id="wide-${role}" type="button">Reset zoom</button><label>View<select id="orientation-${role}"><option value="auto">Auto / native portrait</option><option value="raw">Original orientation</option><option value="cw">Portrait clockwise</option><option value="ccw">Portrait counterclockwise</option></select></label></div><p id="camera-info-${role}" class="small">Webcam or iPhone · full camera image</p></div>`;
 $('feeds').append(section);cameras[role]={video:$(`video-${role}`),canvas:document.createElement('canvas'),overlay:$(`overlay-${role}`),stream:null,result:null,sample:null,acceptedSample:null,inFlight:null,timer:null,preview:$(`preview-${role}`),sequence:0,lastPresented:-1,lastAnalyzed:-1,callback:null,sourceFps:null,fpsStart:null,fpsFrames:0};
 $(`flip-${role}`).addEventListener('change',zero);
 $(`orientation-${role}`).addEventListener('change',()=>{if(running)start();});
 $(`wide-${role}`).addEventListener('click',()=>wideView(role).catch(err=>error(err.message)));
}
function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
async function api(path,body={},role='front',type='application/json',sample=null){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
 try{const headers={'Content-Type':type,'X-Camera-Id':role};if(sample!==null)headers['X-Capture-Sample-Ms']=String(sample);
 const response=await fetch(path,{method:'POST',headers,body:type==='application/json'?JSON.stringify(body):body,signal:controller.signal});const data=await response.json();if(!response.ok)throw new Error(data.error||'Tracking request failed');return data;}finally{clearTimeout(timeout);}
}
async function inventory(){
 const devices=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput'&&!/desk view/i.test(d.label));
 const phones=devices.filter(d=>/iphone|continuity/i.test(d.label)),external=devices.filter(d=>!/macbook|facetime|built.in|iphone|continuity|virtual|camo/i.test(d.label));
 const ordered=[...external,...phones,...devices.filter(d=>!external.includes(d)&&!phones.includes(d))];
 const preferred=[phones[0]||external[0]||ordered[0],external[0]||ordered.find(d=>d.deviceId!==phones[0]?.deviceId)];
 for(const [index,role] of roles.entries()){const select=$(`camera-${role}`),previous=select.value;select.replaceChildren(...ordered.map((d,i)=>new Option(d.label||`Webcam ${i+1}`,d.deviceId)));if(ordered.some(d=>d.deviceId===previous))select.value=previous;else if(preferred[index])select.value=preferred[index].deviceId;}
 if(ordered.length>1&&$('camera-front').value===$('camera-top').value)$('camera-top').value=(external.find(d=>d.deviceId!==$('camera-front').value)||ordered.find(d=>d.deviceId!==$('camera-front').value)).deviceId;
 return devices;
}
function frameLayout(width,height,mode,phone){
 const rotate=width>height&&(mode==='cw'||mode==='ccw');
 return {width:rotate?height:width,height:rotate?width:height,turn:rotate?(mode==='ccw'?-1:1):0};
}
function layout(role){const c=cameras[role];return frameLayout(c.video.videoWidth,c.video.videoHeight,$(`orientation-${role}`).value,/iphone|continuity/i.test(c.stream?.getVideoTracks()[0]?.label||''));}
function paintFrame(role,canvas,longEdge){
 const c=cameras[role],plan=layout(role),scale=Math.min(1,longEdge/Math.max(plan.width,plan.height));
 const w=Math.round(plan.width*scale),h=Math.round(plan.height*scale);
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 const ctx=canvas.getContext('2d');ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,w,h);
 if(plan.turn){ctx.translate(w/2,h/2);ctx.rotate(plan.turn*Math.PI/2);ctx.drawImage(c.video,-h/2,-w/2,h,w);}
 else ctx.drawImage(c.video,0,0,w,h);
 ctx.setTransform(1,0,0,1,0,0);
 c.preview.parentElement.style.aspectRatio=`${plan.width} / ${plan.height}`;
 c.preview.parentElement.style.width=plan.width<plan.height?`min(100%, ${70*plan.width/plan.height}vh)`:'100%';
}
function freshPair(list,key){return list.every(c=>c.video.readyState>=2&&c.sequence>c[key]);}
function observeFrames(role,g){
 const c=cameras[role];if(!c.video.requestVideoFrameCallback)return;
 const observe=(now,metadata)=>{
  if(g!==generation)return;
  c.sequence++;c.mediaTime=metadata.mediaTime;
  if(c.fpsStart===null){c.fpsStart=now;c.fpsFrames=metadata.presentedFrames;}
  if(now-c.fpsStart>=1000){c.sourceFps=(metadata.presentedFrames-c.fpsFrames)*1000/(now-c.fpsStart);c.fpsStart=now;c.fpsFrames=metadata.presentedFrames;}
  c.callback=c.video.requestVideoFrameCallback(observe);
 };
 c.callback=c.video.requestVideoFrameCallback(observe);
}
function smoothPosition(previous,target,elapsed){
 if(!previous)return target.slice();
 // Time-based low-pass response: no velocity prediction or invented measurements.
 const distance=Math.hypot(...target.map((v,i)=>v-previous[i]));
 const response=distance>2?22:55;
 const alpha=1-Math.exp(-Math.max(0,Math.min(elapsed,100))/response);
 return target.map((v,i)=>previous[i]+alpha*(v-previous[i]));
}
function animateMap(now){
 let estimates=0;
 for(const p of pairs){
  const estimate=p.position&&predictPosition(p.prediction,now,$('predict').checked);
  if(!estimate){p.visual=null;p.visualTime=null;continue;}
  p.visualPredicted=estimate.predicted;if(estimate.predicted)estimates++;
  p.visual=smoothPosition(p.visual,estimate.point,p.visualTime===null||p.visualTime===undefined?16:now-p.visualTime);
  p.visualTime=now;
 }
 $('prediction-status').textContent=`${estimates} predicted points · maximum 80 ms look-ahead · stale points hidden after 220 ms · solid trails use measurements`;
 draw();
}
function previewLoop(g,now=performance.now()){
 if(!running||g!==generation)return;
 const list=roles.map(r=>cameras[r]);
 for(const c of list)if(!c.video.requestVideoFrameCallback)c.sequence=c.video.currentTime;
 for(const role of roles){const c=cameras[role];if(c.video.readyState>=2&&c.sequence>c.lastPresented){paintFrame(role,c.preview,960);c.lastPresented=c.sequence;}}
 if(now-previewWindow>=1000){
  $('display-fps').textContent=`Measured input: ${list.map(c=>c.sourceFps===null?'measuring':c.sourceFps.toFixed(1)).join(' / ')} fps · requested side ${cameras.front.requestedFps||30} / overhead ${cameras.top.requestedFps||30} fps · map redraw follows display (up to 60 Hz)`;
  previewWindow=now;
 }
 animateMap(now);
 previewRequest=requestAnimationFrame(t=>previewLoop(g,t));
}
async function matchFrameRates(){
 // Run each source at its own supported rate; a 30 fps overhead must not throttle a 60 fps phone.
 for(const role of roles){
  const c=cameras[role],track=c.stream.getVideoTracks()[0],phone=/iphone|continuity/i.test(track.label);
  const target=Math.min(phone?60:30,track.getCapabilities?.().frameRate?.max||track.getSettings().frameRate||30);
  try{await track.applyConstraints({frameRate:{exact:target}});}catch(_){await track.applyConstraints({frameRate:{ideal:target,max:target}});}
  c.requestedFps=target;
 }
}
async function wideView(role){
 const track=cameras[role].stream?.getVideoTracks()[0];
 if(!track){error('Start the cameras first.');return;}
 const caps=track.getCapabilities?.()||{};
 if(caps.zoom&&Number.isFinite(caps.zoom.min))await track.applyConstraints({advanced:[{zoom:caps.zoom.min}]});
 const settings=track.getSettings();
 $(`camera-info-${role}`).textContent=`${track.label} · ${settings.width} × ${settings.height} · ${caps.zoom?'minimum zoom requested':'zoom control unavailable; move camera farther back for a wider view'}`;
 // Changing the camera field of view invalidates prior origins and paths.
 zero();
}
async function stop(){
 running=false;generation++;clearTimeout(timer);cancelAnimationFrame(previewRequest);
 for(const c of Object.values(cameras)){clearTimeout(c.timer);if(c.callback!==null)c.video.cancelVideoFrameCallback?.(c.callback);c.callback=null;c.stream?.getTracks().forEach(t=>t.stop());c.stream=null;c.video.srcObject=null;}
 await Promise.all(Object.values(cameras).map(async c=>{if(c.inFlight)try{await c.inFlight;}catch(_){}}));
 for(const role of roles){cameras[role].result=null;cameras[role].preview.getContext('2d').clearRect(0,0,cameras[role].preview.width,cameras[role].preview.height);$(`state-${role}`).textContent='Stopped';clearOverlay(role);}
 for(const role of roles)try{await api('/api/reset',{},role);}catch(_){}
 pairs.length=0;candidates.clear();pairNumber=0;if(typeof flatInputs!=='undefined'){flatInputs.clear();if(typeof dismissedFlatInputs!=='undefined')dismissedFlatInputs.clear();$('flat-tracks').replaceChildren();}draw();$('tracks').replaceChildren();$('status').textContent='Stopped';
}
async function start(){
 if(opening)return;opening=true;$('start').disabled=true;error();await stop();const g=++generation;
 try{
 if(!navigator.mediaDevices?.getUserMedia)throw new Error('Open localhost in Safari or Chrome.');
 let devices=await inventory();
 if(!devices.some(d=>d.label)){
 const temporary=await navigator.mediaDevices.getUserMedia({video:true,audio:false});temporary.getTracks().forEach(t=>t.stop());devices=await inventory();}
 const ids=roles.map(r=>$(`camera-${r}`).value);
 if(!ids[0]||!ids[1]||ids[0]===ids[1])throw new Error('Choose two different camera sources. A webcam and an iPhone can be used together.');
 for(const role of roles){
 const phone=/iphone|continuity/i.test($(`camera-${role}`).selectedOptions[0]?.text||'');
 const c=cameras[role];c.sequence=0;c.lastPresented=c.lastAnalyzed=-1;c.fpsStart=null;c.sourceFps=null;c.result=null;c.acceptedSample=null;c.stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{deviceId:{exact:$(`camera-${role}`).value},width:{ideal:phone?720:1280},height:{ideal:phone?1280:720},aspectRatio:{ideal:phone?9/16:16/9},resizeMode:{ideal:'none'},frameRate:{ideal:phone?60:30,max:phone?60:30}}});
 if(g!==generation){c.stream.getTracks().forEach(t=>t.stop());return;}
 c.video.srcObject=c.stream;await c.video.play();observeFrames(role,g);const track=c.stream.getVideoTracks()[0],caps=track.getCapabilities?.()||{};
 await wideView(role);
 if(caps.focusMode?.includes('continuous'))try{await track.applyConstraints({advanced:[{focusMode:'continuous'}]});}catch(_){}
 track.addEventListener('ended',()=>{if(running&&g===generation)stop();});await api('/api/auto',{enabled:true},role);await api('/api/workspace-multi',{},role);
 }
 await matchFrameRates();
 running=true;analysisWindow=performance.now();analysisCount=0;previewLast=0;previewWindow=performance.now();previewCount=0;previewLoop(g);lastCompleted=null;$('status').textContent='Fast tracking · move new objects briefly in both views';$('start').textContent='Reconnect cameras';roles.forEach(role=>pump(role,g));
 }catch(err){await stop();error(err.message);}finally{opening=false;$('start').disabled=false;}
}
function objects(role){return cameras[role].result?.objects||[];}
function find(role,id){return objects(role).find(o=>o.observation.object_id===id);}
function available(role){const used=new Set(pairs.map(p=>p[role]));if(role==='top'&&typeof flatInputs!=='undefined')for(const id of flatInputs.keys())used.add(id);return objects(role).filter(o=>o.observation.tracking_state==='tracked'&&!used.has(o.observation.object_id));}
function compatible(a,b){return a===b||['can','bottle','cup'].includes(a)&&['can','bottle','cup'].includes(b);}
function makePair(a,b){return {front:a.observation.object_id,top:b.observation.object_id,number:0,label:a.object_label,origin:null,points:[],lastSample:null,state:'waiting',position:null,confirmed:false,motionHits:0,lastCenters:null,lastMotion:{},lastSeen:null};}
function addPair(a,b,manual=false,candidate=null){
 if(pairs.some(p=>p.front===a.observation.object_id||p.top===b.observation.object_id))return;
 const pair=candidate||makePair(a,b);pair.number=++pairNumber;pair.manual=manual;
 if(manual)pair.confirmed=true;
 pairs.push(pair);
}
function relinkPairs(){
 // A view re-acquired a paired object under a new track ID: move the pair to it instead of
 // creating a duplicate. Only when exactly one compatible unpaired track exists in that view.
 for(const p of pairs)for(const role of roles){
  if(find(role,p[role]))continue;
  const partner=find(roles.find(r=>r!==role),p[roles.find(r=>r!==role)]);
  if(!partner||partner.observation.tracking_state==='lost')continue;
  const options=available(role).filter(o=>compatible(o.object_label,p.label)&&o.observation.tracking_state!=='lost');
  if(options.length===1){p[role]=options[0].observation.object_id;p.filterState=null;p.filterStamp=null;p.relinked=(p.relinked||0)+1;}
 }
}
function matchObjects(now){
 relinkPairs();
 const side=available('front'),top=available('top'),current=new Set(),ready=[];
 for(const a of side)for(const b of top){
  if(!compatible(a.object_label,b.object_label))continue;
  const key=a.observation.object_id+'|'+b.observation.object_id;current.add(key);
  let candidate=candidates.get(key);if(!candidate){candidate=makePair(a,b);candidates.set(key,candidate);}
  if(candidate.lastCheck!==now){associationStep(candidate,a,b,now);candidate.lastCheck=now;}
  if(candidate.confirmed)ready.push({a,b,candidate});
 }
 // Only commit mutually unique matches. Simultaneous similar-object motion
 // remains unresolved instead of choosing arbitrary enumeration order.
 for(const match of ready){
  if(ready.filter(x=>x.candidate.front===match.candidate.front).length!==1||ready.filter(x=>x.candidate.top===match.candidate.top).length!==1)continue;
  addPair(match.a,match.b,false,match.candidate);
 }
 for(const key of candidates.keys())if(!current.has(key))candidates.delete(key);
}
function zero(){for(const p of pairs){p.origin=null;p.points=[];p.position=null;p.lastSample=null;p.visual=null;p.visualTime=null;p.visualTrail=[];p.prediction=null;p.filterState=null;p.filterStamp=null;}draw();}
function options(){for(const role of roles){const select=$(`pair-${role}`),old=select.value;select.replaceChildren(new Option('Choose an unpaired track…',''),...available(role).map(o=>new Option(`#${o.number} ${o.object_label}`,o.observation.object_id)));if([...select.options].some(o=>o.value===old))select.value=old;}}
function associationStep(pair,a,b,now){
 const tracked=a?.observation.tracking_state==='tracked'&&b?.observation.tracking_state==='tracked'&&a.motion&&b.motion;
 if(!tracked){
  pair.lastCenters=null;
  if(pair.lastSeen!==null&&now-pair.lastSeen>8000){pair.confirmed=false;pair.motionHits=0;pair.lastMotion={};}
  return false;
 }
 const sampleKey=`${cameras.front.acceptedSample}|${cameras.top.acceptedSample}`;
 if(pair.associationKey===sampleKey)return !!pair.confirmed;
 pair.associationKey=sampleKey;
 pair.lastSeen=now;
 const centers={front:a.motion.center_px.map((v,i)=>v/(i?cameras.front.canvas.height:cameras.front.canvas.width)),top:b.motion.center_px.map((v,i)=>v/(i?cameras.top.canvas.height:cameras.top.canvas.width))};
 if(pair.lastCenters){
  for(const role of roles){const p=pair.lastCenters[role],q=centers[role];if(Math.hypot(q[0]-p[0],q[1]-p[1])>=.004)pair.lastMotion[role]=now;}
  if(pair.lastMotion.front!==undefined&&pair.lastMotion.top!==undefined&&Math.abs(pair.lastMotion.front-pair.lastMotion.top)<=350&&now-Math.min(pair.lastMotion.front,pair.lastMotion.top)<=350){pair.motionHits++;pair.lastMotion={};}
  if(pair.motionHits>=2)pair.confirmed=true;
 }
 pair.lastCenters=centers;
 return !!pair.confirmed;
}
function metricXY(b){return Array.isArray(b?.table_xy_m)&&b.table_xy_m.every(Number.isFinite)?b.table_xy_m:null;}
function spatialValues(a,b){
 const side=cameras.front.canvas,top=cameras.top.canvas,xy=metricXY(b);
 // Calibrated overhead camera: absolute table X/Y in metres (shown in cm); Z stays relative to the side view.
 if(xy)return [xy[0],xy[1],-a.motion.center_px[1]/side.height*($('flip-front').checked?-1:1)];
 return [b.motion.center_px[0]/top.width*($('flip-top').checked?-1:1),
         -b.motion.center_px[1]/top.height*($('flip-y').checked?-1:1),
         -a.motion.center_px[1]/side.height*($('flip-front').checked?-1:1)];
}
function fuse(){
 if(typeof renderFlatInputs==='function')renderFlatInputs();
 const newest=Math.max(cameras.front.acceptedSample||0,cameras.top.acceptedSample||0);
 matchObjects(newest);
 const cards=[];
 for(const p of pairs){
 const a=find('front',p.front),b=find('top',p.top),color=colors[(p.number-1)%colors.length];
 const good=associationStep(p,a,b,newest);
 // Views are analysed independently (a few Hz each); pair samples up to 250 ms apart and let the
 // One Euro filter absorb the skew, instead of dropping most updates.
 const synchronized=Math.abs(cameras.front.acceptedSample-cameras.top.acceptedSample)<=250; // ms
 p.position=null;
 if(good&&synchronized){
 const values=spatialValues(a,b);
 p.metric=!!metricXY(b);
 if(!p.origin)p.origin=values;
 const rawPosition=values.map((v,i)=>(v-(p.metric&&i<2?0:p.origin[i]))*100);
 // Jump gate: one sample implying > 3 m/s (or 300 %/s) is held back once; a second agreeing
 // sample is accepted, so a real fast move costs at most one update, a glitch costs nothing.
 let jump=false;
 if(p.lastRaw&&p.lastGood&&!p.jumpHeld){const dt=Math.max(.03,(newest-p.lastGood)/1000),step=Math.hypot(...rawPosition.map((v,i)=>v-p.lastRaw[i]));jump=step>300*dt+5;}
 if(jump){p.jumpHeld=true;p.position=p.lastPosition;p.state='holding';}
 else{p.jumpHeld=false;p.lastRaw=rawPosition;
 if(typeof filterVector==='function'){
  const sourceStamp=newest;
  if(p.filterStamp!==sourceStamp){p.filterState=filterVector(p.filterState,rawPosition,sourceStamp);p.filterStamp=sourceStamp;}
  p.position=p.filterState.map(s=>s.value);
 }else p.position=rawPosition;
 const stamp=`${cameras.front.acceptedSample}|${cameras.top.acceptedSample}`;
 p.lastGood=newest;p.lastPosition=p.position;if(p.lastSample!==stamp){if(p.state==='lost')p.points.push(null);p.points.push(p.position);if(p.points.length>180)p.points.shift();p.lastSample=stamp;p.prediction=updatePrediction(p.prediction,p.position,newest-performance.timeOrigin,[cameras.top.acceptedSample-performance.timeOrigin,cameras.top.acceptedSample-performance.timeOrigin,cameras.front.acceptedSample-performance.timeOrigin]);}p.state='tracked';}
 }else if(p.lastPosition&&p.lastGood&&newest-p.lastGood<=700){ // hold window, ms
  // Brief dropout (one view busy, a missed detection): hold the smoothed position so the
  // trail stays continuous; the prediction module extrapolates for up to 80 ms.
  p.position=p.lastPosition;p.state='holding';
 }else{if(p.position||p.state==='holding')p.state='lost';if(p.visualTrail?.length&&p.visualTrail[p.visualTrail.length-1]!==null)p.visualTrail.push(null);p.visual=null;p.visualTime=null;p.prediction=null;p.filterState=null;p.filterStamp=null;if(p.state!=='lost')p.state=good?'waiting for paired samples':p.confirmed?'waiting for both views':'Move the target left/right so both views see it move';}
 const card=document.createElement('div');card.className='track-card';card.style.borderColor=color;
 const title=document.createElement('strong');title.textContent=`Object ${p.number} · ${p.label}`;title.style.color=color;
 const text=document.createElement('p');text.textContent=p.position?(p.metric?`X ${p.position[0].toFixed(1)} cm · Y ${p.position[1].toFixed(1)} cm (table, calibrated) · Z ${p.position[2].toFixed(1)}% relative`:`X ${p.position[0].toFixed(1)}% · Y ${p.position[1].toFixed(1)}% · Z ${p.position[2].toFixed(1)}%`):p.state;
 const method=document.createElement('p');method.textContent=p.confirmed?(p.manual?'Paired by you · both views':'Motion-matched · both views'):'Move this object in both views to recheck its identity';
 const remove=document.createElement('button');remove.textContent='Unpair';remove.addEventListener('click',()=>{pairs.splice(pairs.indexOf(p),1);candidates.clear();card.remove();options();draw();});
 card.append(title,text,method,remove);cards.push(card);
 }
 $('tracks').replaceChildren(...cards);options();draw();
 $('status').textContent=`${pairs.filter(p=>p.position).length} objects mapped · ${pairs.length} shared IDs · ${available('front').length+available('top').length} unpaired camera tracks`;
}
function clearOverlay(role){const canvas=cameras[role].overlay;canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);}
function trackVelocities(c,result,sample){
 // px per ms for each object, from consecutive results (for drawing boxes where the object is now).
 c.velocity=c.velocity||{};const prev=c.lastCenters||{},next={};
 for(const o of result?.objects||[]){const id=o.observation.object_id,m=o.motion;if(!m||o.observation.tracking_state!=='tracked')continue;next[id]=[m.center_px[0],m.center_px[1],sample];
  const q=prev[id];if(q&&sample>q[2]&&sample-q[2]<400){const v=[(m.center_px[0]-q[0])/(sample-q[2]),(m.center_px[1]-q[1])/(sample-q[2])],old=c.velocity[id];c.velocity[id]=old?[.6*v[0]+.4*old[0],.6*v[1]+.4*old[1]]:v;}}
 for(const id of Object.keys(c.velocity))if(!next[id])delete c.velocity[id];
 c.lastCenters=next;
}
function boxLead(c,id,now){
 // The result describes a frame that is already old; lead the box by speed x age (capped) so it
 // sits on the live video instead of trailing a fast object.
 const v=c.velocity?.[id];if(!v||!now||!c.acceptedSample)return [0,0];
 const age=Math.max(0,Math.min(150,now-c.acceptedSample));return [v[0]*age,v[1]*age];
}
function overlay(role,now=null){const c=cameras[role],canvas=c.overlay;if(canvas.width!==c.canvas.width)canvas.width=c.canvas.width;if(canvas.height!==c.canvas.height)canvas.height=c.canvas.height;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
 for(const o of objects(role)){const obs=o.observation;if(!obs.bbox_xyxy||obs.tracking_state==='lost')continue;const pair=pairs.find(p=>p[role]===obs.object_id),color=pair?colors[(pair.number-1)%colors.length]:'#aab8aa';ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2;ctx.setLineDash(obs.tracking_state==='predicted'?[6,5]:[]);const [lx,ly]=boxLead(c,obs.object_id,now),[x,y,x2,y2]=obs.bbox_xyxy.map((v,i)=>v+(i%2?ly:lx));ctx.strokeRect(x,y,x2-x,y2-y);ctx.font='15px sans-serif';ctx.fillText(typeof flatInputs!=='undefined'&&flatInputs.has(obs.object_id)?`2D input #${o.number}`:pair?`Object ${pair.number}`:`#${o.number} ${o.object_label} · unpaired`,x,Math.max(16,y-5));}
 // Draw measured side silhouette centerlines and estimated overhead joystick pivots.
 for(const o of objects(role))if(o.observation.tracking_state==='tracked'&&o.skeleton){
  const {base_px:base,top_px:top}=o.skeleton;ctx.strokeStyle='#f2dd83';ctx.fillStyle='#f2dd83';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(...base);ctx.lineTo(...top);ctx.stroke();for(const point of [base,top]){ctx.beginPath();ctx.arc(...point,5,0,Math.PI*2);ctx.fill();}ctx.font='12px sans-serif';ctx.fillText('base pivot',base[0]+7,base[1]);ctx.fillText('top',top[0]+7,top[1]);
 }
 if(role==='top'&&typeof flatInputs!=='undefined')for(const [id,input] of flatInputs){const item=objects(role).find(o=>o.observation.object_id===id);if(!input.pivot||!input.origin||!item?.motion||item.observation.tracking_state!=='tracked')continue;
  const base=[input.origin[0]*canvas.width,(1-input.origin[1])*canvas.height],top=item.motion.center_px;ctx.strokeStyle='#9dcfff';ctx.fillStyle='#9dcfff';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(...base);ctx.lineTo(...top);ctx.stroke();for(const point of [base,top]){ctx.beginPath();ctx.arc(...point,5,0,Math.PI*2);ctx.fill();}ctx.font='12px sans-serif';ctx.fillText('saved base',base[0]+7,base[1]);ctx.fillText('top / control',top[0]+7,top[1]);
 }
 $(`state-${role}`).textContent=`${objects(role).filter(o=>o.observation.tracking_state==='tracked').length} objects tracked`;
}
function animateOverlays(){if(running){const now=performance.timeOrigin+performance.now();for(const role of roles)if(cameras[role].result)overlay(role,now);}requestAnimationFrame(animateOverlays);}
if(typeof requestAnimationFrame==='function')requestAnimationFrame(animateOverlays);
async function pump(role,g){
 const c=cameras[role];
 if(!running||g!==generation)return;
 if(document.hidden||c.video.readyState<2||c.sequence<=c.lastAnalyzed){c.timer=setTimeout(()=>pump(role,g),5);return;}
 const started=performance.now(),sample=performance.timeOrigin+started;
 paintFrame(role,c.canvas,640);c.lastAnalyzed=c.sequence;
 c.inFlight=(async()=>{
  const blob=await new Promise(resolve=>c.canvas.toBlob(resolve,'image/jpeg',.85));if(!blob)throw new Error('Camera frame unavailable');
  const result=await api('/api/frame',blob,role,'image/jpeg',sample);
  if(g!==generation||!running)return;
  trackVelocities(c,result,sample);c.result=result;c.sample=c.acceptedSample=sample;c.completed=(c.completed||0)+1;
  fuse();overlay(role);$('model-info').textContent=result.detector;
  const now=performance.now();if(now-analysisWindow>=1000){$('stats').textContent=`Tracking updates/sec: side ${((cameras.front.completed||0)*1000/(now-analysisWindow)).toFixed(1)} · overhead ${((cameras.top.completed||0)*1000/(now-analysisWindow)).toFixed(1)} · independent fresh-frame processing; sensor timing unverified`;analysisWindow=now;cameras.front.completed=cameras.top.completed=0;}
  error(result.detector_error?`Detector error (${role}): ${result.detector_error}. Fell back to in-request detection; see Terminal.`:'');
 })();
 try{await c.inFlight;}catch(err){if(g===generation){error(err.message);c.result=null;c.acceptedSample=null;for(const p of pairs){p.position=null;p.prediction=null;p.visual=null;p.points.push(null);}clearOverlay(role);draw();}}finally{c.inFlight=null;}
 if(running&&g===generation)c.timer=setTimeout(()=>pump(role,g),0);
}
function draw(){
 const bounds=map.getBoundingClientRect();if(!bounds.width)return;const ratio=devicePixelRatio||1;map.width=bounds.width*ratio;map.height=bounds.height*ratio;const ctx=map.getContext('2d');ctx.scale(ratio,ratio);const w=bounds.width,h=bounds.height,pad=40;
 const extent=60; // Fixed box scale prevents the entire map jumping as the path expands.
 const scale=Math.min(w*.32,h*.29)/extent;
 const project=([x,y,z])=>[w*.5+(x-y)*.866*scale,h*.6+(x+y)*.5*scale-z*scale];
 ctx.font='12px system-ui';ctx.lineWidth=1;
 const line=(a,b,color)=>{ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(...project(a));ctx.lineTo(...project(b));ctx.stroke();};
 const lo=-extent,hi=extent;
 for(const z of [lo,hi])for(const x of [lo,hi])line([x,lo,z],[x,hi,z],'#415449');
 for(const z of [lo,hi])for(const y of [lo,hi])line([lo,y,z],[hi,y,z],'#415449');
 for(const x of [lo,hi])for(const y of [lo,hi])line([x,y,lo],[x,y,hi],'#415449');
 for(const [label,p,color] of [['X',[hi,0,0],'#f4ba8a'],['Y',[0,hi,0],'#c5ef9b'],['Z',[0,0,hi],'#9dcaeb']]){line([0,0,0],p,color);const q=project(p);ctx.fillStyle=color;ctx.fillText(label,q[0]+5,q[1]-5);}
 ctx.fillStyle='#aab8aa';ctx.fillText('Relative 3D movement · uncalibrated · % of each image axis',16,22);
 for(const p of pairs){const color=colors[(p.number-1)%colors.length];ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();let pen=false;for(const point of p.points){if(!point){pen=false;continue;}const q=project(point);if(pen)ctx.lineTo(...q);else ctx.moveTo(...q);pen=true;}ctx.stroke();if(p.position&&p.visual){const q=project(p.visual);ctx.fillStyle=color;ctx.beginPath();ctx.arc(...q,6,0,Math.PI*2);if(p.visualPredicted){ctx.setLineDash([3,3]);ctx.stroke();ctx.setLineDash([]);}else ctx.fill();ctx.fillText(`Object ${p.number}${p.visualPredicted?' · predicted':''}`,q[0]+10,q[1]-10);
 const item=find('top',p.top),yaw=item?.orientation?.rotation_degrees;
 ctx.strokeStyle=color;ctx.lineWidth=1.5;const qx=q[0],qy=q[1];ctx.strokeRect(qx-9,qy-19,18,19);ctx.beginPath();ctx.ellipse(qx,qy-19,9,4,0,0,Math.PI*2);ctx.stroke();if(yaw!=null){const a=yaw*Math.PI/180;ctx.beginPath();ctx.moveTo(qx,qy-19);ctx.lineTo(qx+Math.cos(a)*15,qy-19+Math.sin(a)*6);ctx.stroke();}}}

}
$('predict').addEventListener('change',()=>{for(const p of pairs){p.visual=null;p.visualTime=null;}});
$('pair').addEventListener('click',()=>{const a=find('front',$('pair-front').value),b=find('top',$('pair-top').value);if(!a||!b){error('Choose the same physical object from each view.');return;}addPair(a,b,true);candidates.clear();fuse();roles.forEach(overlay);});
$('flip-y').addEventListener('change',zero);
$('refresh-cameras').addEventListener('click',()=>inventory().catch(err=>error(err.message)));
$('start').addEventListener('click',start);$('stop').addEventListener('click',stop);$('zero').addEventListener('click',zero);
$('reset').addEventListener('click',async()=>{const resume=running;running=false;for(const c of Object.values(cameras))clearTimeout(c.timer);await Promise.all(Object.values(cameras).map(async c=>{if(c.inFlight)try{await c.inFlight;}catch(_){}}));for(const role of roles){await api('/api/clear',{},role);cameras[role].result=null;}pairs.length=0;candidates.clear();pairNumber=0;if(typeof flatInputs!=='undefined'){flatInputs.clear();if(typeof dismissedFlatInputs!=='undefined')dismissedFlatInputs.clear();$('flat-tracks').replaceChildren();}$('tracks').replaceChildren();draw();if(resume){running=true;previewLoop(generation);roles.forEach(role=>pump(role,generation));}});
new ResizeObserver(draw).observe(map.parentElement);
window.addEventListener('pagehide',()=>{running=false;generation++;clearTimeout(timer);cancelAnimationFrame(previewRequest);for(const c of Object.values(cameras)){clearTimeout(c.timer);c.stream?.getTracks().forEach(t=>t.stop());}});
if(navigator.mediaDevices){inventory().catch(()=>{});navigator.mediaDevices.addEventListener('devicechange',()=>inventory().catch(()=>{}));}
