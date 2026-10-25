const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),c={};vm.createContext(c);
const source=fs.readFileSync('vision/web/fusion.js','utf8');vm.runInContext(source.slice(source.indexOf('function usbPhoneAllowed('),source.indexOf('async function requireUSBPhone(')),c);
assert.ok(c.usbPhoneAllowed({verified:true,connected:true,phone_count:1}));
for(const status of [null,{}, {verified:false,connected:true,phone_count:1},{verified:true,connected:false,phone_count:0},{verified:true,connected:true,phone_count:2}])assert.equal(c.usbPhoneAllowed(status),false);
console.log('USB camera policy checks passed: only one verified connected iPhone is allowed.');
