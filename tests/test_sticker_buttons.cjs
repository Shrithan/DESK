const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/commands.js','utf8'),elements=new Map(),events={},requests=[];let overhead=0,stops=0,applied=null;
const element=()=>({value:'enter',textContent:'',dataset:{},classList:{toggle(){},remove(){}},addEventListener(name,fn){this[name]=fn;}});
const overlay={width:640,height:480,dataset:{},classList:{toggle(){},remove(){}},getBoundingClientRect:()=>({left:0,top:0,width:640,height:480}),setPointerCapture(){},addEventListener(name,fn){events[name]=fn;}};
const c={running:true,studioDemo:false,cameras:{top:{overlay}},$:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);},stopRealKeys:async()=>stops++,useOverheadJoystick:async()=>overhead++,api:async(path,body,role)=>{requests.push({path,body,role});return {registered_object_id:'sticker-fixed',objects:[]};},syncCommandTargets(){},activateMorph:async m=>{applied=m;},error(message){throw Error(message);}};
vm.createContext(c);vm.runInContext(source.slice(source.indexOf('let registeringRegion=')),c);
(async()=>{
 await c.$('register-region').click();
 events.pointerdown({clientX:100,clientY:100,pointerId:1,preventDefault(){}});
 await events.pointerup({clientX:200,clientY:200});
 assert.equal(stops,1);assert.equal(overhead,1);
 assert.equal(requests[0].path,'/api/register-region');assert.equal(requests[0].body.stationary,true);assert.equal(requests[0].role,'top');
 assert.equal(applied.controller,'cover_button');assert.equal(applied.object_id,'sticker-fixed');assert.equal(applied.bindings.press,'enter');assert.equal(applied.output,'keyboard');
 console.log('Sticker UI checks passed: fixed overhead registration directly maps the chosen key.');
})();
