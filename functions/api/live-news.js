/**
 * SMIM 실시간 뉴스 엔드포인트 — Cloudflare Pages Function
 *
 * quotes.js와 같은 패턴: 원본 API(네이버 뉴스, Yahoo Finance RSS)를 브라우저 요청 시점에
 * 직접 호출해 제목·발행일·링크를 가져온다. 이 응답 자체가 45초 동안 Cloudflare 엣지에
 * 캐시되므로(cache-control), 동시 방문자가 몇 명이든 이 함수는 45초에 한 번만 실제로
 * 실행된다 — 그래서 매 호출마다 AI를 붙여도 비용이 방문자 수에 비례해 커지지 않는다.
 * 본문은 안 가져온다(속도 우선) — 제목만으로 섹터·영향·짧은 이유를 빠르게 붙인다.
 * 배치 실행 때 newsroom.tag()가 붙이는 본문 기반 "AI 해설"(더 깊은 요약)은 여기서는
 * 하지 않는다 — 그건 다음 정기 발행 때 채워진다.
 */
const NAVER_QUERIES = ["코스피 증시", "코스닥 시황", "한국 증시 전망"];
const YAHOO_TICKER = "^GSPC"; // 미국 시장 전반 헤드라인 대체

const TAGGER_SYS = `너는 국내·미국 증시 뉴스 데스크의 에디터다. 아래 기사 제목 목록 각각에 대해
sector(반도체/2차전지/바이오/자동차/금융/조선·방산/IT·플랫폼/소비재/건설·기계/에너지/거시·환율/증시일반 중 하나),
impact(strong_positive/positive/neutral/negative/strong_negative 중 하나),
why(왜 중요한지 한 문장, "~습니다/입니다"체, 제목에서 확인되는 사실만, 지어내지 마라)를 판단해라.
반드시 JSON만: {"items":[{"i":0,"sector":"...","impact":"...","why":"..."}]}`;

async function tagWithAI(env, items) {
  // 태깅이 느려지면(오늘 실제로 배치 태깅에서 몇 분씩 걸리는 걸 겪었다) 이 엔드포인트
  // 응답 전체가 느려져서 "실시간"이라는 이름이 무색해진다. 4초 안에 안 끝나면
  // 그냥 포기하고 원문 제목만 즉시 내보낸다 — 다음 폴링(60초 뒤)에서 다시 시도된다.
  // _debug: 2026-07-16 실시간 태깅이 계속 비어 나오는 원인 추적용 임시 필드. 원인 확인되면 제거.
  if (!env.ANTHROPIC_API_KEY || !items.length) {
    return { items, _debug: { hasKey: !!env.ANTHROPIC_API_KEY, itemCount: items.length, stage: "skip_no_key_or_items" } };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const listing = items.map((it, i) => `${i}. ${it.title}`).join("\n");
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 2000,
        system: TAGGER_SYS,
        messages: [{ role: "user", content: listing }],
      }),
      signal: controller.signal,
    });
    if (!r.ok) {
      const bodyText = await r.text().catch(() => "");
      return { items, _debug: { stage: "anthropic_not_ok", status: r.status, body: bodyText.slice(0, 500) } };
    }
    const data = await r.json();
    const text = (data.content || []).map((b) => b.text || "").join("");
    const m = text.match(/\{[\s\S]*\}/);
    if (!m) return { items, _debug: { stage: "no_json_in_response", raw: text.slice(0, 500) } };
    const parsed = JSON.parse(m[0]);
    const byI = {};
    for (const x of parsed.items || []) byI[x.i] = x;
    const tagged = items.map((it, i) => {
      const t = byI[i];
      return t ? { ...it, sector: t.sector, impact: t.impact, why: t.why } : it;
    });
    return { items: tagged, _debug: { stage: "ok" } };
  } catch (e) {
    return { items, _debug: { stage: "exception", message: String(e && e.message || e) } };
  } finally {
    clearTimeout(timer);
  }
}

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
  const items = [...kr, ...us].sort((a, b) => new Date(b.published) - new Date(a.published)).slice(0, 20);
  const { items: tagged, _debug } = await tagWithAI(env, items);
  return new Response(
    JSON.stringify({ ts: Date.now(), items: tagged, _debug }),
    {
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, max-age=45",
        "access-control-allow-origin": "*",
      },
    }
  );
}
