const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/fusion.js','utf8'),status={textContent:''};let posted=null;
const track={label:'C270 HD WEBCAM',getCapabilities:()=>({}),getSettings:()=>({})};
const context={cameras:{top:{stream:{getVideoTracks:()=>[track]}}},$:()=>status,api:async(path,payload)=>{posted={path,payload};return {message:'Exposure and white balance locked',exposure_ms:33.3};}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('async function cameraExposure('),source.indexOf('async function wideView(')),context);
(async()=>{
 await context.cameraExposure('top',true);assert.equal(posted.path,'/api/camera/exposure');assert.equal(posted.payload.label,'C270 HD WEBCAM');assert.equal(posted.payload.locked,true);assert.match(status.textContent,/hardware verified/);
 track.getCapabilities=()=>({exposureMode:['manual','continuous']});track.applyConstraints=async()=>{};
 await context.cameraExposure('top',true);assert.match(status.textContent,/unavailable/,'silent browser constraint failures must not claim a lock');
 track.getSettings=()=>({exposureMode:'manual',exposureTime:100});
 await context.cameraExposure('top',true);assert.match(status.textContent,/browser verified/);
 context.cameras.top.stream=null;await context.cameraExposure('top',true);assert.match(status.textContent,/Start/);
 console.log('Exposure UI: hardware routing, verified readback, unsupported browser mode and missing camera pass.');
})().catch(e=>{console.error(e);process.exitCode=1;});
