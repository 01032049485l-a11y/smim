# CLAUDE.md — SMIM 프로젝트 인수인계

> 이 파일은 Claude Code가 자동으로 읽습니다. 프로젝트의 헌법입니다.
> 작업 전 반드시 이 문서를 따르세요.

## 프로젝트 정체성

**SMIM (In the stock market, information matters / 주식은 정보다)**
국내 증시(코스피·코스닥) 데이터·공시·뉴스를 AI가 종합 분석해 **매 거래일 아침 자동 발행**하는 리서치 저널 사이트.

- 개발·운영: 이태웅 (비개발자. 설명은 쉽고 구체적으로 할 것)
- 배포: GitHub Actions(파이프라인) → Cloudflare Pages(호스팅) → `smim.kr`
- 투자 시계: **중기 (5~25 거래일)**. 단타 아님.

## 절대 원칙 (어길 시 프로젝트 실패)

1. **무료 운영.** 종목 추천의 대가를 받지 않는다. 유료화하는 순간 자본시장법상 유사투자자문업 신고 대상이 될 수 있다. 수익화 기능을 임의로 추가하지 말 것.
2. **`config.py`의 `DISCLAIMER`를 모든 페이지 하단에서 절대 제거하지 말 것.** 투자 권유가 아님을 항상 명시한다.
3. **`data/snapshots/*.json`은 append-only.** 한 번 발행된 판단은 수정·삭제 금지. 이게 이 프로젝트의 신뢰 기반이다.
4. **뉴스 본문 "저장"은 금지, "일회성 참고"는 허용 (2026-07-15 사용자 승인으로 완화).**
   AI 해설(뉴스룸 "AI 해설" 버튼)을 만들 때 원문 기사를 그 순간 가져와 참고하는 것은 허용한다.
   단, 가져온 원문 텍스트는 요약 생성 직후 버리고 **스냅샷·사이트 어디에도 저장하지 않는다** —
   저장·발행되는 건 AI가 직접 쓴 해설 문장뿐이다. 원문 링크는 항상 함께 제공해 독자가 원문을
   직접 확인할 수 있게 한다. 저작권·약관 위반 리스크가 있다는 걸 사용자가 인지하고 승인했다.
   이 완화는 "AI 해설"에만 적용되며, 원문 저장 자체는 여전히 금지다.
5. **AI가 지어낸 숫자는 발행 금지.** `pipeline/agents.py`의 `verify_numbers()` 게이트를 무력화하지 말 것.
6. **AI 실패 시 조용히 기술지표만으로 신호를 내보내지 말 것.** 아무것도 발행하지 않고 경보를 쏜다.

## 아키텍처 (건드리기 전에 이해할 것)

```
run_daily.py            ← 매일 아침 실행되는 오케스트레이터
pipeline/
  universe.py           1차 룰 필터 + DART 리스크 게이트
  agents.py             Bull(매수측) / Bear(리스크측) / Judge(심사역) 3단 AI + 숫자 검증
  watchlist.py          액티브 워치리스트 코호트 (편입→관찰→편출)
  ledger.py             성과 원장 + AI 캘리브레이션 피드백
  chart.py              서버사이드 SVG 차트 (JS 라이브러리 안 씀)
  newsroom.py           뉴스 수집 + AI 태깅(섹터/영향/의미)
  indicators.py         기술적 지표
  sources/
    prices.py           FinanceDataReader (시세·종목리스트)
    dart.py             DART 오픈API (재무·공시)  ※ 네이버 HTML 스크래핑 금지
    news.py             네이버 뉴스 API
    market.py           지수·시장폭·섹터
render/
  build.py              Jinja2 정적 사이트 빌더 (Node 툴체인 0개 — 유지할 것)
  templates/            HTML
  static/style.css      Light Terminal 디자인
  static/live.js        실시간 티커 폴링
functions/api/quotes.js Cloudflare Pages Function (실시간 시세 API)
data/snapshots/         ★ 불변 스냅샷. 하루 1개.
site/                   빌드 산출물 (Cloudflare가 서빙)
tools/                  로컬 개발 도구 (API 비용 0원)
```

## 왜 이렇게 설계했는가 (되돌리지 말 것)

- **Node/Next.js를 쓰지 않는다.** Python이 HTML까지 직접 생성한다. 빌드 툴체인이 없으면 고장날 부품도 없다. 프레임워크 도입 제안 금지.
- **AI를 한 번만 호출하지 않는다.** 한 번 물으면 반드시 후한 답이 나온다. Bull/Bear/Judge 3단 구조는 낙관 편향을 막기 위한 것이다.
- **차트는 서버사이드 SVG.** 로딩 실패가 없고, 인쇄되고, 검색엔진이 읽고, 스냅샷에 영구 동결된다. (실시간 인터랙티브 차트는 TradingView 임베드로 별도 제공)
- **GitHub Actions cron은 지연·누락된다.** 그래서 06:37 / 07:07 / 07:37 3단 트리거. 이미 발행됐으면 스스로 skip.
- **발행 실패 시 어제 리포트가 그대로 살아있다.** 사이트가 빈 화면이 되는 일은 없어야 한다.

## 디자인 방향 (Light Terminal)

- 밝은 배경(`--bg:#F2F4F7`) + 딥 네이비 잉크. **터미널의 밀도, 밝은 톤.**
- 색은 **한국 증시 문법 두 가지뿐**: 상승 적색 `--rise:#E02B20`, 하락 청색 `--fall:#1B5FE0`. 다른 색 추가 금지.
- 폰트 3종: **Archivo**(영문 디스플레이) / **Pretendard**(한글) / **IBM Plex Mono**(숫자) / **Instrument Serif 이탤릭**(액센트)
- 메뉴는 **우측 상단 햄버거 → 우측 드로어**
- 섹션명은 영어 (Report / Market / Newsroom / Watchlist / Track Record / Archive / Methodology)
- 판정 표기: **강력 매수 추천 / 매수 추천 / 관찰 대상** (그냥 "매수"라고 쓰지 말 것 — 단정적으로 들림)
- 훈계조 부제 금지. ("~도 공개합니다" 같은 문구 쓰지 말 것)
- **AI가 만든 티가 나면 실패다.** 전문 개발자가 만든 것처럼 보여야 한다.

## 로컬 개발 (API 비용 0원)

```bash
pip install -r requirements.txt
python tools/demo_seed.py     # 가짜 데이터 생성
python tools/build_demo.py    # 사이트 빌드
python tools/serve.py         # http://localhost:8000
```
디자인만 고칠 땐 `render/` 만 수정하고 `build_demo.py` 재실행. Anthropic 호출 없음.

실데이터 실행 (API 키 필요):
```bash
python run_daily.py --force
python -m render.build
```

## 필요한 환경변수 / GitHub Secrets

| 이름 | 발급처 | 필수 |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com | ✅ |
| `DART_API_KEY` | opendart.fss.or.kr | ✅ |
| `NAVER_CLIENT_ID` | developers.naver.com | ✅ |
| `NAVER_CLIENT_SECRET` | developers.naver.com | ✅ |
| `TELEGRAM_BOT_TOKEN` | @BotFather | 선택 (실패 경보) |
| `TELEGRAM_CHAT_ID` | | 선택 |

## 남은 작업 (우선순위 순)

1. **로컬 실행 확인** — `tools/serve.py`로 사이트가 뜨는지
2. **DART 키 발급 후 실데이터 1회 실행** — `python run_daily.py --force`
3. **GitHub 저장소 생성 + Secrets 등록 + push**
4. **Cloudflare Pages 연결** (Framework: None / Build command: 비움 / Output: `site`)
5. **도메인 `smim.kr` 연결**
6. 기관·외국인 수급 데이터 연동 (현재 `supply` 축은 거래량 기반 추정치)
7. 관리종목·투자경고 실시간 플래그 (현재 DART 공시 키워드로 간접 탐지)
8. 스냅샷 2~3개월 축적 후 백테스트

## 사용자 응대 원칙

- 비개발자다. **터미널 명령어는 복붙 가능하게, 한 번에 한 단계씩** 제시할 것.
- 에러가 나면 원인을 추측만 하지 말고 실제로 실행해서 확인할 것.
- "이게 더 나을지도" 싶으면 적극적으로 제안할 것. 시키는 것만 하지 말 것.
