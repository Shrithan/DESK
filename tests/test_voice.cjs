const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),c={};vm.createContext(c);const code=fs.readFileSync('vision/web/voice.js','utf8');vm.runInContext(code.slice(0,code.indexOf('const voiceState=')),c);
const state={},entry={key:'one',type:'joystick',active:true};const events=t=>Array.from(c.voiceTransitions(state,true,[entry],t));
assert.deepEqual(events(0),[]);assert.deepEqual(events(400),['joystick_ready']);assert.deepEqual(events(1000),['cameras_ready']);assert.deepEqual(events(1200),[]);
entry.active=false;events(1300);entry.active=true;assert.deepEqual(events(1400),[]);assert.deepEqual(events(1800),[],'tiny dropout stays quiet');
entry.active=false;events(2000);assert.deepEqual(events(2800),['tracking_lost']);assert.deepEqual(events(3000),[]);
entry.active=true;events(3100);assert.deepEqual(events(3500),['tracking_recovered']);assert.deepEqual(events(4000),[]);
assert.deepEqual(Array.from(c.voiceTransitions(state,false,[],4500)),['cameras_stopped']);assert.deepEqual(Array.from(c.voiceTransitions(state,false,[],5000)),[]);
console.log('Voice event checks passed: debounce, quiet brief gaps, single loss/recovery and stop.');
