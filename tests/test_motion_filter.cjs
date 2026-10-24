const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={};vm.createContext(c);vm.runInContext(fs.readFileSync('vision/web/motion-filter.js','utf8'),c);
let state=null,raw=[],filtered=[];
for(let i=0;i<300;i++){const x=Math.sin(i*2.3)*.5;state=c.euroStep(state,x,i*33);if(i>30){raw.push(x);filtered.push(state.value);}}
const rms=a=>Math.sqrt(a.reduce((s,x)=>s+x*x,0)/a.length);
assert.ok(rms(filtered)<rms(raw)*.4,'stationary jitter must be substantially reduced');
state=c.euroStep(null,0,0);for(let i=1;i<=4;i++)state=c.euroStep(state,20,i*16);
assert.ok(state.value>18,'fast motion should settle within 64ms');assert.ok(state.value<=20,'filter must not overshoot');
assert.equal(c.euroStep(state,-10,1000).value,-10,'long gaps reset rather than smearing old state');
console.log(JSON.stringify({test:'adaptive motion filtering',rawJitterRms:rms(raw).toFixed(3),filteredJitterRms:rms(filtered).toFixed(3),stepAt64ms:state.value.toFixed(2)}));
