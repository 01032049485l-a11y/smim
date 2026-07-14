# SMIM — In the stock market, information matters.

AI가 매일 아침 국내 주식을 분석하고, **그 판단을 지우지 않고 전부 기록하는** 리서치 저널.

---

## 이 시스템의 4가지 원칙

1. **워치리스트는 살아있다** — "오늘의 추천 5개"가 아니라, 최대 12종목을 편입→관찰→편출까지 추적한다. 중기(일~주) 투자자의 실제 행동과 일치하는 유일한 구조.
2. **AI는 혼자 판단하지 않는다** — Bull(살 이유) / Bear(사지 말 이유) / Judge(최종 판정) 3단 구조. 한 번 물어보면 AI는 반드시 후해진다.
3. **지어낸 숫자는 발행되지 않는다** — Judge가 쓴 모든 수치를 원본 데이터와 자동 대조. 하나라도 안 맞으면 그 종목은 통째로 제외.
4. **성적표는 자동이다** — 승률·평균수익률을 사람 손 안 대고 계산해서 그대로 공개한다. 나쁜 성적도.

---

## 폴더 구조

```
config.py                  전역 설정 (숫자만 바꾸면 시스템 성격이 바뀜)
run_daily.py               일일 발행 오케스트레이터
pipeline/
  indicators.py            기술적 지표 계산
  universe.py              1차 룰 필터 + 리스크 게이트
  agents.py                Bull / Bear / Judge + 환각 숫자 검증
  watchlist.py             액티브 워치리스트 코호트 관리
  ledger.py                성과 원장 + AI 캘리브레이션 피드백
  sources/
    prices.py              FinanceDataReader (시세·종목리스트)
    dart.py                DART 오픈API (재무·공시)
    news.py                네이버 뉴스 API
render/
  build.py                 Jinja2 정적 사이트 빌더 (Node 불필요)
  templates/               HTML 템플릿
  static/style.css         스타일
data/
  snapshots/               ★ append-only. 하루 1개. 절대 수정 금지.
  ledger.json              마감 포지션 원장
  watchlist.json           현재 워치리스트 상태
site/                      빌드 산출물 → Cloudflare Pages가 이 폴더를 서빙
```

---

## 설치 (딱 5단계)

### 1. GitHub 저장소 만들기
새 저장소 `smim` 생성 → **Public** (Actions 무제한 무료) → 이 파일 전부 업로드.

### 2. DART API 키 발급 (무료, 3분) — **새로 필요합니다**
https://opendart.fss.or.kr → 인증키 신청. 금감원 공식 API라 네이버 스크래핑과 달리 안 죽습니다.

### 3. GitHub Secrets 등록
`Settings → Secrets and variables → Actions → New repository secret`

| 이름 | 설명 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API (기존 것 재사용) |
| `DART_API_KEY` | **신규** — 위에서 발급 |
| `NAVER_CLIENT_ID` | 기존 |
| `NAVER_CLIENT_SECRET` | 기존 |
| `TELEGRAM_BOT_TOKEN` | 선택 — 실패 경보용 |
| `TELEGRAM_CHAT_ID` | 선택 |

### 4. Cloudflare Pages 연결 (실시간 시세 API 포함)
1. https://dash.cloudflare.com → Workers & Pages → **Connect to Git** → `smim` 저장소 선택
2. **Framework preset**: `None`
3. **Build command**: 비워둠 (빌드 명령 없음 — 이미 HTML로 커밋됨)
4. **Build output directory**: `site`
5. Deploy

`functions/api/quotes.js` 는 Cloudflare가 자동으로 인식해 **/api/quotes** 라는 실시간 시세 API로 띄웁니다.
별도 서버·요금·API 키가 필요 없습니다. 상단 티커가 15초마다 이걸 폴링해 살아 움직입니다.
API가 죽어도 HTML에 박힌 종가가 남아 화면은 절대 비지 않습니다.

> 빌드 명령이 없는 게 핵심입니다. Actions가 HTML까지 다 만들어서 커밋하니, Cloudflare는 그냥 폴더만 서빙합니다. **폰에서 빌드 에러 디버깅할 일이 없습니다.**

### 5. 도메인 연결
`smim.kr` 구매(가비아/후이즈 등) → Cloudflare Pages → Custom domains → `smim.kr` 추가 → 안내받은 네임서버로 변경. SSL 자동, 무료.

---

## 로컬 개발 (노트북)

```bash
pip install -r requirements.txt

# API 비용 0원. 가짜 데이터로 사이트 전체를 빌드해서 디자인만 반복
python tools/demo_seed.py
python tools/build_demo.py
python tools/serve.py          # → http://localhost:8000

# 실제 데이터로 한 번 돌려보기 (API 키 필요)
python run_daily.py --force
python -m render.build
```

디자인만 고칠 때는 `render/templates/`, `render/static/style.css`만 만지고
`python tools/build_demo.py` 를 다시 돌리면 됩니다. Anthropic 호출이 전혀 없습니다.

---

## 첫 실행

Actions 탭 → **SMIM Daily Publish** → `Run workflow` 버튼 (폰에서도 됩니다).
5~20분 뒤 `data/snapshots/YYYY-MM-DD.json`이 커밋되고 사이트가 뜹니다.

---

## 발행 스케줄

평일 KST **06:37 / 07:07 / 07:37** 3단 트리거.
GitHub Actions cron은 지연·누락됩니다(공식 정책). 그래서 3번 쏘고, 이미 발행됐으면 스스로 건너뜁니다.
**실패해도 어제 리포트는 그대로 살아있습니다.** 사이트가 빈 화면이 되는 일은 없습니다.

---

## 성격 조절 (config.py)

한국(KR)·미국(US)은 완전히 독립된 파이프라인이라 값도 마켓별로 따로 있습니다.

| 값 | 기본 | 의미 |
|---|---|---|
| `MAX_HOLDINGS_KR` / `_US` | 12 / 12 | 동시 관찰 종목 수 |
| `MAX_NEW_PER_DAY_KR` / `_US` | 2 / 2 | 하루 신규 편입 상한 |
| `MIN_CONVICTION` | 70 | 이 확신도 미만은 편입 안 함 |
| `TAKE_PROFIT_RANGE` | (5.0, 20.0) | 목표 도달 편출선 — 종목마다 AI가 이 범위 안에서 직접 정함 |
| `STOP_LOSS_RANGE` | (-10.0, -5.0) | 손절 편출선 — 마찬가지로 종목별 AI 판단 |
| `MAX_HOLD_DAYS` | 25 | 중기 시계 유지 (넘으면 자동 편출) |
| `MAX_CANDIDATES_TO_AI_KR` / `_US` | 4 / 4 | AI 호출 비용 통제 |

AI 호출은 종목당 3회(Bull/Bear/Judge, Bull·Bear는 Haiku·Judge는 Sonnet). 한국·미국 각 하루 최대 신규 2종목, 후보 4종목이면 **하루 시장당 12회 내외**로 비용이 예측 가능합니다. `run_daily.py` 실행이 끝나면 실제 토큰 사용량과 예상 비용(달러)을 콘솔·텔레그램으로 알려줍니다.

---

## ⚠️ 법적 사항 — 반드시 지킬 것

- 현행 자본시장법 시행령상 유사투자자문업은 **"대가를 받고 행하는 투자조언"**으로 정의됩니다. 따라서 **완전 무료로 운영하는 동안은 신고 대상이 아닐 가능성이 높습니다.**
- **구독료·유료회원·광고형 유료 리딩 등으로 수익화하는 순간** 금융위 신고가 필요해질 수 있습니다. 그때는 반드시 전문가 확인을 받으십시오.
- 저는 변호사가 아니며, 위 내용은 법률 자문이 아닙니다.
- `config.py`의 `DISCLAIMER`는 모든 페이지 하단에 노출됩니다. **절대 지우지 마십시오.**
- 뉴스는 **제목 + 링크만** 저장합니다. 기사 본문은 저장·재배포하지 않습니다(저작권).

---

## 알려진 한계 (정직하게)

- **관리종목·거래정지·투자경고 플래그**: FinanceDataReader가 제공하지 않아 현재는 DART 공시 키워드로 간접 탐지 중. 더 확실한 소스를 붙이는 게 다음 개선 과제.
- **수급(기관/외국인)**: 아직 미연동. 스코어카드의 `supply` 축은 현재 거래량 기반 추정. KIS 오픈API를 붙이면 정확해집니다.
- **백테스트**: 스냅샷이 쌓이면 그 자체가 데이터셋이 됩니다. 최소 2~3개월 축적 후 착수 권장.
