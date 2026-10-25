const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),c={Blob,ArrayBuffer,DataView,Float32Array};vm.createContext(c);const source=fs.readFileSync('vision/web/commands.js','utf8');vm.runInContext(source.slice(0,source.indexOf('let keyboardToken=')),c);
const item=(id,label,n)=>({object_label:label,number:n,observation:{object_id:id,tracking_state:'tracked'},motion:{center_px:[10,10]}}),items=[item('a','can',1),item('b','can',2)];
assert.equal(c.commandCandidates({},items).length,2,'ambiguous objects never guessed');
assert.equal(c.commandCandidates({},items,'a')[0].observation.object_id,'a');
assert.equal(c.commandCandidates({},items,'',new Set(['b']))[0].observation.object_id,'b');
assert.equal(c.commandCandidates({label:'book'},items).length,0);
assert.equal(c.commandCandidates({number:2},items)[0].observation.object_id,'b');
assert.equal(c.commandCandidates({},[{...items[0],observation:{tracking_state:'lost'}}]).length,0);
(async()=>{const blob=c.encodeCommandWav([new Float32Array(48000).fill(.5)],48000);const buffer=await blob.arrayBuffer(),v=new DataView(buffer);assert.equal(v.getUint32(24,true),16000);assert.equal(v.getUint32(40,true),32000);assert.ok(v.getInt16(44,true)>16000);console.log('Voice mapping checks passed: ambiguity, selection, movement, labels, lost tracks and 16k mono PCM WAV.');})();
