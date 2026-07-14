"""유리상자 성적표.

이 파일이 SMIM의 유일한 진짜 해자다.
좋은 성적도, 나쁜 성적도 사람 손 안 대고 자동으로 계산해서 그대로 공개한다.
"""
import os
import json
import statistics as st

import config

LEDGER = os.path.join(config.DATA_DIR, "ledger.json")


def load() -> list[dict]:
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding="utf-8") as f:
        return json.load(f)


def record(closed: list[dict], market_group: str = "KR") -> None:
    """편출된 포지션을 원장에 append. 절대 수정·삭제하지 않는다."""
    if not closed:
        return
    book = load()
    known = {(c.get("market_group", "KR"), c["code"], c["entry_date"]) for c in book}
    for c in closed:
        key = (market_group, c["code"], c["entry_date"])
        if key in known:
            continue
        book.append({
            "market_group": market_group,
            "code": c["code"], "name": c["name"],
            "entry_date": c["entry_date"], "entry_price": c["entry_price"],
            "exit_date": c["exit_date"], "exit_price": c["exit_price"],
            "return_pct": c["return_pct"], "days_held": c["days_held"],
            "status": c["status"],
            "verdict": c.get("verdict"), "confidence": c.get("confidence"),
        })
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=1)


def stats() -> dict:
    book = load()
    if not book:
        return {"total": 0, "win_rate": None, "avg_return": None,
                "best": None, "worst": None, "avg_days": None}
    rets = [b["return_pct"] for b in book]
    wins = [r for r in rets if r > 0]
    best = max(book, key=lambda b: b["return_pct"])
    worst = min(book, key=lambda b: b["return_pct"])
    return {
        "total": len(book),
        "win_rate": round(len(wins) / len(book) * 100, 1),
        "avg_return": round(st.mean(rets), 2),
        "median_return": round(st.median(rets), 2),
        "avg_days": round(st.mean([b["days_held"] for b in book]), 1),
        "best": {"name": best["name"], "return_pct": best["return_pct"]},
        "worst": {"name": worst["name"], "return_pct": worst["return_pct"]},
    }


def calibration_note() -> str:
    """Judge 프롬프트에 매일 주입되는 자기교정 텍스트."""
    book = load()
    if len(book) < 5:
        return "아직 마감된 포지션이 5건 미만이라 캘리브레이션 데이터가 없다. 그러므로 더욱 보수적으로 판정하라."

    buckets = {"90+": [], "80-89": [], "70-79": [], "70미만": []}
    for b in book:
        c = b.get("confidence") or 0
        key = "90+" if c >= 90 else "80-89" if c >= 80 else "70-79" if c >= 70 else "70미만"
        buckets[key].append(b["return_pct"])

    lines = [f"총 마감 {len(book)}건 / 승률 {stats()['win_rate']}% / 평균수익률 {stats()['avg_return']}%"]
    for k, v in buckets.items():
        if not v:
            continue
        wr = round(len([x for x in v if x > 0]) / len(v) * 100)
        lines.append(f"- 네가 confidence {k}로 판정했던 {len(v)}건: 실제 승률 {wr}%, 평균 {round(st.mean(v), 1)}%")
    lines.append("위 기록에서 네 확신도가 실제 결과보다 높았다면, 이번 판정의 confidence를 그만큼 낮춰라.")
    return "\n".join(lines)
