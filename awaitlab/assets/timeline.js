(function(root){
 'use strict';
 // Interval partitioning: the earliest finishing track can be reused first.
 // Heap entries are [end time, track index]; O(n log n), no task/span is hidden.
 function pack(records){
  const tracks=[],heap=[];
  const before=(a,b)=>a[0]<b[0]||(a[0]===b[0]&&a[1]<b[1]);
  function push(value){
   let i=heap.length;heap.push(value);
   while(i){const p=(i-1)>>1;if(!before(value,heap[p]))break;heap[i]=heap[p];i=p;}
   heap[i]=value;
  }
  function pop(){
   const first=heap[0],last=heap.pop();
   if(heap.length){let i=0;while(i*2+1<heap.length){let c=i*2+1;if(c+1<heap.length&&before(heap[c+1],heap[c]))c++;if(!before(heap[c],last))break;heap[i]=heap[c];i=c;}heap[i]=last;}
   return first;
  }
  const ordered=[...records].sort((a,b)=>a.start_ms-b.start_ms||b.duration_ms-a.duration_ms||a.id-b.id);
  for(const span of ordered){
   const index=heap.length&&heap[0][0]<=span.start_ms?pop()[1]:tracks.length;
   if(!tracks[index])tracks.push([]);
   tracks[index].push(span);push([span.start_ms+span.duration_ms,index]);
  }
  return tracks;
 }
 function layout(records,request){
  const rows=records.filter(r=>r.request===request);
  if(!rows.length)return null;
  const start=Math.min(...rows.map(r=>r.start_ms));
  const end=Math.max(...rows.map(r=>r.start_ms+r.duration_ms));
  const requests=rows.filter(r=>r.kind==='request');
  const tasks=new Map();
  for(const row of rows){if(row.kind==='request')continue;if(!tasks.has(row.task))tasks.set(row.task,[]);tasks.get(row.task).push(row);}
  const lanes=pack(requests).map(spans=>({name:'请求',spans}));
  const groups=[...tasks].sort((a,b)=>Math.min(...a[1].map(r=>r.start_ms))-Math.min(...b[1].map(r=>r.start_ms))||a[0]-b[0]);
  for(const [task,spans] of groups){
   pack(spans).forEach((track,index)=>lanes.push({name:index?'↳ '+(index+1):'任务 '+task,task,track:index,spans:track}));
  }
  return {start,end,width:Math.max(end-start,.001),lanes};
 }
 const api={pack,layout};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.AwaitLabTimeline=api;
})(typeof globalThis==='object'?globalThis:this);
