const assert=require('node:assert/strict');
const {pack,layout}=require('../awaitlab/assets/timeline.js');
const row=(id,start,duration,task=1,parent=null)=>({id,start_ms:start,duration_ms:duration,task,parent,request:0,kind:'operation'});
const nested=[{...row(1,0,10,2),kind:'request'},row(2,2,7,1,1),row(3,3,5,1,2)];
const result=layout(nested,0);
assert.equal(result.lanes.length,3);
assert.equal(result.lanes.flatMap(l=>l.spans).length,3);
assert.equal(result.width,10);
assert.equal(layout(nested,1),null);
assert.deepEqual(pack([row(1,0,3),row(2,3,2)]).map(t=>t.map(r=>r.id)),[[1,2]]);
// Independent overlap oracle verifies minimal tracks, identity and no hiding.
let seed=173,cases=0;
const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(let n=1;n<=64;n++){
 for(let run=0;run<10;run++){
  const spans=Array.from({length:n},(_,i)=>row(i,rand()%40,1+rand()%20));
  const tracks=pack(spans);
  const maximum=Math.max(...spans.map(r=>spans.filter(s=>s.start_ms<=r.start_ms&&s.start_ms+s.duration_ms>r.start_ms).length));
  assert.equal(tracks.length,maximum);
  assert.equal(new Set(tracks.flatMap(t=>t.map(r=>r.id))).size,n);
  for(const track of tracks)for(let i=1;i<track.length;i++)assert(track[i-1].start_ms+track[i-1].duration_ms<=track[i].start_ms);
  cases++;
 }
}
console.log(`${cases} interval layouts matched overlap oracle; nested HTTP spans preserved`);
