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
import concurrent.futures as cf

import requests

import config
from pipeline import universe, agents, watchlist, ledger, newsroom
from pipeline.sources import dart, news, market, prices
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


def _health_path() -> str:
    return os.path.join(config.DATA_DIR, "ai_health.json")


def load_health() -> dict:
    try:
        with open(_health_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_health(h: dict) -> None:
    try:
        with open(_health_path(), "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"[run] ai_health 저장 실패: {e}")


def print_big_summary(title: str, lines: list[str]) -> None:
    """스크립트 맨 끝에, 로그를 대충 훑어도 눈에 띄게 큰 배너로 요약을 찍는다.
    (한글은 폭 계산이 어긋나 정렬 대신 굵은 구분선으로 시각적 무게를 준다.)"""
    bar = "═" * 64
    print("\n" + bar)
    print(f"  {title}")
    print(bar)
    for ln in lines:
        print(f"  {ln}")
    print(bar + "\n")


def write_step_summary(title: str, lines: list[str]) -> None:
    """GitHub Actions 실행 페이지 상단에 뜨는 요약($GITHUB_STEP_SUMMARY).
    로그를 파고들지 않아도 실행 화면에서 바로 결과를 볼 수 있다."""
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if not p:
        return
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"## {title}\n\n")
            for ln in lines:
                f.write(f"- {ln}\n")
            f.write("\n")
    except Exception:
        pass


def _build_newsroom_safe(market_group: str, watchlist_state: list[dict]) -> list[dict]:
    """뉴스룸(본문 수집·AI 해설)은 핵심 기능(종목 추천)이 아니다 — 여기서 오래 걸리거나
    멈춰서 발행 전체를 막으면 안 된다. 시간 제한을 넘기면 빈 뉴스룸으로 그냥 발행한다."""
    ex = cf.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(newsroom.build, market_group)
    try:
        items = fut.result(timeout=180)
    except Exception as e:
        print(f"[run] 뉴스룸 수집 시간 초과/실패({e}) — 뉴스룸 비우고 발행 계속")
        return []
    finally:
        ex.shutdown(wait=False)
    return newsroom.link_to_watchlist(items, watchlist_state)


def _snapshot_dir(market_group: str) -> str:
    return os.path.join(config.SNAPSHOT_DIR, market_group.lower())


def already_published(today: dt.date, market_group: str) -> bool:
    """오늘 스냅샷이 이미 있으면 중복 실행을 막는다. 단, 'ai_failure'로 찍힌 스냅샷은
    진짜 발행이 아니라 실패 표식이므로 아직 발행 안 된 것으로 취급한다 —
    크레딧 복구 후 다음 실행(백업 크론 등)이 자동으로 다시 분석해 진짜 리포트로 덮어쓴다."""
    path = os.path.join(_snapshot_dir(market_group), f"{today.isoformat()}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("status") != "ai_failure"
    except Exception:
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="kr", choices=["kr"],
                         help="발행 시장. 현재는 한국(kr) 전용 — 미국 파이프라인은 제거됨.")
    parser.add_argument("--force", action="store_true")
    args, _ = parser.parse_known_args()
    market_group = "KR"

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
    ai_attempts, ai_failures = 0, 0
    ai_error_kind, ai_last_error = "", ""
    max_holdings = config.MAX_HOLDINGS_KR
    max_new = config.MAX_NEW_PER_DAY_KR
    room = max_holdings - len(active)
    if room > 0:
        corp_map = dart.load_corp_codes()
        calib = ledger.calibration_note()
        held = {h["code"] for h in active}

        cands = universe.prescreen(market_group)
        scanned = len(cands)
        for cand in cands:
            if cand["code"] in held:
                continue
            if len(picks) >= max_new:
                break

            print(f"[run] 후보 분석 시작: {cand['name']} ({cand['code']})")
            ok, flags, filings = universe.risk_gate(cand["code"], corp_map, market_group)
            if not ok:
                rejected.append({"name": cand["name"], "reason": f"리스크 공시: {', '.join(flags)}"})
                continue

            key = corp_map.get(cand["code"], "")
            fin = dart.key_financials(key)
            homepage = dart.company_profile(key).get("homepage", "")
            arts = news.for_stock(cand["name"])
            print(f"[run] 재무·뉴스 수집 완료, AI 분석 시작: {cand['name']}")

            ai_attempts += 1
            try:
                judge = agents.analyze(cand, fin, arts, filings, calib)
                ai_calls += 3
                print(f"[run] AI 분석 완료: {cand['name']} → {judge.get('verdict')} (확신도 {judge.get('confidence')})")
            except agents.AIFailure as e:
                ai_failures += 1
                ai_last_error = str(e)
                ai_error_kind = getattr(e, "kind", "unknown")
                print(f"[run] ⚠️ AI 분석 실패: {cand['name']} ({ai_error_kind}) — {e}")
                # 결제·인증 오류는 모든 종목에서 똑같이 실패한다 — 남은 후보를 태우지 말고 즉시 중단.
                # (예전엔 첫 실패에서 바로 return 1 해서 실패율/원인 집계도 못 하고 조용히 묻혔다)
                if ai_error_kind in ("billing", "auth"):
                    print(f"[run] ⚠️ 시스템성 오류({ai_error_kind}) — 남은 후보 분석 중단")
                    break
                continue

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

    # 2.5) AI 분석이 (거의) 전부 실패했는지 판정 — 크레딧 소진 같은 시스템성 오류가
    #      "후보 0개"로 조용히 묻히지 않게 하는 게 이 블록의 핵심.
    ai_fail_rate = (ai_failures / ai_attempts) if ai_attempts else 0.0
    ai_total_failure = ai_attempts > 0 and ai_fail_rate >= config.AI_FAILURE_ABORT_RATE

    # 연속 실패일 집계 (같은 날 백업 크론 재실행은 카운트 유지, 날짜가 바뀌면 +1, 성공하면 리셋)
    health = load_health()
    if ai_total_failure:
        prev = health.get(market_group, {})
        streak = prev.get("consecutive_failures", 0)
        if prev.get("last_failure_date") != today.isoformat():
            streak += 1
        health[market_group] = {"consecutive_failures": streak,
                                 "last_failure_date": today.isoformat(),
                                 "last_kind": ai_error_kind or "unknown"}
    else:
        streak = 0
        health[market_group] = {"consecutive_failures": 0,
                                 "last_success_date": today.isoformat(),
                                 **({"last_failure_date": health.get(market_group, {}).get("last_failure_date")}
                                    if health.get(market_group, {}).get("last_failure_date") else {})}
    save_health(health)

    # 3) 편입 & 저장 (분석 전면 실패면 picks는 비어 있어 신규 편입도 0)
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
        "status": "ai_failure" if ai_total_failure else "ok",
        "status_detail": ({
            "ai_attempts": ai_attempts, "ai_failures": ai_failures,
            "ai_fail_rate": round(ai_fail_rate, 2), "ai_error_kind": ai_error_kind,
            "ai_last_error": ai_last_error[:300], "consecutive_failure_days": streak,
        } if (ai_failures or ai_total_failure) else None),
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
        "newsroom": _build_newsroom_safe(market_group, new_state),
        "ledger": ledger.stats(),
        "universe_scanned": scanned,
        "ai_calls": ai_calls,
        "ai_usage": agents.usage_summary(),
    }
    path = os.path.join(snap_dir, f"{today.isoformat()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)
    print(f"[run] 스냅샷 저장: {path}")

    usage = snapshot["ai_usage"]
    print(f"[run] 토큰 사용: {usage['by_model']} · 예상 비용 ${usage['estimated_cost_usd']}")

    # 6) 사이트 빌드 (실패 상태여도 빌드해서 '분석 실패' 배너가 사이트에 뜨게 한다)
    build.build_site()

    # 7) 결과 요약 — 로그 맨 끝 큰 배너 + GitHub 실행 요약 + 별도 알림(텔레그램).
    #    전면 실패면 런을 실패(exit 1)로 끝내 GitHub가 실패 메일을 자동 발송하게 한다.
    if ai_total_failure:
        kind_ko = {"billing": "결제/크레딧", "auth": "API 키/권한",
                   "rate_limit": "레이트리밋", "overloaded": "서버 과부하"}.get(ai_error_kind, ai_error_kind)
        streak_tag = f" · {streak}일째 연속" if streak >= 2 else ""
        head = f"⚠️ AI 분석 {ai_failures}/{ai_attempts}건 전부 실패 — 오늘 발행 없음{streak_tag}"
        lines = [
            f"시장: {market_group} / 날짜: {today}",
            f"추정 원인: {kind_ko} ({ai_error_kind})",
            f"마지막 오류: {ai_last_error[:200]}",
            "→ '후보가 없는 날'이 아니라 시스템 오류입니다. Anthropic 결제 상태를 확인하세요.",
            "→ 복구되면 다음 실행(백업 크론)이 자동으로 다시 분석해 발행합니다.",
        ]
        if streak >= 2:
            lines.insert(0, f"🚨 {market_group} 시장 {streak}일째 연속 완전 실패 — 즉시 확인 필요")
        print_big_summary(head, lines)
        write_step_summary(head, lines)
        alert(f"🚨 SMIM {market_group} {today}\n{head}\n원인: {kind_ko}\n{ai_last_error[:200]}\n"
              f"Anthropic 결제 상태를 확인하세요.")
        print(f"=== 발행 실패 처리 완료 ({market_group}) — exit 1 ===")
        return 1

    warn = ""
    if ai_failures:
        warn = f" · ⚠️ AI 부분 실패 {ai_failures}/{ai_attempts}건({ai_error_kind})"
    head = f"✅ SMIM {market_group} {today} 발행 완료 — 신규 {len(added)}·관찰 {len(active)}·편출 {len(closed)}{warn}"
    lines = [
        f"신규 편입 {len(added)} / 관찰 {len(active)} / 편출 {len(closed)} / AI후보 {scanned}",
        f"AI 분석 {ai_attempts - ai_failures}/{ai_attempts} 성공 · 토큰 비용 ${usage['estimated_cost_usd']}",
    ]
    if ai_failures:
        lines.append(f"⚠️ 일부 AI 호출 실패 {ai_failures}건({ai_error_kind}) — 발행은 정상 진행")
    print_big_summary(head, lines)
    write_step_summary(head, lines)
    alert(head + f"\n토큰 비용 ${usage['estimated_cost_usd']}"
          + (f"\n⚠️ AI 부분 실패 {ai_failures}/{ai_attempts}건" if ai_failures else ""))

    print(f"=== 발행 완료 ({market_group}) ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        alert(f"🚨 SMIM 파이프라인 예외 발생\n{traceback.format_exc()[-800:]}")
        sys.exit(1)
