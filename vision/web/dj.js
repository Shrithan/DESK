'use strict';
let djState=null,djRequest=false,djInitialized=false,djMixerSignature='';
let djGuide=null,djGuideBusy=false;
function djMessage(text){$('dj-status').textContent=text;}
function djSources(){
 const list=objects('top').filter(o=>o.observation.tracking_state==='tracked'),select=$('dj-source'),old=select.value;
 const key=list.map(o=>o.observation.object_id).join('|');
 if(select.dataset.ids!==key){select.replaceChildren(new Option('Choose detected object…',''),...list.map(o=>new Option(`#${o.number} ${o.object_label}`,o.observation.object_id)));select.dataset.ids=key;if(list.some(o=>o.observation.object_id===old))select.value=old;}
}
function djRender(state){
 djState=state;const peer=state.bridge;
 $('dj-connection').textContent=peer.online?'● Mixxx connected · feedback live':peer.connected?'○ MIDI connected · enable mapping in Mixxx':'○ MIDI disconnected';
 $('dj-connection').classList.toggle('is-connected',peer.online);
 $('dj-arm').disabled=!peer.online||state.armed||!running;$('dj-stop').disabled=!state.armed;
 djMessage(state.reason+(peer.online?'':' · '+peer.reason));
 djGuideRender(state);
 if(!djInitialized){
  $('dj-target').replaceChildren(...Object.entries(state.targets).map(([id,t])=>new Option(t.label,id)));$('dj-axis').value=state.targets[$('dj-target').value].axis;
  const tests=$('dj-tests');
  for(const target of ['mixxx.deck1.volume','mixxx.crossfader','mixxx.deck2.volume']){
   const label=document.createElement('label');label.textContent=state.targets[target].label;
   const range=document.createElement('input');range.type='range';range.min='0';range.max='1';range.step='.005';range.value=peer.values[target]??.5;range.dataset.target=target;
   range.addEventListener('change',async()=>{try{await api('/api/dj/test',{target,value:Number(range.value)});}catch(err){djMessage(err.message);}});label.append(range);tests.append(label);
  }
  djInitialized=true;
 }
 for(const range of $('dj-tests').querySelectorAll('input')){range.disabled=!peer.online;if(document.activeElement!==range&&peer.values[range.dataset.target]!=null)range.value=peer.values[range.dataset.target];}
 const keys=new Set([...['mixxx.deck1.volume','mixxx.crossfader','mixxx.deck2.volume'],...Object.keys(state.mappings)]),cards=[];
 const signature=JSON.stringify([...keys].map(t=>[t,state.mappings[t]?.object_id,state.mappings[t]?.axis,state.mappings[t]?.reverse]));
 if(signature===djMixerSignature){for(const card of $('dj-mixer').children){const target=card.dataset.target,m=state.mappings[target],actual=peer.values[target];card.querySelector('.dj-value').textContent=actual==null?'—':Math.round(actual*100)+'%';card.querySelector('meter').value=actual??0;card.querySelector('.dj-mapping-state').textContent=m?(state.armed?m.state:'Output paused · calibrate or enable DJ controls'):'Map a physical slider to this control';}djSources();return;}
 djMixerSignature=signature;
 for(const target of keys){
  const m=state.mappings[target],actual=peer.values[target],card=document.createElement('article');card.className='dj-channel';card.dataset.target=target;
  const heading=document.createElement('h3');heading.textContent=state.targets[target].label;
  const value=document.createElement('strong');value.className='dj-value';value.textContent=actual==null?'—':Math.round(actual*100)+'%';
  const meter=document.createElement('meter');meter.min=0;meter.max=1;meter.value=actual??0;meter.setAttribute('aria-label',state.targets[target].label+' actual Mixxx value');
  const status=document.createElement('p');status.className='small dj-mapping-state';status.textContent=m?(state.armed?m.state:'Output paused · calibrate or enable DJ controls'):'Map a physical slider to this control';
  const source=document.createElement('p');source.className='small';source.textContent=m?`${m.object_id} · ${m.axis==='y'?'up/down':'left/right'}${m.reverse?' · reversed':''}`:'Waiting for an object';
  card.append(heading,value,meter,status,source);
  if(m){
   for(const [text,end] of [['Set 0% end','low'],['Set 100% end','high']]){const b=document.createElement('button');b.textContent=text;b.addEventListener('click',()=>void djCommand('/api/dj/calibrate',{target,end}));card.append(b);}
   const remove=document.createElement('button');remove.textContent='Remove';remove.addEventListener('click',async()=>{await djCommand('/api/dj/remove',{target});if(flatInputs.get(m.object_id)?.djTarget===target)flatInputs.delete(m.object_id);});card.append(remove);
  }
  cards.push(card);
 }
 $('dj-mixer').replaceChildren(...cards);djSources();
}
async function djCommand(path,body){
 try{const state=await api(path,body);if(state.targets)djRender(state);else await djRefresh();return state;}catch(err){djMessage(err.message);return null;}
}
async function djRefresh(){const response=await fetch('/api/dj/status');if(!response.ok)throw Error('DJ bridge unavailable.');djRender(await response.json());}
async function removeDJSource(id){
 const targets=new Set(Object.entries(djState?.mappings||{}).filter(([,m])=>m.object_id===id).map(([t])=>t));
 const own=flatInputs.get(id)?.djTarget;if(own)targets.add(own);
 for(const target of targets)await api('/api/dj/remove',{target});
 if(targets.size)await djRefresh();
}
async function stopDJSession(){
 await api('/api/dj/arm',{enabled:false});
 for(const target of Object.keys(djState?.mappings||{}))await api('/api/dj/remove',{target});
 await djRefresh();
}
async function addDJMapping(id,target,axis,reverse=false){
 if(!running||studioDemo)throw Error('Start the overhead camera and show your slider first.');
 await stopRealKeys('Using Mixxx DJ sliders');await useOverheadJoystick();
 const state=await api('/api/dj/bind',{object_id:id,target,axis,reverse});djRender(state);
 const item=objects('top').find(o=>o.observation.object_id===id);
 flatInputs.set(id,{mode:axis==='x'?'x':'y',label:state.targets[target].label,djTarget:target,range:null});
 renderFlatInputs();updateStudio();
 $('command-status').textContent=`${item?.object_label||'Object'} mapped to ${state.targets[target].label}. Set the two travel ends, enable DJ controls, then move through the actual Mixxx value to pick up.`;
}
async function activateDJPlan(mapping,message){
 await addDJMapping(mapping.object_id,mapping.output,mapping.controller==='slider_y'?'y':'x',mapping.controller==='slider_y'?mapping.bindings.negative!=='increase':mapping.bindings.positive!=='increase');
 $('command-status').textContent=message+' · Set travel ends and enable DJ controls in the Mixxx panel.';
}
function djGuideError(message=''){
 $('dj-guide-error').textContent=message;$('dj-guide-error').hidden=!message;
}
function djGuideRender(state){
 const g=djGuide,m=g&&state.mappings[g.target],peer=state.bridge;
 const phase=g?.phase||'choose';
 const step=phase==='pickup'||phase==='done'?'enable':phase;
 for(const el of $('dj-guide').querySelectorAll('[data-step]')){el.classList.toggle('current',el.dataset.step===step);el.setAttribute('aria-current',el.dataset.step===step?'step':'false');}
 const locked=!!g&&phase!=='done';
 if(locked)$('dj-arm').disabled=true;
 for(const id of ['dj-source','dj-target','dj-axis','dj-reverse','dj-bind'])$(id).disabled=djGuideBusy||locked;
 const next=$('dj-guide-next'),cancel=$('dj-guide-cancel');next.hidden=!g;cancel.hidden=!g||phase==='done';
 next.disabled=djGuideBusy;cancel.disabled=djGuideBusy;
 if(!g){$('dj-guide-title').textContent='Set up your own physical slider';$('dj-guide-help').textContent='Choose an object, a Mixxx control and a movement direction below, then click Start slider setup. Setup pauses DJ output while you set the travel ends.';$('dj-guide-live').textContent=running?'Move each object briefly so it appears in the list.':'Start the overhead webcam first. No side camera is needed.';return;}
 if(!m){$('dj-guide-title').textContent='Mapping was removed';$('dj-guide-help').textContent='Pause this setup, then choose a visible object again.';next.disabled=true;return;}
 const label=state.targets[g.target].label;
 if(g.phase==='pickup'&&state.armed&&m.picked_up)g.phase='done';
 const copy={
 low:['Set the 0% end','Move your object to the quiet/minimum end of its travel. Leave it visible, then save this position.','Save 0% position'],
 high:['Set the 100% end','Move it to the loud/maximum end. The two ends teach the full range; choose whichever direction feels natural.','Save 100% position'],
 enable:['Your travel is calibrated','Enable the slider, then move it through the current Mixxx value to pick up the fader without a jump.','Enable this slider'],
 pickup:['Pick up the mixer fader',state.armed?'Move toward '+Math.round((peer.values[g.target]??0)*100)+'% of your calibrated travel. The slider takes over when the values meet.':'DJ output is paused. Re-enable, then move through the current mixer value.','Re-enable slider'],
 done:['Your slider is working','This object controls '+label+'. You can add another object for a different mixer control.','Set up another slider']
 }[g.phase];
 $('dj-guide-title').textContent=copy[0];$('dj-guide-help').textContent=copy[1];next.textContent=copy[2];
 next.hidden=g.phase==='pickup'&&state.armed;
 $('dj-guide-live').textContent=label+' · '+(m.input==null?'move to see input':'Object '+Math.round(m.input*100)+'%')+' · Mixxx '+(peer.values[g.target]==null?'disconnected':Math.round(peer.values[g.target]*100)+'%')+' · '+m.state;
 if(!peer.online&&['enable','pickup'].includes(g.phase))next.disabled=true;
}
async function djGuideStart(){
 if(djGuideBusy)return;djGuideError();djGuideBusy=true;
 try{
  if(!running||studioDemo)throw Error('Start the overhead webcam, then move your object briefly.');
  if(!djState?.bridge.online)throw Error('Connect Mixxx MIDI first. The status must say feedback live.');
  const id=$('dj-source').value;if(!id)throw Error('Choose a detected physical object first.');
  const target=$('dj-target').value;
  await api('/api/dj/arm',{enabled:false});
  await addDJMapping(id,target,$('dj-axis').value,false);
  djGuide={target,id,phase:'low'};
 }catch(err){djGuideError(err.message);}finally{djGuideBusy=false;if(djState)djGuideRender(djState);}
}
async function djGuideNext(){
 if(!djGuide||djGuideBusy)return;djGuideError();djGuideBusy=true;
 try{
  const g=djGuide;
  if(g.phase==='done'){djGuide=null;return;}
  if(g.phase==='low'||g.phase==='high'){
   const end=g.phase,state=await api('/api/dj/calibrate',{target:g.target,end});
   if(end==='high'&&Math.abs(state.mappings[g.target].high-state.mappings[g.target].low)<.03)throw Error('Those ends are too close. Move farther from the 0% end, then save 100% again.');
   g.phase=end==='low'?'high':'enable';djRender(state);
  }else{
   const state=await api('/api/dj/arm',{enabled:true});g.phase='pickup';djRender(state);
  }
 }catch(err){djGuideError(err.message);}finally{djGuideBusy=false;if(djState)djGuideRender(djState);}
}
async function djGuidePause(){
 if(djGuideBusy)return;djGuideBusy=true;djGuideError();
 try{const state=await api('/api/dj/arm',{enabled:false});djGuide=null;djRender(state);}
 catch(err){djGuideError(err.message);}finally{djGuideBusy=false;if(djState)djGuideRender(djState);}
}
$('dj-connect').addEventListener('click',()=>void djCommand('/api/dj/connect',{}));
$('dj-arm').addEventListener('click',()=>void djCommand('/api/dj/arm',{enabled:true}));
$('dj-stop').addEventListener('click',()=>void djCommand('/api/dj/arm',{enabled:false}));
$('keyboard-stop').addEventListener('click',()=>void djCommand('/api/dj/arm',{enabled:false}));
$('dj-target').addEventListener('change',()=>{if(djState)$('dj-axis').value=djState.targets[$('dj-target').value].axis;});
$('dj-bind').addEventListener('click',()=>void djGuideStart());
$('dj-guide-next').addEventListener('click',()=>void djGuideNext());
$('dj-guide-cancel').addEventListener('click',()=>void djGuidePause());
setInterval(async()=>{
 if(djRequest)return;djRequest=true;
 try{
  if(running&&!studioDemo&&djState?.armed)djRender(await api('/api/dj/update',{}));else await djRefresh();}
 catch(err){djMessage(err.message);}finally{djRequest=false;}
},50);
void djRefresh().catch(err=>djMessage(err.message));
