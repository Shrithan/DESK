const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/flat-input.js','utf8'),c={};vm.createContext(c);
vm.runInContext(fs.readFileSync('vision/web/stick.js','utf8'),c);
vm.runInContext(source.slice(source.indexOf('function flatValue('),source.indexOf('const flatInputs=')),c);
let p=c.flatValue([160,120],[640,480],'xy');assert.equal(p.x,.25);assert.equal(p.y,.75);
assert.equal(c.flatValue([320,120],[640,480],'x').value,.5);
assert.equal(c.flatValue([320,120],[640,480],'y').value,.75);
assert.equal(c.flatValue([320,120],[640,480],'x',[.25,.75]).value,.5);
assert.equal(c.flatValue([160,120],[640,480],'x',[.75,.25]).value,1,'reversed physical travel works');
assert.equal(c.flatValue([900,120],[640,480],'x').value,1);
assert.equal(c.flatValue([100,100],[640,480],'x',[.5,.501]),null,'zero-length slider calibration is invalid');
console.log('Flat input checks passed: XY normalization, slider travel, direction, clamping and degenerate ranges.');

const stick=c.joystickValue({x:.6,y:.4},[.5,.5]);assert.ok(stick.x>0&&stick.y>0);
const bounded=c.joystickValue({x:1,y:1},[0,0]);assert.ok(Math.abs(Math.hypot(bounded.x,bounded.y)-1)<1e-8);
assert.equal(c.joystickValue({x:.4,y:.6},[.4,.6]).x,0);
console.log('Joystick checks passed: neutral center, XY direction, circular travel limit.');
