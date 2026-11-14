const assert=require('node:assert/strict');
const {pack,layout,union,coverage}=require('../awaitlab/assets/timeline.js');
const row=(id,start,duration,task=1,parent=null)=>({id,start_ms:start,duration_ms:duration,task,parent,request:0,kind:'operation'});
const nested=[{...row(1,0,10,2),kind:'request'},row(2,2,7,1,1),row(3,3,5,1,2)];
const result=layout(nested,0);
assert.equal(result.lanes.length,3);
assert.equal(result.lanes.flatMap(l=>l.spans).length,3);
assert.equal(result.width,10);
assert.equal(layout(nested,1),null);
assert.deepEqual(pack([row(1,0,3),row(2,3,2)]).map(t=>t.map(r=>r.id)),[[1,2]]);
assert.equal(union([[0,3],[1,2],[3,4],[5,8],[6,9],[10,10]]),8);
assert.equal(union([]),0);
assert.equal(coverage(nested,0).covered_ms,7);
assert.equal(coverage(nested,0).uncovered_ms,3);
assert.equal(coverage(nested,1),null);
const parallel=[{...row(1,0,10),kind:'request'},...Array.from({length:12},(_,i)=>({...row(i+2,2,3,i+2,1),name:'inventory'}))];
const c=coverage(parallel,0);
assert.equal(c.groups[0].cumulative_ms,36);assert.equal(c.groups[0].covered_ms,3);
assert.equal(c.uncovered_ms,7); // sum is 36ms, but the request window is only 10ms
const clipped=coverage([{...row(1,5,10),kind:'request'},{...row(2,0,30),name:'out-of-window'}],0);
assert.equal(clipped.groups[0].covered_ms,10);assert.equal(clipped.uncovered_ms,0);
// Independent overlap oracle verifies minimal tracks, identity and no hiding.
let seed=173,cases=0;
const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(let n=1;n<=64;n++){
 for(let run=0;run<10;run++){
  const spans=Array.from({length:n},(_,i)=>row(i,rand()%40,1+rand()%20));
  const tracks=pack(spans);
  const end=Math.max(...spans.map(r=>r.start_ms+r.duration_ms));
  const occupied=Array.from({length:end},(_,i)=>spans.some(r=>r.start_ms<=i&&r.start_ms+r.duration_ms>i)).filter(Boolean).length;
  assert.equal(union(spans.map(r=>[r.start_ms,r.start_ms+r.duration_ms])),occupied);
  const maximum=Math.max(...spans.map(r=>spans.filter(s=>s.start_ms<=r.start_ms&&s.start_ms+s.duration_ms>r.start_ms).length));
  assert.equal(tracks.length,maximum);
  assert.equal(new Set(tracks.flatMap(t=>t.map(r=>r.id))).size,n);
  for(const track of tracks)for(let i=1;i<track.length;i++)assert(track[i-1].start_ms+track[i-1].duration_ms<=track[i].start_ms);
  cases++;
 }
}
console.log(`${cases} layouts and unions matched independent overlap/coverage oracles; nested HTTP spans preserved`);
