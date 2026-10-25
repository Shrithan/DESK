const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/fusion.js','utf8');
const el=()=>({value:'',checked:false,options:[],style:{},append(){},addEventListener(){},replaceChildren(...items){this.options=items;}}),elements=new Map();
const context={performance:{now:()=>500,timeOrigin:0},candidates:new Map(),roles:['front','top'],colors:['green'],pairs:[],pairNumber:0,cameras:{front:{canvas:{width:640,height:480},sample:100,acceptedSample:100,result:{objects:[]}},top:{canvas:{width:640,height:480},sample:100,acceptedSample:100,result:{objects:[]}}},$:id=>{if(!elements.has(id))elements.set(id,el());return elements.get(id);},document:{createElement:el},Option:function(label,value){return {label,value};},draw(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync('vision/web/prediction.js','utf8'),context);vm.runInContext(source.slice(source.indexOf('function objects('),source.indexOf('function clearOverlay(')),context);
const object=(id,label,x,y)=>({number:1,object_label:label,observation:{object_id:id,tracking_state:'tracked'},motion:{center_px:[x,y]}});
const step=(stamp,side,top)=>{context.cameras.front.sample=context.cameras.top.sample=stamp;context.cameras.front.acceptedSample=context.cameras.top.acceptedSample=stamp;context.cameras.front.result.objects=[side];context.cameras.top.result.objects=[top];context.fuse();};
step(100,object('a','bottle',100,200),object('b','cup',100,200));
const candidate=[...context.candidates.values()][0];assert.equal(context.pairs.length,0,'stationary matching labels are not enough');
step(200,object('a','bottle',110,200),object('b','cup',100,200));assert.equal(context.pairs.length,0,'moving side object cannot match stationary overhead background');
step(300,object('a','bottle',120,200),object('b','cup',110,200));
step(400,object('a','can',130,200),object('b','bottle',120,200));const shared=context.pairs[0];assert.ok(shared.confirmed);assert.ok(shared.position.every(x=>x===0));
step(500,object('a','can',130,104),object('b','bottle',184,152));
assert.equal(context.pairs[0],shared);assert.ok(Math.abs(shared.position[0]-10)<1e-8,'X comes from overhead horizontal');assert.ok(Math.abs(shared.position[1]-10)<1e-8,'Y comes from overhead vertical');assert.ok(Math.abs(shared.position[2]-20)<1e-8,'Z comes from side vertical');
context.cameras.top.result.objects[0].observation.tracking_state='lost';context.fuse();assert.equal(shared.state,'holding','brief loss holds the smoothed position');context.cameras.front.acceptedSample+=800;context.cameras.top.acceptedSample+=800;context.fuse();assert.equal(shared.position,null,'missing view beyond the hold window cannot produce combined position');context.cameras.front.acceptedSample-=800;context.cameras.top.acceptedSample-=800;
context.cameras.front.sample=1700;context.cameras.top.sample=1700;context.cameras.front.acceptedSample=context.cameras.top.acceptedSample=1700;context.fuse();assert.equal(shared.confirmed,true,'brief loss retains the established cross-view match');
context.cameras.front.acceptedSample=context.cameras.top.acceptedSample=10000;context.fuse();assert.equal(shared.confirmed,false,'long absence requires motion recheck');
context.addPair(object('c','book',50,50),object('d','book',70,70),true);assert.equal(context.pairs.length,2);
context.addPair(object('c','book',50,50),object('e','book',70,70),true);assert.equal(context.pairs.length,2,'one local track cannot map twice');
context.zero();assert.equal(shared.origin,null);
console.log('Overhead+side checks passed: coordinated motion gate, independent XYZ sources, loss/recheck, fixed identity.');

// Two same-class objects moving together are ambiguous across uncalibrated views.
context.pairs.length=0;context.candidates.clear();
for(let i=0;i<4;i++){
 const stamp=2000+i*100;
 context.cameras.front.sample=context.cameras.top.sample=stamp;context.cameras.front.acceptedSample=context.cameras.top.acceptedSample=stamp;
 context.cameras.front.result.objects=[object('s1','can',50+i*10,100),object('s2','can',300+i*10,100)];
 context.cameras.top.result.objects=[object('t1','bottle',50+i*10,100),object('t2','bottle',300+i*10,100)];
 context.fuse();
}
assert.equal(context.pairs.length,0,'ambiguous simultaneous motion must not assign arbitrary IDs');
context.addPair(context.cameras.front.result.objects[0],context.cameras.top.result.objects[1],true);
context.addPair(context.cameras.front.result.objects[1],context.cameras.top.result.objects[0],true);
context.fuse();assert.equal(context.pairs.length,2);assert.ok(context.pairs.every(p=>p.position));
context.cameras.top.result.objects[1].observation.tracking_state='lost';context.fuse();
assert.equal(context.pairs[0].state,'holding','a lost pair holds briefly');assert.equal(context.pairs[1].state,'tracked');assert.ok(context.pairs[1].position,'loss of one pair must not interrupt the other');
console.log('Multi-object checks passed: ambiguity rejection, explicit pairing, independent loss, no duplicate identities.');

assert.match(context.formatSpatialPosition({position:[12,34,5],metric:true}),/X 12.0 cm.*Y 34.0 cm.*Z 5.0%/);
