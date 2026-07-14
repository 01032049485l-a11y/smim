"""금융감독원 DART 오픈API.

네이버 HTML 스크래핑을 여기로 대체한다.
공식·무료·합법·안정. HTML 구조가 바뀌어도 안 죽는다.
"""
import io
import os
import json
import zipfile
import datetime as dt
import xml.etree.ElementTree as ET

import requests

import config

BASE = "https://opendart.fss.or.kr/api"
CORP_MAP = os.path.join(config.CACHE_DIR, "corp_codes.json")

# 리스크 게이트에서 잡아낼 공시 키워드 (자본 희석 / 부실 신호)
RISK_KEYWORDS = (
    "유상증자", "전환사채", "신주인수권부사채", "교환사채",
    "감자", "관리종목", "상장폐지", "거래정지", "횡령", "배임",
    "감사의견", "회생절차", "불성실공시",
)


def _get(path: str, **params) -> dict:
    params["crtfc_key"] = config.DART_API_KEY
    r = requests.get(f"{BASE}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def load_corp_codes(force: bool = False) -> dict:
    """종목코드(6자리) -> DART corp_code(8자리) 매핑. 주 1회만 갱신하면 충분."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    if os.path.exists(CORP_MAP) and not force:
        age = dt.datetime.now().timestamp() - os.path.getmtime(CORP_MAP)
        if age < 7 * 86400:
            with open(CORP_MAP, encoding="utf-8") as f:
                return json.load(f)
    try:
        r = requests.get(f"{BASE}/corpCode.xml",
                         params={"crtfc_key": config.DART_API_KEY}, timeout=60)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            xml = z.read(z.namelist()[0])
        root = ET.fromstring(xml)
        mapping = {}
        for item in root.iter("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            if stock and corp:
                mapping[stock] = corp
        with open(CORP_MAP, "w", encoding="utf-8") as f:
            json.dump(mapping, f)
        print(f"[dart] corp_code 매핑 갱신: {len(mapping)}건")
        return mapping
    except Exception as e:
        print(f"[dart] corp_code 갱신 실패({e}) → 기존 캐시 사용")
        if os.path.exists(CORP_MAP):
            with open(CORP_MAP, encoding="utf-8") as f:
                return json.load(f)
        return {}


def recent_filings(corp_code: str, days: int = 45) -> list[dict]:
    if not corp_code:
        return []
    end = dt.date.today()
    bgn = end - dt.timedelta(days=days)
    try:
        res = _get("list.json", corp_code=corp_code,
                   bgn_de=bgn.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d"),
                   page_count=50)
        if res.get("status") != "000":
            return []
        return [{"date": i["rcept_dt"], "title": i["report_nm"],
                 "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={i['rcept_no']}"}
                for i in res.get("list", [])]
    except Exception:
        return []


def risk_flags(filings: list[dict]) -> list[str]:
    """공시 제목에서 위험 신호를 뽑는다. 하나라도 걸리면 발행 제외."""
    hits = []
    for f in filings:
        for kw in RISK_KEYWORDS:
            if kw in f["title"] and kw not in hits:
                hits.append(kw)
    return hits


def company_profile(corp_code: str) -> dict:
    """기업개황(company.json)에서 홈페이지 주소만 뽑는다.
    실패·미제출이면 빈 dict → 렌더러가 모노그램 타일로 자연스럽게 대체한다."""
    if not corp_code:
        return {}
    try:
        res = _get("company.json", corp_code=corp_code)
        if res.get("status") != "000":
            return {}
        return {"homepage": (res.get("hm_url") or "").strip()}
    except Exception:
        return {}


def key_financials(corp_code: str) -> dict:
    """최근 사업연도 연결 실적 + YoY. 실패하면 빈 dict (없으면 없는 대로 간다)."""
    if not corp_code:
        return {}
    year = dt.date.today().year - 1
    for y in (year, year - 1):
        try:
            res = _get("fnlttSinglAcntAll.json", corp_code=corp_code,
                       bsns_year=str(y), reprt_code="11011", fs_div="CFS")
            if res.get("status") != "000":
                continue
            want = {"매출액": "revenue", "영업이익": "operating_profit",
                    "당기순이익": "net_income", "자본총계": "equity", "부채총계": "liabilities"}
            out = {"fiscal_year": y}
            for row in res.get("list", []):
                nm = row.get("account_nm", "").strip()
                if nm in want:
                    cur = row.get("thstrm_amount", "").replace(",", "")
                    prv = row.get("frmtrm_amount", "").replace(",", "")
                    try:
                        cur_v, prv_v = int(cur), int(prv)
                    except ValueError:
                        continue
                    k = want[nm]
                    out[k] = cur_v
                    if prv_v:
                        out[f"{k}_yoy_pct"] = round((cur_v - prv_v) / abs(prv_v) * 100, 1)
            if out.get("equity") and out.get("liabilities"):
                out["debt_ratio_pct"] = round(out["liabilities"] / out["equity"] * 100, 1)
            return out
        except Exception:
            continue
    return {}
