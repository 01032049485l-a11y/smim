/* SMIM — 드로어(우측), 차트 탭, TradingView 지연 로딩, 뉴스 필터, 스크롤 리빌, 카운트업, 실시간 시계 */
(function () {
  "use strict";

  /* 상단 티커의 한국/미국 실시간 시계 — 서버 배치 없이 방문자 브라우저에서 매초 갱신 */
  const clocks = document.querySelectorAll("[data-clock]");
  if (clocks.length) {
    const fmt = {
      kr: new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }),
      us: new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }),
    };
    const tickClock = () => {
      const now = new Date();
      clocks.forEach((el) => {
        const key = el.dataset.clock;
        const b = el.querySelector(".ct");
        if (b && fmt[key]) b.textContent = (key === "us" ? "ET " : "KST ") + fmt[key].format(now);
      });
    };
    tickClock();
    setInterval(tickClock, 1000);
  }

  /* 우측 드로어 */
  const dr = document.getElementById("drawer");
  const sc = document.getElementById("scrim");
  const bg = document.getElementById("burger");
  const cx = document.getElementById("drClose");
  function setDrawer(o) {
    if (!dr) return;
    dr.classList.toggle("open", o);
    dr.setAttribute("aria-hidden", String(!o));
    if (bg) bg.classList.toggle("x", o);
    if (sc) sc.hidden = !o;
    document.body.style.overflow = o ? "hidden" : "";
  }
  bg && bg.addEventListener("click", () => setDrawer(!dr.classList.contains("open")));
  cx && cx.addEventListener("click", () => setDrawer(false));
  sc && sc.addEventListener("click", () => setDrawer(false));
  document.addEventListener("keydown", (e) => e.key === "Escape" && setDrawer(false));

  /* 차트 탭 */
  document.querySelectorAll("[data-tabs]").forEach((box) => {
    box.querySelectorAll(".tb").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = btn.dataset.tab;
        box.querySelectorAll(".tb").forEach((b) => b.classList.toggle("on", b === btn));
        box.querySelectorAll(".tp").forEach((p) => p.classList.toggle("on", p.dataset.panel === t));
        if (t === "live") mountTV(box.querySelector("[data-tv]"));
      });
    });
  });

  function mountTV(el) {
    if (!el || el.dataset.mounted) return;
    el.dataset.mounted = "1";
    const tall = el.dataset.tall === "1";
    el.innerHTML = "";
    const h = document.createElement("div");
    h.className = "tv-widget";
    h.style.height = tall ? "560px" : "400px";
    el.appendChild(h);
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol: "KRX:" + el.dataset.tv, interval: "D", timezone: "Asia/Seoul",
      theme: "light", style: "1", locale: "kr", hide_side_toolbar: !tall,
      allow_symbol_change: false, withdateranges: true, autosize: true,
      studies: tall ? ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"] : ["MASimple@tv-basicstudies"],
    });
    h.appendChild(s);
  }
  const io0 = "IntersectionObserver" in window
    ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { mountTV(e.target); io0.unobserve(e.target); } }), { rootMargin: "300px" })
    : null;
  document.querySelectorAll('[data-tv][data-tall="1"]').forEach((el) => io0 ? io0.observe(el) : mountTV(el));

  /* 뉴스 섹터 필터 — 한국/미국 두 목록에 동시에 적용된다 */
  const fb = document.querySelector("[data-filters]");
  const nls = document.querySelectorAll("[data-newslist]");
  if (fb && nls.length) {
    fb.addEventListener("click", (e) => {
      const b = e.target.closest(".fb");
      if (!b) return;
      fb.querySelectorAll(".fb").forEach((x) => x.classList.toggle("on", x === b));
      nls.forEach((nl) => nl.querySelectorAll("li").forEach((li) => {
        li.hidden = !(b.dataset.f === "all" || li.dataset.sector === b.dataset.f);
      }));
    });
  }

  /* 뉴스 목록 기본 노출 개수 제한 — 모바일에서 한쪽(주로 한국) 목록이 너무 길어
     반대쪽 목록을 보려면 한참 스크롤해야 하던 문제를 막는다. 필터를 누르면
     걸려있던 제한은 자동으로 풀린다(위 필터 로직이 hidden을 다시 계산하므로). */
  const NEWS_CAP = 6;
  nls.forEach((nl) => {
    const items = Array.from(nl.querySelectorAll("li"));
    if (items.length <= NEWS_CAP) return;
    items.slice(NEWS_CAP).forEach((li) => { li.hidden = true; });
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "more-news";
    btn.textContent = `전체보기 (총 ${items.length}건)`;
    btn.addEventListener("click", () => {
      items.forEach((li) => { li.hidden = false; });
      btn.remove();
    });
    nl.insertAdjacentElement("afterend", btn);
  });

  /* "AI 해설" 펼치기/접기 — 제목 기반 해설이라 클릭 전엔 숨겨둔다 */
  document.querySelectorAll("[data-ai-explain]").forEach((btn) => {
    const body = btn.nextElementSibling;
    if (!body || !body.classList.contains("ai-explain-body")) return;
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      body.hidden = open;
    });
  });

  /* 스크롤 리빌 */
  if ("IntersectionObserver" in window && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }), { threshold: 0.08, rootMargin: "0px 0px -40px" });
    document.querySelectorAll("[data-rv]").forEach((el) => io.observe(el));
  } else {
    document.querySelectorAll("[data-rv]").forEach((el) => el.classList.add("in"));
  }

  /* 숫자 카운트업 */
  function up(el) {
    const t = parseFloat(el.dataset.n), d = +(el.dataset.d || 0);
    let s0 = null;
    function f(ts) {
      if (!s0) s0 = ts;
      const p = Math.min((ts - s0) / 900, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = (t * e).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
      if (p < 1) requestAnimationFrame(f);
    }
    requestAnimationFrame(f);
  }
  if ("IntersectionObserver" in window) {
    const io2 = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { up(e.target); io2.unobserve(e.target); }
    }), { threshold: 0.6 });
    document.querySelectorAll("[data-n]").forEach((el) => io2.observe(el));
  }
})();
