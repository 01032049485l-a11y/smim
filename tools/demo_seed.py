"""로컬 디자인 작업용 가짜 데이터 생성기 (한국·미국 둘 다).

API 키 없이, 비용 0원으로 사이트 전체를 렌더링해볼 수 있다.
    python tools/demo_seed.py && python -m render.build && python tools/serve.py
※ 실제 종목이 아니다. data/snapshots/ 에 넣지 말 것 — demo 폴더에만 쓴다.
"""
import os, sys, math, json, random, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

random.seed(7)
DEMO_SNAP_DIR = os.path.join(config.DATA_DIR, "demo", "snapshots")
os.makedirs(os.path.join(DEMO_SNAP_DIR, "kr"), exist_ok=True)
os.makedirs(os.path.join(DEMO_SNAP_DIR, "us"), exist_ok=True)

TODAY = dt.date.today()

def walk(start, n=90, drift=0.0015, vol=0.018):
    out, p = [], start
    for i in range(n):
        p *= (1 + random.gauss(drift, vol))
        out.append(round(p, 0))
    return out

def series(start):
    c = walk(start)
    base = TODAY - dt.timedelta(days=130)
    dates, i = [], 0
    d = base
    while len(dates) < len(c):
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    return {"dates": dates, "close": c,
            "volume": [round(abs(random.gauss(1, .45)) * 900000) for _ in c]}

def tech(close, r20, rsi, pos):
    return {"close":close,"change_1d_pct":round(random.uniform(-1.5,2.5),2),
      "change_5d_pct":round(random.uniform(-3,6),2),"change_20d_pct":r20,
      "ma5":close-200,"ma20":close-900,"ma60":close-2400,"ma120":close-3800,
      "above_ma20":True,"above_ma60":True,"golden_cross_20_60":True,
      "rsi14":rsi,"macd_hist":42.1,"macd_turning_up":True,"volume_ratio_vs_20d":1.9,
      "avg_trading_value_20d":random.randint(8,40)*1_000_000_000,
      "pos_in_52w_range_pct":pos,"high_52w":close+9000,"low_52w":close-15000,
      "volatility_20d_pct":2.4,"limit_up_yesterday":False}

def mk(code,name,market,entry,cur,status,verdict,conf,sc,ed,days,market_group="KR"):
    filing_url = "https://sec.gov" if market_group == "US" else "https://dart.fss.or.kr"
    return {"code":code,"name":name,"market":market,"market_group":market_group,"entry_date":ed,
      "entry_price":entry,"current_price":cur,
      "return_pct":round((cur/entry-1)*100,2),"days_held":days,"status":status,
      "verdict":verdict,"confidence":conf,"target_return_pct":random.choice([8,10,12,14,15]),
      "stop_loss_pct":random.choice([-5,-6,-7,-8,-9,-10]),
      "horizon_days":random.choice([10,15,20]),
      "invalidation":"20일 이동평균선을 종가 기준으로 이탈할 경우 상승 논리가 훼손된 것으로 본다.",
      "thesis":"전력 인프라 증설 사이클의 직접 수혜 구간에 진입했다. 20일선과 60일선이 골든크로스를 형성한 직후이며, 거래량이 20일 평균 대비 1.9배로 확대돼 실제 수급이 유입되고 있음이 확인된다. 지난 사업연도 영업이익이 전년 대비 개선됐고 부채비율도 안정적 범위에 있다. 다만 최근 20일간 상승 폭이 작지 않아 단기 조정 가능성은 열려 있으며, 일시 매수보다 분할 접근이 합리적이다. 중기 관점에서 추가 상승 여력이 남아 있다고 판단한다.",
      "scorecard":sc,
      "bull_points":["20일선과 60일선이 골든크로스를 형성해 중기 추세가 전환되는 구간이다.",
        "거래량이 20일 평균의 1.9배로 늘어 실수급 유입이 확인된다.",
        "직전 사업연도 영업이익이 전년 대비 개선되며 실적 방향성이 우호적이다.",
        "RSI 61 수준으로 과열 구간에 진입하지 않았다."],
      "bear_points":["최근 20일간 상승 폭이 커 단기 차익실현 압력이 존재한다.",
        "동종 업종 평균 대비 밸류에이션 부담이 있다.",
        "전방 발주가 지연될 경우 모멘텀이 빠르게 약화될 수 있다."],
      "news":[{"title":"전력기기 업계, 하반기 수주 확대 전망","url":"https://www.hankyung.com","published":str(TODAY-dt.timedelta(days=1)),"sector":"건설·기계","impact":"positive","why":"업종 전반의 수주 환경이 개선되면 관련 부품·소재 기업의 실적 가시성이 높아진다."},
        {"title":f"{name}, 신규 생산라인 증설 검토","url":"https://www.mk.co.kr","published":str(TODAY-dt.timedelta(days=3)),"sector":"건설·기계","impact":"positive","why":"증설은 수요 확신의 신호일 수 있으나, 확정 공시 여부는 확인이 필요하다."},
        {"title":"원자재 가격 변동성 확대…소재주 부담 우려","url":"https://www.sedaily.com","published":str(TODAY-dt.timedelta(days=5)),"sector":"소비재","impact":"negative","why":"투입 원가 상승은 마진을 압박할 수 있어 실적 발표 시 확인이 필요하다."}],
      "filings":[{"date":(TODAY-dt.timedelta(days=12)).strftime("%Y%m%d"),"title":"단일판매·공급계약체결","url":filing_url}],
      "tech":tech(cur,round(random.uniform(4,20),1),round(random.uniform(48,68),1),round(random.uniform(40,85),1)),
      "financials":{"fiscal_year":TODAY.year-1,"revenue":random.randint(4,30)*1e11,
        "revenue_yoy_pct":round(random.uniform(-5,28),1),
        "operating_profit":random.randint(3,20)*1e10,
        "operating_profit_yoy_pct":round(random.uniform(-12,45),1),
        "net_income":random.randint(2,15)*1e10,"debt_ratio_pct":round(random.uniform(45,120),1)},
      "series":series(entry*0.85),"updated":str(TODAY)}

def idx(label,ticker,v,ch):
    s=[round(v*(1+random.gauss(0,.006)),2) for _ in range(29)]+[v]
    t="up" if ch>0.5 else "down" if ch<-0.5 else "flat"
    return {"label":label,"ticker":ticker,"value":v,"change":round(v*ch/100,2),"change_pct":ch,
            "trend":t,"trend_label":{"up":"상승세","down":"하락세","flat":"보합권"}[t],"series":s}

MARKET_CTX = {"indices":[idx("코스피","KOSPI",2734.51,0.62),idx("코스닥","KOSDAQ",881.24,-0.41),
   idx("원/달러","USDKRW",1362.40,-0.18),idx("S&P 500","SPX",5921.33,0.31),idx("나스닥","NASDAQ",19544.10,0.77)],
  "up":512,"down":388,"flat":41,"up_ratio":54.4,"mood":"혼조",
  "sectors":[{"name":"반도체","change_pct":2.14,"count":48},{"name":"조선·방산","change_pct":1.62,"count":22},
   {"name":"건설·기계","change_pct":0.94,"count":61},{"name":"IT·플랫폼","change_pct":0.41,"count":54},
   {"name":"금융","change_pct":0.12,"count":37},{"name":"소비재","change_pct":-0.33,"count":72},
   {"name":"바이오","change_pct":-0.88,"count":91},{"name":"2차전지","change_pct":-1.74,"count":33}]}

MODELS = {"bull":config.BULL_MODEL,"bear":config.BEAR_MODEL,"judge":config.JUDGE_MODEL,"news":config.NEWSTAG_MODEL}
P = lambda a,b,c,d,e: {"price":a,"fundamental":b,"supply":c,"news":d,"valuation":e}

# ── 한국 ──────────────────────────────────────────────────
new_kr = [
 mk("900001","한빛소재","KOSPI",42350,42350,"new","STRONG_BUY",82,P("positive","positive","positive","neutral","negative"),str(TODAY),0),
 mk("900002","다온전자","KOSDAQ",18700,18700,"new","BUY",74,P("positive","neutral","positive","positive","neutral"),str(TODAY),0),
]
hold_kr = [
 mk("900003","세림바이오","KOSPI",61200,65400,"holding","BUY",76,P("positive","positive","neutral","positive","neutral"),str(TODAY-dt.timedelta(days=7)),5),
 mk("900004","우진케미칼","KOSDAQ",25400,24100,"holding","BUY",71,P("negative","positive","negative","neutral","positive"),str(TODAY-dt.timedelta(days=12)),8),
 mk("900005","대성네트웍스","KOSPI",9880,10520,"holding","BUY",73,P("positive","neutral","positive","neutral","positive"),str(TODAY-dt.timedelta(days=14)),10),
 mk("900012","동림에너지","KOSPI",31200,32950,"holding","STRONG_BUY",80,P("positive","positive","positive","positive","neutral"),str(TODAY-dt.timedelta(days=5)),4),
]
exits_kr = [
 mk("900006","현진테크","KOSPI",33000,38050,"target_hit","BUY",79,P("positive","positive","positive","neutral","neutral"),str(TODAY-dt.timedelta(days=28)),19),
 mk("900007","남광정밀","KOSDAQ",14200,12950,"stopped","BUY",72,P("negative","neutral","negative","negative","positive"),str(TODAY-dt.timedelta(days=21)),14),
]
for e in exits_kr:
    e["exit_date"]=str(TODAY); e["exit_price"]=e["current_price"]

NEWS=[("코스피, 외국인 순매수 유입에 이틀째 상승","증시일반","positive","외국인 수급이 이어지면 대형주 중심의 지수 상승 탄력이 유지될 수 있다.",[]),
 ("반도체 업황 개선 신호…메모리 가격 반등, 다온전자 실적 서프라이즈","반도체","strong_positive","메모리 가격 반등은 관련 소재·장비주의 실적 개선으로 이어지는 경우가 많다.",["다온전자"]),
 ("2차전지, 전기차 수요 둔화 우려에 약세…현진테크 감산 검토","2차전지","strong_negative","전방 수요 둔화는 배터리 셀·소재 업체의 가동률과 마진을 동시에 압박한다.",["현진테크"]),
 ("원/달러 환율 소폭 하락 마감","거시·환율","neutral","환율 하락은 수입 원가에 유리하나 수출주에는 부담이 될 수 있다.",[]),
 ("바이오, 임상 결과 발표 앞두고 관망세","바이오","neutral","이벤트 전 관망 구간으로, 결과에 따라 변동성이 크게 확대될 수 있다.",[]),
 ("조선주, 수주 잔고 확대에 강세","조선·방산","positive","수주 잔고 확대는 향후 수년간의 매출 가시성을 높인다.",[]),
 ("금리 동결 전망 우세…은행주 혼조","금융","neutral","금리 동결은 순이자마진에 중립적이며, 대출 성장률이 관건이다.",[]),
 ("건설, 미분양 지표 개선 조짐","건설·기계","positive","미분양 축소는 건설사의 운전자본 부담을 완화한다.",[])]
newsroom=[]
for i,(t,sc,im,why,tk) in enumerate(NEWS):
    newsroom.append({"title":t,"url":"https://finance.naver.com","published":f"{TODAY-dt.timedelta(days=i%2)} {14-i:02d}:{(i*7)%60:02d}",
      "topic":sc,"sector":sc,"impact":im,"why":why,"tickers":tk,"watchlist_hits":[]})
newsroom[1]["watchlist_hits"]=[{"name":"다온전자","code":"900002"}]

snap_kr={"date":str(TODAY),"market_group":"KR","report_id":f"SMIM-KR-{TODAY.strftime('%Y-%m%d')}","issue_no":37,
 "published_at":f"{TODAY}T07:12:04+09:00","models":MODELS,"market":MARKET_CTX,
 "new_entries":new_kr,"holdings":hold_kr,"exits":exits_kr,
 "rejected":[{"name":"태현산업","reason":"리스크 공시 · 전환사채"},
   {"name":"보광엔지","reason":"관찰 대상 · 확신도 63"},
   {"name":"세강모빌리티","reason":"수치 검증 실패 · 원본 미확인 숫자 포함"},
   {"name":"청암정밀","reason":"20일 평균 거래대금 기준 미달"}],
 "newsroom":newsroom,"ledger":{},"universe_scanned":214,"ai_calls":12,
 "ai_usage":{"by_model":{},"estimated_cost_usd":0.0}}
json.dump(snap_kr, open(os.path.join(DEMO_SNAP_DIR,"kr",f"{TODAY}.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)

# ── 미국 (탭 전환 확인용, 소규모) ───────────────────────────
new_us = [
 mk("NVLT","엔비라이트","NASDAQ",412.30,412.30,"new","BUY",77,P("positive","positive","neutral","positive","negative"),str(TODAY),0,"US"),
]
hold_us = [
 mk("QTRX","퀀트릭스","NASDAQ",88.40,93.10,"holding","BUY",73,P("positive","neutral","positive","neutral","positive"),str(TODAY-dt.timedelta(days=9)),6,"US"),
]
newsroom_us=[]
for i,(t,sc,im,why,tk) in enumerate(NEWS[:5]):
    newsroom_us.append({"title":t,"url":"https://finance.yahoo.com","published":f"{TODAY-dt.timedelta(days=i%2)} {13-i:02d}:{(i*11)%60:02d}",
      "topic":sc,"sector":sc,"impact":im,"why":why,"tickers":tk,"watchlist_hits":[]})

snap_us={"date":str(TODAY),"market_group":"US","report_id":f"SMIM-US-{TODAY.strftime('%Y-%m%d')}","issue_no":5,
 "published_at":f"{TODAY}T20:12:04+09:00","models":MODELS,"market":MARKET_CTX,
 "new_entries":new_us,"holdings":hold_us,"exits":[],
 "rejected":[{"name":"Solara Systems","reason":"WATCH · 확신도 58"}],
 "newsroom":newsroom_us,"ledger":{},"universe_scanned":89,"ai_calls":6,
 "ai_usage":{"by_model":{},"estimated_cost_usd":0.0}}
json.dump(snap_us, open(os.path.join(DEMO_SNAP_DIR,"us",f"{TODAY}.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)

book=[{"code":"900006","name":"현진테크","market_group":"KR","entry_date":str(TODAY-dt.timedelta(days=28)),"entry_price":33000,"exit_date":str(TODAY),"exit_price":38050,"return_pct":15.3,"days_held":19,"status":"target_hit","verdict":"BUY","confidence":79},
 {"code":"900007","name":"남광정밀","market_group":"KR","entry_date":str(TODAY-dt.timedelta(days=21)),"entry_price":14200,"exit_date":str(TODAY),"exit_price":12950,"return_pct":-8.8,"days_held":14,"status":"stopped","verdict":"BUY","confidence":72},
 {"code":"900008","name":"청우머티리얼","market_group":"KR","entry_date":str(TODAY-dt.timedelta(days=39)),"entry_price":21500,"exit_date":str(TODAY-dt.timedelta(days=11)),"exit_price":24300,"return_pct":13.02,"days_held":20,"status":"expired","verdict":"BUY","confidence":75},
 {"code":"900009","name":"동방플랜트","market_group":"KR","entry_date":str(TODAY-dt.timedelta(days=34)),"entry_price":8700,"exit_date":str(TODAY-dt.timedelta(days=17)),"exit_price":10100,"return_pct":16.09,"days_held":13,"status":"target_hit","verdict":"STRONG_BUY","confidence":84},
 {"code":"900010","name":"신흥로보틱스","market_group":"KR","entry_date":str(TODAY-dt.timedelta(days=42)),"entry_price":45000,"exit_date":str(TODAY-dt.timedelta(days=24)),"exit_price":41100,"return_pct":-8.67,"days_held":14,"status":"stopped","verdict":"BUY","confidence":71},
 {"code":"900011","name":"제일화학","market_group":"KR","entry_date":str(TODAY-dt.timedelta(days=47)),"entry_price":17800,"exit_date":str(TODAY-dt.timedelta(days=26)),"exit_price":19200,"return_pct":7.87,"days_held":15,"status":"expired","verdict":"BUY","confidence":73}]
json.dump(book,open(os.path.join(config.DATA_DIR,"demo","ledger.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("demo 데이터 생성 완료 (KR+US) → data/demo/")
