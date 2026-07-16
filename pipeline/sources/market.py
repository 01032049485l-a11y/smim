"""마켓 개요 — 지수, 시장 폭, 섹터 흐름.

종목만 나열하면 블로그다. 시장 맥락이 있어야 리서치다.
"""
import datetime as dt
import math

import FinanceDataReader as fdr

from pipeline.sources.prices import _with_timeout

INDICES = [
    ("KS11", "코스피", "KOSPI"),
    ("KQ11", "코스닥", "KOSDAQ"),
    ("USD/KRW", "원/달러", "USDKRW"),
]


def _trend(closes: list[float]) -> str:
    """상승세 / 하락세 / 보합 — 5일 이동 방향으로 판정."""
    if len(closes) < 6:
        return "flat"
    chg = closes[-1] / closes[-6] - 1
    if chg > 0.01:
        return "up"
    if chg < -0.01:
        return "down"
    return "flat"


TREND_LABEL = {"up": "상승세", "down": "하락세", "flat": "보합권"}


def _quote(symbol: str, label: str, ticker: str) -> dict | None:
    try:
        start = (dt.date.today() - dt.timedelta(days=45)).isoformat()
        df = _with_timeout(15, fdr.DataReader, symbol, start)
        if df is None or len(df) < 2:
            return None
        # 휴장일 등으로 결측치가 섞이면 NaN이 그대로 JSON에 박혀 브라우저에서 파싱이 깨진다.
        closes = [float(x) for x in df["Close"].tail(30) if not math.isnan(float(x))]
        if len(closes) < 2:
            return None
        last, prev = closes[-1], closes[-2]
        t = _trend(closes)
        return {
            "label": label, "ticker": ticker,
            "value": round(last, 2),
            "change": round(last - prev, 2),
            "change_pct": round((last / prev - 1) * 100, 2),
            "trend": t, "trend_label": TREND_LABEL[t],
            "series": [round(c, 2) for c in closes],
        }
    except Exception:
        return None


def overview() -> list[dict]:
    return [q for q in (_quote(s, l, t) for s, l, t in INDICES) if q]


def breadth_and_sectors() -> dict:
    """등락 종목 수 + 업종별 평균 등락률. 지수보다 정직한 체감 지표."""
    try:
        df = _with_timeout(20, fdr.StockListing, "KRX")
        df = df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy()
        col = "ChagesRatio" if "ChagesRatio" in df.columns else None
        if not col:
            return {}
        ch = df[col].dropna()
        up, down = int((ch > 0).sum()), int((ch < 0).sum())
        flat = int((ch == 0).sum())
        total = up + down + flat or 1

        sectors = []
        if "Sector" in df.columns:
            g = (df.dropna(subset=["Sector"])
                   .groupby("Sector")[col]
                   .agg(["mean", "count"]))
            g = g[g["count"] >= 5].sort_values("mean", ascending=False)
            for name, row in list(g.head(6).iterrows()) + list(g.tail(6).iterrows()):
                sectors.append({"name": name, "change_pct": round(float(row["mean"]), 2),
                                "count": int(row["count"])})
            seen, uniq = set(), []
            for s in sectors:
                if s["name"] in seen:
                    continue
                seen.add(s["name"])
                uniq.append(s)
            sectors = uniq

        return {
            "up": up, "down": down, "flat": flat,
            "up_ratio": round(up / total * 100, 1),
            "mood": "위험선호" if up > down * 1.4 else "위험회피" if down > up * 1.4 else "혼조",
            "sectors": sectors,
        }
    except Exception:
        return {}
