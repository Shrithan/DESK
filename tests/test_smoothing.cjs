const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vision/web/fusion.js','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function smoothPosition('),source.indexOf('function animateMap(')),ctx);
assert.equal(ctx.smoothPosition(null,[1,2,3],16).join(','),'1,2,3');
const first=ctx.smoothPosition([0,0,0],[5,-5,0],16);assert.ok(first[0]>0&&first[0]<5);assert.ok(first[1]<0&&first[1]>-5);
let p=[0,0,0];for(let i=0;i<120;i++)p=ctx.smoothPosition(p,[5,-5,0],16);assert.ok(Math.abs(p[0]-5)<.001);
const a=ctx.smoothPosition([0,0,0],[5,0,0],32),b=ctx.smoothPosition(ctx.smoothPosition([0,0,0],[5,0,0],16),[5,0,0],16);assert.ok(Math.abs(a[0]-b[0])<1e-10,'same smoothing at different display rates');
assert.equal(ctx.smoothPosition([0,0,0],[5,0,0],0)[0],0);
console.log('Map smoothing checks passed: convergence, no overshoot, time-based response.');
