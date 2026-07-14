"""뉴스룸.

단순 헤드라인 나열은 아무 가치가 없다. 네이버에서 이미 볼 수 있다.
SMIM의 뉴스룸은 각 기사에 대해 "그래서 어느 종목에, 왜 중요한가"를 붙인다.
그게 이 사이트에 머무를 이유다.

저작권: 기사 제목·링크·발행일만 저장한다. 본문은 절대 저장·재배포하지 않는다.
        해석 문장은 AI가 제목과 공개 정보를 근거로 직접 쓴 것이다.
"""
import json
import re

import config
from pipeline.agents import _call, _parse_json, AIFailure
from pipeline.sources import news, us_news, prices

TOPICS = [
    ("증시", "코스피 코스닥 증시"),
    ("반도체", "반도체 주가"),
    ("2차전지", "2차전지 배터리 주가"),
    ("바이오", "제약 바이오 주가"),
    ("자동차", "자동차 전기차 주가"),
    ("금융", "은행 증권 금리"),
    ("환율·거시", "환율 금리 물가"),
]

# 미국은 네이버 같은 키워드 검색 API가 없어 Yahoo Finance의 종목별 RSS를
# 섹터 대표 종목으로 묶어 대체한다 — KR의 TOPICS와 같은 섹터 이름을 그대로 써서
# 화면에서 같은 필터 버튼으로 한국/미국 뉴스를 동시에 걸러낼 수 있게 한다.
US_TOPICS = [
    ("증시", ["SPY", "QQQ"]),
    ("반도체", ["NVDA", "AVGO", "AMD", "TSM"]),
    ("2차전지", ["TSLA", "ALB", "ENPH"]),
    ("바이오", ["PFE", "MRNA", "LLY"]),
    ("자동차", ["GM", "F", "TM"]),
    ("금융", ["JPM", "BAC", "GS"]),
    ("IT·플랫폼", ["AAPL", "MSFT", "GOOGL", "META"]),
]

TAGGER_SYS = """너는 국내·미국 증시 뉴스 데스크의 에디터다.
아래는 오늘 수집된 기사 제목 목록이다. 각 기사에 대해 다음을 판단한다.

- sector: 반도체 / 2차전지 / 바이오 / 자동차 / 금융 / 조선·방산 / IT·플랫폼 / 소비재 / 건설·기계 / 에너지 / 거시·환율 / 증시일반 중 하나
- impact: strong_positive / positive / neutral / negative / strong_negative 중 하나
        (제목에 등장하는 상장사·업종에 미치는 방향과 강도. 실적 서프라이즈·대규모 계약·
        규제 리스크 확정처럼 방향과 크기가 둘 다 뚜렷할 때만 strong_*을 쓰고, 애매하면
        positive/negative/neutral로 보수적으로 판단한다)
- why: 이 뉴스가 투자자에게 왜 중요한지 한 문장. 제목에서 확인되는 사실만 근거로 쓴다.
        추측이나 확인되지 않은 숫자를 절대 만들어내지 마라. 불확실하면 "확인 필요"라고 써라.
- tickers: 제목에 명시적으로 등장하는 상장사 이름만 배열로. 없으면 빈 배열.

기사 본문은 주어지지 않았다. 제목만 보고 판단하되, 과장하지 마라.

반드시 아래 JSON만 출력한다. 입력 순서와 동일한 개수로.
{"items":[{"i":0,"sector":"...","impact":"strong_positive|positive|neutral|negative|strong_negative","why":"...","tickers":["..."]}]}"""


def collect_kr() -> list[dict]:
    seen, items = set(), []
    for topic, query in TOPICS:
        for n in news.search(query, display=8, days=2):
            if n["url"] in seen:
                continue
            seen.add(n["url"])
            items.append({**n, "topic": topic})
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:40]


def collect_us() -> list[dict]:
    seen, items = set(), []
    for topic, tickers in US_TOPICS:
        for ticker in tickers:
            for n in us_news.for_stock(ticker, display=4):
                if n["url"] in seen:
                    continue
                seen.add(n["url"])
                items.append({**n, "topic": topic})
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:40]


def collect(market_group: str = "KR") -> list[dict]:
    return collect_us() if market_group == "US" else collect_kr()


def tag(items: list[dict]) -> list[dict]:
    """AI 1회 호출로 전체 기사에 맥락을 붙인다. 실패해도 기사 목록은 살아남는다."""
    if not items:
        return []
    listing = "\n".join(f"{i}. {it['title']}" for i, it in enumerate(items))
    try:
        res = _parse_json(_call(TAGGER_SYS, listing, config.NEWSTAG_MODEL, max_tokens=4000))
    except (AIFailure, json.JSONDecodeError, ValueError) as e:
        print(f"[newsroom] 태깅 실패({e}) — 원문 링크만 발행")
        return items

    by_i = {int(x["i"]): x for x in res.get("items", []) if "i" in x}
    for i, it in enumerate(items):
        t = by_i.get(i)
        if not t:
            continue
        it["sector"] = t.get("sector")
        it["impact"] = t.get("impact", "neutral")
        it["why"] = t.get("why")
        it["tickers"] = [x for x in (t.get("tickers") or []) if isinstance(x, str)][:4]
    return items


_SUFFIX_RE = re.compile(
    r"\b(incorporated|corporation|holdings?|group|company|limited|adr|"
    r"inc|corp|co|ltd|plc|class [ab])\b\.?", re.IGNORECASE)

# 뉴스 제목에서 흔히 쓰는 약칭·별칭이 상장사 공식명과 아예 다른 대표 사례.
# (예: "TSMC" 기사 제목에는 자주 나오지만 공식 상장명은 "Taiwan Semiconductor...")
_ALIASES = {
    "tsmc": "taiwan semiconductor manufacturing",
    "google": "alphabet",
    "facebook": "meta platforms",
    "ibm": "international business machines",
    "gm": "general motors",
    "amd": "advanced micro devices",
}


def _norm(name: str) -> str:
    n = _SUFFIX_RE.sub("", name.lower().strip())
    n = re.sub(r"[^a-z0-9가-힣 ]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return _ALIASES.get(n, n)


def _match_name(name: str, norm_index: dict) -> dict | None:
    """정확히 일치 → 별칭·접미사 제거 후 일치 → 부분 문자열 순으로 완화하며 찾는다.
    뉴스 제목의 회사명 표기가 거래소 공식 상장명과 정확히 같지 않은 경우가 많아서
    (예: "TSMC" vs "Taiwan Semiconductor Manufacturing Co Ltd ADR") 단계적으로 느슨하게 본다."""
    key = _norm(name)
    if not key or len(key) < 2:
        return None
    if key in norm_index:
        return norm_index[key]
    if len(key) >= 4:  # 너무 짧은 이름은 부분일치 시 오탐이 잦아 제외
        for k, v in norm_index.items():
            if key in k or k in key:
                return v
    return None


def resolve_tickers(items: list[dict], market_group: str) -> list[dict]:
    """AI가 제목에서 뽑은 회사명을 실제 종목코드 + 전일 대비 등락률에 매칭한다.
    "반도체 뉴스 떴는데 이게 어느 종목 얘기지?"를 숫자로 바로 보여주기 위함.
    유니버스에 없는 이름(비상장·해외 대형주 등)은 이름만 남고 등락률은 비운다.
    여기서 붙는 change_pct는 발행 시점 값이고, 화면에서는 live.js가 실시간으로 다시 갱신한다."""
    try:
        uni = prices.load_universe(market_group)
        norm_index = {_norm(r["Name"]): {"code": r["Code"], "market": r["Market"]} for _, r in uni.iterrows()}
    except Exception as e:
        print(f"[newsroom] 종목 매칭용 유니버스 로드 실패({e}) — 이름만 표시")
        norm_index = {}

    price_cache: dict[str, dict | None] = {}

    def _change(code: str) -> dict | None:
        if code not in price_cache:
            df = prices.ohlcv(code, days=10, fast=True)
            if df is not None and len(df) >= 2:
                last, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
                price_cache[code] = {"price": last, "change_pct": round((last / prev - 1) * 100, 2)} if prev else None
            else:
                price_cache[code] = None
        return price_cache[code]

    for it in items:
        resolved = []
        for name in (it.get("tickers") or []):
            row = _match_name(name, norm_index)
            if not row:
                resolved.append({"name": name, "code": None, "market": None, "change_pct": None})
                continue
            chg = _change(row["code"])
            resolved.append({"name": name, "code": row["code"], "market": row["market"],
                              "change_pct": (chg or {}).get("change_pct")})
        it["ticker_prices"] = resolved
    return items


def build(market_group: str = "KR") -> list[dict]:
    return resolve_tickers(tag(collect(market_group)), market_group)


def link_to_watchlist(items: list[dict], watchlist: list[dict]) -> list[dict]:
    """뉴스에 언급된 종목이 우리 워치리스트에 있으면 내부 링크를 건다.
    → 사용자가 뉴스에서 종목으로, 종목에서 리포트로 계속 흐르게 만든다."""
    names = {h["name"]: h["code"] for h in watchlist}
    for it in items:
        hits = []
        title = it.get("title", "")
        for nm, code in names.items():
            if nm in title or nm in (it.get("tickers") or []):
                hits.append({"name": nm, "code": code})
        it["watchlist_hits"] = hits[:3]
    return items
