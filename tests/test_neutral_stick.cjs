const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),c={};vm.createContext(c);
for(const file of ['stick.js','motion-filter.js','neutral-stick.js'])vm.runInContext(fs.readFileSync('vision/web/'+file,'utf8'),c);
// An upright can from an oblique camera already has an elongated, rotated projection.
const f=(dx=0,dy=0)=>({cx:260+dx,cy:170+dy,area:Math.PI*400,cxx:530,cxy:120,cyy:95});
let stamp=1000;const input={};let result;
for(let i=0;i<32;i++){result=c.stepStickPose(input,f(Math.sin(i)*.1,Math.cos(i)*.1),stamp);stamp+=40;}
assert.equal(input.poseCalibration.phase,'ready');assert.ok(Math.hypot(result.x,result.y)<.01,'oblique neutral is not a held tilt');
assert.ok(Object.values(c.stickKeys(result)).every(x=>!x));
for(let i=0;i<50;i++){result=c.stepStickPose(input,f(),stamp);stamp+=40;}assert.equal(Math.hypot(result.x,result.y),0,'staying upright remains neutral');
const learn=(key,dx,dy)=>{c.beginStickDirection(input,key);for(let i=0;i<17;i++){c.stepStickPose(input,f(dx,dy),stamp);stamp+=40;}assert.equal(input.poseCalibration.phase,'return');assert.equal(c.stepStickPose(input,f(dx,dy),stamp),null,'keys suppressed until returned upright');stamp+=40;c.stepStickPose(input,f(),stamp);stamp+=40;};
learn('W',5,-7);learn('D',7,2);assert.ok(input.directionBasis.W&&input.directionBasis.D);
for(let i=0;i<20;i++){result=c.stepStickPose(input,f(5,-7),stamp);stamp+=40;}assert.ok(result.y>.98&&Math.abs(result.x)<.02,'learned oblique W produces only W');assert.ok(c.stickKeys(result).W&&!c.stickKeys(result).D);
for(let i=0;i<20;i++){result=c.stepStickPose(input,f(7,2),stamp);stamp+=40;}assert.ok(result.x>.98&&Math.abs(result.y)<.02,'nonorthogonal learned D produces only D');
assert.equal(c.stepStickPose(input,{...f(),area:20},stamp),null,'occluded mask invalid');
// Rendering the same frame cannot satisfy the one-second upright calibration.
const repeated={};for(let i=0;i<100;i++)c.stepStickPose(repeated,f(),1000);assert.equal(repeated.poseCalibration.phase,'neutral');
const moving={};for(let i=0;i<40;i++){c.stepStickPose(moving,f(i*2,0),1000+i*40);}assert.equal(moving.poseCalibration.phase,'neutral','moving can never calibrates');
const gaps={};c.stepStickPose(gaps,f(),1000);c.stepStickPose(gaps,f(),3000);assert.equal(gaps.poseCalibration.phase,'neutral','long gap does not count as still time');
c.beginStickNeutral(input);assert.ok(Object.values(input.keys).every(x=>!x));assert.equal(input.neutralPose,null,'recalibration clears output immediately');
console.log('Oblique-camera joystick checks passed: neutral bias, fresh/still frames, learned skewed axes, return gate, occlusion and immediate recalibration release.');
