const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/flat-input.js','utf8');
const options=[],select={value:'',options,replaceChildren(...items){this.options=items;}};
const nodes={'flat-object':select,'flat-tracks':{replaceChildren(){}}};
const removed=[];
const ctx={sessionStorage:{getItem:()=> '1',removeItem:key=>removed.push(key)},
 objects:()=>['disk','can','bottle'].map((object_label,i)=>({object_label,number:i,motion:{center_px:[50,50]},observation:{object_id:'object'+i,tracking_state:'tracked',bbox_xyxy:[0,0,100,100]}})),
 $:id=>nodes[id],Option:function(label,value){this.value=value;},pairs:[],cameras:{front:{stream:null}},
 document:{createElement:()=>{throw Error('Unexpected automatic control card');}}};
vm.createContext(ctx);
vm.runInContext(source.slice(0,source.indexOf("$('flat-add').addEventListener")),ctx);
for(let i=0;i<3;i++)ctx.renderFlatInputs();
assert.equal(vm.runInContext('flatInputs.size',ctx),0,'disk/container detections must remain unassigned even with a stale saved joystick request');
assert(removed.includes('can-joystick-armed'));
console.log('Detection alone never assigns disks or containers, including stale joystick session state.');
