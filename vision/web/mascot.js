'use strict';
// Explicit local commands share the exact handlers used by the setup controls.
// Open-ended object-to-app mappings still go through the validated Morph planner.
function normalizedSpeech(text){return String(text||'').trim().toLowerCase().replace(/[.!?]+$/,'').replace(/\s+/g,' ');}
function spokenTarget(text,entries){
 const numbered=text.match(/\b(?:number|#)\s*(\d+|one|two|three|four|five)\b|\b(?:disk|can|bottle|cup|mouse|book|phone|object|slider|joystick|button)\s+(\d+|one|two|three|four|five)\b/);
 const numberWord=numbered?.[1]||numbered?.[2];
 const number=numberWord?({one:1,two:2,three:3,four:4,five:5}[numberWord]||Number(numberWord)):null;
 const label=(text.match(/\b(can|bottle|cup|disk|mouse|book|phone|pen|ball|box|scissors|remote)\b/)||[])[1];
 let choices=entries;
 if(number!==null)choices=choices.filter(e=>e.item?.number===number||e.name?.includes('#'+number)||e.name?.includes(' #'+number));
 if(label)choices=choices.filter(e=>e.item?.object_label===label||label==='can'&&['cup','bottle'].includes(e.item?.object_label)||e.name?.toLowerCase().includes(label));
 if(!number&&!label&&choices.length!==1)return null;
 return choices.length===1?choices[0]:null;
}
function clickControl(id){const el=$(id);if(!el||el.disabled)throw Error('That control is unavailable right now.');el.click();}
function setCheckbox(id,value){const el=$(id);if(el.checked!==value){el.checked=value;el.dispatchEvent(new Event('change'));}}
function cardControl(entry,label){const card=studioCards.get(entry.key),button=[...(card?.actions?.querySelectorAll('button')||[])].find(b=>b.textContent===label);if(!button||button.disabled)throw Error(`${label} is unavailable for that object right now.`);button.click();}
function chooseInputTarget(text,types=['candidate','joystick','slider','button','object']){
 const entries=registryItems().filter(e=>types.includes(e.type)&&e.active);
 const target=spokenTarget(text,entries);
 if(!target)throw Error(entries.length?'Please name one visible object, such as “disk number one.”':'Show an object to the overhead camera first.');
 return target;
}
async function routeStudioCommand(transcript){
 const text=normalizedSpeech(transcript);
 const done=message=>({handled:true,message});
 if(/^(hello|hi|hey)( bear)?$/.test(text))return done('Hi! Say “start the camera,” or ask me to make a visible object a control.');
 if(/^(help|what can (you|i) (say|do)|list commands)$/.test(text))return done('I can start cameras, make visible objects into joysticks, sliders or buttons, calibrate controls, arm or stop output, and adjust camera settings.');
 if(/\b(open|show) (the )?(workspace|setup|controls|camera feeds)\b/.test(text)){$('workspace-setup').open=true;return done('Workspace controls are open below.');}
 if(/\b(close|hide) (the )?(workspace|setup|controls|camera feeds)\b/.test(text)){$('workspace-setup').open=false;return done('Workspace controls are closed.');}
 if(/\b(stop all output|emergency stop|stop everything)\b/.test(text)){clickControl('keyboard-stop');return {handled:true,message:'All output stopped. Hands-free listening is off.',silent:true};}
 if(/\b(stop|turn off) (the )?(camera|cameras|webcam|webcams)\b/.test(text)){clickControl('studio-stop');return done('Stopping the cameras.');}
 if(/\b(start|turn on|connect) (the )?(overhead )?(camera|cameras|webcam|webcams)\b/.test(text)){if(text.includes('overhead')){$('overhead-only').checked=true;await useOverheadJoystick();}clickControl('start');return done('Starting the camera. Allow browser camera access if asked.');}
 if(/\b(start|show|exit) (the )?(demo|preview)\b/.test(text)){clickControl('preview-layout');return done('Changing the demo view.');}
 if(/\b(refresh|find) (the )?cameras\b/.test(text)){clickControl('refresh-cameras');return done('Refreshing available cameras.');}
 if(/\b(overhead only|one camera mode|single camera mode)\b/.test(text)){setCheckbox('overhead-only',true);return done('Overhead-only camera mode selected.');}
 if(/\b(two camera mode|both cameras mode)\b/.test(text)){setCheckbox('overhead-only',false);return done('Two-camera mode selected.');}
 if(/\b(require usb|usb only)\b/.test(text)){setCheckbox('iphone-usb-only',true);return done('USB is required for the iPhone camera.');}
 if(/\b(allow wireless|turn off usb only)\b/.test(text)){setCheckbox('iphone-usb-only',false);return done('Wireless and USB iPhone cameras are allowed.');}
 if(/\b(reset all tracks|clear all tracks)\b/.test(text)){clickControl('reset');return done('Resetting all tracked objects.');}
 if(/\b(set (the )?current positions as zero|zero (the )?(workspace|positions))\b/.test(text)){clickControl('zero');return done('The current positions are the new zero.');}
 if(/\b(reset zoom|wide view)\b/.test(text)){const role=/\b(side|front)\b/.test(text)?'front':'top';clickControl('wide-'+role);return done(`Resetting ${role==='top'?'overhead':'side'} zoom.`);}
 if(/\b(lock (the )?(exposure|color|colour|white balance))\b/.test(text)){const role=/\b(side|front)\b/.test(text)?'front':'top';clickControl('lock-exposure-'+role);return done(`Locking ${role==='top'?'overhead':'side'} exposure and colour.`);}
 if(/\b(auto (exposure|color|colour|white balance)|unlock exposure)\b/.test(text)){const role=/\b(side|front)\b/.test(text)?'front':'top';clickControl('auto-exposure-'+role);return done(`Returning ${role==='top'?'overhead':'side'} exposure to automatic.`);}
 if(/\b(reverse|flip) (the )?(x|y|z) (direction|axis)?\b/.test(text)){const axis=text.match(/\b(x|y|z)\b/)[1];const id=axis==='x'?'flip-top':axis==='y'?'flip-y':'flip-front';setCheckbox(id,!$(id).checked);return done(`Reversed the ${axis.toUpperCase()} direction.`);}
 if(/\b(turn on|enable) (the )?(prediction|motion prediction)\b/.test(text)){setCheckbox('predict',true);return done('Motion prediction is on.');}
 if(/\b(turn off|disable) (the )?(prediction|motion prediction)\b/.test(text)){setCheckbox('predict',false);return done('Motion prediction is off.');}
 if(/\b(turn on|enable) (the )?(voice feedback|spoken feedback)\b/.test(text)){$('voice-enabled').checked=true;$('voice-enabled').dispatchEvent(new Event('change'));return done('Voice feedback is on.');}
 if(/\b(turn off|disable) (the )?(voice feedback|spoken feedback)\b/.test(text)){$('voice-enabled').checked=false;$('voice-enabled').dispatchEvent(new Event('change'));return done('Voice feedback is off.');}
 if(/\b(test (the )?voice|say something)\b/.test(text)){clickControl('voice-test');return done('Playing a Cartesia voice test.');}
 if(/\b(undo (the )?(last )?mapping|restore previous mapping)\b/.test(text)){clickControl('morph-undo');return done('Restoring the previous mapping.');}
 if(/\b(request|open|check) (keyboard )?permission\b/.test(text)){clickControl('keyboard-permission');return done('Requesting macOS keyboard permission. Follow the system prompt.');}
 if(/\btest (the )?(real )?(keyboard|keys|wasd)\b/.test(text)){clickControl('keyboard-test-send');return done('Sending the local keyboard test.');}
 if(/\b(arm|enable|resume) (the )?(mapped )?(keys|keyboard|output)\b/.test(text)){clickControl('keyboard-arm');return done('Arming the selected output.');}
 if(/\b(stop|disarm|release) (the )?(keys|keyboard|output)\b/.test(text)){await stopRealKeys('Stopped by voice');return done('Keyboard and desktop output stopped.');}
 if(/\b(game mode|hold keys)\b/.test(text)){$('keyboard-mode').value='game';$('keyboard-mode').dispatchEvent(new Event('change'));return done('Game mode selected. Arm output when ready.');}
 if(/\b(document mode|typing mode|repeat letters)\b/.test(text)){$('keyboard-mode').value='typing';$('keyboard-mode').dispatchEvent(new Event('change'));return done('Document mode selected. Arm output when ready.');}
 if(/\b(calibrate upright|learn (the )?neutral)\b/.test(text)){const e=chooseInputTarget(text,['joystick']);cardControl(e,'Calibrate upright (1s)');return done(`Calibrating ${e.name} upright. Hold it still for one second.`);}
 if(/\blearn (w|forward)\b/.test(text)){const e=chooseInputTarget(text,['joystick']);cardControl(e,'Learn W');return done(`Learning forward for ${e.name}.`);}
 if(/\blearn (d|right)\b/.test(text)){const e=chooseInputTarget(text,['joystick']);cardControl(e,'Learn D');return done(`Learning right for ${e.name}.`);}
 if(/\b(center|recenter|zero yaw)\b/.test(text)){const e=chooseInputTarget(text,['joystick']);cardControl(e,'Center & zero yaw');return done(`Centered ${e.name}.`);}
 if(/\b(set (the )?(slider )?(zero|0|100|one hundred)( percent|%)?( here)?)\b/.test(text)){const e=chooseInputTarget(text,['slider']);const high=/100|one hundred/.test(text);cardControl(e,high?'Set 100%':'Set 0%');return done(`Set ${e.name} to ${high?'100':'0'} percent here.`);}
 if(/\b(remove|delete) (this |the )?(input|joystick|slider|button|control)\b/.test(text)){const e=chooseInputTarget(text,['joystick','slider','button']);cardControl(e,'Remove');return done(`Removed ${e.name}.`);}
 if(/\b(unpair)\b/.test(text)){const e=chooseInputTarget(text,['object']);cardControl(e,'Unpair');return done(`Unpaired ${e.name}.`);}
 if(/\b(reconnect|relearn) (the )?(button|object)\b/.test(text)){const e=chooseInputTarget(text,['button']);cardControl(e,'Reconnect / relearn object');return done(`Reconnecting ${e.name}.`);}
 if(/\b(use pivot|pivot mode|use wasd)\b/.test(text)){const e=chooseInputTarget(text,['joystick']);cardControl(e,'Use pivot / WASD');return done(`Pivot control is on for ${e.name}.`);}
 if(/\b(switch|swap|change) (the )?(slider )?(x|horizontal) (to )?(y|vertical)\b|\b(switch|swap|change) (the )?(slider )?(y|vertical) (to )?(x|horizontal)\b/.test(text)){const e=chooseInputTarget(text,['slider']);cardControl(e,'X ↔ Y');return done(`Changed the slider axis for ${e.name}.`);}
 if(/\b(make|turn) (this |the )?slider (a |into a )?joystick\b/.test(text)){const e=chooseInputTarget(text,['slider']);cardControl(e,'Make joystick');return done(`Made ${e.name} a joystick.`);}
 if(/\b(make|turn) (this |the )?joystick (a |into a )?slider\b/.test(text)){const e=chooseInputTarget(text,['joystick']);cardControl(e,'Make slider');return done(`Made ${e.name} a slider.`);}
 if(/\b(use (my |the )?can as (a )?joystick)\b/.test(text)){clickControl('can-joystick');return done('Can joystick setup is ready. Show the can to the overhead camera.');}
 if(/\b(pair (the )?(selected )?objects)\b/.test(text)){clickControl('pair');return done('Pairing the two selected camera tracks.');}
 if(/\b(make|turn|use|add|map)\b/.test(text)&&/\b(joystick|slider|button)\b/.test(text)&&!/(brightness|volume|scroll|open|keyboard|keys|arrows|wasd)/.test(text)){
  const kind=/\bjoystick\b/.test(text)?'joystick':/\bslider\b/.test(text)?'slider':'button';
  const e=chooseInputTarget(text,['candidate','joystick','slider','button','object']);
  if(kind==='button'){if(!await assignDetectedButton({id:e.id||e.pair?.top,name:e.name}))throw Error('The button could not be created. Check that the object is visible.');}
  else assignInput({id:e.id||e.pair?.top,name:e.name},kind==='joystick'?'xy':'x');
  return done(`Made ${e.name} a ${kind}.`);
 }
 const requested=text.match(/^(?:press|click|activate) (?:the )?(.+)$/)?.[1];
 if(requested){
  const [label,targetText]=requested.split(/\s+on\s+(.+)$/);
  const buttons=targetText?(()=>{const e=chooseInputTarget(targetText);return [...(studioCards.get(e.key)?.actions?.querySelectorAll('button')||[])];})():[...document.querySelectorAll('.workspace-content button')].filter(b=>!b.closest('[hidden]'));
  const matches=buttons.filter(b=>normalizedSpeech(b.textContent)===label);
  if(matches.length!==1)throw Error(matches.length?'More than one control has that name. Name the object or camera.':'I cannot find that button. Say “help” for examples.');
  if(matches[0].disabled)throw Error('That control is unavailable right now.');
  matches[0].click();return done(`Activated ${matches[0].textContent.trim()}.`);
 }
 return null;
}
function bearCaption(message){$('bear-response').textContent=message;}
async function bearSay(message){
 bearCaption(message);
 if(!voiceConfigured||!message||voiceAudio.micBusy)return;
 voiceAudio.replyBusy=true;cancelVoice();
 try{
  unlockVoice();const response=await fetch('/api/voice/utterance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:message})});
  if(!response.ok){const data=await response.json();throw Error(data.error||'Cartesia speech unavailable.');}
  const buffer=await voiceAudio.context.decodeAudioData(await response.arrayBuffer());
  const source=voiceAudio.context.createBufferSource();source.buffer=buffer;source.connect(voiceAudio.context.destination);voiceAudio.source=source;
  await new Promise(resolve=>{source.onended=()=>{if(voiceAudio.source===source)voiceAudio.source=null;resolve();};source.start();});
 }catch(err){$('bear-state').textContent=err.message;}
 finally{voiceAudio.replyBusy=false;}
}
$('bear-talk').addEventListener('click',async()=>{
 if(!$('command-hands-free').checked){
  try{unlockVoice();if(!await refreshVoiceStatus()){$('bear-state').textContent='Add CARTESIA_API_KEY to this checkout’s .env file, then try again.';return;}}
  catch(err){$('bear-state').textContent=err.message;return;}
  $('voice-enabled').checked=true;$('voice-enabled').dispatchEvent(new Event('change'));
  $('command-hands-free').checked=true;$('command-hands-free').dispatchEvent(new Event('change'));
 }
});
$('bear-stop').addEventListener('click',()=>{$('command-hands-free').checked=false;$('command-hands-free').dispatchEvent(new Event('change'));});
void fetch('/api/voice/status').then(r=>r.json()).then(s=>{if(!s.configured)bearCaption('Add your Cartesia API key to this checkout’s .env file, then I can listen and speak.');}).catch(()=>{});
setInterval(()=>{
 const listening=$('command-hands-free').checked;
 $('bear-talk').disabled=listening;$('bear-stop').disabled=!listening;
 document.body.classList.toggle('bear-listening',listening&&!!commandRecorder);
 document.body.classList.toggle('bear-speaking',!!voiceAudio.source);
 $('bear-live').textContent=$('studio-state').textContent;
 $('bear-state').textContent=listening?($('command-status').textContent||'Listening…'):(voiceConfigured?'Cartesia ready · microphone off':'Cartesia API key needed · microphone off');
 const transcript=$('command-transcript').textContent;if(transcript)$('bear-transcript').textContent=transcript;
},250);
