const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/module-agent.js','utf8');
const elements=new Map(),calls=[],entries=new Map();
const $=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',checked:true,disabled:false});return elements.get(id);};
const c={$,console,performance:{timeOrigin:0,now:()=>100},running:true,studioDemo:false,
 objects:()=>[{number:1,object_label:'can',observation:{object_id:'can',tracking_state:'tracked'}}],
 cameras:{top:{acceptedSample:100}},GAME_MODULES:{'flight-stick':{help:'flight'},'subway-slide':{help:'subway'}},
 gameModuleOptions:()=>calls.push('options'),mapGameModule:async flag=>calls.push(['game',$('game-module').value,$('game-object').value,flag]),
 removeDJSource:async()=>{},controlBusy:false,controlNumber:0,controlEntries:entries,controlsCatalog:{targets:{}},
 renderControlEntries:()=>{},activateControlEntry:async n=>{calls.push(['control',n]);entries.get(n).token='active';},
 api:async(path,body)=>calls.push([path,body]),activateMorph:async()=>calls.push('generic'),
 djGuide:null,djState:null,activateDJPlan:async()=>calls.push('dj-map'),djGuideRender:()=>{},
 djGuideNext:async()=>vm.runInContext("djGuide.phase=({low:'high',high:'enable',enable:'pickup'})[djGuide.phase]",c)};
vm.createContext(c);vm.runInContext(source.slice(0,source.indexOf('async function stopModuleOutputs')),c);
(async()=>{
 assert.equal(c.needsSetupReply({status:'clarify'}),true);
 assert.equal(c.needsSetupReply({status:'unsupported'}),false);
 assert.equal(c.needsSetupReply({status:'ready',mapping:{output:'app.open.test'}}),false,'finished button mapping must end background listening');
 for(const module of ['flight-stick','subway-slide']){
  await c.activateModulePlan({object_id:'can',module,controller:'joystick'},'Ready');
  assert.deepEqual(calls.at(-1),['game',module,'can',true]);
 }
 entries.set(0,{mapping:{object_id:'other'},token:'keep'});
 await c.activateModulePlan({object_id:'can',module:'general',controller:'slider_y',output:'display.brightness'},'Brightness');
 assert.equal(entries.get(0).token,'keep','another object remains active');assert.equal(entries.size,2);
 await c.activateModulePlan({object_id:'can',module:'general',controller:'cover_button',output:'keyboard'},'Space');
 assert.equal(entries.size,2,'reassign same object replaces its mapping');assert(calls.some(x=>x[0]==='/api/controls/stop'));
 const dj={object_id:'can',module:'dj',controller:'slider_y',output:'mixxx.deck1.volume'};
 await c.activateModulePlan(dj,'DJ');assert.equal(vm.runInContext('djGuide.phase',c),'low');assert.equal(c.needsSetupReply({status:'ready',mapping:dj}),true);
 await assert.rejects(c.activateModulePlan({...dj,setup_action:'enable'},'Enable'),/current DJ setup/);
 for(const setup_action of ['calibrate_low','calibrate_high','enable'])await c.activateModulePlan({...dj,setup_action},'Next');
 assert.equal(vm.runInContext('djGuide.phase',c),'pickup');assert.equal(c.needsSetupReply({status:'ready',mapping:dj}),false);
 c.running=false;await assert.rejects(c.activateModulePlan(dj,'DJ'),/Show the object/);
 console.log('Voice module routing: original game entry points, additive controls, source reassignment, ordered DJ calibration and camera freshness pass.');
})().catch(e=>{console.error(e);process.exitCode=1;});
