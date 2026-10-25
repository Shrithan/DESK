'use strict';
let buttonPolling=false,hadButtonInputs=false;
function unregisteredButtonState(){return {value:null,phase:'unmapped',presses:0,reason:'Button connection expired. Reconnect to a detected object.'};}
async function assignDetectedButton(entry){
 try{
  if(!running||studioDemo)throw Error('Start the overhead camera and show the object first.');
  if(typeof removeDJSource==='function')await removeDJSource(entry.id);
  await stopRealKeys('Mapping an object to a 0/1 button');
  if(typeof useOverheadJoystick==='function')await useOverheadJoystick();
  const state=await api('/api/buttons/add',{object_id:entry.id},'top');
  flatInputs.set(entry.id,{mode:'button',controlKind:'cover_button',previewOnly:true,label:`${entry.name} · button`,actionState:state,buttonStamp:performance.timeOrigin+performance.now()});
  const pair=pairs.find(p=>p.top===entry.id);if(pair)pairs.splice(pairs.indexOf(pair),1);
  candidates.clear();renderFlatInputs();updateStudio();
  $('command-status').textContent='Object mapped as button. Leave it uncovered to learn 0; cover it for 1. This is a live input value, with no key output.';
  return true;
 }catch(err){error(err.message);return false;}
}
async function pollObjectButtons(){
 if(buttonPolling)return;
 const inputs=[...flatInputs].filter(([id,input])=>input.previewOnly&&input.controlKind==='cover_button');
 if(!running||studioDemo){for(const [,input] of inputs)input.actionState={value:0,phase:'stopped',presses:input.actionState?.presses||0};return;}
 if(!inputs.length&&!hadButtonInputs)return;
 buttonPolling=true;hadButtonInputs=inputs.length>0;
 try{
  const result=await api('/api/buttons/update',{object_ids:inputs.map(([id])=>id)},'top'),stamp=performance.timeOrigin+performance.now();
  for(const [id,input] of inputs){
   if(flatInputs.get(id)!==input)continue;
   input.actionState=result.buttons[id]||unregisteredButtonState();input.buttonStamp=stamp;
   // Recover a dropped registration only when the original detected ID still
   // exists. A different ID requires explicit selection rather than guessing.
   const visible=objects('top').find(o=>o.observation.object_id===id&&o.observation.tracking_state==='tracked');
   if(!result.buttons[id]&&visible&&(!input.reconnectAttempt||stamp-input.reconnectAttempt>1500)){
    input.reconnectAttempt=stamp;
    try{input.actionState=await api('/api/buttons/add',{object_id:id},'top');}
    catch(err){input.actionState={...unregisteredButtonState(),reason:err.message};}
   }
  }
 }catch(err){for(const [,input] of inputs)input.actionState={value:0,phase:'unavailable',presses:input.actionState?.presses||0};error(err.message);}
 finally{buttonPolling=false;}
}
setInterval(()=>void pollObjectButtons(),80);

async function reconnectDetectedButton(entry){
 const tracked=objects('top').filter(o=>o.observation.tracking_state==='tracked');
 const id=tracked.some(o=>o.observation.object_id===entry.id)?entry.id:($('flat-object').value||(tracked.length===1?tracked[0].observation.object_id:null));
 const item=tracked.find(o=>o.observation.object_id===id);
 if(!item){error('Choose the object in Overhead input object, then click Reconnect.');return;}
 if(await assignDetectedButton({id,name:`${item.object_label} #${item.number}`})){
  if(id!==entry.id)flatInputs.delete(entry.id);
  updateStudio();
 }
}
