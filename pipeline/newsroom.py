"""뉴스룸.

단순 헤드라인 나열은 아무 가치가 없다. 네이버에서 이미 볼 수 있다.
SMIM의 뉴스룸은 각 기사에 대해 "그래서 어느 종목에, 왜 중요한가"를 붙인다.
그게 이 사이트에 머무를 이유다.

저작권 (2026-07-15 사용자 승인으로 완화, CLAUDE.md 참고): 스냅샷·사이트에는
기사 제목·링크·발행일과 AI가 쓴 해설 문장만 저장한다. "AI 해설"을 만들 때
원문 기사를 그 순간 가져와 참고는 하지만, 가져온 원문 텍스트 자체는 요약
생성 직후 버리고 어디에도 저장하지 않는다.
"""
import json
import re
import concurrent.futures as cf

import requests
from bs4 import BeautifulSoup

import config
from pipeline.agents import _call_json, AIFailure
from pipeline.sources import news, prices

_ARTICLE_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _fetch_article_text(url: str, max_chars: int = 1500) -> str:
    """"AI 해설"을 위해 원문을 그 자리에서 잠깐 읽어온다 — 반환값은 요약에만 쓰이고
    호출한 쪽에서 저장하지 않는다(newsroom.py 상단 저작권 메모 참고)."""
    try:
        r = requests.get(url, headers=_ARTICLE_HEADERS, timeout=8)
        r.raise_for_status()
    except Exception:
        return ""
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        paras = [p for p in paras if len(p) > 30]  # 짧은 문구(광고·안내 문구)는 배제
        return " ".join(paras)[:max_chars]
    except Exception:
        return ""


def _fetch_bodies(items: list[dict]) -> None:
    """기사 본문을 병렬로 가져와 각 항목에 임시로 붙인다(제자리 수정)."""
    def _one(it):
        it["_body"] = _fetch_article_text(it["url"])
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(_one, items))

TOPICS = [
    ("증시", "코스피 코스닥 증시"),
    ("반도체", "반도체 주가"),
    ("2차전지", "2차전지 배터리 주가"),
    ("바이오", "제약 바이오 주가"),
    ("자동차", "자동차 전기차 주가"),
    ("금융", "은행 증권 금리"),
    ("환율·거시", "환율 금리 물가"),
]

TAGGER_SYS = """너는 국내 증시 뉴스 데스크의 에디터다.
아래는 오늘 수집된 기사 제목 목록이다. 각 기사에 대해 다음을 판단한다.

- sector: 반도체 / 2차전지 / 바이오 / 자동차 / 금융 / 조선·방산 / IT·플랫폼 / 소비재 / 건설·기계 / 에너지 / 거시·환율 / 증시일반 중 하나
- impact: strong_positive / positive / neutral / negative / strong_negative 중 하나
        (제목에 등장하는 상장사·업종에 미치는 방향과 강도. 실적 서프라이즈·대규모 계약·
        규제 리스크 확정처럼 방향과 크기가 둘 다 뚜렷할 때만 strong_*을 쓰고, 애매하면
        positive/negative/neutral로 보수적으로 판단한다)
- why: 이 뉴스가 투자자에게 왜 중요한지 한 문장. 본문에서 확인되는 사실만 근거로 쓴다.
        추측이나 확인되지 않은 숫자를 절대 만들어내지 마라. 불확실하면 "확인이 필요합니다"라고
        써라. "~습니다/입니다"체로 끝낸다.
- insight: "AI 해설" 버튼을 눌렀을 때 펼쳐지는 3~5문장짜리 해설. 각 기사에는 본문 일부가
        같이 주어진다 — 그 본문을 실제로 읽고 핵심 내용을 네 말로 요약한 뒤, 투자자 관점에서
        왜 중요한지·무엇을 더 확인해야 하는지를 덧붙인다. 본문에 없는 숫자·사실을 절대
        지어내지 마라. 본문이 비어있거나 너무 짧아 판단이 어려우면 제목과 공개 정보만으로
        판단하되 과장하지 마라. 문장은 반드시 "~습니다/입니다"체의 정중한 존댓말로 끝낸다.
        "~다"로 끝나는 반말체(개조식)는 절대 쓰지 마라.
- tickers: "실제 거래소에 상장된 종목"으로 명시적으로 등장하는 이름만 배열로.
        투자자문사·자산운용사·사모펀드·행동주의 펀드(예: 얼라인파트너스 같은 곳)·
        정부기관·애널리스트·증권사처럼 뉴스에 등장은 하지만 그 자체가 매매 가능한
        상장 종목이 아닌 이름은 절대 넣지 마라. 없으면 빈 배열.

각 기사에는 제목과 함께 원문 일부(크롤링된 본문, 잘려있거나 광고 문구가 섞여있을 수 있음)가
주어진다. 본문이 비어있는 기사는 제목만 보고 판단하라. 과장하지 마라.

반드시 아래 JSON만 출력한다. 입력 순서와 동일한 개수로.
{"items":[{"i":0,"sector":"...","impact":"strong_positive|positive|neutral|negative|strong_negative","why":"...","insight":"...","tickers":["..."]}]}"""


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


def collect(market_group: str = "KR") -> list[dict]:
    return collect_kr()


def tag(items: list[dict]) -> list[dict]:
    """AI 1회 호출로 전체 기사에 맥락을 붙인다. 실패해도 기사 목록은 살아남는다.

    "AI 해설"용으로 원문을 그 자리에서 잠깐 읽어와 프롬프트에 넣지만, 원문 텍스트
    자체(_body)는 이 함수가 끝나기 전에 지워 스냅샷에 절대 남지 않게 한다."""
    if not items:
        return []
    _fetch_bodies(items)
    listing = "\n\n".join(
        f"{i}. 제목: {it['title']}\n본문 일부: {it.get('_body') or '(가져오지 못함)'}"
        for i, it in enumerate(items)
    )
    try:
        res = _call_json(TAGGER_SYS, listing, config.NEWSTAG_MODEL, max_tokens=16000)
    except (AIFailure, json.JSONDecodeError, ValueError) as e:
        print(f"[newsroom] 태깅 실패({e}) — 원문 링크만 발행")
        res = {}

    by_i = {int(x["i"]): x for x in res.get("items", []) if "i" in x}
    for i, it in enumerate(items):
        it.pop("_body", None)  # 원문은 프롬프트에만 쓰고 절대 저장하지 않는다
        t = by_i.get(i)
        if not t:
            continue
        it["sector"] = t.get("sector")
        it["impact"] = t.get("impact", "neutral")
        it["why"] = t.get("why")
        it["insight"] = t.get("insight")
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
        norm_index = {_norm(r["Name"]): {"code": r["Code"], "market": r["Market"], "name": r["Name"]}
                      for _, r in uni.iterrows()}
    except Exception as e:
        print(f"[newsroom] 종목 매칭용 유니버스 로드 실패({e}) — 이름만 표시")
        norm_index = {}

    # 먼저 이름 -> 매칭 결과만 전부 계산해둔다(가격 조회는 아직 안 함).
    name_matches: dict[str, dict | None] = {}
    for it in items:
        for name in (it.get("tickers") or []):
            if name not in name_matches:
                name_matches[name] = _match_name(name, norm_index)

    # 실제 가격 조회가 필요한 종목코드만 모아서 병렬로 한 번에 가져온다 —
    # 종목마다 순차로 조회하면(뉴스에 언급된 종목이 많을 때) 그만큼 쌓여서 느려진다
    # (2026-07-15 실서비스에서 순차 조회가 병목이었던 것으로 추정).
    codes = sorted({m["code"] for m in name_matches.values() if m})
    price_cache: dict[str, dict | None] = {}

    def _change(code: str) -> dict | None:
        df = prices.ohlcv(code, days=10, fast=True)
        if df is not None and len(df) >= 2:
            last, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
            return {"price": last, "change_pct": round((last / prev - 1) * 100, 2)} if prev else None
        return None

    if codes:
        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            for code, chg in zip(codes, ex.map(_change, codes)):
                price_cache[code] = chg

    for it in items:
        resolved = []
        for name in (it.get("tickers") or []):
            row = name_matches.get(name)
            if not row:
                resolved.append({"name": name, "code": None, "market": None, "change_pct": None})
                continue
            chg = price_cache.get(row["code"])
            # 화면엔 AI가 뽑은 약칭(예: "한국타이어") 대신 실제 상장명("한국타이어앤테크놀로지")을 보여준다.
            resolved.append({"name": row["name"], "code": row["code"], "market": row["market"],
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
