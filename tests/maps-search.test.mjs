import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const endpointSource = fs.readFileSync(new URL('../functions/api/places.js', import.meta.url), 'utf8');
const appSource = fs.readFileSync(new URL('../static/app.js', import.meta.url), 'utf8');
function api(fetch) {
  const ctx = vm.createContext({ Response, URL, AbortSignal, fetch });
  vm.runInContext(endpointSource.replace('export async function', 'async function') + '\nglobalThis.handler = onRequestGet;', ctx);
  return (q, env = { NAVER_SEARCH_CLIENT_ID: 'test-id', NAVER_SEARCH_CLIENT_SECRET: 'test-secret' }) =>
    ctx.handler({ request: new Request('https://example.test/api/places?q=' + encodeURIComponent(q)), env });
}
test('rejects invalid query before upstream access', async () => {
  const handler = api(() => { throw Error('must not call'); });
  assert.equal((await handler('a')).status, 400);
  assert.equal((await handler('x'.repeat(101))).status, 400);
});
test('missing configuration returns a safe 503', async () => {
  const result = await api(() => { throw Error('must not call'); })('서울역', {});
  assert.equal(result.status, 503);
  assert.equal(result.headers.get('Cache-Control'), 'no-store');
});
test('normalizes WGS84 coordinates and removes markup; secrets stay upstream', async () => {
  const handler = api(async (url, options) => {
    assert.equal(url.hostname, 'naverapihub.apigw.ntruss.com');
    assert.equal(url.pathname, '/search/v1/local');
    assert.equal(url.searchParams.get('display'), '5');
    assert.equal(options.headers['X-NCP-APIGW-API-KEY-ID'], 'test-id');
    assert.equal(options.headers['X-NCP-APIGW-API-KEY'], 'test-secret');
    return Response.json({ items: [
      { title: '<b>서울역</b>', roadAddress: '서울 용산구', mapx: '1269700000', mapy: '375500000' },
      { title: 'invalid', mapx: 'x', mapy: '0' }
    ] });
  });
  const result = await handler('서울역');
  assert.deepEqual(await result.json(), { items: [{ name: '서울역', address: '서울 용산구', lat: 37.55, lng: 126.97 }] });
});
test('upstream rejection and timeout hide upstream data', async () => {
  for (const fetch of [async () => new Response('test-secret', { status: 401 }), async () => { throw Error('test-secret'); }]) {
    const result = await api(fetch)('서울역');
    assert.equal(result.status, 502);
    assert.equal((await result.text()).includes('test-secret'), false);
  }
});

class Element {
  constructor() { this.children = []; this.events = {}; this.attrs = {}; this.value = ''; this.textContent = ''; this.innerHTML = ''; this.hidden = true; }
  addEventListener(name, fn) { this.events[name] = fn; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); }
  replaceChildren() { this.children = []; }
}
function app(mode = 'home', fetch = async () => Response.json({ items: [] })) {
  const nodes = Object.fromEntries(['map', 'destination-form', 'destination-query', 'destination-status', 'destination-results', 'list', 'list-count', 'more', 'listbar', 'nearby-result', 'nearby-msg'].map(k => ['#' + k, new Element()]));
  if (mode === 'home') nodes['#nearby'] = new Element();
  const ctx = vm.createContext({ console, URL, AbortController, setTimeout, clearTimeout, fetch,
    window: { addEventListener() {}, FREEMAP: { mode, indexUrl: '/data/index.json', dataBase: '/data/' } },
    document: { querySelector: s => nodes[s] || null, createElement: () => new Element(), addEventListener() {} }
  });
  vm.runInContext(appSource.replace(/\}\)\(\);\s*$/, 'globalThis.testAPI = {state, bindDestinationSearch, loadNearby, initMap, applyFilter, geocodeAddress, renderMarkers, declutter};\n})();'), ctx);
  return { ...ctx.testAPI, nodes, ctx };
}
const flush = () => new Promise(resolve => setTimeout(resolve, 20));
test('map SDK missing still leaves readable fallback and region list', () => {
  const t = app('region'); t.initMap();
  assert.match(t.nodes['#map'].innerHTML, /지도를 불러오지 못했습니다/);
  t.state.all = [{ nm: '테스트 주차장', la: 37.55, lo: 126.97, fr: 1 }];
  t.applyFilter(); assert.match(t.nodes['#list'].innerHTML, /테스트 주차장/);
});
test('search renders text safely and selecting destination loads nearby region results without map SDK', async () => {
  const t = app('region', async url => {
    if (url.startsWith('/api/')) return Response.json({ items: [{ name: '<img onerror=evil()>', address: '서울', lat: 37.55, lng: 126.97 }] });
    if (url.endsWith('index.json')) return Response.json({ sido: [{ nm: '서울', sgg: [{ nm: '용산구', c: [37.55, 126.97] }] }] });
    return Response.json({ p: { f: ['nm','la','lo','fr'], d: [['먼 곳',37.6,127,0],['가까운 곳',37.55,126.97,1]] } });
  });
  t.bindDestinationSearch(); t.nodes['#destination-query'].value = '서울역';
  t.nodes['#destination-form'].events.submit({ preventDefault() {} }); await flush();
  const button = t.nodes['#destination-results'].children[0];
  assert.equal(button.children[0].textContent, '<img onerror=evil()>');
  assert.equal(button.children[0].innerHTML, '');
  button.events.click(); await flush();
  assert.equal(t.state.all[0].nm, '가까운 곳');
  assert.equal(t.nodes['#destination-status'].textContent, '');
  assert.equal(t.nodes['#nearby-msg'].textContent, '');
  t.state.onlyFree = true; t.applyFilter(); assert.equal(t.state.rows.length, 1);
});
test('search outage offers recovery instead of an empty success', async () => {
  const t = app('home', async () => new Response('', { status: 503 }));
  t.bindDestinationSearch(); t.nodes['#destination-query'].value = '서울역';
  t.nodes['#destination-form'].events.submit({ preventDefault() {} }); await flush();
  assert.match(t.nodes['#destination-status'].textContent, /지금 이용할 수 없습니다/);
  assert.equal(t.nodes['#destination-form'].attrs['aria-busy'], undefined);
});
test('stale search response cannot replace new input', async () => {
  let resolve;
  const t = app('home', () => new Promise(r => { resolve = r; }));
  t.bindDestinationSearch(); t.nodes['#destination-query'].value = '서울역';
  t.nodes['#destination-form'].events.submit({ preventDefault() {} });
  t.nodes['#destination-query'].value = '부산역'; t.nodes['#destination-query'].events.input();
  resolve(Response.json({ items: [{ name: '서울역', lat: 37.55, lng: 126.97 }] })); await flush();
  assert.equal(t.nodes['#destination-results'].children.length, 0);
});
test('address fallback uses query and validates returned coordinates', async () => {
  const t = app();
  t.ctx.window.naver = t.ctx.naver = { maps: { Service: { Status: { OK: 200 }, geocode({ query }, cb) {
    assert.equal(query, '서울 도로명');
    cb(200, { v2: { addresses: [{ roadAddress: '서울 도로명', jibunAddress: '서울', x: '126.97', y: '37.55' }] } });
  } } } };
  const rows = await t.geocodeAddress('서울 도로명'); assert.equal(rows[0].lat, 37.55);
});

test('Naver marker lifecycle: filter replaces markers; popup and origin marker work (SDK mock)', async () => {
  const t = app('region', async url => url.endsWith('index.json')
    ? Response.json({ sido: [{ nm: '서울', sgg: [{ nm: '중구', c: [37.55,126.97] }] }] })
    : Response.json({ p: { f: ['nm','la','lo','fr'], d: [['주차장',37.55,126.97,1]] } }));
  class LatLng { constructor(lat, lng) { this.y=lat; this.x=lng; } lat() { return this.y; } lng() { return this.x; } }
  class Map { constructor(_, options) { this.center=options.center; this.zoom=options.zoom; } getBounds() { return {hasLatLng: () => true}; } getProjection() { return {fromCoordToOffset: p => ({x:p.x*1000,y:p.y*1000})}; } setCenter(p) {this.center=p;} setZoom(z) {this.zoom=z;} getZoom() {return this.zoom;} fitBounds() {} }
  class Marker { constructor(options) {Object.assign(this,options);} setMap(map) {this.map=map;} }
  class InfoWindow { constructor(options) {this.content=options.content;} open(map,marker) {this.marker=marker;} close() {this.marker=null;} }
  t.ctx.window.naver=t.ctx.naver={maps: {Map, Marker, LatLng, InfoWindow, Point: class {}, Position:{TOP_RIGHT:1},
    LatLngBounds: class {extend() {}}, Event:{addListener(obj,event,fn) {(obj.events ||= {})[event]=fn;},clearInstanceListeners(obj) {obj.events={};}} }};
  t.initMap(); t.state.rows=[{nm:'무료',fr:1,la:37.55,lo:126.97},{nm:'유료',p30:1000,la:37.7,lo:127.1}];
  t.renderMarkers(); const old=t.state.layer[0]; assert.equal(t.state.layer.length,2);
  old.events.click(); assert.match(t.state.infoWindow.content,/무료/);
  t.state.rows=[]; t.renderMarkers(); assert.equal(old.map,null); assert.equal(t.state.layer.length,0);
  t.state.origin=[37.55,126.97]; await t.loadNearby('목적지');
  assert.equal(t.state.map.center.lat(),37.55); assert.equal(t.state.map.zoom,15);
  assert.equal(t.state.originMarker.title,'목적지');
  const first=t.state.originMarker; await t.loadNearby('새 목적지'); assert.equal(first.map,null);
  t.state.map.setZoom(18);
  t.state.onlyFree=true;
  t.applyFilter(true);
  assert.equal(t.state.map.zoom,18,'filtering must not reset the explored map viewport');
  const detail = new Element();
  detail.showModal = function () { this.open = true; };
  detail.close = function () { this.open = false; };
  t.nodes['#spot-detail'] = detail;
  t.ctx.window.matchMedia = () => ({matches:true});
  t.renderMarkers(); t.state.layer[0].events.click();
  assert.equal(detail.open,true,'mobile marker must open a top-layer detail dialog');
  assert.match(detail.innerHTML,/주차장/);
  assert.equal(t.state.popupOpen,true);
});


test('dense viewport caps individual markers and preserves every overflow parking in bounded groups', () => {
  const t = app('region');
  t.ctx.naver = {maps:{LatLng:class {constructor(la,lo) {this.la=la;this.lo=lo;}}}};
  t.state.map = {getBounds:()=>({hasLatLng:p=>p.la>=0}),
    getProjection:()=>({fromCoordToOffset:p=>({x:p.lo*100,y:p.la*100})})};
  t.state.rows = Array.from({length:5000},(_,i)=>({la:Math.floor(i/100),lo:i%100}));
  t.state.rows.push({la:-1,lo:0});
  const result=t.declutter();
  assert.equal(result.labeled.length,50);
  assert.ok(result.groups.length<=40);
  assert.equal(result.groups.reduce((n,g)=>n+g.count,0)+result.labeled.length,5000);
  t.state.rows=Array.from({length:5000},()=>({la:1,lo:1}));
  const overlapping=t.declutter();
  assert.equal(overlapping.labeled.length,1);
  assert.equal(overlapping.groups.length,1);
  assert.equal(overlapping.groups[0].count,4999);
});
