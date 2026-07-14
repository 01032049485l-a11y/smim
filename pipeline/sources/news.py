"""네이버 뉴스 오픈API.

저작권 원칙: 기사 본문은 절대 저장·재배포하지 않는다.
             제목 + 발행일 + 원문 링크만 보관하고, 해석은 AI가 자기 말로 쓴다.
"""
import html
import re
import datetime as dt

import requests

import config

ENDPOINT = "https://openapi.naver.com/v1/search/news.json"


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _headers() -> dict:
    return {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }


def search(query: str, display: int = 10, days: int = 14) -> list[dict]:
    try:
        r = requests.get(ENDPOINT, headers=_headers(),
                         params={"query": query, "display": display, "sort": "date"},
                         timeout=12)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        print(f"[news] 검색 실패 '{query}': {e}")
        return []

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out = []
    for it in items:
        try:
            pub = dt.datetime.strptime(it["pubDate"], "%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            continue
        if pub < cutoff:
            continue
        out.append({
            "title": _clean(it["title"]),
            "url": it.get("originallink") or it.get("link"),
            "published": pub.astimezone(config.KST).strftime("%Y-%m-%d"),
        })
    return out


def for_stock(name: str) -> list[dict]:
    """종목 뉴스: 일반 + 리스크 각도로 두 번 긁어서 확증편향을 구조적으로 막는다."""
    seen, merged = set(), []
    for q in (f"{name}", f"{name} 실적", f"{name} 리스크 우려"):
        for n in search(q, display=6):
            if n["url"] in seen:
                continue
            seen.add(n["url"])
            merged.append(n)
    return sorted(merged, key=lambda x: x["published"], reverse=True)[:8]


def market_headlines() -> list[dict]:
    seen, merged = set(), []
    for q in ("코스피 증시", "코스닥 시황", "한국 증시 전망"):
        for n in search(q, display=5, days=2):
            if n["url"] in seen:
                continue
            seen.add(n["url"])
            merged.append(n)
    return sorted(merged, key=lambda x: x["published"], reverse=True)[:10]
