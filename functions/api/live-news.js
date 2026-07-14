/**
 * SMIM 실시간 뉴스 엔드포인트 — Cloudflare Pages Function
 *
 * quotes.js와 같은 패턴: 원본 API(네이버 뉴스, Yahoo Finance RSS)를 브라우저 요청 시점에
 * 직접 호출해 제목·발행일·링크만 즉시 반환한다. AI 태깅은 하지 않는다(호출마다 비용이
 * 드는 게 아니라 무료) — 정식 섹터·영향·의미 해설은 하루 배치 실행 때 newsroom.tag()가
 * 붙인다. 그래서 방금 올라온 기사는 "실시간" 배지만 달고, 다음 정기 발행 때 정식 해설이
 * 채워진다.
 */
const NAVER_QUERIES = ["코스피 증시", "코스닥 시황", "한국 증시 전망"];
const YAHOO_TICKER = "^GSPC"; // 미국 시장 전반 헤드라인 대체

function stripHtml(s) {
  return (s || "").replace(/<[^>]+>/g, "").replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&#39;/g, "'").trim();
}

async function naverNews(env) {
  if (!env.NAVER_CLIENT_ID || !env.NAVER_CLIENT_SECRET) return [];
  const headers = {
    "X-Naver-Client-Id": env.NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": env.NAVER_CLIENT_SECRET,
  };
  const out = [];
  for (const q of NAVER_QUERIES) {
    try {
      const url = `https://openapi.naver.com/v1/search/news.json?query=${encodeURIComponent(q)}&display=5&sort=date`;
      const r = await fetch(url, { headers, cf: { cacheTtl: 30 } });
      if (!r.ok) continue;
      const j = await r.json();
      for (const it of j.items || []) {
        out.push({
          title: stripHtml(it.title),
          url: it.originallink || it.link,
          published: new Date(it.pubDate).toISOString(),
          market: "KR",
        });
      }
    } catch (e) { /* 이 질의만 건너뛰고 계속 */ }
  }
  return out;
}

async function yahooNews() {
  try {
    const url = `https://feeds.finance.yahoo.com/rss/2.0/headline?s=${encodeURIComponent(YAHOO_TICKER)}&region=US&lang=en-US`;
    const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }, cf: { cacheTtl: 30 } });
    if (!r.ok) return [];
    const xml = await r.text();
    const out = [];
    for (const chunk of xml.split("<item>").slice(1, 9)) {
      const title = (chunk.match(/<title>([\s\S]*?)<\/title>/) || [])[1];
      const link = (chunk.match(/<link>([\s\S]*?)<\/link>/) || [])[1];
      const pub = (chunk.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1];
      if (!title || !link) continue;
      const d = pub ? new Date(pub) : null;
      out.push({
        title: stripHtml(title),
        url: link.trim(),
        published: d && !isNaN(d) ? d.toISOString() : new Date().toISOString(),
        market: "US",
      });
    }
    return out;
  } catch (e) {
    return [];
  }
}

export async function onRequest({ env }) {
  const [kr, us] = await Promise.all([naverNews(env).catch(() => []), yahooNews().catch(() => [])]);
  const items = [...kr, ...us].sort((a, b) => new Date(b.published) - new Date(a.published));
  return new Response(
    JSON.stringify({ ts: Date.now(), items: items.slice(0, 20) }),
    {
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, max-age=45",
        "access-control-allow-origin": "*",
      },
    }
  );
}
