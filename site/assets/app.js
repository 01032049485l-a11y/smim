/* SMIM — 드로어(우측), 차트 탭, TradingView 지연 로딩, 뉴스 필터, 스크롤 리빌, 카운트업 */
(function () {
  "use strict";

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

  /* 뉴스 섹터 필터 */
  const fb = document.querySelector("[data-filters]");
  const nl = document.querySelector("[data-newslist]");
  if (fb && nl) {
    fb.addEventListener("click", (e) => {
      const b = e.target.closest(".fb");
      if (!b) return;
      fb.querySelectorAll(".fb").forEach((x) => x.classList.toggle("on", x === b));
      nl.querySelectorAll("li").forEach((li) => { li.hidden = !(b.dataset.f === "all" || li.dataset.sector === b.dataset.f); });
    });
  }

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
