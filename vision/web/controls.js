'use strict';
// Manual controls module; reuses the validated native action registry, not the planner.
function controlMapping(id,controller,output,key,reverse=false){
 if(!id)throw Error('Choose a visible object.');
 const button=controller==='cover_button';
 let bindings;
 if(button)bindings={press:output==='keyboard'?key:'open'};
 else if(output==='desktop.scroll')bindings=reverse?{negative:'down',positive:'up'}:{negative:'up',positive:'down'};
 else {const increasing=controller==='slider_x'?!reverse:reverse;bindings=increasing?{negative:'decrease',positive:'increase'}:{negative:'increase',positive:'decrease'};}
 return {object_id:id,controller,output,bindings,mode:'game',deadzone:.18};
}
let controlsCatalog=null,controlNumber=0,controlEntries=new Map(),controlBusy=false;
function controlMessage(text){$('controls-status').textContent=text;}
function controlTargets(){
 if(!controlsCatalog)return;
 const controller=$('controls-input').value,select=$('controls-action'),previous=select.value;
 const targets=Object.entries(controlsCatalog.targets||{}).filter(([id,t])=>t.available&&t.controllers.includes(controller)&&
  (controller==='cover_button'?(id==='keyboard'||id.startsWith('app.open.')):['audio.volume','display.brightness','desktop.scroll'].includes(id)));
 select.replaceChildren(...targets.map(([id,t])=>new Option(t.label,id)));
 if(targets.some(([id])=>id===previous))select.value=previous;
 $('controls-key-row').hidden=controller!=='cover_button'||select.value!=='keyboard';
 $('controls-reverse-row').hidden=controller==='cover_button';
 $('controls-help').textContent=controller==='cover_button'?'Leave the object uncovered to learn its resting appearance. Cover it to press once; uncover before pressing again.':'Move the object in a straight line. Right/up increases volume or brightness by default. Scroll follows movement and stops when you stop. Activation starts from the current system value.';
 if(controller==='cover_button'&&!controlsCatalog.cover_available)controlMessage('Cover buttons need the hand detector dependency. Slider mappings are available.');
 $('controls-save').disabled=!targets.length||controller==='cover_button'&&!controlsCatalog.cover_available;
}
function renderControlEntries(){
 const list=$('controls-list');list.replaceChildren();
 for(const [number,entry] of controlEntries){
  const card=document.createElement('div');card.className='track-card';
  const title=document.createElement('strong');title.textContent=entry.name;
  const info=document.createElement('p');info.textContent=`${entry.source} → ${entry.target} · ${entry.mapping.controller==='cover_button'?'cover / uncover':entry.mapping.controller==='slider_x'?'horizontal':'vertical'}`;
  const activate=document.createElement('button');activate.textContent=entry.token?'Active · recheck':'Activate';activate.disabled=controlBusy;
  activate.addEventListener('click',()=>void activateControlEntry(number));
  const reconnect=document.createElement('button');reconnect.textContent='Use selected object';
  reconnect.addEventListener('click',async()=>{if(entry.token)await api('/api/controls/stop',{token:entry.token});entry.token=null;const id=$('controls-object').value;if(!id){controlMessage('Choose a visible object first.');return;}entry.mapping.object_id=id;entry.source=$('controls-object').selectedOptions[0].text;renderControlEntries();controlMessage('Source updated. Activate when ready.');});
  const remove=document.createElement('button');remove.textContent='Remove mapping';
  remove.addEventListener('click',async()=>{if(entry.token)await api('/api/controls/stop',{token:entry.token});controlEntries.delete(number);renderControlEntries();});
  const status=document.createElement('p');status.textContent=entry.state?.reason||'Inactive';status.dataset.controlStatus=String(number);card.append(title,info,status,activate,reconnect,remove);list.append(card);
 }
}
async function activateControlEntry(number){
 if(controlBusy)return;const entry=controlEntries.get(number);if(!entry)return;
 controlBusy=true;renderControlEntries();
 try{
  if(!running||studioDemo)throw Error('Start the overhead camera first.');
  const result=await api('/api/controls/arm',{mapping:entry.mapping});
  entry.token=result.token;entry.sequence=0;entry.state=result;
  controlMessage(`Active: ${entry.name}. All other mappings remain active.`);
 }catch(error){controlMessage(error.message);}finally{controlBusy=false;renderControlEntries();}
}
$('controls-save').addEventListener('click',()=>{
 try{
  const mapping=controlMapping($('controls-object').value,$('controls-input').value,$('controls-action').value,$('controls-key').value,$('controls-reverse').checked);
  const spec=controlsCatalog?.targets[mapping.output];if(!spec?.available)throw Error('Choose an available action.');
  const source=$('controls-object').selectedOptions[0].text,target=spec.label+(mapping.output==='keyboard'?' · '+mapping.bindings.press.toUpperCase():'');
  controlEntries.set(++controlNumber,{mapping,source,target,name:$('controls-name').value.trim()||`${source} · ${target}`});
  renderControlEntries();controlMessage('Mapping saved, output off. Click Activate when ready.');
 }catch(error){controlMessage(error.message);}
});
$('controls-stop').addEventListener('click',()=>void stopGeneralControls());
$('controls-input').addEventListener('change',controlTargets);
$('controls-action').addEventListener('change',()=>{$('controls-key-row').hidden=$('controls-input').value!=='cover_button'||$('controls-action').value!=='keyboard';});
async function refreshControlsCatalog(){
 try{const response=await fetch('/api/morph/status');if(!response.ok)throw Error('Cannot load action catalog.');const state=await response.json();controlsCatalog=state.catalog;
 $('controls-key').replaceChildren(...(controlsCatalog.outputs.keyboard||[]).map(key=>new Option(key.toUpperCase(),key)));$('controls-key').value='space';controlMessage('Ready. Choose an object, input type and action, then save a mapping.');controlTargets();}
 catch(error){controlMessage(error.message);}
}
$('controls-refresh').addEventListener('click',()=>void refreshControlsCatalog());
setInterval(()=>{
 const select=$('controls-object'),previous=select.value;
 const fresh=running&&!studioDemo&&performance.timeOrigin+performance.now()-cameras.top.acceptedSample<250;
 const items=fresh?objects('top').filter(o=>o.motion&&o.observation.tracking_state==='tracked'):[];
 const signature=items.map(o=>o.observation.object_id+o.object_label+o.number).join('|');if(select.dataset.ids===signature)return;
 select.dataset.ids=signature;select.replaceChildren(new Option('Choose visible object…',''),...items.map(o=>new Option(`#${o.number} ${o.object_label}`,o.observation.object_id)));
 if(items.some(o=>o.observation.object_id===previous))select.value=previous;else if(items.length===1)select.value=items[0].observation.object_id;
},200);
void refreshControlsCatalog();

async function stopGeneralControls(){
 for(const entry of controlEntries.values()){entry.token=null;entry.state=null;}
 await api('/api/controls/stop',{});renderControlEntries();controlMessage('All general controls stopped.');
}
let generalPolling=false;
setInterval(async()=>{
 if(generalPolling)return;generalPolling=true;
 try{await Promise.all([...controlEntries].filter(([,e])=>e.token).map(async([number,entry])=>{
  const token=entry.token;
  if(!running||studioDemo){try{await api('/api/controls/stop',{token});}finally{entry.token=null;}return;}
  const enabled=entry.mapping.output!=='desktop.scroll'&&entry.mapping.output!=='keyboard'||!document.hasFocus()||['keyboard-test','action-test'].includes(document.activeElement?.id);
  try{const state=await api('/api/controls/update',{token,sequence:entry.sequence++,enabled});if(entry.token!==token)return;entry.state=state;if(!state.armed)entry.token=null;
   const status=$('controls-list').querySelector(`[data-control-status="${number}"]`);if(status)status.textContent=state.reason+(state.details?.evidence?' · '+state.details.evidence:'');
   entry.region=state.region;
  }catch(error){entry.token=null;entry.state={reason:error.message};controlMessage(entry.name+': '+error.message);}
 }));}finally{generalPolling=false;}
},70);
function drawGeneralControlRegions(ctx){
 ctx.save();ctx.lineWidth=2;ctx.font='14px sans-serif';
 for(const entry of controlEntries.values())if(entry.token&&entry.region){const [x,y,x2,y2]=entry.region;ctx.strokeStyle=entry.state?.details?.value?'#67ffa7':'#ffdc64';ctx.strokeRect(x,y,x2-x,y2-y);ctx.fillStyle=ctx.strokeStyle;ctx.fillText(entry.name,x,Math.max(16,y-5));}
 ctx.restore();
}
window.addEventListener('pagehide',()=>{void fetch('/api/controls/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true});});
