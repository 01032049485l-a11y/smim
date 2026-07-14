"""SMIM 일일 발행 파이프라인.

한 번 실행 = 하루치 불변 스냅샷 1개 생성 + 사이트 재빌드.
실패하면 아무것도 발행하지 않고 경보를 쏜다. (조용히 틀린 걸 내보내는 것보다 낫다)
"""
import os
import sys
import json
import argparse
import traceback
import datetime as dt

import requests

import config
from pipeline import universe, agents, watchlist, ledger, newsroom
from pipeline.sources import dart, news, market, prices, us_filings, us_news
from render import build

# Windows 콘솔(cp949)은 이모지를 인코딩 못 해 print()가 죽는다.
# 경보 메시지가 그 자리에서 크래시하며 진짜 원인을 가리는 걸 막는다.
sys.stdout.reconfigure(errors="replace")
sys.stderr.reconfigure(errors="replace")


def alert(text: str) -> None:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        print(f"[alert] {text}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[alert] 전송 실패: {e}")


def _snapshot_dir(market_group: str) -> str:
    return os.path.join(config.SNAPSHOT_DIR, market_group.lower())


def already_published(today: dt.date, market_group: str) -> bool:
    return os.path.exists(os.path.join(_snapshot_dir(market_group), f"{today.isoformat()}.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="kr", choices=["kr", "us"],
                         help="어느 시장을 발행할지. 한국/미국은 완전히 독립된 실행이다.")
    parser.add_argument("--force", action="store_true")
    args, _ = parser.parse_known_args()
    market_group = args.market.upper()
    is_us = market_group == "US"

    today = dt.datetime.now(config.KST).date()

    if today.weekday() >= 5:
        print(f"[run] 주말({market_group}) — 발행하지 않음")
        return 0
    if already_published(today, market_group) and not args.force:
        print(f"[run] 오늘 이미 발행됨({market_group}) — 중복 실행 방지")
        return 0

    print(f"=== SMIM 발행 시작 {today} ({market_group}) ===")

    # 1) 보유 종목 갱신 & 편출
    active, closed = watchlist.refresh(today, market_group)
    ledger.record(closed, market_group)
    print(f"[run] 관찰 중 {len(active)} / 오늘 편출 {len(closed)}")

    # 2) 자리가 있을 때만 신규 후보 탐색 (AI 비용 절약)
    picks, rejected = [], []
    scanned, ai_calls = 0, 0
    max_holdings = config.MAX_HOLDINGS_US if is_us else config.MAX_HOLDINGS_KR
    max_new = config.MAX_NEW_PER_DAY_US if is_us else config.MAX_NEW_PER_DAY_KR
    room = max_holdings - len(active)
    if room > 0:
        corp_map = us_filings.load_ticker_cik_map() if is_us else dart.load_corp_codes()
        calib = ledger.calibration_note()
        held = {h["code"] for h in active}

        cands = universe.prescreen(market_group)
        scanned = len(cands)
        for cand in cands:
            if cand["code"] in held:
                continue
            if len(picks) >= max_new:
                break

            ok, flags, filings = universe.risk_gate(cand["code"], corp_map, market_group)
            if not ok:
                rejected.append({"name": cand["name"], "reason": f"리스크 공시: {', '.join(flags)}"})
                continue

            key = corp_map.get(cand["code"], "")
            if is_us:
                fin = us_filings.key_financials(key)
                homepage = ""  # SEC 데이터엔 홈페이지 필드가 없음 — 로고는 모노그램으로 대체
                arts = us_news.for_stock(cand["code"])
            else:
                fin = dart.key_financials(key)
                homepage = dart.company_profile(key).get("homepage", "")
                arts = news.for_stock(cand["name"])

            try:
                judge = agents.analyze(cand, fin, arts, filings, calib)
                ai_calls += 3
            except agents.AIFailure as e:
                alert(f"⚠️ SMIM({market_group}): AI 판단 실패 ({cand['name']})\n{e}")
                return 1  # AI가 죽었으면 아무것도 발행하지 않는다

            if judge["unverified_numbers"]:
                rejected.append({"name": cand["name"],
                                 "reason": f"검증 실패 숫자: {judge['unverified_numbers']}"})
                print(f"[run] ⛔ {cand['name']} 환각 숫자 감지 → 제외")
                continue

            if judge["verdict"] in ("BUY", "STRONG_BUY") and judge["confidence"] >= config.MIN_CONVICTION:
                picks.append({**cand, "judge": judge, "news": arts,
                              "filings": filings, "financials": fin, "homepage": homepage})
            else:
                rejected.append({"name": cand["name"],
                                 "reason": f"{judge['verdict']} (확신도 {judge['confidence']})"})
    else:
        print(f"[run] 워치리스트 만석({market_group}) — 신규 편입 없음")

    # 3) 편입 & 저장
    added = watchlist.admit(active, picks, today, market_group)
    new_state = active + added
    watchlist.save(new_state, market_group)

    # 4) 차트용 시계열 — 스냅샷 안에 동결한다 (나중에 재현 가능해야 하므로)
    for h in new_state + closed:
        h["series"] = prices.series(h["code"], n=90)

    # 5) 불변 스냅샷 (append-only). 한국/미국은 각자 스냅샷 디렉터리를 쓴다.
    snap_dir = _snapshot_dir(market_group)
    os.makedirs(snap_dir, exist_ok=True)
    snapshot = {
        "date": today.isoformat(),
        "market_group": market_group,
        "report_id": f"SMIM-{market_group}-{today.strftime('%Y-%m%d')}",
        "issue_no": len(os.listdir(snap_dir)) + 1,
        "published_at": dt.datetime.now(config.KST).isoformat(timespec="seconds"),
        "models": {
            "bull": config.BULL_MODEL,
            "bear": config.BEAR_MODEL,
            "judge": config.JUDGE_MODEL,
            "news": config.NEWSTAG_MODEL,
        },
        "market": {"indices": market.overview(), **market.breadth_and_sectors()},
        "new_entries": added,
        "holdings": [h for h in new_state if h["status"] != "new"],
        "exits": closed,
        "rejected": rejected[:12],
        "newsroom": newsroom.link_to_watchlist(newsroom.build(market_group), new_state),
        "ledger": ledger.stats(),
        "universe_scanned": scanned,
        "ai_calls": ai_calls,
        "ai_usage": agents.usage_summary(),
    }
    path = os.path.join(snap_dir, f"{today.isoformat()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)
    print(f"[run] 스냅샷 저장: {path}")

    # 비용 보고는 빌드보다 먼저 — 빌드가 실패해도(예: 파일 잠금) 이미 쓴 비용은 반드시 알려야 한다.
    usage = snapshot["ai_usage"]
    print(f"[run] 토큰 사용: {usage['by_model']} · 예상 비용 ${usage['estimated_cost_usd']}")
    alert(f"✅ SMIM {market_group} {today} 발행 완료\n신규 {len(added)} · 관찰 {len(active)} · 편출 {len(closed)}\n"
          f"토큰 비용 ${usage['estimated_cost_usd']}")

    # 6) 사이트 빌드 (한국·미국 스냅샷을 모두 모아 다시 렌더)
    build.build_site()

    print(f"=== 발행 완료 ({market_group}) ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        alert(f"🚨 SMIM 파이프라인 예외 발생\n{traceback.format_exc()[-800:]}")
        sys.exit(1)
