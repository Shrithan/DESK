const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/dj.js','utf8'),elements=new Map(),calls=[];
const element=()=>({textContent:'',hidden:false,disabled:false,value:'',querySelectorAll:()=>[],classList:{toggle(){}},setAttribute(){}});
const state={armed:false,bridge:{online:true,values:{deck:.5}},targets:{deck:{label:'Deck A volume'}},mappings:{}};
let position=.2;
const c={djGuide:null,djGuideBusy:false,djState:state,running:true,studioDemo:false,
 $:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);},
 addDJMapping:async(id,target,axis,reverse)=>{calls.push({id,target,axis,reverse});state.mappings[target]={object_id:id,low:.25,high:.75,state:'Calibrate'};},
 api:async(path,body)=>{calls.push({path,body});if(path.endsWith('/arm'))state.armed=body.enabled;else if(path.endsWith('/calibrate'))state.mappings[body.target][body.end]=position;return state;},
 djRender:s=>{c.djState=s;c.djGuideRender(s);}};
vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function djGuideError'),source.indexOf("$('dj-connect')")),c);
(async()=>{
 c.$('dj-target').value='deck';c.$('dj-axis').value='y';
 await c.djGuideStart();assert.match(c.$('dj-guide-error').textContent,/Choose/);assert.equal(calls.length,0);
 c.$('dj-source').value='bottle';state.bridge.online=false;await c.djGuideStart();assert.match(c.$('dj-guide-error').textContent,/Connect/);
 state.bridge.online=true;await c.djGuideStart();assert.equal(c.djGuide.phase,'low');assert.equal(state.armed,false);assert.equal(calls[0].body.enabled,false);
 assert.equal(c.$('dj-source').disabled,true);assert.equal(c.$('dj-arm').disabled,true);
 await c.djGuideNext();assert.equal(c.djGuide.phase,'high');assert.equal(state.mappings.deck.low,.2);
 position=.21;await c.djGuideNext();assert.equal(c.djGuide.phase,'high');assert.match(c.$('dj-guide-error').textContent,/too close/);assert.equal(state.armed,false);
 position=.8;await c.djGuideNext();assert.equal(c.djGuide.phase,'enable');assert.equal(c.$('dj-guide-error').hidden,true);
 await c.djGuideNext();assert.equal(c.djGuide.phase,'pickup');assert.equal(state.armed,true);assert.equal(c.$('dj-guide-next').hidden,true);
 state.mappings.deck.picked_up=true;c.djGuideRender(state);assert.equal(c.djGuide.phase,'done');assert.match(c.$('dj-guide-title').textContent,/working/);
 await c.djGuideNext();assert.equal(c.djGuide,null);assert.ok(state.mappings.deck,'add another keeps the existing mixer binding');
 await c.djGuideStart();await c.djGuidePause();assert.equal(c.djGuide,null);assert.equal(state.armed,false);
 console.log('DJ guide: missing source, offline bridge, paused setup, ordered endpoints, short travel, pickup, multiple mappings and pause pass.');
})();
