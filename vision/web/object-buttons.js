'use strict';
let buttonPolling=false,hadButtonInputs=false;
async function assignDetectedButton(entry){
 try{
  if(!running||studioDemo)throw Error('Start the overhead camera and show the object first.');
  await stopRealKeys('Mapping an object to a 0/1 button');
  if(typeof useOverheadJoystick==='function')await useOverheadJoystick();
  const state=await api('/api/buttons/add',{object_id:entry.id},'top');
  flatInputs.set(entry.id,{mode:'button',controlKind:'cover_button',previewOnly:true,label:`${entry.name} · button`,actionState:state,buttonStamp:performance.timeOrigin+performance.now()});
  const pair=pairs.find(p=>p.top===entry.id);if(pair)pairs.splice(pairs.indexOf(pair),1);
  candidates.clear();renderFlatInputs();updateStudio();
  $('command-status').textContent='Object mapped as button. Leave it uncovered to learn 0; cover it for 1. This is a live input value, with no key output.';
 }catch(err){error(err.message);}
}
async function pollObjectButtons(){
 if(buttonPolling)return;
 const inputs=[...flatInputs].filter(([id,input])=>input.previewOnly&&input.controlKind==='cover_button');
 if(!running||studioDemo){for(const [,input] of inputs)input.actionState={value:0,phase:'stopped',presses:input.actionState?.presses||0};return;}
 if(!inputs.length&&!hadButtonInputs)return;
 buttonPolling=true;hadButtonInputs=inputs.length>0;
 try{
  const result=await api('/api/buttons/update',{object_ids:inputs.map(([id])=>id)},'top'),stamp=performance.timeOrigin+performance.now();
  for(const [id,input] of inputs){if(flatInputs.get(id)!==input)continue;input.actionState=result.buttons[id]||{value:0,phase:'remap object',presses:0};input.buttonStamp=stamp;}
 }catch(err){for(const [,input] of inputs)input.actionState={value:0,phase:'unavailable',presses:input.actionState?.presses||0};error(err.message);}
 finally{buttonPolling=false;}
}
setInterval(()=>void pollObjectButtons(),80);
