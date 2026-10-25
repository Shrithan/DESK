class PhantomMicrophone extends AudioWorkletProcessor {
 process(inputs,outputs){const samples=inputs[0]?.[0];if(samples?.length){const copy=new Float32Array(samples);this.port.postMessage(copy,[copy.buffer]);}return true;}
}
registerProcessor('phantom-microphone',PhantomMicrophone);
