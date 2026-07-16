"""시세 · 종목 리스트 (FinanceDataReader)

원칙: 외부 호출은 언제든 실패한다고 가정한다.
      종목 리스트는 캐시를 저장소에 커밋해두고, 실패하면 캐시로 살아남는다.
"""
import os
import time
import datetime as dt
import concurrent.futures as cf

import pandas as pd
import FinanceDataReader as fdr

import config


def _with_timeout(timeout, fn, *args, **kwargs):
    """fdr.DataReader는 timeout 인자가 없어 네트워크가 응답 없이 멈추면 영원히 걸린다
    (2026-07-15 실제로 발행 파이프라인 전체가 멈춘 원인). 별도 스레드에서 실행하고
    시간 초과 시 포기한다 — 그 스레드는 못 죽이지만(파이썬 한계), shutdown(wait=False)로
    기다리지 않고 바로 넘어가 최소한 우리 쪽은 멈추지 않는다."""
    ex = cf.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout)
    finally:
        ex.shutdown(wait=False)

UNIVERSE_CACHE_KR = os.path.join(config.CACHE_DIR, "universe.csv")


def _is_excluded_kr(name: str) -> bool:
    return any(p in name for p in config.EXCLUDE_NAME_PATTERNS) or name.endswith("우")


def _load_universe_kr() -> pd.DataFrame:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    try:
        df = _with_timeout(30, fdr.StockListing, "KRX")
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


def load_universe(market_group: str = "KR") -> pd.DataFrame:
    """코스피+코스닥. 실패 시 저장소에 커밋된 캐시로 폴백. (미국 유니버스는 제거됨)"""
    return _load_universe_kr()


def ohlcv(code: str, days: int = 400, fast: bool = False) -> pd.DataFrame | None:
    """fast=True: 1차 스크리닝(수천 종목 병렬 스캔)용 — 실패해도 재시도 없이 바로 넘어간다.
    하루 스크리닝에서 종목 하나 놓치는 건 치명적이지 않다. 최종 후보에 오른 뒤엔
    fast=False(기본, 3회 재시도)로 다시 불러 신뢰도를 높인다."""
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    attempts = 1 if fast else 3
    timeout = 10 if fast else 20
    for attempt in range(attempts):
        try:
            df = _with_timeout(timeout, fdr.DataReader, code, start)
            if df is None or df.empty:
                return None
            return df
        except Exception:
            if not fast:
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
        return _with_timeout(15, fdr.DataReader, "KS11", start)
    except Exception:
        return None
