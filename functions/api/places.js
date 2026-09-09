// Secrets are supplied by Cloudflare Pages, never by the browser or a repository file.
export async function onRequestGet({ request, env }) {
  const reply = (body, status = 200) => Response.json(body, {
    status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }
  });
  const query = (new URL(request.url).searchParams.get('q') || '').trim();
  if (query.length < 2 || query.length > 100) return reply({ error: 'invalid_query' }, 400);
  const missing = ['NAVER_SEARCH_CLIENT_ID', 'NAVER_SEARCH_CLIENT_SECRET']
    .filter(name => !env[name]);
  if (missing.length) {
    // Report only expected variable names, never values or other bindings.
    return reply({ error: 'search_unavailable', code: 'missing_configuration', missing }, 503);
  }
  const url = new URL('https://naverapihub.apigw.ntruss.com/search/v1/local');
  url.searchParams.set('query', query);
  url.searchParams.set('display', '5');
  try {
    const result = await fetch(url, {
      headers: { 'X-NCP-APIGW-API-KEY-ID': env.NAVER_SEARCH_CLIENT_ID,
        'X-NCP-APIGW-API-KEY': env.NAVER_SEARCH_CLIENT_SECRET },
      signal: AbortSignal.timeout(6000)
    });
    if (!result.ok) return reply({ error: 'search_unavailable', code: 'upstream_rejected', upstreamStatus: result.status }, 502);
    const data = await result.json();
    const items = (data.items || []).slice(0, 5).map(item => ({
      name: String(item.title || '').replace(/<[^>]*>/g, ''),
      address: String(item.roadAddress || item.address || ''),
      lat: Number(item.mapy) / 1e7, lng: Number(item.mapx) / 1e7
    })).filter(item => item.name && Number.isFinite(item.lat) && Number.isFinite(item.lng) &&
      item.lat >= 33 && item.lat <= 39.5 && item.lng >= 124 && item.lng <= 132);
    return reply({ items });
  } catch (_) {
    return reply({ error: 'search_unavailable', code: 'upstream_failure' }, 502);
  }
}
