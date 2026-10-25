const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/commands.js','utf8'),game=fs.readFileSync('vision/web/game-controls.js','utf8');
const elements=new Map(),requests=[];
const $=id=>{if(!elements.has(id))elements.set(id,{value:'game',textContent:'',classList:{toggle(){}}});return elements.get(id);};
const input={mode:'xy',poseMode:false,controlActive:true,gameModule:'flight-stick',gameSlide:{flight:true},joystick:{x:0,y:0}};
const c={$,console,Map,Set,Error,performance:{timeOrigin:0,now:()=>100},flatInputs:new Map([['can',input]]),
 running:true,studioDemo:false,cameras:{top:{acceptedSample:100}},document:{hasFocus:()=>false,activeElement:{}},
 objects:()=>[{observation:{object_id:'can',tracking_state:'tracked'}}],
 api:async(path,body)=>{requests.push({path,body});return path.endsWith('/arm')?{token:'test',armed:true}:{armed:true,held:body.keys||[]};},
 fetch:async()=>({}),sessionStorage:{getItem:()=>null},};
vm.createContext(c);vm.runInContext(source.slice(0,source.indexOf('setInterval(()=>void sendRealKeys()')),c);
vm.runInContext(game.slice(0,game.indexOf('function fixedZoneBoxes')),c);
vm.runInContext("morphMapping={object_id:'can',controller:'joystick',output:'keyboard',bindings:GAME_MODULES['flight-stick'].bindings,deadzone:.35}",c);
(async()=>{
 await c.armRealKeys('can');
 for(const [x,y,keys] of [[0,1,['a']],[0,-1,['d']],[-1,0,['w']],[1,0,['s']],[1,1,['a','s']],[0,0,[]]]){
  input.joystick={x,y};await c.sendRealKeys();assert.deepEqual(Array.from(requests.at(-1).body.keys),keys);
 }
 c.document.hasFocus=()=>true;input.joystick={x:1,y:1};await c.sendRealKeys();assert.deepEqual(Array.from(requests.at(-1).body.keys),[],'dashboard focus suppresses native keys');
 c.document.hasFocus=()=>false;c.performance.now=()=>1000;await c.sendRealKeys();assert.deepEqual(Array.from(requests.at(-1).body.keys),[],'stale frames release');
 console.log('Flight delivery: original mounting-specific directions, dual keys, neutral, external focus and stale-frame release pass.');
})().catch(e=>{console.error(e);process.exitCode=1;});
