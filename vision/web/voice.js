'use strict';
// Debounce meaningful transitions; never narrate every frame or WASD change.
function voiceTransitions(state,live,entries,now){
 const events=[];
 if(live!==state.live){state.live=live;state.liveSince=now;state.cameraAnnounced=false;if(!live){if(state.wasLive)events.push('cameras_stopped');state.wasLive=false;state.controls=new Map();}}
 if(live&&!state.cameraAnnounced&&now-state.liveSince>=1000){events.push('cameras_ready');state.cameraAnnounced=true;state.wasLive=true;}
 state.controls=state.controls||new Map();const present=new Set();
 for(const e of entries.filter(e=>['joystick','slider'].includes(e.type))){
  present.add(e.key);let c=state.controls.get(e.key);
  if(!c){c={active:e.active,since:now,ready:false,lost:false};state.controls.set(e.key,c);}
  if(e.active!==c.active){c.active=e.active;c.since=now;}
  if(e.active&&now-c.since>=400){if(!c.ready){events.push(e.type==='joystick'?'joystick_ready':'slider_ready');c.ready=true;}else if(c.lost)events.push('tracking_recovered');c.lost=false;}
  if(!e.active&&c.ready&&!c.lost&&now-c.since>=750){events.push('tracking_lost');c.lost=true;}
 }
 for(const key of state.controls.keys())if(!present.has(key))state.controls.delete(key);
 return [...new Set(events)];
}
const voiceState={live:running,liveSince:performance.now(),controls:new Map()},voiceAudio={context:null,source:null,request:null,busy:false,version:0,pending:null};
let voiceConfigured=false,lastVoiceAt=-Infinity;
function voiceStatus(text){$('voice-status').textContent=text;}
async function refreshVoiceStatus(){
 try{const r=await fetch('/api/voice/status');if(!r.ok)throw new Error('Voice server is unavailable.');const s=await r.json();voiceConfigured=s.configured;voiceStatus(s.configured?`Cartesia · ${s.model} · ready · voice is ${$('voice-enabled').checked?'on':'off'}`:'Add your Cartesia API key to the local .env file, then press Test voice.');}
 catch(_){voiceConfigured=false;voiceStatus('Voice needs the live server at localhost:8765.');}
 return voiceConfigured;
}
function unlockVoice(){const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw new Error('Audio playback is unavailable in this browser.');voiceAudio.context=voiceAudio.context||new Audio();voiceAudio.context.resume();}
function cancelVoice(){voiceAudio.version++;voiceAudio.pending=null;voiceAudio.request?.abort();try{voiceAudio.source?.stop();}catch(_){}voiceAudio.source=null;}
async function speakVoice(event,test=false){
 if(!test&&!$('voice-enabled').checked)return;
 if(voiceAudio.busy){voiceAudio.pending={event,stamp:performance.now()};return;}
 if(!test&&performance.now()-lastVoiceAt<2500)return;
 if(!voiceConfigured)return;
 voiceAudio.busy=true;const version=voiceAudio.version;lastVoiceAt=performance.now();
 const controller=new AbortController();voiceAudio.request=controller;const timeout=setTimeout(()=>controller.abort(),10000);
 try{
  const response=await fetch('/api/voice/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event}),signal:controller.signal});
  if(!response.ok){const data=await response.json();throw new Error(data.error||'Voice request failed.');}
  const bytes=await response.arrayBuffer();if(version!==voiceAudio.version)return;
  const audio=await voiceAudio.context.decodeAudioData(bytes);if(version!==voiceAudio.version)return;
  const source=voiceAudio.context.createBufferSource();voiceAudio.source=source;source.buffer=audio;source.connect(voiceAudio.context.destination);
  voiceStatus('Cartesia · speaking');await new Promise(resolve=>{source.onended=resolve;source.start();});
  if(version===voiceAudio.version)voiceStatus('Cartesia · ready');
 }catch(err){if(version===voiceAudio.version){voiceStatus(err.name==='AbortError'?'Voice request timed out; tracking continues.':err.message);$('voice-enabled').checked=false;voiceAudio.pending=null;}}
 finally{clearTimeout(timeout);voiceAudio.busy=false;voiceAudio.request=null;const pending=voiceAudio.pending;voiceAudio.pending=null;if(pending&&performance.now()-pending.stamp<4000&&$('voice-enabled').checked)void speakVoice(pending.event);}
}
$('voice-enabled').addEventListener('change',async()=>{
 if(!$('voice-enabled').checked){cancelVoice();voiceStatus('Voice feedback off');return;}
 try{unlockVoice();if(!await refreshVoiceStatus()){$('voice-enabled').checked=false;return;}voiceState.controls=new Map();void speakVoice('test');}catch(err){$('voice-enabled').checked=false;voiceStatus(err.message);}
});
$('voice-test').addEventListener('click',async()=>{try{unlockVoice();if(await refreshVoiceStatus())void speakVoice('test',true);}catch(err){voiceStatus(err.message);}});
setInterval(()=>{if(studioDemo)return;const events=voiceTransitions(voiceState,running,registryItems(),performance.now());if($('voice-enabled').checked)for(const event of events)void speakVoice(event);},250);
window.addEventListener('pagehide',cancelVoice);
void refreshVoiceStatus();
