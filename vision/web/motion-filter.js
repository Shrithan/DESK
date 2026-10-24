'use strict';
// One Euro filter: suppress small stationary jitter, open bandwidth during motion.
function euroStep(state,value,stamp,{minCutoff=1.8,beta=.18,derivativeCutoff=1.}={}){
 if(!state||stamp<=state.stamp||stamp-state.stamp>250)return {value,raw:value,derivative:0,stamp};
 const dt=(stamp-state.stamp)/1000;
 const alpha=cutoff=>1/(1+1/(2*Math.PI*cutoff*dt));
 const derivative=state.derivative+alpha(derivativeCutoff)*((value-state.raw)/dt-state.derivative);
 const filtered=state.value+alpha(minCutoff+beta*Math.abs(derivative))*(value-state.value);
 return {value:filtered,raw:value,derivative,stamp};
}
function filterVector(state,point,stamp){return point.map((value,i)=>euroStep(state?.[i],value,stamp));}
function drawObjectProxy(canvas,{kind='object',yaw=null,color='#b8efc8',active=true}={}){
 const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);
 const x=w/2,y=h*.52,rx=w*.25,ry=h*.15,height=kind==='disk'?10:kind==='bottle'?h*.35:h*.25;
 ctx.globalAlpha=active?1:.35;ctx.strokeStyle=color;ctx.fillStyle=color+'22';ctx.lineWidth=2;
 ctx.beginPath();ctx.ellipse(x,y-height/2,rx,ry,0,0,Math.PI*2);ctx.fill();ctx.stroke();
 ctx.beginPath();ctx.moveTo(x-rx,y-height/2);ctx.lineTo(x-rx,y+height/2);ctx.ellipse(x,y+height/2,rx,ry,0,0,Math.PI);ctx.lineTo(x+rx,y-height/2);ctx.stroke();
 ctx.strokeStyle='#456152';ctx.beginPath();ctx.moveTo(16,h-18);ctx.lineTo(w-16,h-18);ctx.stroke();
 if(yaw!==null&&Number.isFinite(yaw)){const a=(yaw-90)*Math.PI/180;ctx.strokeStyle='#9dcfff';ctx.beginPath();ctx.moveTo(x,y-height/2);ctx.lineTo(x+Math.cos(a)*rx,y-height/2+Math.sin(a)*ry);ctx.stroke();}
 ctx.globalAlpha=1;
}
