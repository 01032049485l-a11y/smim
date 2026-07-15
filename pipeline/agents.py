"""AI 판단부 — Bull / Bear / Judge.

한 번 물어보면 AI는 반드시 후하게 준다. (전 프로젝트가 그걸로 무너졌다)
그래서 사는 이유만 찾는 놈과, 사지 말 이유만 찾는 놈을 따로 세우고,
제3의 심판이 둘의 주장을 읽고 결정하게 한다.

그리고 심판이 뱉은 모든 숫자는 원본 데이터와 대조한다.
지어낸 숫자가 하나라도 있으면 그 종목은 발행에서 제외한다.
"""
import json
import re

import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=60.0, max_retries=1)

# 이날 실제로 쓴 토큰 기록 — run_daily.py가 끝날 때 비용을 계산해 보여준다.
_usage_log: list[dict] = []


class AIFailure(Exception):
    pass


def _call(system: str, user: str, model: str, max_tokens: int = 1600) -> str:
    for attempt in range(3):
        try:
            msg = _client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            _usage_log.append({
                "model": model,
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
            })
            return "".join(b.text for b in msg.content if b.type == "text")
        except Exception as e:
            if attempt == 2:
                raise AIFailure(f"Anthropic 호출 실패: {e}")
    raise AIFailure("unreachable")


def usage_summary() -> dict:
    """지금까지의 호출을 모델별로 집계하고 예상 비용(달러)을 계산한다."""
    by_model: dict[str, dict] = {}
    for u in _usage_log:
        t = by_model.setdefault(u["model"], {"input_tokens": 0, "output_tokens": 0})
        t["input_tokens"] += u["input_tokens"]
        t["output_tokens"] += u["output_tokens"]

    cost = 0.0
    for model, t in by_model.items():
        in_price, out_price = config.MODEL_PRICING.get(model, (0.0, 0.0))
        cost += t["input_tokens"] / 1_000_000 * in_price
        cost += t["output_tokens"] / 1_000_000 * out_price

    return {"by_model": by_model, "estimated_cost_usd": round(cost, 4)}


def _parse_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise AIFailure("JSON 파싱 실패")
    return json.loads(m.group(0))


def _call_json(system: str, user: str, model: str, max_tokens: int = 1600, retries: int = 1) -> dict:
    """호출+JSON 파싱을 묶어서, 파싱 실패도 API 실패와 똑같이 재시도한다.
    AI가 한국어 문장 안에 따옴표를 잘못 이스케이프해 JSON이 깨지는 경우가 실제로 있었다
    (2026-07-15 실서비스 크래시) — 같은 질문을 다시 하면 대개 정상적인 JSON이 나온다.
    retries=1(기본): _client 자체에도 max_retries=1이 걸려있어(agents.py 상단) 두 겹
    재시도가 곱해지면 최악의 경우 대기가 너무 길어진다 — 여기서는 낮게 유지한다."""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        raw = _call(system, user, model, max_tokens=max_tokens)
        try:
            return _parse_json(raw)
        except (json.JSONDecodeError, AIFailure) as e:
            last_err = e
    raise AIFailure(f"JSON 파싱 반복 실패: {last_err}")


# ── 팩트시트 ────────────────────────────────────────────────
def build_factsheet(cand: dict, fin: dict, news: list[dict], filings: list[dict]) -> str:
    t = cand["tech"]
    is_us = cand.get("market_group") == "US"
    money = (lambda v: f"${v:,.0f}") if is_us else (lambda v: f"{v:,.0f}원")
    filing_source = "SEC EDGAR" if is_us else "DART"
    cap = money(cand["market_cap"]) if cand.get("market_cap") is not None else "정보 없음"
    lines = [
        f"종목: {cand['name']} ({cand['code']}, {cand['market']})",
        f"시가총액: {cap}",
        "",
        "[가격·기술적 사실]",
        f"- 종가 {money(t['close'])} / 1일 {t['change_1d_pct']}% / 5일 {t['change_5d_pct']}% / 20일 {t['change_20d_pct']}%",
        f"- 이평 5:{money(t['ma5'])} 20:{money(t['ma20'])} 60:{money(t['ma60'])} 120:{money(t['ma120'])}",
        f"- 20일선 위: {t['above_ma20']} / 60일선 위: {t['above_ma60']} / 20-60 골든크로스: {t['golden_cross_20_60']}",
        f"- RSI(14) {t['rsi14']} / MACD히스토그램 {t['macd_hist']} (상승전환: {t['macd_turning_up']})",
        f"- 거래량 20일평균 대비 {t['volume_ratio_vs_20d']}배 / 20일 평균거래대금 {money(t['avg_trading_value_20d'])}",
        f"- 52주 고점 {money(t['high_52w'])} 저점 {money(t['low_52w'])} / 현재 위치 {t['pos_in_52w_range_pct']}%",
        f"- 20일 변동성 {t['volatility_20d_pct']}%",
        "",
        f"[재무 사실 ({filing_source} 공시 기준)]",
    ]
    if fin:
        lines.append(f"- {fin.get('fiscal_year')}년 연결 기준")
        for k, label in (("revenue", "매출액"), ("operating_profit", "영업이익"),
                         ("net_income", "당기순이익")):
            if k in fin:
                yoy = fin.get(f"{k}_yoy_pct")
                lines.append(f"- {label} {money(fin[k])}" + (f" (전년比 {yoy}%)" if yoy is not None else ""))
        if "debt_ratio_pct" in fin:
            lines.append(f"- 부채비율 {fin['debt_ratio_pct']}%")
    else:
        lines.append(f"- 재무 데이터 없음 ({filing_source} 조회 실패 또는 미제출)")

    lines += ["", "[최근 공시 제목]"]
    lines += [f"- {f['date']} {f['title']}" for f in filings] or ["- 없음"]

    lines += ["", "[최근 뉴스 제목 — 본문 아님, 제목만]"]
    lines += [f"- {n['published']} {n['title']}" for n in news] or ["- 없음"]
    return "\n".join(lines)


# ── 세 명의 AI ──────────────────────────────────────────────
BULL_SYS = """너는 국내·미국 주식을 함께 다루는 리서치 하우스의 매수측 애널리스트다.
아래 팩트시트만 근거로, 이 종목을 '지금 사야 하는 이유'를 최대한 강하게 논증한다.
중기(5~20거래일) 관점이다. 데이터에 없는 숫자는 절대 지어내지 마라.
반드시 아래 JSON만 출력한다.
{"arguments":[{"tag":"기술적|펀더멘탈|수급|뉴스|밸류에이션","claim":"한 문장","evidence":"팩트시트의 어떤 수치·사실에 근거하는지"}],
 "upside_case":"3~4문장으로 상승 시나리오","strength":1-10}"""

BEAR_SYS = """너는 같은 리서치 하우스의 리스크 담당 애널리스트다.
아래 팩트시트만 근거로, 이 종목을 '지금 사면 안 되는 이유'를 최대한 냉정하게 논증한다.
"딱히 없다"는 답은 금지다. 반드시 최소 2개 이상의 실질적 위험을 찾아낸다.
데이터에 없는 숫자는 절대 지어내지 마라.
반드시 아래 JSON만 출력한다.
{"arguments":[{"tag":"기술적|펀더멘탈|수급|뉴스|밸류에이션","claim":"한 문장","evidence":"근거"}],
 "downside_case":"3~4문장으로 하락 시나리오","severity":1-10}"""

JUDGE_SYS = """너는 리서치 하우스의 최종 심사역이다. 매수측과 리스크측의 주장을 모두 읽고 판정한다.

원칙:
- 틀린 매수 추천 하나가 좋은 기회 하나를 놓치는 것보다 훨씬 나쁘다. 이건 실제 돈이 걸린 판단이고,
  과거에 이런 종류의 낙관적 판단이 실제로 손실을 낸 전례가 있다. 애매하면 기회를 놓치는 쪽을 택하라.
- 습관적으로 후하게 주지 마라. 확신이 없으면 confidence를 낮게 준다.
- 아래 '캘리브레이션 기록'은 과거 네 판정의 실제 성적이다. 이걸 보고 자기 과신을 교정하라.
- 팩트시트에 없는 숫자는 절대 쓰지 마라. 숫자를 쓸 거면 팩트시트에 있는 값 그대로만 써라.
- target_return_pct와 horizon_days는 임의로 정하지 마라. 팩트시트의 20일 변동성, 최근 등락폭,
  52주 위치를 근거로 현실적인 범위에서 산정하고, 근거 없이 두 자릿수 후반 이상의 목표수익률을 쓰지 마라.
- target_return_pct는 반드시 5~20 사이(퍼센트, 양수)에서 정한다. stop_loss_pct는 반드시 -10~-5
  사이(퍼센트, 음수)에서 정한다. 이 두 값은 전 종목에 같은 숫자를 쓰지 말고 종목마다 다르게 판단하라 —
  20일 변동성이 크고 등락이 거친 종목일수록 손절선은 -10에 가깝게(더 느슨하게) 잡아야 노이즈에
  흔들려 잘못 편출되지 않는다. 반대로 변동성이 작고 안정적인 종목은 -5에 가깝게(더 타이트하게) 잡는다.
- 5개 축을 각각 긍정/중립/부정으로 판정한다.
- verdict는 STRONG_BUY / BUY / WATCH / PASS 중 하나. 애매하면 WATCH나 PASS다.

반드시 아래 JSON만 출력한다.
{"verdict":"STRONG_BUY|BUY|WATCH|PASS",
 "confidence":0-100,
 "scorecard":{"price":"positive|neutral|negative","fundamental":"...","supply":"...","news":"...","valuation":"..."},
 "thesis":"이 종목을 한 문단(4~6문장)으로 요약한 투자 논리. 일반 투자자가 읽고 이해할 수 있게.",
 "bull_points":["매수 근거 3~5개, 각 한 문장"],
 "bear_points":["반드시 함께 표기할 리스크 2~4개, 각 한 문장"],
 "invalidation":"이 논리가 깨졌다고 판단할 구체적 조건 한 문장 (예: 20일선 종가 이탈)",
 "horizon_days":5-25,
 "target_return_pct":5~20 사이 숫자,
 "stop_loss_pct":-10~-5 사이 숫자}"""


def analyze(cand: dict, fin: dict, news: list[dict], filings: list[dict],
            calibration: str) -> dict:
    fs = build_factsheet(cand, fin, news, filings)

    bull = _call_json(BULL_SYS, fs, config.BULL_MODEL)
    bear = _call_json(BEAR_SYS, fs, config.BEAR_MODEL)

    judge_input = (
        f"{fs}\n\n"
        f"[매수측 주장]\n{json.dumps(bull, ensure_ascii=False, indent=1)}\n\n"
        f"[리스크측 주장]\n{json.dumps(bear, ensure_ascii=False, indent=1)}\n\n"
        f"[캘리브레이션 기록 — 과거 네 판정의 실제 성적]\n{calibration}"
    )
    judge = _call_json(JUDGE_SYS, judge_input, config.JUDGE_MODEL, max_tokens=2200)

    judge["_bull"] = bull
    judge["_bear"] = bear
    judge["unverified_numbers"] = verify_numbers(judge, cand, fin)
    return judge


# ── 환각 차단 게이트 ────────────────────────────────────────
_NUM = re.compile(r"\d[\d,]*\.?\d*")


def _known_values(cand: dict, fin: dict) -> set[str]:
    vals = set()
    def add(v):
        if v is None or isinstance(v, bool):
            return
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        vals.add(f"{f:.10g}")
        vals.add(f"{abs(f):.10g}")
        vals.add(f"{round(abs(f)):.10g}")
        vals.add(f"{round(abs(f), 1):.10g}")

    for v in cand["tech"].values():
        add(v)
    for v in fin.values():
        add(v)
    add(cand["market_cap"])
    return vals


def verify_numbers(judge: dict, cand: dict, fin: dict) -> list[str]:
    """AI가 쓴 숫자가 원본 데이터에 실재하는지 대조. 없으면 환각 후보."""
    known = _known_values(cand, fin)
    # 목표수익률·손절선·기간·연도·퍼센트 소수 등 AI가 정당하게 만들어내는 값은 예외
    allowed_self = {str(judge.get("confidence")), str(judge.get("horizon_days")),
                    str(judge.get("target_return_pct")), str(judge.get("stop_loss_pct")),
                    str(abs(judge.get("stop_loss_pct")) if judge.get("stop_loss_pct") is not None else None)}

    text = " ".join(
        judge.get("thesis", "")
        + " " + " ".join(judge.get("bull_points", []))
        + " " + " ".join(judge.get("bear_points", []))
        + " " + judge.get("invalidation", "")
    )
    bad = []
    for m in _NUM.findall(text):
        raw = m.replace(",", "")
        if raw in allowed_self:
            continue
        try:
            f = float(raw)
        except ValueError:
            continue
        if f <= 30:          # 5일, 20일선, RSI 구간 같은 일반 상수는 통과
            continue
        if f"{f:.10g}" in known or f"{round(f):.10g}" in known:
            continue
        bad.append(m)
    return sorted(set(bad))
