"""SEC EDGAR 오픈 API — 미국 종목의 공시·재무. DART의 미국판.

공식·무료·키 발급 불필요. 대신 요청자를 식별할 User-Agent를 요구한다(SEC 정책).
DART와 완전히 동일한 반환 shape을 유지해 agents.py가 시장을 몰라도 되게 한다.
"""
import os
import json
import datetime as dt

import requests

import config

BASE_SUBMISSIONS = "https://data.sec.gov/submissions"
BASE_FACTS = "https://data.sec.gov/api/xbrl/companyfacts"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
TICKER_MAP_CACHE = os.path.join(config.CACHE_DIR, "sec_ticker_cik.json")

# 희석·지연공시·상장폐지 계열 폼타입 — DART의 키워드 리스크 게이트와 같은 역할
RISK_FORMS = ("S-1", "S-1/A", "S-3", "S-3/A", "S-3ASR", "NT 10-K", "NT 10-Q", "25-NSE", "15-12B")

# 임원 개인 지분거래 신고(Form 3/4/5) 등은 회사 차원의 공시가 아니라 노이즈라서 목록에서 뺀다
NOISE_FORMS = ("3", "4", "5", "3/A", "4/A", "5/A")


def _headers() -> dict:
    return {"User-Agent": config.SEC_USER_AGENT}


def _get(url: str) -> dict:
    r = requests.get(url, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def load_ticker_cik_map(force: bool = False) -> dict:
    """티커(대문자) → 10자리 CIK 문자열. 주 1회만 갱신하면 충분."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    if os.path.exists(TICKER_MAP_CACHE) and not force:
        age = dt.datetime.now().timestamp() - os.path.getmtime(TICKER_MAP_CACHE)
        if age < 7 * 86400:
            with open(TICKER_MAP_CACHE, encoding="utf-8") as f:
                return json.load(f)
    try:
        raw = _get(TICKER_MAP_URL)
        mapping = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in raw.values()}
        with open(TICKER_MAP_CACHE, "w", encoding="utf-8") as f:
            json.dump(mapping, f)
        print(f"[us_filings] ticker-CIK 매핑 갱신: {len(mapping)}건")
        return mapping
    except Exception as e:
        print(f"[us_filings] ticker-CIK 갱신 실패({e}) → 기존 캐시 사용")
        if os.path.exists(TICKER_MAP_CACHE):
            with open(TICKER_MAP_CACHE, encoding="utf-8") as f:
                return json.load(f)
        return {}


def recent_filings(cik: str, days: int = 45) -> list[dict]:
    if not cik:
        return []
    try:
        data = _get(f"{BASE_SUBMISSIONS}/CIK{cik}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        out = []
        for form, date, acc, doc in zip(forms, dates, accs, docs):
            if date < cutoff or form in NOISE_FORMS:
                continue
            acc_nodash = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
            out.append({"date": date.replace("-", ""), "title": form, "url": url})
        return out
    except Exception:
        return []


def risk_flags(filings: list[dict]) -> list[str]:
    """폼타입 기반 리스크 게이트. 하나라도 걸리면 발행 제외 (DART risk_flags와 동일 역할)."""
    hits = []
    for f in filings:
        if f["title"] in RISK_FORMS and f["title"] not in hits:
            hits.append(f["title"])
    return hits


def key_financials(cik: str) -> dict:
    """최근 회계연도(10-K, FY) 연결 실적 + YoY. DART key_financials와 동일한 키로 정규화."""
    if not cik:
        return {}
    try:
        data = _get(f"{BASE_FACTS}/CIK{cik}.json")
        gaap = data.get("facts", {}).get("us-gaap", {})

        def annual_series(concept_names):
            """여러 개념명 후보 중, 가장 최근 데이터를 가진 것을 고른다.
            기업이 회계기준 변경으로 태그를 갈아탄 경우(예: Revenues → RevenueFromContract...)
            첫 번째로 매치되는 개념을 무조건 쓰면 오래전에 버려진 태그를 붙잡을 수 있다."""
            best, best_end = [], ""
            for name in concept_names:
                node = gaap.get(name)
                if not node:
                    continue
                units = node.get("units", {}).get("USD", [])
                annual = [u for u in units if u.get("form") == "10-K" and u.get("fp") == "FY" and u.get("fy")]
                if not annual:
                    continue
                # 같은 회계연도가 여러 번(정정·재표시) 나오면 가장 나중 값으로 덮어써 1건만 남긴다
                by_fy = {}
                for u in sorted(annual, key=lambda u: (u["fy"], u.get("end", ""))):
                    by_fy[u["fy"]] = u
                series = [by_fy[k] for k in sorted(by_fy)]
                latest_end = series[-1].get("end", "")
                if latest_end > best_end:
                    best, best_end = series, latest_end
            return best

        rev = annual_series(["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"])
        op = annual_series(["OperatingIncomeLoss"])
        ni = annual_series(["NetIncomeLoss"])
        liab = annual_series(["Liabilities"])
        eq = annual_series(["StockholdersEquity"])
        if not rev and not ni:
            return {}

        out = {}
        if rev:
            out["fiscal_year"] = rev[-1]["fy"]
            out["revenue"] = rev[-1]["val"]
            if len(rev) >= 2 and rev[-2]["val"]:
                out["revenue_yoy_pct"] = round((rev[-1]["val"] - rev[-2]["val"]) / abs(rev[-2]["val"]) * 100, 1)
        if op:
            out.setdefault("fiscal_year", op[-1]["fy"])
            out["operating_profit"] = op[-1]["val"]
            if len(op) >= 2 and op[-2]["val"]:
                out["operating_profit_yoy_pct"] = round((op[-1]["val"] - op[-2]["val"]) / abs(op[-2]["val"]) * 100, 1)
        if ni:
            out.setdefault("fiscal_year", ni[-1]["fy"])
            out["net_income"] = ni[-1]["val"]
        if liab and eq and eq[-1]["val"]:
            out["debt_ratio_pct"] = round(liab[-1]["val"] / eq[-1]["val"] * 100, 1)
        return out
    except Exception:
        return {}
