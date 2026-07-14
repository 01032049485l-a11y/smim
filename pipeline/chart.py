"""SVG 가격 차트 생성기.

JS 라이브러리를 쓰지 않는다. 파이썬이 SVG를 직접 그린다.
이유: 로딩 실패가 없고, 인쇄해도 안 깨지고, 검색엔진이 읽고, 영구 보존된다.
      리서치 리포트의 차트는 '인터랙티브'할 필요가 없다. '정확'하면 된다.
"""
from datetime import date

W, H = 720, 240          # viewBox 기준. CSS로 반응형 스케일링.
PAD_L, PAD_R, PAD_T = 8, 52, 12
VOL_H = 42               # 하단 거래량 영역
PLOT_H = H - PAD_T - VOL_H - 22


def _path(pts: list[tuple[float, float]]) -> str:
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _sma(vals: list[float], n: int) -> list[float | None]:
    out, acc = [], 0.0
    for i, v in enumerate(vals):
        acc += v
        if i >= n:
            acc -= vals[i - n]
        out.append(acc / n if i >= n - 1 else None)
    return out


def render(series: dict, entry_price: float | None = None,
           entry_date: str | None = None) -> str:
    """series = {"dates":[...], "close":[...], "volume":[...]} (최근 90거래일)"""
    dates = series.get("dates") or []
    close = series.get("close") or []
    vol = series.get("volume") or []
    n = len(close)
    if n < 20:
        return ""

    ma20 = _sma(close, 20)
    ma60 = _sma(close, 60)

    lo, hi = min(close), max(close)
    span = (hi - lo) or 1
    lo -= span * 0.08
    hi += span * 0.08
    span = hi - lo

    plot_w = W - PAD_L - PAD_R

    def X(i: int) -> float:
        return PAD_L + (i / max(1, n - 1)) * plot_w

    def Y(v: float) -> float:
        return PAD_T + (1 - (v - lo) / span) * PLOT_H

    up = close[-1] >= close[0]
    stroke = "#C0392F" if up else "#1E4FB8"
    fill = "url(#gRise)" if up else "url(#gFall)"

    line = _path([(X(i), Y(v)) for i, v in enumerate(close)])
    area = line + f" L{X(n-1):.1f},{PAD_T+PLOT_H:.1f} L{X(0):.1f},{PAD_T+PLOT_H:.1f} Z"

    def ma_path(ma):
        pts = [(X(i), Y(v)) for i, v in enumerate(ma) if v is not None]
        return _path(pts) if len(pts) > 1 else ""

    p20, p60 = ma_path(ma20), ma_path(ma60)

    # 거래량
    vmax = max(vol) if vol else 1
    bw = max(1.0, plot_w / n * 0.62)
    vy0 = PAD_T + PLOT_H + 18
    bars = []
    for i, v in enumerate(vol):
        h = (v / vmax) * VOL_H if vmax else 0
        c = "#C0392F" if (i == 0 or close[i] >= close[i - 1]) else "#1E4FB8"
        bars.append(
            f'<rect x="{X(i)-bw/2:.1f}" y="{vy0+VOL_H-h:.1f}" width="{bw:.1f}" '
            f'height="{max(0.6,h):.1f}" fill="{c}" opacity=".26"/>'
        )

    # 눈금 (고가 / 저가 / 현재가)
    ticks = []
    for v, cls in ((max(close), "hi"), (min(close), "lo")):
        ticks.append(
            f'<line x1="{PAD_L}" y1="{Y(v):.1f}" x2="{W-PAD_R}" y2="{Y(v):.1f}" '
            f'stroke="#D7DBE0" stroke-width=".7" stroke-dasharray="2 3"/>'
            f'<text x="{W-PAD_R+6}" y="{Y(v)+3.5:.1f}" class="ax">{v:,.0f}</text>'
        )

    # 현재가 라벨
    cy = Y(close[-1])
    ticks.append(
        f'<circle cx="{X(n-1):.1f}" cy="{cy:.1f}" r="3.2" fill="{stroke}"/>'
        f'<rect x="{W-PAD_R+2}" y="{cy-9:.1f}" width="48" height="18" rx="2" fill="{stroke}"/>'
        f'<text x="{W-PAD_R+26}" y="{cy+3.5:.1f}" class="axv" text-anchor="middle">{close[-1]:,.0f}</text>'
    )

    # 편입 시점 마커
    marker = ""
    if entry_date and entry_date in dates:
        i = dates.index(entry_date)
        marker = (
            f'<line x1="{X(i):.1f}" y1="{PAD_T}" x2="{X(i):.1f}" y2="{PAD_T+PLOT_H}" '
            f'stroke="#0F1620" stroke-width="1" stroke-dasharray="3 2" opacity=".55"/>'
            f'<text x="{X(i)+4:.1f}" y="{PAD_T+9}" class="mk">편입</text>'
        )
    elif entry_price:
        marker = (
            f'<line x1="{PAD_L}" y1="{Y(entry_price):.1f}" x2="{W-PAD_R}" y2="{Y(entry_price):.1f}" '
            f'stroke="#0F1620" stroke-width="1" stroke-dasharray="3 2" opacity=".55"/>'
            f'<text x="{PAD_L+4}" y="{Y(entry_price)-5:.1f}" class="mk">편입가 {entry_price:,.0f}</text>'
        )

    # 날짜 축
    xlabels = ""
    for i in (0, n // 2, n - 1):
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        d = dates[i][5:] if i < len(dates) else ""
        xlabels += (f'<text x="{X(i):.1f}" y="{H-4}" class="ax" '
                    f'text-anchor="{anchor}">{d}</text>')

    return f'''<svg class="chart" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img"
 aria-label="최근 {n}거래일 주가 추이">
<defs>
 <linearGradient id="gRise" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#C0392F" stop-opacity=".16"/><stop offset="1" stop-color="#C0392F" stop-opacity="0"/>
 </linearGradient>
 <linearGradient id="gFall" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#1E4FB8" stop-opacity=".16"/><stop offset="1" stop-color="#1E4FB8" stop-opacity="0"/>
 </linearGradient>
</defs>
{''.join(ticks)}
<path d="{area}" fill="{fill}"/>
<path d="{p60}" fill="none" stroke="#9AA2AC" stroke-width="1" stroke-dasharray="4 3"/>
<path d="{p20}" fill="none" stroke="#5B6570" stroke-width="1.1"/>
<path d="{line}" fill="none" stroke="{stroke}" stroke-width="1.9" stroke-linejoin="round"/>
{''.join(bars)}
{marker}
{xlabels}
</svg>'''


def legend() -> str:
    return ('<ul class="chart-legend">'
            '<li><i class="k-price"></i>종가</li>'
            '<li><i class="k-ma20"></i>20일선</li>'
            '<li><i class="k-ma60"></i>60일선</li>'
            '<li><i class="k-vol"></i>거래량</li>'
            '</ul>')


def sparkline(close: list[float], w: int = 96, h: int = 26) -> str:
    """표 안에 들어가는 초소형 추이선."""
    if not close or len(close) < 5:
        return ""
    lo, hi = min(close), max(close)
    span = (hi - lo) or 1
    n = len(close)
    pts = [(i / (n - 1) * w, (1 - (v - lo) / span) * (h - 4) + 2) for i, v in enumerate(close)]
    c = "#C0392F" if close[-1] >= close[0] else "#1E4FB8"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<path d="{_path(pts)}" fill="none" stroke="{c}" stroke-width="1.4"/></svg>')
