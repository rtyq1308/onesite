import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../static/reading.js',import.meta.url),'utf8');
test('detail keeps useful facts and navigation before ad, requests ad only once on approach',async()=>{
  const nodes=Object.fromEntries(['#reading-content','#reading-title','#reading-ad'].map(id=>[id,{innerHTML:'',addEventListener(){}}]));
  let observe;
  const context=vm.createContext({URLSearchParams,location:{search:'?area=서울/중구&id=one'},
    document:{querySelector:id=>nodes[id]},
    window:{READING:{mode:'parking',ad:{client:'test',slot:'test'}},IntersectionObserver:true,gtag(){throw Error('analytics unavailable');}},
    IntersectionObserver:class {constructor(fn){observe=fn;}observe(){}disconnect(){}},
    fetch:async()=>({ok:true,json:async()=>({p:{f:['id','nm','ad','tm','fr','la','lo'],d:[['one','테스트','서울','매일',1,37.5,127]]}})})});
  vm.runInContext(source,context);
  await new Promise(resolve=>setImmediate(resolve));
  const html=nodes['#reading-content'].innerHTML;
  assert.ok(html.indexOf('무료 이용 조건')<html.indexOf('id="reading-ad"'));
  assert.ok(html.indexOf('네이버지도 길찾기')<html.indexOf('id="reading-ad"'));
  assert.ok(html.indexOf('id="reading-ad"')<html.indexOf('요금 기준'));
  assert.equal(context.window.adsbygoogle,undefined);
  observe([{isIntersecting:false,intersectionRatio:0}]);
  assert.equal(context.window.adsbygoogle,undefined);
  observe([{isIntersecting:true,intersectionRatio:0.2}]);
  observe([{isIntersecting:true,intersectionRatio:1}]);
  assert.equal(context.window.adsbygoogle.length,1);
  assert.notEqual(nodes['#reading-ad'].hidden,true);
});
