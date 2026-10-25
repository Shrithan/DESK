'use strict';
// Presentation adapter only: delegate to the existing studio controls.
(()=>{
 const stage=document.createElement('section');stage.className='bear-stage';stage.setAttribute('aria-label','Cal voice assistant');
 stage.innerHTML=`<div class="bear-topline"><span>DESK / YOUR SPATIAL ASSISTANT</span><span class="bear-live" id="bear-live">CAMERA OFF</span></div>
 <div class="bear-introduction"><p class="bear-eyebrow">MEET CAL</p><h1>Your desk has a voice.</h1><p>Show me your objects. Tell me what you want to do.</p></div>
 <button class="bear-avatar" id="bear-avatar" aria-label="Talk to Cal"><span class="bear-halo" aria-hidden="true"></span><canvas id="bear-canvas" aria-hidden="true"></canvas><img id="bear-fallback" alt="Cal bear wearing a blue cap" hidden></button>
 <div class="bear-message"><span class="bear-state" id="bear-state" role="status">READY WHEN YOU ARE</span><p id="bear-hint">Click Cal to talk</p></div>
 <div class="bear-dock"><button id="bear-camera">Start camera</button><button id="bear-mute" aria-pressed="false">Mute Cal</button><button id="bear-reset">Reset module</button><button id="bear-stop" class="bear-emergency">Stop output</button></div>
 <div class="bear-conversation"><p id="bear-transcript"></p><p id="bear-reply" aria-live="polite">Try “Use this can for Flight” or “Make this bottle a brightness slider.”</p></div>`;
 document.querySelector('main').prepend(stage);document.body.classList.add('bear-interface');
 let bearMuted=false;$('voice-enabled').checked=true;
 const artwork=$('bear-fallback');artwork.src=BEAR_ARTWORK;
 // Keep all original elements and their listeners; change only the visible presentation.
 const textForm=document.createElement('form');textForm.className='bear-text-form';
 const field=$('command-text'),send=$('command-text-send');
 field.placeholder='Or tell Cal what you want to control…';field.setAttribute('aria-label','Message Cal');send.textContent='Send';send.type='submit';
 textForm.append(field,send);stage.querySelector('.bear-conversation').before(textForm);
 textForm.addEventListener('submit',event=>event.preventDefault());
 field.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();send.click();}});
 const drawer=document.createElement('details');drawer.className='bear-workspace';drawer.innerHTML='<summary>Camera & workspace</summary>';
 const developer=document.querySelector('.developer-tools');
 for(const node of [...document.querySelector('main').children])if(node!==stage&&node!==developer)drawer.append(node);
 document.querySelector('main').append(drawer);if(developer)document.querySelector('main').append(developer);
 $('bear-avatar').addEventListener('click',()=>{
  if(commandRecorder){$('command-talk').click();return;}
  if(commandRequest||agentApplication){$('command-cancel').disabled=false;$('command-cancel').click();return;}
  if(voiceAudio.source)cancelVoice();
  $('command-talk').click();$('voice-enabled').checked=!bearMuted;
 });
 $('bear-camera').addEventListener('click',()=>{$(running?'studio-stop':'start').click();});
 $('bear-reset').addEventListener('click',()=>{$('module-reset').click();});
 $('bear-stop').addEventListener('click',()=>{$('keyboard-stop').click();});
 $('bear-mute').addEventListener('click',()=>{
  const muted=!bearMuted;bearMuted=muted;
  $('voice-enabled').checked=!muted;
  if(muted)cancelVoice();
  $('bear-mute').textContent=muted?'Unmute Cal':'Mute Cal';$('bear-mute').setAttribute('aria-pressed',String(muted));
 });
 let lastReply='';
 setInterval(()=>{
  const speaking=!!voiceAudio.source&&voiceAudio.context?.state==='running'&&voiceAudio.context.currentTime<(voiceAudio.source._bearEnd??-1);
  const state=commandRecorder?'listening':speaking?'speaking':commandRequest||agentApplication?'thinking':'idle';
  for(const name of ['listening','speaking','thinking'])document.body.classList.toggle('va-'+name,state===name);
  stage.dataset.state=state;
  $('bear-state').textContent=({listening:'I’M LISTENING',thinking:'LET ME FIGURE THAT OUT',speaking:'CAL IS SPEAKING',idle:'READY WHEN YOU ARE'})[state];
  $('bear-hint').textContent=({listening:'Tell me what your objects should do · click to finish',thinking:'Choosing a module and its inputs · click to cancel',speaking:'Click to interrupt Cal',idle:'Click Cal to talk'})[state];
  $('bear-avatar').setAttribute('aria-label',({listening:'Finish speaking to Cal',thinking:'Cancel Cal request',speaking:'Interrupt Cal',idle:'Talk to Cal'})[state]);
  $('bear-avatar').disabled=moduleResetting;
  $('bear-camera').textContent=running?'Stop camera':'Start camera';$('bear-camera').disabled=opening;
  $('bear-reset').disabled=moduleResetting;
  $('bear-live').textContent=running?'● CAMERA LIVE':'CAMERA OFF';
  $('bear-live').classList.toggle('is-live',running);
  $('bear-transcript').textContent=$('command-transcript').textContent;
  const reply=$('command-status').textContent;if(reply&&reply!==lastReply){lastReply=reply;$('bear-reply').textContent=reply.replaceAll('Talk to map','Cal').replace('click Talk','click Cal');}
  // Reflect errors without hiding a failed mapping behind the character.
  if(!$('error').hidden&&$('error').textContent)$('bear-reply').textContent=$('error').textContent;
  send.disabled=!!(commandRecorder||commandRequest||moduleResetting);
 },100);
})();

// Connect the existing Cartesia audio to its original destination and animate
// the imported jaw from its actual decoded waveform. No extra speech request.
function connectBearVoice(source){
 source.connect(voiceAudio.context.destination);
 source._bearEnd=voiceAudio.context.currentTime+source.buffer.duration;
 const data=source.buffer.getChannelData(0),rate=source.buffer.sampleRate,started=voiceAudio.context.currentTime;
 let level=0,ended=false;
 source.addEventListener('ended',()=>{ended=true;source._bearEnd=-1;window.setBearMouth?.(0);},{once:true});
 function animate(){
  if(ended||voiceAudio.source!==source){window.setBearMouth?.(0);return;}
  const offset=Math.max(0,Math.floor((voiceAudio.context.currentTime-started)*rate));
  const end=Math.min(data.length,offset+Math.round(rate*.02));let sum=0;
  for(let i=offset;i<end;i++)sum+=data[i]*data[i];
  const rms=Math.sqrt(sum/Math.max(1,end-offset));const target=Math.min(1,Math.max(0,(rms-.01)*9));
  level+=(target-level)*(target>level?.5:.25);window.setBearMouth?.(level);
  requestAnimationFrame(animate);
 }
 requestAnimationFrame(animate);
}
