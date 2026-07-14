"""시세 · 종목 리스트 (FinanceDataReader)

원칙: 외부 호출은 언제든 실패한다고 가정한다.
      종목 리스트는 캐시를 저장소에 커밋해두고, 실패하면 캐시로 살아남는다.
"""
import os
import time
import datetime as dt

import pandas as pd
import FinanceDataReader as fdr

import config

UNIVERSE_CACHE_KR = os.path.join(config.CACHE_DIR, "universe.csv")
UNIVERSE_CACHE_US = os.path.join(config.CACHE_DIR, "universe_us.csv")


def _is_excluded_kr(name: str) -> bool:
    return any(p in name for p in config.EXCLUDE_NAME_PATTERNS) or name.endswith("우")


def _is_excluded_us(name: str) -> bool:
    return any(p in name for p in config.EXCLUDE_NAME_PATTERNS_US)


def _load_universe_kr() -> pd.DataFrame:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    try:
        df = fdr.StockListing("KRX")
        df = df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy()
        need = {"Code", "Name", "Market", "Marcap"}
        if not need.issubset(df.columns):
            raise ValueError(f"예상 컬럼 없음: {list(df.columns)}")
        df = df[["Code", "Name", "Market", "Marcap"]].dropna()
        df.to_csv(UNIVERSE_CACHE_KR, index=False)
        print(f"[prices] 유니버스 갱신(KR): {len(df)}종목")
    except Exception as e:
        print(f"[prices] 유니버스 조회 실패(KR, {e}) → 캐시 사용")
        if not os.path.exists(UNIVERSE_CACHE_KR):
            raise RuntimeError("유니버스 캐시도 없음. 파이프라인 중단.")
        df = pd.read_csv(UNIVERSE_CACHE_KR, dtype={"Code": str})

    df["Code"] = df["Code"].astype(str).str.zfill(6)
    df = df[~df["Name"].apply(_is_excluded_kr)]
    df = df[df["Marcap"] >= config.MIN_MARKET_CAP]
    return df.reset_index(drop=True)


def _load_universe_us() -> pd.DataFrame:
    """나스닥+뉴욕증권거래소. 이 리스팅엔 시가총액 컬럼이 없어 1차 필터에서 시총 조건은 적용하지 않는다."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    try:
        parts = []
        for exch in ("NASDAQ", "NYSE"):
            d = fdr.StockListing(exch)
            need = {"Symbol", "Name"}
            if not need.issubset(d.columns):
                raise ValueError(f"예상 컬럼 없음({exch}): {list(d.columns)}")
            d = d[["Symbol", "Name", "Industry"]].copy() if "Industry" in d.columns else d[["Symbol", "Name"]].copy()
            d["Market"] = exch
            parts.append(d)
        df = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["Symbol"])
        if "Industry" in df.columns:
            df = df.dropna(subset=["Industry"])  # 산업분류 없는 행은 ETF·펀드일 가능성이 높음
        df = df.rename(columns={"Symbol": "Code"})[["Code", "Name", "Market"]].dropna()
        df.to_csv(UNIVERSE_CACHE_US, index=False)
        print(f"[prices] 유니버스 갱신(US): {len(df)}종목")
    except Exception as e:
        print(f"[prices] 유니버스 조회 실패(US, {e}) → 캐시 사용")
        if not os.path.exists(UNIVERSE_CACHE_US):
            raise RuntimeError("US 유니버스 캐시도 없음. 파이프라인 중단.")
        df = pd.read_csv(UNIVERSE_CACHE_US, dtype={"Code": str})

    df = df[~df["Name"].apply(_is_excluded_us)]
    return df.reset_index(drop=True)


def load_universe(market_group: str = "KR") -> pd.DataFrame:
    """market_group: 'KR'(코스피+코스닥) | 'US'(나스닥+NYSE). 실패 시 커밋된 캐시로 폴백."""
    if market_group == "US":
        return _load_universe_us()
    return _load_universe_kr()


def ohlcv(code: str, days: int = 400) -> pd.DataFrame | None:
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    for attempt in range(3):
        try:
            df = fdr.DataReader(code, start)
            if df is None or df.empty:
                return None
            return df
        except Exception:
            time.sleep(1.2 * (attempt + 1))
    return None


def last_close(code: str) -> float | None:
    df = ohlcv(code, days=12)
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])


def series(code: str, n: int = 90) -> dict:
    """차트용 최근 n거래일 시계열. 스냅샷에 그대로 동결된다."""
    df = ohlcv(code, days=int(n * 1.9) + 40)
    if df is None or df.empty:
        return {}
    df = df.tail(n)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "close": [float(x) for x in df["Close"]],
        "volume": [float(x) for x in df["Volume"]],
    }


def kospi_series(days: int = 400) -> pd.DataFrame | None:
    try:
        start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        return fdr.DataReader("KS11", start)
    except Exception:
        return None
