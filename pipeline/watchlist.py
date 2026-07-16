"""액티브 워치리스트 — SMIM의 심장.

"오늘의 추천 5개"가 아니라, 살아있는 12종목의 상태를 매일 갱신한다.
중기(일~주) 투자자는 매일 새 종목을 사는 게 아니라, 들고 있는 걸 지켜본다.
"""
import os
import json
import datetime as dt

import config
from pipeline.sources import prices

STATUS_LABEL = {
    "new": "신규 편입",
    "holding": "관찰 중",
    "target_hit": "목표 도달",
    "stopped": "손절 도달",
    "expired": "기간 만료",
}


def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _state_path(market_group: str) -> str:
    """한국/미국은 완전히 독립된 워치리스트 상태 파일을 쓴다."""
    return os.path.join(config.DATA_DIR, f"watchlist_{market_group.lower()}.json")


def load(market_group: str = "KR") -> list[dict]:
    path = _state_path(market_group)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(items: list[dict], market_group: str = "KR") -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(_state_path(market_group), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def _biz_days(start: str, end: dt.date) -> int:
    s = dt.date.fromisoformat(start)
    days = (end - s).days
    return max(0, int(days * 5 / 7))


def refresh(today: dt.date, market_group: str = "KR") -> tuple[list[dict], list[dict]]:
    """보유 종목 가격·상태 갱신. 반환: (계속 관찰, 오늘 편출)"""
    active, closed = [], []
    for h in load(market_group):
        px = prices.last_close(h["code"])
        if px is None:
            active.append(h)
            continue

        h["current_price"] = round(px)
        h["return_pct"] = round((px / h["entry_price"] - 1) * 100, 2)
        h["days_held"] = _biz_days(h["entry_date"], today)
        h["updated"] = today.isoformat()

        # 전 종목 공통 숫자가 아니라, 편입 당시 AI가 이 종목에 맞게 정한 값을 쓴다.
        # 값이 없는(과거) 항목은 더 보수적인 쪽(손절은 타이트하게, 목표는 낮게)으로 기본값을 잡는다.
        target = h.get("target_return_pct") or config.TAKE_PROFIT_RANGE[0]
        stop = h.get("stop_loss_pct") or config.STOP_LOSS_RANGE[1]

        if h["return_pct"] >= target:
            h["status"] = "target_hit"
        elif h["return_pct"] <= stop:
            h["status"] = "stopped"
        elif h["days_held"] >= config.MAX_HOLD_DAYS:
            h["status"] = "expired"
        else:
            h["status"] = "holding"

        if h["status"] in ("target_hit", "stopped", "expired"):
            h["exit_date"] = today.isoformat()
            h["exit_price"] = round(px)
            closed.append(h)
        else:
            active.append(h)

    return active, closed


def admit(active: list[dict], picks: list[dict], today: dt.date, market_group: str = "KR") -> list[dict]:
    """빈 자리만큼 신규 편입. 이미 들고 있는 종목은 중복 편입하지 않는다."""
    held = {h["code"] for h in active}
    max_holdings = config.MAX_HOLDINGS_KR
    max_new = config.MAX_NEW_PER_DAY_KR
    room = min(max_holdings - len(active), max_new)
    added = []
    for p in picks:
        if room <= 0:
            break
        if p["code"] in held:
            continue
        if p["judge"]["confidence"] < config.MIN_CONVICTION:
            continue
        if p["judge"]["verdict"] not in ("BUY", "STRONG_BUY"):
            continue
        added.append({
            "code": p["code"],
            "name": p["name"],
            "market": p["market"],
            "market_group": market_group,
            "homepage": p.get("homepage", ""),
            "entry_date": today.isoformat(),
            "entry_price": p["tech"]["close"],
            "current_price": p["tech"]["close"],
            "return_pct": 0.0,
            "days_held": 0,
            "status": "new",
            "verdict": p["judge"]["verdict"],
            "confidence": p["judge"]["confidence"],
            "target_return_pct": _clamp(p["judge"].get("target_return_pct"),
                                         *config.TAKE_PROFIT_RANGE, config.TAKE_PROFIT_RANGE[0]),
            "stop_loss_pct": _clamp(p["judge"].get("stop_loss_pct"),
                                    *config.STOP_LOSS_RANGE, config.STOP_LOSS_RANGE[1]),
            "horizon_days": p["judge"].get("horizon_days"),
            "invalidation": p["judge"].get("invalidation"),
            "thesis": p["judge"]["thesis"],
            "scorecard": p["judge"]["scorecard"],
            "bull_points": p["judge"]["bull_points"],
            "bear_points": p["judge"]["bear_points"],
            "news": p["news"],
            "filings": p["filings"],
            "tech": p["tech"],
            "financials": p["financials"],
            "updated": today.isoformat(),
        })
        room -= 1
    return added
