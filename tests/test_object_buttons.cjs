const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/object-buttons.js','utf8');
let state={value:0,phase:'ready',presses:0},requests=[],native=0;
const c={running:true,studioDemo:false,flatInputs:new Map(),pairs:[],candidates:new Map(),performance:{now:()=>100,timeOrigin:1000},stopRealKeys:async()=>native++,useOverheadJoystick:async()=>{},api:async(path,body)=>{requests.push(path);return path.endsWith('/add')?state:{buttons:{'detected-42':state}};},renderFlatInputs(){},updateStudio(){},$:()=>({textContent:''}),error(message){throw Error(message);},setInterval(){}};
vm.createContext(c);vm.runInContext(source,c);
(async()=>{
 await c.assignDetectedButton({id:'detected-42',name:'Can #1'});
 const input=c.flatInputs.get('detected-42');assert.equal(input.previewOnly,true);assert.equal(input.controlKind,'cover_button');assert.equal(native,1,'old native output is stopped before mapping');
 state={value:1,phase:'pressed',presses:1};await c.pollObjectButtons();assert.equal(input.actionState.value,1);
 state={value:0,phase:'ready',presses:1};await c.pollObjectButtons();assert.equal(input.actionState.value,0);
 assert.ok(requests.every(path=>path.startsWith('/api/buttons/')),'binary preview must not arm or send real key events');
 c.running=false;await c.pollObjectButtons();assert.equal(input.actionState.value,0);
 console.log('Detected-object button checks passed: original object ID, binary updates, and no native output.');
})();
