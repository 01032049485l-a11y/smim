/**
 * SMIM 실시간 시세 엔드포인트 — Cloudflare Pages Function
 *
 * 정적 사이트에는 서버가 없다. 그런데 Cloudflare Pages는 이 파일 하나만 두면
 * /api/quotes 라는 진짜 API를 무료로 띄워준다. 별도 서버도, 키도 필요 없다.
 *
 * 프런트가 15초마다 여기를 때리고, 값이 바뀌면 화면이 깜빡이며 갱신된다.
 */
const SYMBOLS = [
  { id: "^KS11",  label: "코스피",   ticker: "KOSPI"  },
  { id: "^KQ11",  label: "코스닥",   ticker: "KOSDAQ" },
  { id: "KRW=X",  label: "원/달러",  ticker: "USDKRW" },
  { id: "^GSPC",  label: "S&P 500",  ticker: "SPX"    },
  { id: "^IXIC",  label: "나스닥",   ticker: "NASDAQ" },
];

async function quoteSymbol(id) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(id)}?range=1d&interval=5m`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" }, cf: { cacheTtl: 30 } });
  if (!r.ok) return null;
  const j = await r.json();
  const m = j?.chart?.result?.[0]?.meta;
  if (!m) return null;
  const closes = (j.chart.result[0].indicators?.quote?.[0]?.close || []).filter((x) => x != null);
  const last = m.regularMarketPrice ?? closes.at(-1);
  const prev = m.chartPreviousClose ?? m.previousClose;
  if (last == null || prev == null) return null;
  return {
    last: +last.toFixed(2),
    prev: +prev.toFixed(2),
    state: m.marketState || "",
    series: closes.slice(-40).map((v) => +v.toFixed(2)),
  };
}

async function quote(sym) {
  const q = await quoteSymbol(sym.id);
  if (!q) return null;
  return {
    label: sym.label,
    ticker: sym.ticker,
    value: q.last,
    change: +(q.last - q.prev).toFixed(2),
    change_pct: +(((q.last / q.prev) - 1) * 100).toFixed(2),
    state: q.state,
    series: q.series,
  };
}

// 종목추천(판정·논거)은 스냅샷 그대로 하루 단위지만, 가격·수익률은 장중 실시간으로 보여준다.
// 한국은 코드(6자리)에 시장별 접미사를 붙여 야후 티커를 만들고(코스피 .KS / 코스닥 .KQ),
// 미국(NASDAQ/NYSE)은 티커 자체가 이미 야후 심볼이라 그대로 쓴다.
function yahooStockSymbol(code, market) {
  if (market === "KOSDAQ") return `${code}.KQ`;
  if (market === "KOSPI") return `${code}.KS`;
  return code;
}

async function quoteStock(code, market) {
  const q = await quoteSymbol(yahooStockSymbol(code, market));
  if (!q) return null;
  return {
    ticker: code,
    value: q.last,
    change: +(q.last - q.prev).toFixed(2),
    change_pct: +(((q.last / q.prev) - 1) * 100).toFixed(2),
    state: q.state,
  };
}

const MAX_STOCK_CODES = 60; // 워치리스트(한국+미국, 최대 24) + 뉴스룸 언급 종목까지 여유있게.

export async function onRequest({ request }) {
  const url = new URL(request.url);
  const pairs = (url.searchParams.get("codes") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, MAX_STOCK_CODES)
    .map((s) => {
      const [code, market] = s.split(":");
      return { code, market };
    })
    // 한국: 6자리 숫자 코드 / 미국: 알파벳(+.) 티커 1~6자
    .filter((p) => /^\d{6}$/.test(p.code) || /^[A-Za-z][A-Za-z.]{0,5}$/.test(p.code));

  const [indices, stocks] = await Promise.all([
    Promise.all(SYMBOLS.map((s) => quote(s).catch(() => null))),
    Promise.all(pairs.map((p) => quoteStock(p.code, p.market).catch(() => null))),
  ]);

  return new Response(
    JSON.stringify({ ts: Date.now(), quotes: [...indices, ...stocks].filter(Boolean) }),
    {
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, max-age=20",
        "access-control-allow-origin": "*",
      },
    }
  );
}
