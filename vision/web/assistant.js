'use strict';
// The bear as the whole interface: Cartesia STT → ASI:One tool calls → the studio's real handlers →
// Cartesia Sonic reply. Every tool runs the same code the old buttons ran and reports what it verified.
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const ROLE_ID={overhead:'top',side:'front'};
const NUMBER_WORDS={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10};
const OBJECT_LABELS=['can','bottle','cup','disk','mouse','book','phone','pen','ball','box','scissors','remote','keyboard','sticker'];
const convo={history:[],version:0,busy:false,focus:null,voiceTarget:null,muted:false,stopAfterReply:false,navigateAfterReply:null,listening:false,activity:[]};
try{convo.muted=localStorage.getItem('bear-voice-muted')==='1';}catch(_){}
const ok=(result={})=>({ok:true,...result});
const fail=(error,extra={})=>({ok:false,error,...extra});
function words(text){return String(text||'').toLowerCase().replace(/[^a-z0-9#\s]/g,' ').split(/\s+/).filter(Boolean);}

// ---------- object references ----------
function entryId(e){return e.id||e.pair?.top||null;}
function describeEntry(e){return `${e.name} (${{candidate:'not a control yet',joystick:'joystick',slider:'slider',button:'cover button',object:'spatial object'}[e.type]||e.type})`;}
function resolveEntry(ref,types=['candidate','joystick','slider','button','object']){
 const all=registryItems(),entries=all.filter(e=>types.includes(e.type));
 const text=String(ref||'').trim().toLowerCase(),tokens=words(text);
 const pick=e=>{convo.focus=entryId(e)||e.key;return e;};
 if(!entries.length)throw Error(all.length?`There is no ${types.join(' or ')} to use. Current objects: ${all.map(describeEntry).join(', ')}.`:running?'I don\'t see any objects yet. Move one briefly under the overhead camera.':'The cameras are off, so there are no objects yet.');
 const exact=entries.find(e=>[e.id,e.key,e.pair?.top].includes(ref));if(exact)return pick(exact);
 if(!tokens.length||/^(it|that|this|that one|this one|the one|same one|the same one|auto)$/.test(text)){
  for(const id of [convo.focus,convo.voiceTarget,$('command-target')?.value]){const e=id&&entries.find(x=>entryId(x)===id||x.key===id);if(e)return pick(e);}
  if(entries.length===1)return pick(entries[0]);
  throw Error(`Which one? ${entries.map(describeEntry).join(', ')}.`);
 }
 const numberToken=tokens.map(t=>t.replace('#','')).find(t=>/^\d+$/.test(t)||NUMBER_WORDS[t]);
 const number=numberToken?(NUMBER_WORDS[numberToken]||Number(numberToken)):null;
 const label=tokens.find(t=>OBJECT_LABELS.includes(t)||t==='disc'||t==='mug');
 const wanted=label==='disc'?'disk':label==='mug'?'cup':label;
 let matches=entries;
 if(number!=null)matches=matches.filter(e=>e.item?.number===number||e.pair?.number===number||e.name?.includes('#'+number));
 if(wanted)matches=matches.filter(e=>{const l=e.item?.object_label||e.pair?.label||'';return l===wanted||wanted==='can'&&['bottle','cup'].includes(l)||e.name?.toLowerCase().includes(wanted);});
 if(number==null&&!wanted)matches=entries.filter(e=>tokens.every(t=>e.name?.toLowerCase().includes(t)));
 if(matches.length===1)return pick(matches[0]);
 if(!matches.length)throw Error(`I can't find "${ref}". Current objects: ${entries.map(describeEntry).join(', ')}.`);
 throw Error(`"${ref}" matches more than one: ${matches.map(describeEntry).join(', ')}. Which one?`);
}
function resolveCameraObject(role,ref){
 const list=objects(role).filter(o=>o.observation.tracking_state==='tracked'),tokens=words(ref);
 const n=tokens.map(t=>t.replace('#','')).map(t=>NUMBER_WORDS[t]||(/^\d+$/.test(t)?Number(t):null)).find(v=>v!=null);
 const label=tokens.find(t=>OBJECT_LABELS.includes(t));
 const hits=list.filter(o=>o.observation.object_id===ref||(n==null||o.number===n)&&(!label||compatible(o.object_label,label)));
 if(hits.length===1)return hits[0];
 const name=role==='top'?'overhead':'side';
 throw Error(hits.length?`Several ${name} objects match "${ref}": ${hits.map(o=>`#${o.number} ${o.object_label}`).join(', ')}.`:`No ${name} object matches "${ref}". Visible: ${list.map(o=>`#${o.number} ${o.object_label}`).join(', ')||'none'}.`);
}
function cardButton(entry,label){
 const card=studioCards.get(entry.key),button=[...(card?.actions?.querySelectorAll('button')||[])].find(b=>b.textContent===label);
 if(!button)throw Error(`${label} isn't available for ${entry.name} right now.`);
 return button;
}
function setChecked(id,value){const el=$(id);if(el.checked!==value){el.checked=value;el.dispatchEvent(new Event('change'));}return el.checked===value;}
function setSelect(id,value){const el=$(id);el.value=value;el.dispatchEvent(new Event('change'));return el.value===value;}
const armed=()=>!!(keyboardToken||actionToken);
function controlSummary(e){
 const i=e.input,s={name:e.name,type:e.type,active:!!e.active,id:entryId(e)};
 if(e.type==='joystick'){s.pivot=!!i.pivot;if(i.poseMode)s.calibration=i.poseCalibration?.phase||'needs upright calibration';if(e.active&&i.joystick)s.position={x:+i.joystick.x.toFixed(2),y:+i.joystick.y.toFixed(2)};s.keys=Object.keys(i.keys||{}).filter(k=>i.keys[k]);}
 if(e.type==='slider'){s.axis=i.mode==='x'?'horizontal':'vertical';s.ends_set=!!i.range;if(i.current?.value!=null)s.value_percent=Math.round(i.current.value*100);}
 if(e.type==='button')s.state=i.actionState?.phase||'waiting';
 if(e.type==='object')s.position=e.pair.position?.map(v=>+v.toFixed(1))||null;
 if(e.item)s.label=e.item.object_label;
 return s;
}

// ---------- live state, sent with every reasoning step ----------
function appState(){
 const role=r=>{const c=cameras[r],select=$(`camera-${r}`),track=c.stream?.getVideoTracks()[0];return {source:select?.selectedOptions[0]?.text||null,connected:!!track,state:$(`state-${r}`)?.textContent,orientation:$(`orientation-${r}`)?.value,exposure:$(`exposure-status-${r}`)?.textContent};};
 const items=registryItems();
 return {
  cameras:{running,demo_preview:studioDemo,starting:opening,mode:$('overhead-only').checked?'overhead_only':'two_cameras',iphone_usb_required:$('iphone-usb-only').checked,
   overhead:role('top'),side:$('overhead-only').checked?'off in overhead-only mode':role('front'),
   available_sources:[...$('camera-top').options].map(o=>o.text).slice(0,8),status:$('status').textContent,error:$('error').hidden?null:$('error').textContent,
   reversed:{x:$('flip-top').checked,y:$('flip-y').checked,z:$('flip-front').checked},motion_prediction:$('predict').checked},
  objects_not_yet_controls:items.filter(e=>e.type==='candidate').map(controlSummary).slice(0,12),
  controls:items.filter(e=>e.type!=='candidate').map(controlSummary).slice(0,12),
  side_camera_unpaired:running&&!$('overhead-only').checked?available('front').map(o=>`#${o.number} ${o.object_label}`).slice(0,8):[],
  mapping:{current:morphMapping?{object:morphMapping.object_id,controller:morphMapping.controller,output:morphMapping.output||'keyboard',bindings:morphMapping.bindings,mode:morphMapping.mode,deadzone:morphMapping.deadzone}:null,can_undo:!!morphPrevious},
  output:{armed:armed(),selected_control:$('keyboard-target').value||null,mode:$('keyboard-mode').value==='typing'?'document (repeat letters)':'game (hold keys)',status:$('keyboard-status').textContent,action_status:$('action-status').textContent},
  voice:{status_announcements:$('voice-enabled').checked,bear_voice_muted:convo.muted,listening:convo.listening,voice_target:convo.voiceTarget||'auto'},
  display:{panel:assistantView.current,controls_filter:studioFilter},
  last_discussed:convo.focus
 };
}

// ---------- tools: each one calls the original handler, then checks the result ----------
async function waitFor(check,ms=1500){const end=performance.now()+ms;while(performance.now()<end){if(check())return true;await sleep(50);}return check();}
const MAPPING_DEFAULTS={
 joystick:{keyboard:{up:'w',down:'s',left:'a',right:'d'}},
 slider_x:{'desktop.scroll':{negative:'up',positive:'down'},'display.brightness':{negative:'decrease',positive:'increase'},'audio.volume':{negative:'decrease',positive:'increase'}},
 slider_y:{'desktop.scroll':{negative:'up',positive:'down'},'display.brightness':{negative:'increase',positive:'decrease'},'audio.volume':{negative:'increase',positive:'decrease'}},
};
let actionCatalog=null;
async function catalogTargets(){if(!actionCatalog){const r=await fetch('/api/morph/status');actionCatalog=(await r.json()).catalog;}return actionCatalog.targets||{};}
const TOOLS={
 async start_cameras({mode}){
  if(mode)setChecked('overhead-only',mode==='overhead_only');
  if(studioDemo)clearStudioDemo();
  await start();await sleep(200);
  if(!running)return fail($('error').hidden?'The cameras did not start.':$('error').textContent);
  return ok({running:true,mode:$('overhead-only').checked?'overhead_only':'two_cameras',sources:Object.fromEntries(['top','front'].filter(r=>cameras[r].stream).map(r=>[r==='top'?'overhead':'side',cameras[r].stream.getVideoTracks()[0].label]))});
 },
 async stop_cameras(){await stop();return running?fail('The cameras are still running.'):ok({running:false,output_armed:armed()});},
 async set_camera_mode({mode}){
  const was=running;setChecked('overhead-only',mode==='overhead_only');await sleep(300);
  return ok({mode,note:mode==='two_cameras'&&was?'Two-camera mode stopped the cameras; start them again to use both.':undefined,running});
 },
 async list_cameras(){
  const devices=await inventory();
  return ok({sources:devices.map(d=>d.label||'Unnamed camera (permission not granted yet)'),overhead:$('camera-top').selectedOptions[0]?.text||null,side:$('camera-front').selectedOptions[0]?.text||null});
 },
 async choose_camera({role,device}){
  const id=ROLE_ID[role],select=$(`camera-${id}`);await inventory().catch(()=>{});
  const want=words(device),options=[...select.options].filter(o=>want.every(w=>o.text.toLowerCase().includes(w)));
  if(options.length!==1)return fail(options.length?`Several cameras match: ${options.map(o=>o.text).join(', ')}.`:`No camera matches "${device}". Available: ${[...select.options].map(o=>o.text).join(', ')||'none'}.`);
  select.value=options[0].value;
  if(running){await start();if(!running)return fail($('error').textContent||'The cameras did not restart.');}
  return ok({role,source:options[0].text,applied:running?'restarted cameras':'used next time the cameras start'});
 },
 async set_camera_orientation({role,orientation}){
  const id=ROLE_ID[role],value={auto:'auto',original:'raw',clockwise:'cw',counterclockwise:'ccw'}[orientation];
  $(`orientation-${id}`).value=value;
  if(running){await start();if(!running)return fail($('error').textContent||'The cameras did not restart.');}
  return ok({role,orientation,applied:running?'restarted cameras':'used next time the cameras start'});
 },
 async reset_camera_zoom({role}){
  const id=ROLE_ID[role];if(!cameras[id].stream)return fail(`The ${role} camera isn't running.`);
  await wideView(id);return ok({role,info:$(`camera-info-${id}`).textContent});
 },
 async set_camera_exposure({role,locked}){
  const id=ROLE_ID[role];await cameraExposure(id,locked);const status=$(`exposure-status-${id}`).textContent;
  return /unavailable|Start this camera|Camo Studio/.test(status)?fail(status):ok({role,status});
 },
 async set_iphone_usb_required({required}){const was=running;setChecked('iphone-usb-only',required);return ok({required,status:$('usb-phone-status').textContent,cameras_stopped:was&&!running});},
 async reverse_axis({axis,reversed}){const id={x:'flip-top',y:'flip-y',z:'flip-front'}[axis];return setChecked(id,reversed)?ok({axis,reversed,note:'Positions re-zeroed.'}):fail('The setting did not change.');},
 async set_motion_prediction({enabled}){return setChecked('predict',enabled)?ok({enabled}):fail('The setting did not change.');},
 async set_demo_preview({enabled}){
  if(enabled&&running)return fail('The demo needs the cameras off. Stop the cameras first.');
  if(studioDemo!==enabled)$('preview-layout').click();
  return studioDemo===enabled?ok({demo_preview:enabled,note:enabled?'Simulated controls, not real tracking.':undefined}):fail('The demo did not change.');
 },
 async zero_workspace(){zero();return ok({spatial_objects:pairs.length});},
 async reset_all_tracks(){await resetTracks();return pairs.length===0&&flatInputs.size===0?ok({running}):fail('Some tracks remain.');},
 async pair_objects({side_object,overhead_object}){
  const a=resolveCameraObject('front',side_object),b=resolveCameraObject('top',overhead_object);
  options();$('pair-front').value=a.observation.object_id;$('pair-top').value=b.observation.object_id;$('pair').click();
  const pair=pairs.find(p=>p.front===a.observation.object_id&&p.top===b.observation.object_id);
  return pair?ok({paired:`Object ${pair.number} · ${pair.label}`}):fail($('error').textContent||'Those two could not be paired; one may already be paired or used as a control.');
 },
 async unpair_object({object}){const e=resolveEntry(object,['object']);cardButton(e,'Unpair').click();return pairs.includes(e.pair)?fail('It is still paired.'):ok({unpaired:e.name});},
 async assign_control({object,kind}){
  const e=resolveEntry(object),id=entryId(e);
  if(!running&&!studioDemo)return fail('Start the cameras first.');
  if(kind==='button'){
   error();const done=await assignDetectedButton({id,name:e.item?`${e.item.object_label} #${e.item.number}`:e.name});
   return done&&flatInputs.get(id)?.controlKind==='cover_button'?ok({control:flatInputs.get(id).label,note:'Leave it uncovered to learn 0; cover it for 1.'}):fail($('error').textContent||'The button could not be created.');
  }
  const mode={joystick:'xy',horizontal_slider:'x',vertical_slider:'y'}[kind];
  if(e.input?.previewOnly)await api('/api/buttons/remove',{object_id:id},'top').catch(()=>{});
  assignInput({id,name:e.item?`${e.item.object_label} #${e.item.number}`:e.name},mode);
  if(mode!=='xy')flatInputs.get(id).mode=mode;
  return flatInputs.get(id)?.mode===mode?ok({control:flatInputs.get(id).label,kind,next:kind==='joystick'&&['can','bottle','cup'].includes(e.item?.object_label)?'Calibrate upright, then learn forward and right.':undefined}):fail('The control was not created.');
 },
 async use_can_as_joystick(){
  if(!running)return fail('Start the overhead camera first.');
  $('can-joystick').click();await waitFor(()=>[...flatInputs.values()].some(i=>i.label==='Can joystick'),2500);
  const done=[...flatInputs.values()].some(i=>i.label==='Can joystick');
  return ok({assigned:done,status:$('can-status').textContent});
 },
 async calibrate_joystick({object,step}){
  const e=resolveEntry(object,['joystick']),i=e.input,label={upright:'Calibrate upright (1s)',learn_forward:'Learn W',learn_right:'Learn D'}[step];
  const button=cardButton(e,label);
  if(button.disabled){
   const canPose=i.pivot&&['can','bottle','cup'].includes(e.item?.object_label);
   return fail(!canPose?'Only a can, bottle or cup joystick in pivot mode can be calibrated.':!(e.item?.observation.tracking_state==='tracked')?'I can\'t see it right now.':!i.neutralPose?'Calibrate upright first.':step==='learn_right'&&!i.directionBasis?.W?'Learn forward first.':'Wait until the current calibration step finishes.');
  }
  button.click();await sleep(250);
  return ok({joystick:e.name,step,status:i.calibrationStatus||i.poseCalibration?.phase||'started',instruction:step==='upright'?'Hold it upright and still for one second.':`Tilt it ${step==='learn_forward'?'forward':'to the right'} and hold.`});
 },
 async center_joystick({object}){const e=resolveEntry(object,['joystick']),b=cardButton(e,'Center & zero yaw');if(b.disabled)return fail(`${e.name} isn't being tracked right now.`);b.click();await sleep(300);return ok({centered:e.name});},
 async use_pivot_mode({object}){const e=resolveEntry(object,['joystick']);cardButton(e,'Use pivot / WASD').click();return e.input.pivot?ok({joystick:e.name,pivot:true}):fail('Pivot mode did not turn on.');},
 async set_slider_end({object,end}){
  const e=resolveEntry(object,['slider']),b=cardButton(e,`Set ${end}%`);if(b.disabled)return fail(`${e.name} isn't being tracked right now.`);
  b.click();return e.input.range?ok({slider:e.name,end,range_percent:e.input.range.map(v=>Math.round(v*100))}):fail('The end was not saved.');
 },
 async swap_slider_axis({object}){const e=resolveEntry(object,['slider']),before=e.input.mode;cardButton(e,'X ↔ Y').click();return e.input.mode!==before?ok({slider:e.name,axis:e.input.mode==='x'?'horizontal':'vertical'}):fail('The axis did not change.');},
 async remove_control({object}){const e=resolveEntry(object,['joystick','slider','button']),id=entryId(e);cardButton(e,'Remove').click();if(convo.focus===id)convo.focus=null;return flatInputs.has(id)?fail('It is still a control.'):ok({removed:e.name});},
 async relearn_button({object}){
  const e=resolveEntry(object,['button']);
  if(e.input.previewOnly){error();await reconnectDetectedButton(e);const state=flatInputs.get(e.id)?.actionState?.phase;return state&&state!=='unmapped'?ok({button:e.name,state}):fail($('error').textContent||'The button could not reconnect. Show the object to the overhead camera.');}
  try{await armRealKeys(e.id);}catch(err){return fail(err.message);}
  return armed()?ok({button:e.name,armed:true,status:$('action-status').textContent}):fail($('keyboard-status').textContent);
 },
 async map_to_action({object,controller,output,bindings,mode='game',deadzone=.18}){
  if(!running||studioDemo)return fail('Start the real overhead camera and show the object first.');
  const e=resolveEntry(object),id=entryId(e),targets=await catalogTargets(),target=targets[output];
  if(!target)return fail(`Unknown action "${output}". Use find_actions to look it up.`);
  if(!target.available)return fail(`${target.label} isn't available on this computer: ${target.reason||'adapter missing'}.`);
  if(!target.controllers.includes(controller))return fail(`${target.label} works with: ${target.controllers.join(', ')}.`);
  const filled=bindings||(target.kind==='trigger'?{press:'open'}:MAPPING_DEFAULTS[controller]?.[output]);
  if(!filled)return fail(controller==='cover_button'?'Which key should the button press?':'Which keys should each direction press?');
  const mapping={object_id:id,controller,output,bindings:Object.fromEntries(Object.entries(filled).map(([k,v])=>[k,String(v).toLowerCase()])),mode,deadzone};
  const response=await fetch('/api/morph/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping})});
  const checked=await response.json();if(!response.ok)return fail(checked.error||'That mapping is not valid.');
  await activateMorph(checked.mapping,`${e.name} → ${target.label}.`);
  if(morphMapping?.object_id!==id)return fail($('command-status').textContent||'The mapping was not applied.');
  return ok({mapped:e.name,controller,output:target.label,bindings:mapping.bindings,armed:armed(),output_status:$('keyboard-status').textContent,next:controller==='joystick'?'Hold it upright to learn neutral.':undefined});
 },
 async find_actions({query=''}){
  const q=words(query),entries=Object.entries(await catalogTargets()).filter(([id,t])=>!q.length||q.every(w=>(id+' '+t.label+' '+(t.app_name||'')).toLowerCase().includes(w)));
  const apps=entries.filter(([id])=>id.startsWith('app.open.')).length;
  return ok({count:entries.length,installed_app_matches:apps,targets:entries.slice(0,15).map(([id,t])=>({id,label:t.label,available:t.available,controllers:t.controllers,reason:t.reason||undefined}))});
 },
 async undo_mapping(){
  if(!morphPrevious)return fail('There is no previous mapping to restore.');
  const previous=structuredClone(morphPrevious);await activateMorph(previous,'Restored previous mapping.');
  return morphMapping?.object_id===previous.object_id?ok({restored:previous.controller+' → '+(previous.output||'keyboard'),armed:armed()}):fail($('command-status').textContent);
 },
 async set_output_control({object}){
  const e=resolveEntry(object,['joystick','slider','button']),id=entryId(e);syncCommandTargets();
  if(![...$('keyboard-target').options].some(o=>o.value===id))return fail(`${e.name} isn't a mapped joystick or mapped control yet.`);
  setSelect('keyboard-target',id);return ok({selected:e.name,armed:armed(),note:'Output is disarmed until you arm it.'});
 },
 async set_output_mode({mode}){setSelect('keyboard-mode',mode);return $('keyboard-mode').value===mode?ok({mode:mode==='typing'?'document':'game',armed:armed()}):fail('Mode did not change.');},
 async arm_output({object}){
  let id=$('keyboard-target').value;
  if(object){const e=resolveEntry(object,['joystick','slider','button']);id=entryId(e);}
  if(!id)return fail('No mapped control is selected. Map an object first.');
  try{await armRealKeys(id);}catch(err){return fail(err.message);}
  return armed()?ok({armed:true,status:$('keyboard-status').textContent}):fail($('keyboard-status').textContent||'Output did not arm.');
 },
 async stop_output(){await stopRealKeys('Stopped by voice');return armed()?fail('Output is still armed.'):ok({armed:false});},
 async request_keyboard_permission(){
  await stopRealKeys('Permission setup');const state=await api('/api/keys/request-permission',{});
  keyStatus(state.accessibility?'Permission granted':'macOS permission requested');
  return ok({accessibility_granted:!!state.accessibility,next:state.accessibility?undefined:'Enable the app running this server in System Settings, Privacy and Security, Accessibility.'});
 },
 async open_accessibility_settings(){
  assistantView.show('keyboard_test');
  try{window.location.href='x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';}catch(_){}
  return ok({requested:true,verified:false,note:'The browser may ask before opening System Settings. A link is also shown on screen.'});
 },
 async test_keyboard(){
  await stopRealKeys('Local test');assistantView.show('keyboard_test');
  const field=$('keyboard-test');field.value='';field.focus();
  try{await api('/api/keys/test',{});}catch(err){return fail(err.message);}
  const arrived=await waitFor(()=>/w.*a.*s.*d/i.test(field.value),1500);
  return arrived?ok({received:field.value.trim()}):fail('The test keys did not arrive. Check macOS Accessibility permission for the app running the server, and keep this browser window in front.',{received:field.value});
 },
 async add_sticker_button({key,grid_cell}){
  if(!running||studioDemo||!cameras.top.stream)return fail('Start the overhead camera and place the sticker in view first.');
  assistantView.show('camera',{grid:true});
  const col=(grid_cell-1)%3,row=Math.floor((grid_cell-1)/3),inset=.06;
  const bbox=[col/3+inset,row/3+inset,(col+1)/3-inset,(row+1)/3-inset];
  await stopRealKeys('Adding a sticker button');await useOverheadJoystick();
  $('sticker-key').value=key;
  let result;try{result=await api('/api/register-region',{stationary:true,bbox},'top');}catch(err){return fail(err.message);}
  cameras.top.result=result;syncCommandTargets();
  await activateMorph({object_id:result.registered_object_id,controller:'cover_button',output:'keyboard',bindings:{press:key},mode:'game',deadzone:.18},`Sticker button → ${key.toUpperCase()}.`);
  return morphMapping?.object_id===result.registered_object_id?ok({sticker_button:`grid cell ${grid_cell}`,key,armed:armed(),note:'Keep it uncovered until ready, then cover and uncover to press.'}):fail($('command-status').textContent);
 },
 async set_voice_feedback({enabled}){
  setChecked('voice-enabled',enabled);await sleep(enabled?1200:50);
  return $('voice-enabled').checked===enabled?ok({status_announcements:enabled}):fail($('voice-status').textContent||'Voice feedback could not be turned on.');
 },
 async test_voice(){
  unlockVoice();if(!await refreshVoiceStatus())return fail($('voice-status').textContent);
  await speakVoice('test',true);const status=$('voice-status').textContent;
  return /ready|speaking/i.test(status)?ok({played:'Phantom voice is ready. Turn everyday objects into controls.'}):fail(status);
 },
 async set_bear_voice({muted}){convo.muted=muted;try{localStorage.setItem('bear-voice-muted',muted?'1':'0');}catch(_){}renderAssistantChrome();return ok({bear_voice_muted:muted});},
 async set_voice_target({object}){
  if(/^(auto|none|clear)$/i.test(object.trim())){convo.voiceTarget=null;$('command-target').value='';return ok({voice_target:'auto'});}
  const e=resolveEntry(object);convo.voiceTarget=entryId(e);syncCommandTargets();
  if([...$('command-target').options].some(o=>o.value===convo.voiceTarget))$('command-target').value=convo.voiceTarget;
  return ok({voice_target:e.name});
 },
 async show_view({view}){assistantView.show(view);return ok({showing:view});},
 async filter_controls({type}){document.querySelector(`[data-filter="${type}"]`)?.click();assistantView.show('controls');return studioFilter===type?ok({filter:type}):fail('Filter did not change.');},
 async adjust_map_view({action,amount=1}){
  if(action==='reset')Object.assign(view,VIEW_DEFAULT);
  else if(action==='rotate_left'||action==='rotate_right')view.yaw+=(action==='rotate_left'?-20:20)*amount;
  else if(action==='tilt_up'||action==='tilt_down')view.pitch=Math.min(89,Math.max(-10,view.pitch+(action==='tilt_up'?12:-12)*amount));
  else view.zoom=Math.min(4,Math.max(.4,view.zoom*Math.pow(action==='zoom_in'?1.3:1/1.3,amount)));
  draw();assistantView.show('map');
  return ok({yaw:Math.round(view.yaw),pitch:Math.round(view.pitch),zoom:+view.zoom.toFixed(2)});
 },
 async stop_listening(){convo.stopAfterReply=true;return ok({microphone:'turns off after this reply'});},
 async open_single_camera_page(){convo.navigateAfterReply='/single';return ok({navigating:'after this reply'});},
 async get_status(){return ok({state:appState()});},
};
async function runTool(name,args){
 const fn=TOOLS[name];if(!fn)return fail(`Unknown tool ${name}.`);
 try{const result=await fn(args||{});return JSON.parse(JSON.stringify(result));}
 catch(err){return fail(err.message||String(err));}
}

// ---------- visible results next to the bear ----------
const assistantView={current:'none',grid:false,
 show(view,{grid=false}={}){
  this.current=view;this.grid=grid;const panel=$('va-panel');panel.hidden=view==='none';panel.dataset.view=view;
  const titles={camera:'Camera view',map:'3D workspace map',controls:'Controls',scroll_test:'Scroll test area',keyboard_test:'Keyboard test',actions:'Available actions'};
  $('va-panel-title').textContent=titles[view]||'';
  const body=$('va-panel-body');body.replaceChildren();
  if(view==='camera'||view==='map'){const c=document.createElement('canvas');c.id='va-mirror';body.append(c);}
  if(view==='controls'){const list=document.createElement('ul');list.id='va-controls';body.append(list);}
  if(view==='scroll_test')body.append($('action-test'));
  if(view==='keyboard_test'){body.append($('keyboard-test'));const a=document.createElement('a');a.href='x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';a.textContent='Open Accessibility settings';body.append(a);}
  if(view==='actions'){const list=document.createElement('ul');list.id='va-actions';body.append(list);void catalogTargets().then(t=>{list.replaceChildren(...Object.entries(t).filter(([id])=>!id.startsWith('app.open.')).map(([id,x])=>{const li=document.createElement('li');li.textContent=`${x.label}${x.available?'':' · unavailable'}`;return li;}));const apps=Object.keys(t).filter(id=>id.startsWith('app.open.')).length;if(apps){const li=document.createElement('li');li.textContent=`Open any of ${apps} installed apps with a cover button`;list.append(li);}}).catch(()=>{});}
 },
};
function paintMirror(){
 const c=$('va-mirror');
 if(c&&assistantView.current==='camera'){
  const sources=['top','front'].filter(r=>cameras[r].stream&&cameras[r].preview.width);
  if(!sources.length){c.width=320;c.height=60;const x=c.getContext('2d');x.fillStyle='#203a41';x.font='15px system-ui';x.fillText('Cameras are off.',12,34);}
  else{const w=sources.reduce((n,r)=>n+cameras[r].preview.width,0),h=Math.max(...sources.map(r=>cameras[r].preview.height));if(c.width!==w)c.width=w;if(c.height!==h)c.height=h;
   const x=c.getContext('2d');let left=0;
   for(const r of sources){const p=cameras[r].preview,o=cameras[r].overlay;x.drawImage(p,left,0);if(o.width)x.drawImage(o,left,0,p.width,p.height);
    if(r==='top'&&assistantView.grid){x.strokeStyle='#f2dd83';x.fillStyle='#f2dd83';x.lineWidth=3;x.font=`${Math.round(p.height/9)}px system-ui`;for(let i=1;i<3;i++){x.beginPath();x.moveTo(left+p.width*i/3,0);x.lineTo(left+p.width*i/3,p.height);x.moveTo(left,p.height*i/3);x.lineTo(left+p.width,p.height*i/3);x.stroke();}for(let n=0;n<9;n++)x.fillText(String(n+1),left+p.width*((n%3)/3+.03),p.height*(Math.floor(n/3)/3+.12));}
    left+=p.width;}}
 }
 if(c&&assistantView.current==='map'){if(c.width!==map.width)c.width=map.width;if(c.height!==map.height)c.height=map.height;const x=c.getContext('2d');x.fillStyle='#101a1c';x.fillRect(0,0,c.width,c.height);x.drawImage(map,0,0);}
 requestAnimationFrame(paintMirror);
}
function renderControlsList(){
 const list=$('va-controls');if(!list)return;
 const items=registryItems().filter(e=>studioFilter==='all'||e.type===studioFilter);
 list.replaceChildren(...(items.length?items:[null]).map(e=>{const li=document.createElement('li');
  if(!e){li.textContent=running?'No objects yet: move one under the overhead camera.':'Cameras are off.';return li;}
  const s=controlSummary(e);li.className=s.active?'active':'';
  li.textContent=`${s.name} · ${{candidate:'available',joystick:'joystick',slider:'slider',button:'button',object:'3D object'}[s.type]}`+(s.type==='joystick'&&s.keys?.length?` · ${s.keys.join('+')}`:'')+(s.value_percent!=null?` · ${s.value_percent}%`:'')+(s.calibration?` · ${s.calibration}`:'')+(s.state?` · ${s.state}`:'')+(s.active?'':' · not visible');return li;}));
}

// ---------- speech out ----------
const speech={controller:null,source:null,recent:[],endedAt:-Infinity,phrases:[]};
function bearAudible(){return !!voiceAudio.source||performance.now()-speech.endedAt<1200;}
async function say(text,version){
 $('bear-response').textContent=text;$('va-reply').textContent=text;
 speech.recent.push({text,at:performance.now()});speech.recent=speech.recent.filter(r=>performance.now()-r.at<20000);
 if(convo.muted||!voiceConfigured)return;
 const controller=new AbortController();speech.controller=controller;let source=null;
 setPhase('speaking');
 try{
  unlockVoice();
  const response=await fetch('/api/voice/utterance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.slice(0,800)}),signal:controller.signal});
  if(!response.ok){const data=await response.json().catch(()=>({}));throw Error(data.error||'Cartesia speech is unavailable.');}
  const bytes=await response.arrayBuffer();if(version!==convo.version)return;
  const buffer=await voiceAudio.context.decodeAudioData(bytes);if(version!==convo.version)return;
  cancelVoice();source=voiceAudio.context.createBufferSource();source.buffer=buffer;voiceAudio.source=source;speech.source=source;connectBearAudio(source);
  await new Promise(resolve=>{source.onended=resolve;source.start();});
 }catch(err){if(err.name!=='AbortError')showNotice('Voice output: '+err.message+' Replies stay on screen.');}
 finally{if(voiceAudio.source===source)voiceAudio.source=null;if(speech.source===source){speech.source=null;speech.endedAt=performance.now();}if(speech.controller===controller)speech.controller=null;}
}
function interruptSpeech(){speech.controller?.abort();if(speech.source){try{speech.source.stop();}catch(_){}speech.source=null;speech.endedAt=performance.now();}}
function looksLikeEcho(transcript){
 const heard=words(transcript);if(!heard.length)return true;
 const pool=new Set(words([...speech.recent.filter(r=>performance.now()-r.at<12000).map(r=>r.text),...speech.phrases].join(' ')));
 return heard.filter(w=>pool.has(w)).length/heard.length>=.75;
}

// ---------- the conversation loop ----------
const EMERGENCY=/^(?:please )?(?:stop all output|emergency stop|stop everything|stop all keys)\W*$/i;
const CANCEL=/^(?:cancel|never ?mind|stop|stop talking|be quiet|quiet|shh+|hush|wait|hold on|that's all|forget it)\W*$/i;
function trimHistory(){
 while(convo.history.length>36){const next=convo.history.findIndex((m,i)=>i>0&&m.role==='user');convo.history.splice(0,next>0?next:convo.history.length);}
}
function record(call,result){
 convo.activity.unshift({name:call.name,ok:result.ok,text:result.ok?(result.status||result.note||''):result.error});convo.activity.length=Math.min(convo.activity.length,4);
 const list=$('va-activity');list.replaceChildren(...convo.activity.map(a=>{const li=document.createElement('li');li.className=a.ok?'ok':'failed';li.textContent=`${a.ok?'✓':'✗'} ${a.name.replace(/_/g,' ')}${a.ok?'':' · '+a.text}`;return li;}));
}
let stepController=null;
async function reasoningStep(version){
 stepController?.abort();const controller=new AbortController();stepController=controller;
 const timer=setTimeout(()=>controller.abort(),45000);
 try{
  const response=await fetch('/api/assistant/step',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({messages:convo.history,state:appState()})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok){const err=Error(data.error||'The reasoning service failed.');err.status=response.status;throw err;}
  return data;
 }catch(err){if(err.name==='AbortError'&&version===convo.version){const e=Error('The reasoning service took too long. Nothing more was changed.');e.status=504;throw e;}throw err;}
 finally{clearTimeout(timer);}
}
async function localFallback(text,reason,version){
 // Without the reasoning model, the original explicit command list still drives the same handlers.
 try{const local=await routeStudioCommand(text);if(local?.handled){convo.history.push({role:'assistant',content:local.message});await say(local.message,version);return;}}
 catch(err){await say(err.message,version);return;}
 const message=`${reason} I can still do simple commands like "start the camera" or "stop all output".`;
 convo.history.push({role:'assistant',content:message});await say(message,version);
}
async function handleUtterance(text,source='voice'){
 text=String(text||'').trim().slice(0,1000);if(!text)return;
 const wasBusy=convo.busy||!!speech.source,version=++convo.version;
 interruptSpeech();stepController?.abort();
 $('va-heard').textContent=(source==='typed'?'You typed: ':'You said: ')+text;$('bear-transcript').textContent=text;$('command-transcript').textContent='Heard: “'+text+'”';
 lastActivity=performance.now();
 if(EMERGENCY.test(text)){
  const result=await runTool('stop_output',{});record({name:'stop_output'},result);
  const message=result.ok?'All output is stopped.':'I could not confirm output stopped: '+result.error;
  convo.history.push({role:'user',content:text},{role:'assistant',content:message});trimHistory();await say(message,version);finish(version);return;
 }
 if(CANCEL.test(text)){
  let message='Okay.';
  if(!wasBusy&&/^stop\W*$/i.test(text)&&armed()){const result=await runTool('stop_output',{});record({name:'stop_output'},result);message=result.ok?'Output stopped.':result.error;}
  convo.history.push({role:'user',content:text},{role:'assistant',content:wasBusy?'(Stopped and cancelled at the user\'s request.)':message});trimHistory();
  if(!wasBusy||message!=='Okay.')await say(message,version);
  finish(version);return;
 }
 convo.history.push({role:'user',content:text});trimHistory();
 convo.busy=true;setPhase('thinking');
 try{
  for(let round=0;round<6;round++){
   const step=await reasoningStep(version);if(version!==convo.version)return;
   if(step.tool_calls?.length){
    convo.history.push({role:'assistant',content:step.content||'',tool_calls:step.tool_calls.map(c=>({id:c.id,name:c.name,arguments:c.arguments||{}}))});
    for(const call of step.tool_calls){
     const result=version!==convo.version?fail('Cancelled: the user interrupted before this ran.'):call.error?fail(call.error):await runTool(call.name,call.arguments);
     convo.history.push({role:'tool',tool_call_id:call.id,content:JSON.stringify(result).slice(0,3500)});record(call,result);
    }
    if(version!==convo.version)return;
    continue;
   }
   convo.history.push({role:'assistant',content:step.content});trimHistory();
   convo.busy=false;await say(step.content,version);finish(version);return;
  }
  const message='That took more steps than I expected, so I stopped. Tell me what to do next.';
  convo.history.push({role:'assistant',content:message});convo.busy=false;await say(message,version);finish(version);
 }catch(err){
  if(version!==convo.version)return;
  convo.busy=false;
  if(convo.history.at(-1)?.role==='user')convo.history.pop();
  if(err.status===503||err.status===502||err.status===504||err instanceof TypeError){convo.history.push({role:'user',content:text});await localFallback(text,err instanceof TypeError?'I can\'t reach the studio server.':err.message,version);}
  else await say(err.message||'Something went wrong.',version);
  finish(version);
 }finally{if(version===convo.version)convo.busy=false;}
}
function finish(version){
 if(version!==convo.version)return;
 setPhase(convo.listening?'listening':'idle');
 if(convo.stopAfterReply){convo.stopAfterReply=false;stopListening('Microphone off. Click the bear to talk again.');}
 if(convo.navigateAfterReply){const to=convo.navigateAfterReply;convo.navigateAfterReply=null;location.href=to;}
 try{sessionStorage.setItem('bear-history',JSON.stringify(convo.history.slice(-24)));}catch(_){}
}
try{const saved=JSON.parse(sessionStorage.getItem('bear-history')||'[]');if(Array.isArray(saved)){const start=saved.findIndex(m=>m.role==='user');convo.history=start>=0?saved.slice(start):[];}}catch(_){}

// ---------- microphone session and barge-in ----------
let stt=null,turn=null,lastActivity=performance.now();
function showNotice(text){$('va-notice').textContent=text;$('va-notice').hidden=!text;}
function setPhase(phase){
 for(const p of ['idle','listening','hearing','thinking','speaking','error'])document.body.classList.toggle('va-'+p,p===phase);
 document.body.classList.toggle('bear-listening',['listening','hearing'].includes(phase));
 $('va-phase').textContent={idle:'Mic off · click the bear or type',listening:'Listening…',hearing:'Hearing you…',thinking:'Thinking…',speaking:'Speaking · talk to interrupt',error:'Voice unavailable · type below'}[phase];
 $('bear-state').textContent=$('va-phase').textContent;
}
function onSttEvent(event){
 if(event.type==='turn.start'){turn={whileSpeaking:bearAudible(),text:''};lastActivity=performance.now();if(!speech.source&&!convo.busy)setPhase('hearing');}
 else if(event.type==='turn.update'||event.type==='turn.eager_end'){
  if(!turn)turn={whileSpeaking:bearAudible(),text:''};turn.text=event.transcript||'';lastActivity=performance.now();
  if(turn.text)$('va-heard').textContent='…'+turn.text;
  // Barge-in: stop talking as soon as real words (not our own echo) come in.
  const meaningful=words(turn.text).length>=2||/\b(stop|wait|cancel|no|bear|hold)\b/i.test(turn.text);
  if(speech.source&&meaningful&&!looksLikeEcho(turn.text)){interruptSpeech();setPhase('hearing');}
 }else if(event.type==='turn.end'){
  const text=(event.transcript||'').trim(),t=turn;turn=null;lastActivity=performance.now();
  if(!text){if(!convo.busy&&!speech.source)setPhase('listening');return;}
  if((t?.whileSpeaking||bearAudible())&&looksLikeEcho(text)){if(!convo.busy&&!speech.source)setPhase('listening');return;}
  void handleUtterance(text,'voice');
 }
}
function onSttStatus(status,detail){
 if(status==='open'){showNotice('');if(!convo.busy&&!speech.source)setPhase('listening');}
 else if(status==='reconnecting')showNotice('Reconnecting to Cartesia…');
 else if(status==='warning')showNotice(detail);
 else if(status==='error'){convo.listening=false;stt=null;showNotice(detail);setPhase('error');void say(detail,convo.version);renderAssistantChrome();}
}
async function startListening(){
 if(stt)return;
 try{unlockVoice();}catch(_){}
 if(!voiceConfigured)await refreshVoiceStatus();
 stt=new SttStream({onEvent:onSttEvent,onStatus:onSttStatus});convo.listening=true;renderAssistantChrome();setPhase('listening');showNotice('Connecting…');lastActivity=performance.now();
 try{await stt.start();}
 catch(err){stt?.stop();stt=null;convo.listening=false;renderAssistantChrome();setPhase('error');showNotice(err.message);await say(err.message,convo.version);}
}
function stopListening(message='Microphone off.'){stt?.stop();stt=null;convo.listening=false;turn=null;renderAssistantChrome();if(!convo.busy&&!speech.source)setPhase('idle');showNotice(message);}
setInterval(()=>{
 // Silence: after two quiet minutes, stop streaming rather than listen indefinitely.
 if(convo.listening&&!convo.busy&&!speech.source&&!turn&&performance.now()-lastActivity>120000)stopListening('I stopped listening after two quiet minutes. Click the bear to talk again.');
 if(assistantView.current==='controls')renderControlsList();
 const live=$('va-live');live.textContent=`${studioDemo?'Demo':running?'Cameras live':'Cameras off'} · ${registryItems().filter(e=>e.type!=='candidate').length} controls · output ${armed()?'ARMED':'off'}`;live.classList.toggle('armed',armed());
},500);
function renderAssistantChrome(){
 $('va-mic').textContent=convo.listening?'Stop listening':'Start listening';$('va-mic').setAttribute('aria-pressed',String(convo.listening));
 $('va-mute').textContent=convo.muted?'Unmute bear voice':'Mute bear voice';$('va-mute').setAttribute('aria-pressed',String(convo.muted));
 $('bear-avatar').setAttribute('aria-label',convo.listening?'Stop listening':'Start voice conversation');
}
function toggleListening(){if(convo.listening)stopListening();else void startListening();}
$('va-mic').addEventListener('click',toggleListening);
$('va-mute').addEventListener('click',()=>{void TOOLS.set_bear_voice({muted:!convo.muted});if(convo.muted)interruptSpeech();});
$('va-panel-close').addEventListener('click',()=>assistantView.show('none'));
window.addEventListener('keydown',e=>{if(e.key==='Escape'){interruptSpeech();convo.version++;stepController?.abort();convo.busy=false;setPhase(convo.listening?'listening':'idle');}});
window.addEventListener('pagehide',()=>stt?.stop());
void fetch('/api/voice/status').then(r=>r.json()).then(s=>{speech.phrases=s.phrases||[];}).catch(()=>{});
void fetch('/api/assistant/status').then(r=>r.json()).then(s=>{
 const missing=(s.tools||[]).map(t=>t.name).filter(n=>!TOOLS[n]);if(missing.length)console.error('Bear tools without a browser handler:',missing);
 if(!s.configured)showNotice('Add ASI1_API_KEY to .env for full conversation. Simple commands still work.');
}).catch(()=>{});
renderAssistantChrome();setPhase('idle');requestAnimationFrame(paintMirror);
window.bearAssistant={handleUtterance,startListening,stopListening,toggleListening,runTool,appState,TOOLS};
