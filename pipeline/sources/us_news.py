"""Yahoo Finance 뉴스 RSS — 미국 종목 뉴스. 네이버 뉴스 API의 미국판.

저작권 원칙은 동일: 제목 + 발행일 + 원문 링크만 보관한다. 본문은 절대 저장·재배포하지 않는다.
무료, 키 발급 불필요 — functions/api/quotes.js가 이미 Yahoo Finance를 쓰고 있는 것과 같은 소스.
"""
import html
import email.utils
import xml.etree.ElementTree as ET

import requests

import config

RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _parse_rss(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = item.findtext("pubDate") or ""
        if not title or not link:
            continue
        try:
            pub = email.utils.parsedate_to_datetime(pub_raw)
            published = pub.astimezone(config.KST).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            continue
        out.append({"title": html.unescape(title), "url": link, "published": published})
    return out


def for_stock(ticker: str, display: int = 8) -> list[dict]:
    try:
        r = requests.get(RSS_URL, params={"s": ticker, "region": "US", "lang": "en-US"},
                         headers=_HEADERS, timeout=12)
        r.raise_for_status()
    except Exception as e:
        print(f"[us_news] 검색 실패 '{ticker}': {e}")
        return []
    return _parse_rss(r.text)[:display]


def market_headlines(display: int = 10) -> list[dict]:
    """시장 전반 헤드라인 — S&P 500 지수 피드로 대체."""
    return for_stock("^GSPC", display=display)
