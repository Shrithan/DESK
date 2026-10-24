// Jump gate (3D map) and box lead (camera overlay) for fast motion.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/fusion.js','utf8');
const el=()=>({value:'',checked:false,options:[],style:{},append(){},addEventListener(){},replaceChildren(...items){this.options=items;}}),elements=new Map();
const context={performance:{now:()=>500,timeOrigin:0},candidates:new Map(),roles:['front','top'],colors:['green'],pairs:[],pairNumber:0,cameras:{front:{canvas:{width:100,height:100},sample:0,acceptedSample:0,result:{objects:[]}},top:{canvas:{width:100,height:100},sample:0,acceptedSample:0,result:{objects:[]}}},$:id=>{if(!elements.has(id))elements.set(id,el());return elements.get(id);},document:{createElement:el},Option:function(label,value){return {label,value};},draw(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync('vision/web/prediction.js','utf8'),context);
vm.runInContext(source.slice(source.indexOf('function trackVelocities('),source.indexOf('function overlay(')),context);
vm.runInContext(source.slice(source.indexOf('function objects('),source.indexOf('function clearOverlay(')),context);
const object=(id,x,y)=>({number:1,object_label:'can',observation:{object_id:id,tracking_state:'tracked'},motion:{center_px:[x,y]}});
const step=(t,sx,sy,tx,ty)=>{for(const r of ['front','top']){context.cameras[r].sample=context.cameras[r].acceptedSample=t;}context.cameras.front.result.objects=[object('a',sx,sy)];context.cameras.top.result.objects=[object('b',tx,ty)];context.fuse();};
context.addPair(object('a',10,50),object('b',10,50),true);
for(let i=0;i<6;i++)step(100*i,10+i,50,10+i,50);
const p=context.pairs[0];assert.equal(p.state,'tracked');const before=p.position.slice();
step(600,10,50,90,10);                       // one-sample teleport (bad mask): ~89 units in 0.1 s
assert.equal(p.state,'holding','a single impossible jump is held back');assert.deepEqual(p.position,before);
step(700,16,50,16,50);                        // back to the real track: accepted
assert.equal(p.state,'tracked');assert.ok(Math.abs(p.position[0]-before[0])<20,'glitch never reached the map');
step(800,60,50,60,50);step(900,61,50,61,50);  // a real fast move: first held, second agreeing sample accepted
assert.equal(p.state,'tracked');assert.ok(p.position[0]>40,'real fast moves still get through within one update');
// Box lead: a box result 100 ms old on an object moving 0.5 px/ms is drawn 50 px ahead.
const c={velocity:{}};context.trackVelocities(c,{objects:[object('x',100,100)]},1000);context.trackVelocities(c,{objects:[object('x',150,100)]},1100);
c.acceptedSample=1100;const lead=context.boxLead(c,'x',1200);assert.ok(Math.abs(lead[0]-50)<1&&Math.abs(lead[1])<1e-9);
assert.ok(context.boxLead(c,'x',2000)[0]<=75+1e-9,'lead is capped at 150 ms');
console.log('Glitch checks passed: teleport rejected, real fast move accepted, boxes lead by speed x age.');
