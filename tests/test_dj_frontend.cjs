const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/dj.js','utf8'),calls=[],inputs=new Map(),elements=new Map();
const c={running:true,studioDemo:false,flatInputs:inputs,objects:()=>[{object_label:'bottle',observation:{object_id:'a'}}],
 stopRealKeys:async()=>calls.push('stop-keys'),useOverheadJoystick:async()=>calls.push('overhead'),
 api:async(path,body)=>{calls.push({path,body});return {targets:{[body.target]:{label:'Deck A volume'}}};},
 djRender(){},renderFlatInputs(){},updateStudio(){},$:id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
vm.createContext(c);vm.runInContext(source.slice(source.indexOf('async function addDJMapping'),source.indexOf("$('dj-connect')")),c);
(async()=>{
 const mapping={object_id:'a',output:'mixxx.deck1.volume',controller:'slider_y',bindings:{negative:'increase',positive:'decrease'}};
 await c.activateDJPlan(mapping,'Mapped');
 assert.equal(calls.at(-1).body.reverse,false,'normal upward voice mapping must not invert twice');
 assert.equal(calls.at(-1).body.axis,'y');assert.equal(inputs.get('a').djTarget,mapping.output);
 assert.equal(calls[0],'stop-keys');assert.equal(calls[1],'overhead');
 await c.activateDJPlan({...mapping,bindings:{negative:'decrease',positive:'increase'}},'Mapped');
 assert.equal(calls.at(-1).body.reverse,true);
 await c.activateDJPlan({...mapping,object_id:'b',output:'mixxx.crossfader',controller:'slider_x',bindings:{negative:'decrease',positive:'increase'}},'Mapped');
 assert.equal(calls.at(-1).body.reverse,false);assert.equal(inputs.size,2,'new DJ targets retain other physical faders');
 c.running=false;await assert.rejects(c.addDJMapping('a','mixxx.deck1.volume','y'),/Start the overhead/);
 console.log('DJ frontend: upward/rightward voice axes, inversion, simultaneous objects and camera gate pass.');
})();
// A poll may see a backend binding before its creator receives the POST response.
// Polling must never infer deletion from another tab's or a pending bind's local map.
let pollTick;const tickCalls=[],poll={running:false,studioDemo:false,djState:{mappings:{'mixxx.deck1.volume':{object_id:'pending-bind'}}},djRequest:false,
 flatInputs:new Map(),api:async(p)=>{tickCalls.push(p);return {};},djRefresh:async()=>tickCalls.push('status'),djRender(){},djMessage(){},
 setInterval(fn){pollTick=fn;}};
vm.createContext(poll);vm.runInContext(source.slice(source.lastIndexOf('setInterval(async()=>'),source.indexOf('void djRefresh().catch')),poll);
(async()=>{await pollTick();assert.deepEqual(tickCalls,['status'],'a concurrent poll must not delete a new or another tab\'s mapping');console.log('DJ cleanup regression: concurrent status polling never removes physical mappings.');})();
