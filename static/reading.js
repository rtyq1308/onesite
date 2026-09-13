(function () {
  'use strict';
  const config = window.READING || {}, query = new URLSearchParams(location.search);
  const content = document.querySelector('#reading-content'), title = document.querySelector('#reading-title');
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => Number(value).toLocaleString() + '원';
  const expand = block => block.d.map(values => Object.fromEntries(block.f.map((key,i)=>[key,values[i]])));
  async function json(url) { const response=await fetch(url); if (!response.ok) throw Error('load'); return response.json(); }
  function areaUrl(area) { const parts=area.split('/'); if(parts.length!==2 || parts.some(p=>!p || p==='..' || p==='.' || p.includes('\\'))) throw Error('area'); return '/data/'+parts.map(encodeURIComponent).join('/')+'.json'; }
  function detailUrl(row) { return '/parking/?area='+encodeURIComponent(row.area)+'&id='+encodeURIComponent(row.id); }
  function km(a,b,c,d) { const rad=Math.PI/180, x=Math.sin((c-a)*rad/2)**2+Math.cos(a*rad)*Math.cos(c*rad)*Math.sin((d-b)*rad/2)**2; return 6371*2*Math.atan2(Math.sqrt(x),Math.sqrt(1-x)); }
  function fee(row) { return row.fr ? '무료로 등록' : row.p30 ? '30분 환산 '+money(row.p30) : '요금 미등록'; }
  function conditions(row) { return row.fr ? '데이터상 무료로 등록되어 있습니다. 이용 대상 제한과 운영시간은 현장에서 확인하세요.' : row.fl && row.fl.length ? row.fl.join(' · ')+' / 그 외 시간의 무료 이용은 보장되지 않습니다.' : '무료 개방 조건이 등록되어 있지 않습니다.'; }
  function routes(row) { return '<div class="reading-actions"><a href="https://map.naver.com/p/search/'+encodeURIComponent(row.ad || row.nm)+'">네이버지도 길찾기</a><a href="https://map.kakao.com/link/map/'+encodeURIComponent(row.nm)+','+row.la+','+row.lo+'">카카오맵 길찾기</a><a href="https://www.google.com/maps/dir/?api=1&amp;destination='+row.la+','+row.lo+'">구글맵 길찾기</a></div>'; }
  function advertisement() {
    const slot=document.querySelector('#reading-ad');
    if(!slot || !config.ad || !config.ad.client || !config.ad.slot) return;
    slot.innerHTML='<span>광고</span><ins class="adsbygoogle" style="display:block;width:300px;height:250px" data-ad-client="'+esc(config.ad.client)+'" data-ad-slot="'+esc(config.ad.slot)+'"></ins>';
    let requested=false;
    function request(){if(requested) return; requested=true;try{(window.adsbygoogle=window.adsbygoogle||[]).push({});}catch(e){slot.hidden=true;}}
    if(window.IntersectionObserver){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){request();observer.disconnect();}},{rootMargin:'150px'});observer.observe(slot);}else request();
  }
  async function detail() {
    const area=query.get('area')||'', id=query.get('id');
    const data=await json(areaUrl(area)), row=expand(data.p).find(r=>r.id===id);
    if(!row) throw Error('missing');
    title.textContent=row.nm; document.title=row.nm+' 요금·무료 조건 | 공짜맵';
    const facts=[['주소',row.ad || '미등록'],['운영시간',row.tm || '미등록 — 운영기관에 확인 필요'],['주차면',row.cp ? row.cp+'면 (실시간 빈자리 아님)' : '미등록'],['구분',[row.se,row.kd].filter(Boolean).join(' · ') || '미등록']];
    content.innerHTML='<p class="reading-lead">'+esc(fee(row))+'</p>'+routes(row)+'<section><h2>요금 기준</h2><dl>'+[
      ['기본 요금',row.bt && row.bc ? row.bt+'분 '+money(row.bc) : '미등록'],['추가 요금',row.at && row.ac ? row.at+'분 '+money(row.ac) : '미등록'],['일 최대 요금',row.dm ? money(row.dm) : '미등록']
    ].map(([k,v])=>'<dt>'+k+'</dt><dd>'+esc(v)+'</dd>').join('')+'</dl><p>30분 환산 요금은 비교용입니다. 실제 결제액은 최소 부과 단위·할인·운영 규정에 따라 달라집니다. 미등록은 무료를 의미하지 않습니다.</p></section><section><h2>무료 이용 조건</h2><p>'+esc(conditions(row))+'</p></section><aside id="reading-ad" aria-label="광고"></aside><section><h2>운영 정보</h2><dl>'+facts.map(([k,v])=>'<dt>'+k+'</dt><dd>'+esc(v)+'</dd>').join('')+'</dl>'+(row.tel?'<p>문의: <a href="tel:'+esc(row.tel)+'">'+esc(row.tel)+'</a></p>':'')+'</section><section><h2>주변 대안 비교</h2><p>이 주차장을 기준으로 가까운 곳의 요금과 무료 조건을 함께 확인하세요.</p><a class="reading-primary" href="/compare/?lat='+row.la+'&amp;lng='+row.lo+'&amp;name='+encodeURIComponent(row.nm)+'">이 주변 주차장 비교하기</a></section><p class="reading-note">자료: 공공데이터포털·서울 열린데이터광장. 운영정보는 현장 안내를 우선하며 실시간 빈자리는 제공하지 않습니다.</p>';
  }
  async function compare() {
    const lat=Number(query.get('lat')), lng=Number(query.get('lng')), name=(query.get('name')||'목적지').slice(0,100);
    if(!Number.isFinite(lat)||!Number.isFinite(lng)||lat<33||lat>39.5||lng<124||lng>132) throw Error('coords');
    title.textContent=name+' 주변 주차장 비교'; document.title=title.textContent+' | 공짜맵';
    const index=await json('/data/index.json');
    const areas=index.sido.flatMap(s=>s.sgg.filter(g=>g.c).map(g=>({area:s.nm+'/'+g.nm,d:km(lat,lng,g.c[0],g.c[1])}))).sort((a,b)=>a.d-b.d).slice(0,8);
    const files=await Promise.allSettled(areas.map(a=>json(areaUrl(a.area))));
    if(files.every(f=>f.status==='rejected')) throw Error('load');
    const seen=new Set();
    const rows=files.filter(f=>f.status==='fulfilled').flatMap(f=>expand(f.value.p)).filter(r=>{if(seen.has(r.id))return false;seen.add(r.id);return true;}).map(r=>({...r,d:km(lat,lng,r.la,r.lo)})).filter(r=>r.d<=5).sort((a,b)=>a.d-b.d).slice(0,30);
    content.innerHTML='<p>목적지 반경 5km 안에서 가까운 최대 30곳을 비교합니다. 인근 8개 지역 데이터 기준이며 거리·요금은 실제 도보거리·결제액과 다릅니다.</p>'+(files.some(f=>f.status==='rejected')?'<p>일부 지역 정보를 불러오지 못해 결과가 제한됩니다.</p>':'')+'<label for="compare-sort">정렬 </label><select id="compare-sort"><option value="distance">가까운 순</option><option value="price">30분 환산 요금 순</option></select><label class="compare-filter"><input id="compare-free" type="checkbox"> 무료로 등록된 곳만</label><div id="compare-list"></div><aside id="reading-ad" aria-label="광고"></aside><div id="compare-tail"></div><section><h2>선택 전에 확인하세요</h2><p>요일별 무료 주차장은 방문 요일에 따라 유료일 수 있습니다. 상세 페이지의 기본·추가 요금과 운영시간을 확인하세요. 요금 미등록 주차장은 저렴한 것으로 판단하지 않습니다.</p></section>';
    function paint(){let selected=rows.filter(r=>!document.querySelector('#compare-free').checked || r.fr); if(document.querySelector('#compare-sort').value==='price')selected.sort((a,b)=>(a.fr?0:a.p30||Infinity)-(b.fr?0:b.p30||Infinity)||a.d-b.d);
      const cards=selected.map(r=>'<article><h2><a href="'+esc(detailUrl(r))+'">'+esc(r.nm)+'</a></h2><p><strong>'+esc(fee(r))+'</strong> · 직선 '+r.d.toFixed(2)+'km</p><p>'+esc(r.ad)+'</p><p>'+esc(conditions(r))+'</p><p>운영시간: '+esc(r.tm||'미등록')+'</p><a class="reading-primary" href="'+esc(detailUrl(r))+'">요금·무료 조건 상세</a>'+routes(r)+'</article>'); document.querySelector('#compare-list').innerHTML=cards.slice(0,3).join('') || '<p>조건에 맞는 주차장이 없습니다. 지도에서 다른 지역을 찾아보세요.</p>'; document.querySelector('#compare-tail').innerHTML=cards.slice(3).join('');}
    document.querySelector('#compare-sort').addEventListener('change',paint);document.querySelector('#compare-free').addEventListener('change',paint);paint();
    if(!rows.length)document.querySelector('#reading-ad').remove();
  }
  (config.mode==='parking'?detail():compare()).then(advertisement).catch(()=>{content.innerHTML='<p>정보를 불러오지 못했거나 유효하지 않은 주소입니다. 지도에서 주차장을 다시 선택해 주세요.</p><a href="/">지도로 돌아가기</a>';});
})();
