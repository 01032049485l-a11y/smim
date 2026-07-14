"""기술적 지표. 판단은 하지 않고 사실만 계산한다."""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    return line, signal, line - signal


def compute(df: pd.DataFrame) -> dict:
    """일봉 DataFrame(Open/High/Low/Close/Volume) -> 지표 사실 묶음"""
    if df is None or len(df) < 60:
        return {}
    c, v = df["Close"], df["Volume"]
    ma5, ma20, ma60 = c.rolling(5).mean(), c.rolling(20).mean(), c.rolling(60).mean()
    ma120 = c.rolling(120).mean() if len(df) >= 120 else ma60
    r = rsi(c)
    _, _, hist = macd(c)
    vol20 = v.rolling(20).mean()
    last = float(c.iloc[-1])
    hi52 = float(c.tail(250).max())
    lo52 = float(c.tail(250).min())

    return {
        "close": round(last),
        "change_1d_pct": round(float(c.pct_change().iloc[-1] * 100), 2),
        "change_5d_pct": round(float((last / c.iloc[-6] - 1) * 100), 2) if len(c) > 6 else None,
        "change_20d_pct": round(float((last / c.iloc[-21] - 1) * 100), 2) if len(c) > 21 else None,
        "ma5": round(float(ma5.iloc[-1])),
        "ma20": round(float(ma20.iloc[-1])),
        "ma60": round(float(ma60.iloc[-1])),
        "ma120": round(float(ma120.iloc[-1])),
        "above_ma20": bool(last > ma20.iloc[-1]),
        "above_ma60": bool(last > ma60.iloc[-1]),
        "golden_cross_20_60": bool(ma20.iloc[-1] > ma60.iloc[-1] and ma20.iloc[-2] <= ma60.iloc[-2]),
        "rsi14": round(float(r.iloc[-1]), 1),
        "macd_hist": round(float(hist.iloc[-1]), 2),
        "macd_turning_up": bool(hist.iloc[-1] > hist.iloc[-2] > hist.iloc[-3]) if len(hist) > 3 else False,
        "volume_ratio_vs_20d": round(float(v.iloc[-1] / vol20.iloc[-1]), 2) if vol20.iloc[-1] else None,
        "avg_trading_value_20d": int(float((c * v).rolling(20).mean().iloc[-1])),
        "pos_in_52w_range_pct": round((last - lo52) / (hi52 - lo52) * 100, 1) if hi52 > lo52 else None,
        "high_52w": round(hi52),
        "low_52w": round(lo52),
        "volatility_20d_pct": round(float(c.pct_change().tail(20).std() * 100), 2),
        "limit_up_yesterday": bool(c.pct_change().iloc[-1] > 0.28),
    }
