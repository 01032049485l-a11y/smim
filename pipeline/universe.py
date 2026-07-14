"""AI를 부르기 전에, 룰로 먼저 자른다.

AI 호출은 비싸고 느리다. 그리고 AI는 후하다.
그래서 "명백히 아닌 것"은 규칙으로 먼저 떨어뜨린다.
"""
import time

import config
from pipeline import indicators
from pipeline.sources import prices, dart, us_filings


def prescreen(market_group: str = "KR", limit: int = None) -> list[dict]:
    """전 종목 스캔 → 중기 상승 구조를 갖춘 후보만 남긴다. market_group: 'KR' | 'US'."""
    is_us = market_group == "US"
    uni = prices.load_universe(market_group)
    if limit:
        uni = uni.head(limit)
    print(f"[universe] 스캔 대상({market_group}) {len(uni)}종목")

    min_trading_value = config.MIN_AVG_TRADING_VALUE_US if is_us else config.MIN_AVG_TRADING_VALUE_KR
    max_candidates = config.MAX_CANDIDATES_TO_AI_US if is_us else config.MAX_CANDIDATES_TO_AI_KR

    candidates = []
    for i, row in uni.iterrows():
        code, name = row["Code"], row["Name"]
        df = prices.ohlcv(code)
        tech = indicators.compute(df)
        if not tech:
            continue

        # 유동성: 못 사고 못 파는 종목은 아무리 좋아도 무의미
        if (tech["avg_trading_value_20d"] or 0) < min_trading_value:
            continue
        # 어제 상한가 → 추격매수 유도 금지 (미국은 상하한가 제도가 없어 KR에만 적용)
        if not is_us and tech["limit_up_yesterday"]:
            continue
        # 중기 상승 구조 최소 요건
        if not tech["above_ma60"]:
            continue
        if not (tech["above_ma20"] or tech["golden_cross_20_60"]):
            continue
        # 과열 배제 (중기 관점에서 RSI 78 넘는 건 늦었다)
        if tech["rsi14"] >= 78:
            continue
        # 이미 52주 고점 근처 100% + 20일 30% 급등 = 상투 위험
        if (tech["change_20d_pct"] or 0) > 35:
            continue

        score = _rule_score(tech)
        candidates.append({
            "code": code, "name": name, "market": row["Market"],
            "market_group": market_group,
            "market_cap": int(row["Marcap"]) if "Marcap" in row and not is_us else None,
            "tech": tech, "rule_score": score,
        })

        if i % 100 == 0:
            print(f"[universe] {i}/{len(uni)} … 후보 {len(candidates)}")
        time.sleep(0.05)

    candidates.sort(key=lambda c: c["rule_score"], reverse=True)
    top = candidates[:max_candidates]
    print(f"[universe] 룰 통과({market_group}) {len(candidates)} → AI 후보 {len(top)}")
    return top


def _rule_score(t: dict) -> float:
    """AI에게 넘길 순서를 정하는 용도. 판단이 아니라 정렬 기준일 뿐."""
    s = 0.0
    s += 15 if t["golden_cross_20_60"] else 0
    s += 10 if t["macd_turning_up"] else 0
    s += max(0, 20 - abs(t["rsi14"] - 58))          # RSI 58 근처가 가장 이상적
    s += min(15, (t["volume_ratio_vs_20d"] or 1) * 5)
    s += min(15, max(0, (t["change_20d_pct"] or 0)) * 0.6)
    s += 10 if 40 <= (t["pos_in_52w_range_pct"] or 0) <= 85 else 0
    s -= min(10, t["volatility_20d_pct"])            # 과도한 변동성은 감점
    return round(s, 1)


def risk_gate(code: str, corp_map: dict, market_group: str = "KR") -> tuple[bool, list[str], list[dict]]:
    """발행 직전 최종 관문. 하나라도 걸리면 무조건 제외.

    반환: (통과여부, 위험플래그, 최근공시목록)
    KR은 DART corp_code, US는 SEC CIK를 corp_map에서 찾는다.
    """
    key = corp_map.get(code, "")
    if market_group == "US":
        filings = us_filings.recent_filings(key, days=45)
        flags = us_filings.risk_flags(filings)
    else:
        filings = dart.recent_filings(key, days=45)
        flags = dart.risk_flags(filings)
    return (len(flags) == 0), flags, filings[:5]
