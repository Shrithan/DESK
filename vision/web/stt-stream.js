'use strict';
// Live microphone → Cartesia Realtime STT (ink-2, Cartesia's own turn detection).
// The browser only ever holds a short-lived STT-only token from /api/voice/token.
class PcmDownsampler{
 // Float32 at the AudioContext rate → 16-bit PCM at 16 kHz. Box-filter averaging; the fractional
 // read position is carried across chunks so consecutive chunks join without clicks.
 constructor(inRate,outRate=16000){this.ratio=inRate/outRate;this.pos=0;this.carry=new Float32Array(0);}
 push(input){
  const data=new Float32Array(this.carry.length+input.length);data.set(this.carry);data.set(input,this.carry.length);
  const out=[];let pos=this.pos;
  while(pos+this.ratio<=data.length){
   const start=Math.floor(pos),end=Math.max(start+1,Math.floor(pos+this.ratio));let sum=0;
   for(let i=start;i<end;i++)sum+=data[i];
   const v=Math.max(-1,Math.min(1,sum/(end-start)));out.push(v<0?v*32768:v*32767);pos+=this.ratio;
  }
  const keep=Math.floor(pos);this.carry=data.slice(keep);this.pos=pos-keep;
  return Int16Array.from(out);
 }
}
const STT_KEYTERMS=['joystick','slider','WASD','disk','overhead camera','calibrate upright','deadzone','Red Bull','cover button'];
class SttStream{
 constructor({onEvent,onStatus,fetchToken=sttToken,keyterms=STT_KEYTERMS}){
  Object.assign(this,{onEvent,onStatus,fetchToken,keyterms});
  this.ws=null;this.stopped=true;this.retries=0;this.stats={chunks:0,framesSent:0,events:0,peak:0};this.pending=[];this.pendingSamples=0;this.backlog=[];this.retryTimer=null;
 }
 async start(){
  this.stopped=false;this.retries=0;
  if(!navigator.mediaDevices?.getUserMedia)throw Error('This browser cannot use a microphone here. Open the app on localhost in Chrome or Safari.');
  try{this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1},video:false});}
  catch(err){
   this.stopped=true;
   if(err.name==='NotAllowedError'||err.name==='SecurityError')throw Error('Microphone access is blocked. Allow the microphone for localhost in the browser\'s site settings, then click the bear again.');
   if(err.name==='NotFoundError')throw Error('No microphone was found. Connect one, or type to the bear instead.');
   throw Error('The microphone could not start: '+(err.message||err.name));
  }
  if(this.stopped){this.stream.getTracks().forEach(t=>t.stop());return;}
  this.context=new AudioContext();await this.context.audioWorklet.addModule('/mic-worklet.js');await this.context.resume();
  const source=this.context.createMediaStreamSource(this.stream),node=new AudioWorkletNode(this.context,'phantom-microphone'),sink=this.context.createGain();
  sink.gain.value=0;source.connect(node);node.connect(sink);sink.connect(this.context.destination);
  this.source=source;this.node=node;this.down=new PcmDownsampler(this.context.sampleRate);
  node.port.onmessage=e=>this.audio(e.data);
  this.stream.getAudioTracks()[0]?.addEventListener('ended',()=>{if(!this.stopped){this.stop();this.onStatus?.('error','The microphone was disconnected. Click the bear to start again.');}});
  await this.connect();
 }
 async connect(){
  if(this.stopped)return;
  this.onStatus?.('connecting');
  let token;
  try{token=await this.fetchToken();}
  catch(err){
   // A missing/invalid key will not fix itself: stop instead of retrying forever.
   if(err.permanent){this.stop();this.onStatus?.('error',err.message);return;}
   this.scheduleReconnect(err.message);return;
  }
  if(this.stopped)return;
  const query=new URLSearchParams({model:token.model||'ink-2',encoding:'pcm_s16le',sample_rate:'16000',cartesia_version:token.version,access_token:token.token,turn_end_timeout_ms:'2400'});
  for(const term of this.keyterms)query.append('keyterm',term);
  const ws=new WebSocket(token.endpoint+'?'+query);ws.binaryType='arraybuffer';this.ws=ws;
  ws.onopen=()=>{if(this.ws!==ws)return;this.retries=0;this.onStatus?.('open');for(const chunk of this.backlog.splice(0))ws.send(chunk);};
  ws.onmessage=e=>{
   if(this.ws!==ws||typeof e.data!=='string')return;
   let event;try{event=JSON.parse(e.data);}catch(_){return;}
   if(event.type==='error'){this.onStatus?.('warning',`Cartesia speech error: ${event.message||event.title||'unknown'}`);return;}
   this.stats.events++;this.onEvent?.(event);
  };
  ws.onerror=()=>{};
  ws.onclose=e=>{if(this.ws!==ws)return;this.ws=null;if(!this.stopped)this.scheduleReconnect(e.reason||`connection closed (${e.code})`);};
 }
 scheduleReconnect(reason){
  if(this.stopped)return;
  this.retries++;
  if(this.retries>6){this.stop();this.onStatus?.('error',`I lost the connection to Cartesia (${reason}). Click the bear to try again, or type instead.`);return;}
  this.onStatus?.('reconnecting',reason);
  clearTimeout(this.retryTimer);this.retryTimer=setTimeout(()=>void this.connect(),Math.min(8000,400*2**(this.retries-1)));
 }
 audio(chunk){
  if(this.stopped||!this.down)return;
  this.stats.chunks++;for(const v of chunk){const a=Math.abs(v);if(a>this.stats.peak)this.stats.peak=a;}
  const pcm=this.down.push(chunk);if(!pcm.length)return;
  this.pending.push(pcm);this.pendingSamples+=pcm.length;
  if(this.pendingSamples<1600)return; // ~100 ms frames, as Cartesia recommends
  const frame=new Int16Array(this.pendingSamples);let offset=0;for(const p of this.pending){frame.set(p,offset);offset+=p.length;}
  this.pending=[];this.pendingSamples=0;
  if(this.ws?.readyState===WebSocket.OPEN){this.ws.send(frame.buffer);this.stats.framesSent++;}
  else{this.backlog.push(frame.buffer);if(this.backlog.length>15)this.backlog.shift();} // keep ~1.5 s while reconnecting
 }
 stop(){
  this.stopped=true;clearTimeout(this.retryTimer);
  const ws=this.ws;this.ws=null;
  if(ws){try{if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'close'}));ws.close();}catch(_){}}
  this.node?.port&&(this.node.port.onmessage=null);this.source?.disconnect();this.node?.disconnect();
  this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;
  if(this.context&&this.context.state!=='closed')void this.context.close();this.context=null;this.down=null;
  this.pending=[];this.pendingSamples=0;this.backlog=[];
 }
}
async function sttToken(){
 let response;
 try{response=await fetch('/api/voice/token',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});}
 catch(_){throw Error('The studio server is not reachable. Is python -m vision.live still running?');}
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const err=Error(data.error||'Voice token unavailable.');err.permanent=response.status===503||/rejected the API key/.test(err.message);throw err;}
 return data;
}
if(typeof module!=='undefined')module.exports={PcmDownsampler,SttStream};
