/* SMIM — 라이브 시세.
   Cloudflare Pages Function(/api/quotes)을 15초마다 폴링한다.
   값이 바뀌면 숫자가 튀어오르고, 오르면 적색 / 내리면 청색으로 깜빡인다.
   API가 죽어도 HTML에 박힌 종가 값이 그대로 남으므로 화면은 절대 비지 않는다.

   종목추천(판정·논거·편입가)은 하루 단위 스냅샷 그대로 고정이지만,
   화면에 보이는 현재가·수익률은 [data-live-stock] 요소를 통해 장중 실시간으로 갱신한다. */
(function () {
  "use strict";
  const box = document.getElementById("quotes");
  const stamp = document.getElementById("tstamp");
  const tape = document.getElementById("tape");

  const stockEls = document.querySelectorAll("[data-live-stock]");
  const stockMeta = {}; // code -> { market, entry }
  stockEls.forEach((el) => {
    const code = el.dataset.code;
    if (!code) return;
    stockMeta[code] = {
      market: el.dataset.market || "KOSPI",
      entry: parseFloat(el.dataset.entry),
    };
  });
  const codesParam = Object.entries(stockMeta)
    .map(([code, m]) => `${code}:${m.market}`)
    .join(",");

  if (!box && !codesParam) return;

  const prev = {};
  const fmt = (v) => v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtWon = (v) => Math.round(v).toLocaleString("ko-KR");
  const fmtPct = (v) => (v > 0 ? "+" : "") + v.toFixed(2) + "%";

  function tick(el, oldVal, newVal) {
    if (oldVal !== undefined && oldVal !== newVal) {
      el.classList.remove("tick-up", "tick-dn");
      void el.offsetWidth;                       // 리플로우 강제 → 애니메이션 재시작
      el.classList.add(newVal > oldVal ? "tick-up" : "tick-dn");
    }
  }

  function paint(q) {
    if (!box) return;
    const el = box.querySelector(`[data-t="${q.ticker}"]`);
    if (!el) return;
    const vEl = el.querySelector(".v");
    const cEl = el.querySelector(".c");
    const old = prev[q.ticker];

    vEl.textContent = fmt(q.value);
    cEl.textContent = fmtPct(q.change_pct);
    cEl.className = "c " + (q.change_pct > 0 ? "rise" : q.change_pct < 0 ? "fall" : "flat");

    tick(el, old, q.value);
    prev[q.ticker] = q.value;
  }

  function paintStock(q) {
    const meta = stockMeta[q.ticker];
    if (!meta) return;
    const retPct = meta.entry ? ((q.value / meta.entry) - 1) * 100 : null;
    const sign = retPct === null ? "flat" : retPct > 0 ? "rise" : retPct < 0 ? "fall" : "flat";
    const old = prev[q.ticker];

    document.querySelectorAll(`[data-live-stock][data-code="${q.ticker}"]`).forEach((el) => {
      const priceEl = el.querySelector('[data-field="price"]');
      const retEl = el.querySelector('[data-field="return"]');
      const tileEl = el.querySelector(".mono-tile");

      if (priceEl) priceEl.textContent = fmtWon(q.value);
      if (retEl && retPct !== null) {
        // 일부 마크업은 <td data-field="return"><b>텍스트</b></td> 구조라
        // 안쪽 <b>만 바꿔야 굵은 글씨가 유지된다. <b>가 없으면 자기 자신을 쓴다.
        (retEl.querySelector("b") || retEl).textContent = fmtPct(retPct);
        retEl.classList.remove("rise", "fall", "flat");
        retEl.classList.add(sign);
      }
      if (tileEl) {
        tileEl.classList.remove("up", "dn");
        if (sign === "rise") tileEl.classList.add("up");
        if (sign === "fall") tileEl.classList.add("dn");
      }
      el.classList.remove("rise", "fall", "flat");
      if (el.classList.contains("chip")) el.classList.add(sign);

      tick(el, old, q.value);
    });
    prev[q.ticker] = q.value;
  }

  let fails = 0;
  async function poll() {
    try {
      const qs = codesParam ? `?codes=${encodeURIComponent(codesParam)}` : "";
      const r = await fetch(`/api/quotes${qs}`, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      if (!j.quotes || !j.quotes.length) throw new Error("empty");
      j.quotes.forEach((q) => (stockMeta[q.ticker] ? paintStock(q) : paint(q)));
      if (tape) tape.classList.add("is-live");
      if (stamp) {
        const t = new Date(j.ts);
        stamp.textContent =
          String(t.getHours()).padStart(2, "0") + ":" +
          String(t.getMinutes()).padStart(2, "0") + ":" +
          String(t.getSeconds()).padStart(2, "0") + " 기준";
      }
      fails = 0;
    } catch (e) {
      fails++;
      if (fails >= 2) {
        if (tape) tape.classList.remove("is-live");
        if (stamp) stamp.textContent = "전일 종가 기준";
      }
    }
  }

  poll();
  let timer = setInterval(poll, 15000);
  document.addEventListener("visibilitychange", () => {
    clearInterval(timer);
    if (!document.hidden) { poll(); timer = setInterval(poll, 15000); }
  });
})();
