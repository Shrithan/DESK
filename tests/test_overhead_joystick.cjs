const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/fusion.js','utf8');
let stopped=0,reset=[];const elements=new Map();
const el=()=>({checked:false,textContent:'',children:[{}],classList:{toggle(){}},addEventListener(){}});
const front={stream:{getTracks:()=>[{stop(){stopped++;}}]},video:{srcObject:{},cancelVideoFrameCallback(){}},callback:7,preview:{width:640,height:480,getContext:()=>({clearRect(){}})},result:{objects:[]},acceptedSample:100};
const top={stream:{name:'overhead'},result:{objects:[{id:'slider-keep'}]},acceptedSample:100};
const c={cameras:{front,top},pairs:[{}],candidates:new Map([['old',{}]]),sessionStorage:{setItem(){}},clearTimeout(){},clearOverlay(){},api:async(p,b,r)=>reset.push(r),error(){},$:id=>{if(!elements.has(id))elements.set(id,el());return elements.get(id);}};
vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function showCameraMode('),source.indexOf("$('overhead-only').addEventListener")),c);
(async()=>{
 const savedStream=top.stream,savedResult=top.result;
 await c.useOverheadJoystick();
 assert.equal(stopped,1);assert.equal(front.stream,null);assert.equal(front.disabled,true);
 assert.equal(top.stream,savedStream);assert.equal(top.result,savedResult,'switching must not erase overhead IDs/mappings');
 assert.deepEqual(reset,['front']);assert.equal(c.$('overhead-only').checked,true);
 assert.equal(c.pairs.length,0);assert.equal(c.candidates.size,0);
 // A side pump already scheduled before the switch must not send another frame.
 Object.assign(c,{running:true,generation:1,performance:{now:()=>0,timeOrigin:0},setTimeout(){},paintFrame(){throw Error('disabled camera captured');}});
 front.video.readyState=4;front.video.currentTime=1;
 vm.runInContext(source.slice(source.indexOf('function cameraFrameMarker('),source.indexOf('// Interactive orbit view')),c);
 await c.pump('front',1);assert.deepEqual(reset,['front']);
 console.log('Overhead joystick checks passed: side capture stops, late pumps are blocked, overhead IDs are preserved.');
})();
