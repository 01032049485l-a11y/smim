"""정적 사이트 빌더. Node 툴체인 0개. 파이썬이 HTML까지 직접 뽑는다."""
import os
import re
import json
import glob
import shutil
import datetime as dt
from collections import defaultdict
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

import config
from pipeline import ledger, chart

HERE = os.path.dirname(os.path.abspath(__file__))
env = Environment(
    loader=FileSystemLoader(os.path.join(HERE, "templates")),
    autoescape=select_autoescape(["html"]),
)

VERDICT_KO = {"STRONG_BUY": "강력 매수 추천", "BUY": "매수 추천", "WATCH": "관찰 대상"}
STATUS_KO = {"new": "신규 편입", "holding": "관찰 중", "target_hit": "목표 도달",
             "stopped": "손절 도달", "expired": "보유기간 만료"}


def _money(v):
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def _eok(v, market_group="KR"):
    """금액 표시. 한국은 억/조원, 미국은 K/M/B 달러 — 재무 숫자는 이렇게 써야 읽힌다."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if market_group == "US":
        if abs(v) >= 1e9:
            return f"${v/1e9:,.2f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:,.0f}M"
        return f"${v:,.0f}"
    if abs(v) >= 1e12:
        return f"{v/1e12:,.2f}조원"
    if abs(v) >= 1e8:
        return f"{v/1e8:,.0f}억원"
    return f"{v:,.0f}원"


def _money_cur(v, market_group="KR"):
    """편입가 등 종가성 금액 — 미국은 $, 한국은 원."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "—"
    return f"${n:,}" if market_group == "US" else f"{n:,}원"


def _pct(v):
    return "—" if v is None else f"{v:+.2f}%"


def _sign(v):
    if v is None:
        return "flat"
    return "rise" if v > 0 else "fall" if v < 0 else "flat"


env.filters["money"] = _money
env.filters["eok"] = _eok
env.filters["moneycur"] = _money_cur
env.filters["pct"] = _pct
env.filters["sign"] = _sign
env.globals["verdict_ko"] = lambda v: VERDICT_KO.get(v, v)
env.globals["status_ko"] = lambda v: STATUS_KO.get(v, v)
env.globals["chart_svg"] = lambda s, ep=None, ed=None: Markup(chart.render(s or {}, ep, ed))
env.globals["chart_spark"] = lambda c, w=96, h=26: Markup(chart.sparkline(c or [], w, h))
env.globals["chart_legend"] = lambda: Markup(chart.legend())
env.globals["now_year"] = dt.date.today().year
env.globals["mono1"] = lambda n: (n or "?")[0]
SIG_KO = {"positive": "긍정", "negative": "부정", "neutral": "중립"}
env.globals["sig_ko"] = lambda v: SIG_KO.get(v, "중립")

MARKET_FLAG = {"KOSPI": "KR", "KOSDAQ": "KR", "NASDAQ": "US", "NYSE": "US", "KR": "KR", "US": "US"}

# 이모지 국기는 OS·폰트에 따라 깨지거나(윈도우 다수 환경에서 "KR"/"US" 문자로만 보임)
# 아예 안 나올 수 있어, 어떤 환경에서도 동일하게 보이도록 SVG를 직접 그린다.
_FLAG_SVG = {
    # 4괘(건곤감리)까지 갖춘 정식 태극기. 좌상 건(乾,모두 실선)·우상 감(坎,가운데만 실선)·
    # 좌하 리(離,가운데만 끊김)·우하 곤(坤,모두 끊김) — 실제 태극기와 같은 배치.
    # 각 괘는 자기 중심을 기준으로 회전시켜 태극(12,8)을 향하게 하고(막대가 중심선과 수직),
    # 태극 원 자체는 시계방향 90도 회전시킨다.
    "KR": (
        '<svg class="fico" viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="24" height="16" rx="2" fill="#fff"/>'
        '<g fill="#000">'
        '<g transform="rotate(-57.4 4.5 3.2)">'          # 좌상 건(乾)
        '<rect x="1.8" y="1.4" width="5.4" height="0.8"/>'
        '<rect x="1.8" y="2.8" width="5.4" height="0.8"/>'
        '<rect x="1.8" y="4.2" width="5.4" height="0.8"/>'
        '</g>'
        '<g transform="rotate(57.4 19.5 3.2)">'          # 우상 감(坎)
        '<rect x="16.8" y="1.4" width="2.05" height="0.8"/><rect x="20.15" y="1.4" width="2.05" height="0.8"/>'
        '<rect x="16.8" y="2.8" width="5.4" height="0.8"/>'
        '<rect x="16.8" y="4.2" width="2.05" height="0.8"/><rect x="20.15" y="4.2" width="2.05" height="0.8"/>'
        '</g>'
        '<g transform="rotate(57.4 4.5 12.8)">'          # 좌하 리(離)
        '<rect x="1.8" y="11.0" width="5.4" height="0.8"/>'
        '<rect x="1.8" y="12.4" width="2.05" height="0.8"/><rect x="5.15" y="12.4" width="2.05" height="0.8"/>'
        '<rect x="1.8" y="13.8" width="5.4" height="0.8"/>'
        '</g>'
        '<g transform="rotate(-57.4 19.5 12.8)">'        # 우하 곤(坤)
        '<rect x="16.8" y="11.0" width="2.05" height="0.8"/><rect x="20.15" y="11.0" width="2.05" height="0.8"/>'
        '<rect x="16.8" y="12.4" width="2.05" height="0.8"/><rect x="20.15" y="12.4" width="2.05" height="0.8"/>'
        '<rect x="16.8" y="13.8" width="2.05" height="0.8"/><rect x="20.15" y="13.8" width="2.05" height="0.8"/>'
        '</g>'
        '</g>'
        '<g transform="rotate(90 12 8)">'                # 태극(중앙 원) 시계방향 90도
        '<path d="M12 3.8a4.2 4.2 0 0 1 0 8.4 2.1 2.1 0 0 1 0-4.2 2.1 2.1 0 0 0 0-4.2z" fill="#0047a0"/>'
        '<path d="M12 12.2a4.2 4.2 0 0 1 0-8.4 2.1 2.1 0 0 1 0 4.2 2.1 2.1 0 0 0 0 4.2z" fill="#cd2e3a"/>'
        '</g>'
        '</svg>'
    ),
    "US": (
        '<svg class="fico" viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="24" height="16" rx="2" fill="#fff"/>'
        '<g fill="#B22234">'
        '<rect y="0" width="24" height="1.23"/><rect y="2.46" width="24" height="1.23"/>'
        '<rect y="4.92" width="24" height="1.23"/><rect y="7.38" width="24" height="1.23"/>'
        '<rect y="9.84" width="24" height="1.23"/><rect y="12.3" width="24" height="1.23"/>'
        '<rect y="14.76" width="24" height="1.23"/></g>'
        '<rect width="10" height="8.6" fill="#3C3B6E"/>'
        '</svg>'
    ),
}


def _flag_svg(mkt):
    code = MARKET_FLAG.get(mkt, "KR")
    return Markup(_FLAG_SVG[code])


env.globals["flag_svg"] = _flag_svg


def _stock_logo(h):
    """DART 기업개황의 홈페이지 주소(hm_url)에서 도메인을 뽑아 파비콘을 가져온다.
    homepage가 없으면(데모 데이터, 미등록 회사 등) None → 템플릿이 모노그램만 보여준다."""
    url = (h or {}).get("homepage") or ""
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    domain = urlparse(url).netloc.split(":")[0].strip()
    if not domain:
        return None
    return f"https://www.google.com/s2/favicons?sz=128&domain={domain}"


env.globals["stock_logo"] = _stock_logo


def load_snapshots(market_group: str = "KR"):
    """한국/미국은 완전히 독립된 스냅샷 디렉터리를 쓴다."""
    snap_dir = os.path.join(config.SNAPSHOT_DIR, market_group.lower())
    out = []
    for p in sorted(glob.glob(os.path.join(snap_dir, "*.json")), reverse=True):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def _write(rel, html):
    path = os.path.join(config.SITE_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def build_site():
    snaps_kr = load_snapshots("KR")
    snaps_us = load_snapshots("US")
    if not snaps_kr and not snaps_us:
        print("[build] 스냅샷 없음 — 빌드 중단")
        return

    os.makedirs(config.SITE_DIR, exist_ok=True)
    static_dst = os.path.join(config.SITE_DIR, "assets")
    if os.path.isdir(static_dst):
        shutil.rmtree(static_dst)
    shutil.copytree(os.path.join(HERE, "static"), static_dst)

    latest_kr = snaps_kr[0] if snaps_kr else None
    latest_us = snaps_us[0] if snaps_us else None
    latest = latest_kr or latest_us  # 한국이 원조 시장이라 있으면 우선
    mk = (latest or {}).get("market", {}) or {}
    book = sorted(ledger.load(), key=lambda b: b["exit_date"], reverse=True)
    all_snaps = sorted(snaps_kr + snaps_us, key=lambda s: s["date"], reverse=True)

    ctx = {
        "cfg": config,
        "stats": ledger.stats(),
        "archive": all_snaps[:200],
        "indices": mk.get("indices", []),
        "breadth": mk,
        "latest": latest,
    }

    def render(tpl, rel, **kw):
        _write(rel, env.get_template(tpl).render(**{**ctx, **kw}))

    # 리포트 (최신 = index, 한국/미국 탭 전환)
    render("report.html", "index.html", s=latest, s_kr=latest_kr, s_us=latest_us,
           is_latest=True, page="report")
    for s in snaps_kr:
        smk = s.get("market", {}) or {}
        render("report.html", f"reports/kr/{s['date']}/index.html", s=s, market_group="KR",
               is_latest=False, page="report", indices=smk.get("indices", []), breadth=smk)
    for s in snaps_us:
        smk = s.get("market", {}) or {}
        render("report.html", f"reports/us/{s['date']}/index.html", s=s, market_group="US",
               is_latest=False, page="report", indices=smk.get("indices", []), breadth=smk)

    render("market.html", "market/index.html", s=latest, page="market")
    render("newsroom.html", "newsroom/index.html", s=latest, s_kr=latest_kr, s_us=latest_us,
           page="news")
    render("watchlist.html", "watchlist/index.html", s_kr=latest_kr, s_us=latest_us, page="watchlist")
    render("archive.html", "archive/index.html", page="archive")
    render("performance.html", "performance/index.html", book=book, page="track")
    render("methodology.html", "methodology/index.html", page="method")

    # 종목 페이지 (한국·미국 통합 — 종목코드/티커로 유일)
    hist = defaultdict(list)
    for s in snaps_kr + snaps_us:
        mg = s.get("market_group", "KR")
        for h in s.get("new_entries", []) + s.get("holdings", []) + s.get("exits", []):
            hist[h["code"]].append({"date": s["date"], "item": h, "market_group": mg})
    for code, rows in hist.items():
        rows.sort(key=lambda r: r["date"], reverse=True)
        cur = rows[0]["item"]
        closed = [b for b in book if b["code"] == code]
        render("stock.html", f"stock/{code}/index.html", code=code, name=cur["name"],
               cur=cur, rows=rows, closed=closed, page="")

    # 원본 데이터 공개 (검증 가능성 = 신뢰). 한국/미국이 같은 날짜를 쓸 수 있어 시장 접두사를 붙인다.
    dd = os.path.join(config.SITE_DIR, "data")
    os.makedirs(dd, exist_ok=True)
    for s in snaps_kr + snaps_us:
        mg = s.get("market_group", "KR").lower()
        with open(os.path.join(dd, f"{mg}-{s['date']}.json"), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)

    _write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {config.SITE_URL}/sitemap.xml\n")

    urls = ["/", "/market/", "/newsroom/", "/watchlist/", "/archive/", "/performance/", "/methodology/"]
    urls += [f"/reports/kr/{s['date']}/" for s in snaps_kr]
    urls += [f"/reports/us/{s['date']}/" for s in snaps_us]
    urls += [f"/stock/{c}/" for c in hist]
    _write("sitemap.xml",
           '<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(f"  <url><loc>{config.SITE_URL}{u}</loc></url>" for u in urls)
           + "\n</urlset>")

    # RSS — 한국/미국 통합, 최신 30건
    items = ""
    for s in all_snaps[:30]:
        names = ", ".join(h["name"] for h in s.get("new_entries", [])) or "신규 편입 없음"
        mg = s.get("market_group", "KR")
        items += (f"  <item><title>[{mg}] {escape(s['date'])} Watchlist</title>"
                  f"<link>{config.SITE_URL}/reports/{mg.lower()}/{s['date']}/</link>"
                  f"<guid>{config.SITE_URL}/reports/{mg.lower()}/{s['date']}/</guid>"
                  f"<description>{escape('신규 편입: ' + names)}</description></item>\n")
    _write("feed.xml",
           '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>\n'
           f"  <title>SMIM — {escape(config.SITE_TAGLINE)}</title>\n"
           f"  <link>{config.SITE_URL}/</link>\n"
           f"  <description>{escape(config.SITE_DESC)}</description>\n{items}"
           "</channel></rss>")

    print(f"[build] 리포트 KR {len(snaps_kr)}·US {len(snaps_us)} · 종목 {len(hist)} · 페이지 {len(urls)}")


if __name__ == "__main__":
    build_site()
