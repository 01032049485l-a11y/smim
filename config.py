"""SMIM 전역 설정. 여기 숫자만 바꾸면 시스템 성격이 바뀝니다."""
import os
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# ── 브랜드 ────────────────────────────────────────────────
SITE_NAME = "SMIM"
SITE_TAGLINE = "주식은 정보다"
SITE_DESC = "국내 증시 데이터·공시·뉴스를 종합 분석해 매 거래일 아침 발행하는 리서치 저널."
SITE_URL = os.environ.get("SITE_URL", "https://smim.kr")

# 개발·운영자 (푸터 크레딧)
DEVELOPER = os.environ.get("DEVELOPER", "이태웅")
DEVELOPER_ROLE = "Founder & Developer"

# ── 워치리스트 정책 (중기: 일~주 단위) ──────────────────────
# 한국/미국은 완전히 독립된 파이프라인이라 상한도 마켓별로 따로 관리한다.
MAX_HOLDINGS_KR = 12          # 한국 동시 관찰 최대 종목 수
MAX_HOLDINGS_US = 12          # 미국 동시 관찰 최대 종목 수
MAX_NEW_PER_DAY_KR = 2        # 한국 하루 신규 편입 상한 (비용 통제)
MAX_NEW_PER_DAY_US = 2        # 미국 하루 신규 편입 상한 (비용 통제)
MIN_CONVICTION = 60        # Judge confidence 이 값 이상만 신규 편입 (2026-07-15 완화: 70→60)
MAX_HOLD_DAYS = 25         # 이 거래일 넘기면 자동 편출(중기 시계 유지)

# 목표수익률·손절선은 전 종목에 같은 숫자를 박아두지 않는다 — 종목마다 변동성·기술적
# 구조가 다르므로 Judge가 이 범위 안에서 직접 정한다(pipeline/agents.py JUDGE_SYS).
TAKE_PROFIT_RANGE = (5.0, 20.0)    # 목표 도달 편출선, AI가 이 안에서 결정
STOP_LOSS_RANGE = (-10.0, -5.0)    # 손절 편출선, AI가 이 안에서 결정 (더 타이트 ~ 더 느슨)

# ── 1차 룰 필터 (AI 호출 전 유니버스 축소) ──────────────────
MIN_MARKET_CAP = 150_000_000_000      # 시총 1,500억 이상 (한국 전용 — 미국 유니버스엔 시총 컬럼이 없어 미적용)
MIN_AVG_TRADING_VALUE_KR = 3_000_000_000  # 20일 평균 거래대금 30억원 이상
MIN_AVG_TRADING_VALUE_US = 2_000_000      # 20일 평균 거래대금 $200만 이상 (달러 기준)
MAX_CANDIDATES_TO_AI_KR = 4                # 한국 AI 분석 후보 수 (비용 통제, 한/미 반반)
MAX_CANDIDATES_TO_AI_US = 4                # 미국 AI 분석 후보 수 (비용 통제, 한/미 반반)

# ── AI ────────────────────────────────────────────────────
# 한 번만 물으면 AI는 후하다 — Bull/Bear/Judge를 서로 다른 모델로 분리해 비용을 낮춘다.
# Judge(최종 심사역)만 정확도가 중요해 sonnet 유지, 나머지는 haiku.
BULL_MODEL = "claude-haiku-4-5-20251001"
BEAR_MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-sonnet-5"
NEWSTAG_MODEL = "claude-haiku-4-5-20251001"

# $ per 1M tokens (input, output). sonnet-5는 ~2026-08-31까지 도입 할인가 적용 중
# (표준가 3.00/15.00으로 복귀 예정 — 그때 이 표를 갱신할 것).
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
}

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── 데이터 소스 키 ──────────────────────────────────────────
DART_API_KEY = os.environ.get("DART_API_KEY", "")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

# SEC EDGAR는 키 발급이 없는 대신 요청자를 식별할 수 있는 User-Agent를 요구한다(정책).
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", f"SMIM Research Bot ({SITE_URL})")

# ── 경보 (파이프라인 실패 시) ────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── 경로 ──────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")   # append-only. 절대 수정 금지.
CACHE_DIR = os.path.join(DATA_DIR, "cache")
SITE_DIR = os.path.join(ROOT, "site")

# ── 제외 패턴 (스팩/우선주/리츠/ETF/ETN) ─────────────────────
EXCLUDE_NAME_PATTERNS = ("스팩", "우B", "리츠", "ETN", "KODEX", "TIGER", "KBSTAR",
                         "ARIRANG", "HANARO", "SOL ", "ACE ", "PLUS ", "RISE ")
EXCLUDE_NAME_PATTERNS_US = ("ETF", "Trust", "Fund", "Depositary", " L.P.", "Acquisition Corp")

# ── 법적 고지 (모든 페이지 노출. 절대 제거하지 말 것) ──────────
DISCLAIMER = (
    "SMIM이 제공하는 모든 정보는 AI가 공개 데이터를 분석해 생성한 참고자료이며, "
    "특정 종목의 매수·매도를 권유하는 투자 권유가 아닙니다. "
    "SMIM은 자본시장법상 금융투자업자가 아니며, 어떠한 수익도 보장하지 않습니다. "
    "AI가 올려준 종목을 보고 매수할지 판단하는 것은 오롯이 투자자 본인의 몫이며, "
    "투자 결과에 대한 책임은 전적으로 투자자 본인에게 있습니다."
)
