'use strict';
function commandCandidates(intent,items,selected='',moved=new Set()){
 let eligible=items.filter(o=>o.observation.tracking_state==='tracked'&&o.motion);
 if(intent.label)eligible=eligible.filter(o=>o.object_label===intent.label||(intent.label==='can'&&['bottle','cup'].includes(o.object_label)));
 if(intent.number!=null)eligible=eligible.filter(o=>o.number===intent.number);
 if(selected)return eligible.filter(o=>o.observation.object_id===selected);
 if(eligible.length===1)return eligible;
 const moving=eligible.filter(o=>moved.has(o.observation.object_id));return moving.length===1?moving:eligible;
}
function encodeCommandWav(chunks,rate){
 const total=chunks.reduce((n,c)=>n+c.length,0),source=new Float32Array(total);let offset=0;for(const c of chunks){source.set(c,offset);offset+=c.length;}
 const size=Math.floor(total*16000/rate),buffer=new ArrayBuffer(44+size*2),view=new DataView(buffer);
 const str=(at,s)=>{for(let i=0;i<s.length;i++)view.setUint8(at+i,s.charCodeAt(i));};
 str(0,'RIFF');view.setUint32(4,36+size*2,true);str(8,'WAVE');str(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);str(36,'data');view.setUint32(40,size*2,true);
 for(let i=0;i<size;i++){const start=Math.floor(i*rate/16000),end=Math.max(start+1,Math.floor((i+1)*rate/16000));let sum=0;for(let j=start;j<end&&j<total;j++)sum+=source[j];const value=Math.max(-1,Math.min(1,sum/(end-start)));view.setInt16(44+i*2,value<0?value*32768:value*32767,true);}
 return new Blob([buffer],{type:'audio/wav'});
}
function morphKeys(mapping,input){
 if(!mapping||!input)return [];
 const b=mapping.bindings,d=mapping.deadzone;
 if(mapping.controller==='joystick'){const j=input.joystick;if(!j)return [];return [j.y>d?b.up:j.y< -d?b.down:null,j.x>d?b.right:j.x< -d?b.left:null].filter(Boolean);}
 const value=mapping.controller==='dial'?input.filteredYaw:input.current?.value;
 if(!Number.isFinite(value))return [];
 if(!Number.isFinite(input.morphCenter))input.morphCenter=value;
 const delta=mapping.controller==='dial'?((value-input.morphCenter+540)%360-180)/90:(value-input.morphCenter)*2;
 return Math.abs(delta)>d?[b[delta<0?'negative':'positive']]:[];
}
let keyboardToken=null,keyboardObject=null,keySequence=0,keySending=false,keyboardVersion=0,commandVersion=0,commandRecorder=null,commandRequest=null;
const commandMotion=new Map();
let morphMapping=null,morphPrevious=null,actionToken=null,actionSequence=0,actionRegion=null;
function keyStatus(text){$('keyboard-status').textContent=text;$('keyboard-status').classList.toggle('is-armed',!!(keyboardToken||actionToken));}
async function stopRealKeys(reason='Stopped'){
 keyboardVersion++;keyboardToken=null;keyboardObject=null;actionToken=null;actionRegion=null;keyStatus(reason+' · real keys disarmed');
 try{await Promise.all(['/api/keys/stop','/api/actions/stop'].map(path=>fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true})));}catch(_){}
 $('action-status').textContent=reason+' · desktop actions stopped';
}
async function armRealKeys(id=$('keyboard-target').value){
 if(!id)throw new Error('Map and choose a joystick first.');
 const input=flatInputs.get(id);if(!input||(input.mode!=='xy'&&morphMapping?.object_id!==id))throw new Error('Choose a mapped joystick.');
 const version=++keyboardVersion;
 if(morphMapping?.object_id===id&&(morphMapping.output&&morphMapping.output!=='keyboard'||morphMapping.controller==='cover_button')){
  const state=await api('/api/actions/arm',{mapping:morphMapping});
  if(version!==keyboardVersion){void stopRealKeys('Arming cancelled');return;}
  keyboardToken=null;actionToken=state.token;actionSequence=0;keyboardObject=id;keyStatus('ARMED · '+(morphMapping.output||'keyboard'));$('action-status').textContent=state.reason;return;
 }
 const result=await api('/api/keys/arm',{object_id:id,mode:$('keyboard-mode').value,allowed_keys:morphMapping?.object_id===id?Object.values(morphMapping.bindings):undefined});
 if(version!==keyboardVersion){void stopRealKeys('Arming cancelled');return;}
 keyboardToken=result.token;keyboardObject=id;keySequence=0;keyStatus('ARMED · '+($('keyboard-mode').value==='typing'?'repeating letters':'holding mapped keys')+' · switch to your target app');
}
async function sendDesktopAction(){
 if(!actionToken||keySending)return;
 if(!running||studioDemo||!flatInputs.has(keyboardObject)){void stopRealKeys('Cameras or mapped control stopped');return;}
 const version=keyboardVersion,token=actionToken;
 const systemParameter=morphMapping?.output&& !['keyboard','desktop.scroll'].includes(morphMapping.output);
 const enabled=!!systemParameter||!document.hasFocus()||['keyboard-test','action-test'].includes(document.activeElement?.id);
 keySending=true;
 try{
  const state=await api('/api/actions/update',{token,sequence:actionSequence++,enabled});
  if(version!==keyboardVersion)return;
  if(!state.armed){actionToken=null;keyboardObject=null;keyStatus(state.reason+' · click Arm mapped keys to resume');}else keyStatus('ARMED · '+(morphMapping?.output||'keyboard'));
  const info=state.details||{};actionRegion=state.region||null;const input=flatInputs.get(keyboardObject);if(input)input.actionState=info;
  $('action-status').textContent=state.reason+(info.value!=null?` · ${(info.value*100).toFixed(0)}%`:'')+(info.presses!=null?` · ${info.presses} presses`:'')+(info.axis?` · move ${info.axis} · position ${(info.position*100).toFixed(0)}%`:'');
  $('action-status').classList.toggle('is-pressed',info.phase==='pressed');
 }catch(err){if(version===keyboardVersion)void stopRealKeys(err.message);}
 finally{keySending=false;}
}
async function sendRealKeys(){
 if(actionToken){await sendDesktopAction();return;}
 if(!keyboardToken||keySending)return;
 const version=keyboardVersion,token=keyboardToken,id=keyboardObject,input=flatInputs.get(id);
 if(!running||studioDemo||!input||(input.mode!=='xy'&&morphMapping?.object_id!==id)){void stopRealKeys('Joystick unavailable');return;}
 // Never use the short prediction/hold to drive real keys when no measured observation exists.
 const item=objects('top').find(o=>o.observation.object_id===id);
 const fresh=item?.observation.tracking_state==='tracked'&&performance.timeOrigin+performance.now()-cameras.top.acceptedSample<250;
 const calibrated=morphMapping?.object_id===id&&morphMapping.controller!=='joystick'||!input.poseMode||input.poseCalibration?.phase==='ready';
 const active=morphMapping?.object_id===id;
 // Within this dashboard, native output is only enabled in the explicit test field.
 const targetReady=!document.hasFocus()||document.activeElement?.id==='keyboard-test';
 const keys=targetReady&&fresh&&calibrated&&(input.controlActive||active&&input.mode!=='xy')?(active?morphKeys(morphMapping,input):Object.keys(input.keys||{}).filter(k=>input.keys[k]).map(k=>k.toLowerCase())):[];
 keySending=true;
 try{const state=await api('/api/keys/update',{token,keys,sequence:keySequence++});if(version===keyboardVersion)keyStatus('ARMED · '+(state.held.join(' + ').toUpperCase()||'neutral')+' · sends to the focused app');}
 catch(err){if(version===keyboardVersion)void stopRealKeys(err.message);}
 finally{keySending=false;}
}
setInterval(()=>void sendRealKeys(),50);
function syncCommandTargets(){
 const now=performance.timeOrigin+performance.now(),items=objects('top').filter(o=>o.motion&&o.observation.tracking_state==='tracked'&&now-cameras.top.acceptedSample<250);
 for(const item of items){const id=item.observation.object_id,old=commandMotion.get(id),p=item.motion.center_px,r=Math.sqrt(Math.max(1,item.control_features?.area||400)/Math.PI);let moved=old?.moved||0;
  if(old&&Math.hypot(p[0]-old.p[0],p[1]-old.p[1])>Math.max(2,r*.08))moved=now;commandMotion.set(id,{p,stamp:now,moved});}
 for(const [id,m] of commandMotion)if(now-m.stamp>3000)commandMotion.delete(id);
 const populate=(select,entries,placeholder)=>{const key=entries.map(e=>e[0]+e[1]).join('|');if(select.dataset.entries===key)return;const value=select.value;select.replaceChildren(new Option(placeholder,''),...entries.map(([id,label])=>new Option(label,id)));select.dataset.entries=key;if([...select.options].some(o=>o.value===value))select.value=value;};
 populate($('command-target'),items.map(o=>[o.observation.object_id,`#${o.number} ${o.object_label}`]),'Auto · one visible / moving item');
 populate($('keyboard-target'),[...flatInputs].filter(([id,i])=>(i.mode==='xy'||morphMapping?.object_id===id)).map(([id,i])=>[id,i.label]),'Choose a mapped joystick…');
}
setInterval(syncCommandTargets,200);
async function commandReply(event){
 try{unlockVoice();if(!voiceConfigured)await refreshVoiceStatus();await speakVoice(event,true);}catch(_){}
}
function renderMorph(){
 const box=$('morph-active');box.textContent=morphMapping?`${morphMapping.controller} · ${morphMapping.object_id} → ${Object.entries(morphMapping.bindings).map(([d,k])=>d+': '+k.toUpperCase()).join(' · ')} · ${morphMapping.output||'keyboard'} · ${morphMapping.mode}`:'No AI mapping active.';
 $('morph-undo').disabled=!morphPrevious;
}
async function activateMorph(mapping,message){
 const mappingVersion=commandVersion;
 const item=objects('top').find(o=>o.observation.object_id===mapping.object_id&&o.observation.tracking_state==='tracked');
 if(!running||studioDemo||!item||performance.timeOrigin+performance.now()-cameras.top.acceptedSample>250)throw new Error('Object is no longer visible. Show it and repeat your command.');
 if(!['joystick','slider_x','slider_y','cover_button'].includes(mapping.controller))throw new Error('Unsupported controller.');
 if(mapping.controller==='joystick'&&typeof useOverheadJoystick==='function')await useOverheadJoystick();
 await stopRealKeys('Applying agent mapping');
 if(mappingVersion!==commandVersion)return;
 morphPrevious=morphMapping?structuredClone(morphMapping):null;morphMapping=structuredClone(mapping);
 const id=mapping.object_id,mode=({slider_x:'x',slider_y:'y'})[mapping.controller]||'xy';
 flatInputs.set(id,{mode,pivot:mapping.controller==='joystick'&&['can','bottle','cup'].includes(item.object_label),label:`AI ${mapping.controller} · ${item.object_label} #${item.number}`,controlKind:mapping.controller,target:mapping.output||'keyboard',range:null});
 const pair=pairs.find(p=>p.top===id);if(pair)pairs.splice(pairs.indexOf(pair),1);candidates.clear();renderFlatInputs();updateStudio();syncCommandTargets();
 // Learn the source center before activating its target.
 const input=flatInputs.get(id);input.morphCenter=input.current?.value;
 $('keyboard-target').value=id;$('keyboard-mode').value=mapping.mode;renderMorph();
 $('command-status').textContent=message+(mapping.controller==='joystick'?' Hold upright to learn neutral.':mapping.controller==='cover_button'?' Keep the target stationary. Uncover to reset; click the local test field or switch apps to enable presses.':' Move along the chosen camera axis. Re-arm here to learn a new center.');
 try{await armRealKeys(id);}catch(err){keyStatus(err.message+' · mapping ready, output off');}
}
async function applyVoiceCommand(result){
 $('command-transcript').textContent='Heard: “'+result.transcript+'”';
 if(result.intent?.action==='stop_keys'){await stopRealKeys('Stopped by voice');$('command-status').textContent='Keyboard output stopped.';void commandReply('keys_stopped');return;}
 if(!running||studioDemo)throw new Error('Start the real camera first, then show your item.');
 const version=commandVersion,now=performance.timeOrigin+performance.now();
 $('command-status').textContent='ASI:One is choosing a mapping from your live inputs…';
 const response=await fetch('/api/morph/plan',{method:'POST',headers:{'Content-Type':'application/json'},signal:commandRequest?.signal,body:JSON.stringify({transcript:result.transcript,selected:$('command-target').value||null,moved:[...commandMotion].filter(([id,m])=>now-m.moved<1500).map(([id])=>id),current:morphMapping})});
 const answer=await response.json();if(version!==commandVersion)return;
 if(!response.ok)throw new Error(answer.error||'Mapping agent failed.');
 const plan=answer.plan;
 if(plan.status==='stop'){await stopRealKeys('Stopped by agent');$('command-status').textContent=plan.message;return;}
 if(plan.status!=='ready'){$('command-status').textContent=plan.message;return;}
 await activateMorph(plan.mapping,plan.message);
}
async function finishCommand(send=true){
 const rec=commandRecorder;if(!rec)return;commandRecorder=null;
 clearTimeout(rec.timer);rec.node?.disconnect();rec.source?.disconnect();rec.stream.getTracks().forEach(t=>t.stop());await rec.context.close();voiceAudio.micBusy=false;
 $('command-talk').textContent='Talk to map';$('command-talk').disabled=send;$('command-cancel').disabled=!send;
 if(!send){$('command-status').textContent='Voice cancelled · microphone off';return;}
 if(!rec.voiced){$('command-status').textContent='No speech detected. Click Talk and speak clearly.';$('command-talk').disabled=false;$('command-cancel').disabled=true;return;}
 const version=commandVersion,controller=new AbortController();commandRequest=controller;
 const timer=setTimeout(()=>controller.abort(),55000);$('command-status').textContent='Cartesia is listening to your command… microphone off';
 try{const response=await fetch('/api/voice/transcribe',{method:'POST',headers:{'Content-Type':'audio/wav'},body:encodeCommandWav(rec.chunks,rec.context.sampleRate),signal:controller.signal});const result=await response.json();if(!response.ok)throw new Error(result.error||'Voice transcription failed.');if(version===commandVersion)await applyVoiceCommand(result);}
 catch(err){if(version===commandVersion)$('command-status').textContent=err.name==='AbortError'?'Voice request cancelled or timed out.':err.message;}
 finally{clearTimeout(timer);if(version===commandVersion){commandRequest=null;$('command-talk').disabled=false;$('command-cancel').disabled=true;}}
}
async function startCommand(){
 if(commandRecorder){await finishCommand(true);return;}
 const version=++commandVersion;let stream=null,context=null;$('command-talk').disabled=true;$('command-cancel').disabled=false;cancelVoice();voiceAudio.micBusy=true;await stopRealKeys('Listening for mapping');
 try{
  unlockVoice();if(!await refreshVoiceStatus())throw new Error('Configure your Cartesia key first.');
  stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1},video:false});
  if(version!==commandVersion){stream.getTracks().forEach(t=>t.stop());return;}
  context=new AudioContext();await context.audioWorklet.addModule('/mic-worklet.js');await context.resume();
  if(version!==commandVersion){stream.getTracks().forEach(t=>t.stop());await context.close();voiceAudio.micBusy=false;return;}
  const source=context.createMediaStreamSource(stream),node=new AudioWorkletNode(context,'phantom-microphone');source.connect(node);node.connect(context.destination);
  const rec={stream,context,source,node,chunks:[],voiced:false,speechMs:0,lastSpeech:performance.now(),start:performance.now()};commandRecorder=rec;
  node.port.onmessage=e=>{if(commandRecorder!==rec)return;const chunk=e.data;rec.chunks.push(chunk);let power=0;for(const v of chunk)power+=v*v;const loud=Math.sqrt(power/chunk.length)>.015;
   if(loud){rec.speechMs+=chunk.length/context.sampleRate*1000;rec.lastSpeech=performance.now();}if(rec.speechMs>200)rec.voiced=true;
   if(rec.voiced&&performance.now()-rec.lastSpeech>900&&performance.now()-rec.start>1000)void finishCommand(true);};
  rec.timer=setTimeout(()=>void finishCommand(true),10000);$('command-talk').disabled=false;$('command-talk').textContent='Finish command';$('command-cancel').disabled=false;$('command-status').textContent='Microphone on · say “Map this can to a joystick,” then pause or click Finish.';
 }catch(err){stream?.getTracks().forEach(t=>t.stop());if(context&&context.state!=='closed')await context.close();voiceAudio.micBusy=false;if(version===commandVersion){$('command-talk').disabled=false;$('command-cancel').disabled=true;$('command-status').textContent=err.message||'Microphone could not start.';}}
}
$('command-talk').addEventListener('click',()=>void startCommand());
$('command-cancel').addEventListener('click',()=>{commandVersion++;commandRequest?.abort();voiceAudio.micBusy=false;void finishCommand(false);$('command-talk').disabled=false;$('command-text-send').disabled=false;$('command-cancel').disabled=true;$('command-status').textContent='Voice cancelled · no command applied';});
$('keyboard-arm').addEventListener('click',()=>{void armRealKeys().catch(err=>keyStatus(err.message));});
$('keyboard-stop').addEventListener('click',()=>{commandVersion++;commandRequest?.abort();$('command-text-send').disabled=false;void finishCommand(false);void stopRealKeys('Emergency stop');});
$('keyboard-mode').addEventListener('change',()=>void stopRealKeys('Output mode changed'));
$('keyboard-target').addEventListener('change',()=>void stopRealKeys('Joystick target changed'));
window.addEventListener('keydown',e=>{if(e.key==='Escape'){void stopRealKeys('Escape');if(commandRecorder){commandVersion++;void finishCommand(false);}}});
window.addEventListener('pagehide',()=>{commandVersion++;commandRequest?.abort();void finishCommand(false);void stopRealKeys('Dashboard closed');});
void fetch('/api/keys/status').then(r=>r.json()).then(s=>{if(!s.accessibility)keyStatus('macOS Accessibility permission is needed · real keys disarmed');}).catch(()=>{});

$('keyboard-permission').addEventListener('click',async()=>{try{await stopRealKeys('Permission setup');const state=await api('/api/keys/request-permission',{});keyStatus(state.accessibility?'Permission granted · click Arm real WASD':'macOS permission requested · enable the named app in Accessibility, then click Arm real WASD');}catch(err){keyStatus(err.message);}});

$('keyboard-test-send').addEventListener('click',async()=>{try{await stopRealKeys('Local test');$('keyboard-test').focus();await api('/api/keys/test',{});keyStatus('Test sent · the field above should show wasd · real control remains disarmed');}catch(err){keyStatus(err.message);}});

$('morph-undo').addEventListener('click',async()=>{if(!morphPrevious)return;const previous=structuredClone(morphPrevious);try{await activateMorph(previous,'Restored previous mapping.');}catch(err){$('command-status').textContent=err.message;}});
void fetch('/api/morph/status').then(r=>r.json()).then(s=>{
 $('morph-status').textContent=s.configured?`ASI:One · ${s.model} · ready`:'ASI:One needs ASI1_API_KEY in your local .env. Add it, then speak; no restart needed.';
 $('morph-catalog').textContent=JSON.stringify(s.catalog,null,2);
 $('morph-targets').textContent='Available actions: '+Object.values(s.catalog.targets||{}).filter(t=>t.available).map(t=>t.label).join(' · ');
}).catch(()=>{$('morph-status').textContent='Mapping agent unavailable.';});
renderMorph();

$('command-text-send').addEventListener('click',async()=>{
 const text=$('command-text').value.trim();if(!text)return;
 const version=++commandVersion;commandRequest?.abort();commandRequest=new AbortController();
 $('command-text-send').disabled=true;
 try{await stopRealKeys('Planning mapping');await applyVoiceCommand({transcript:text,intent:{}});}
 catch(err){if(version===commandVersion)$('command-status').textContent=err.message;}
 finally{if(version===commandVersion){commandRequest=null;$('command-text-send').disabled=false;}}
});
let registeringRegion=false,regionStart=null;
$('register-region').addEventListener('click',()=>{
 if(!running||studioDemo){$('command-status').textContent='Start the real overhead webcam first.';return;}
 registeringRegion=!registeringRegion;cameras.top.overlay.classList.toggle('registering-region',registeringRegion);
 $('command-status').textContent=registeringRegion?'Drag a tight rectangle around the sticker in the overhead feed. Registration is only needed if automatic detection misses it.':'Region registration cancelled.';
});
const regionCanvas=cameras.top.overlay;
function regionPoint(e){const r=regionCanvas.getBoundingClientRect(),scale=Math.min(r.width/regionCanvas.width,r.height/regionCanvas.height),w=regionCanvas.width*scale,h=regionCanvas.height*scale;return [Math.max(0,Math.min(1,(e.clientX-r.left-(r.width-w)/2)/w)),Math.max(0,Math.min(1,(e.clientY-r.top-(r.height-h)/2)/h))];}
regionCanvas.addEventListener('pointerdown',e=>{if(!registeringRegion)return;e.preventDefault();regionStart=regionPoint(e);regionCanvas.setPointerCapture(e.pointerId);});
regionCanvas.addEventListener('pointermove',e=>{if(!regionStart)return;const p=regionPoint(e);regionCanvas.dataset.region=JSON.stringify([...regionStart,...p]);});
regionCanvas.addEventListener('pointercancel',()=>{regionStart=null;delete regionCanvas.dataset.region;});
regionCanvas.addEventListener('pointerup',async e=>{
 if(!regionStart)return;const p=regionPoint(e),a=regionStart;regionStart=null;registeringRegion=false;delete regionCanvas.dataset.region;regionCanvas.classList.remove('registering-region');
 try{const result=await api('/api/register-region',{bbox:[Math.min(a[0],p[0]),Math.min(a[1],p[1]),Math.max(a[0],p[0]),Math.max(a[1],p[1])]},'top');cameras.top.result=result;syncCommandTargets();$('command-status').textContent='Sticker registered. Say what you want it to control.';}
 catch(err){$('command-status').textContent=err.message;}
});
