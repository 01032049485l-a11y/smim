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

  /* 차트 탭 (실시간 탭은 TradingView 무료 임베드가 국내 개별종목 실시간 데이터를
     제한해 애플 등 엉뚱한 심볼로 대체 표시되는 문제가 있어, 인라인 위젯 대신
     TradingView 페이지로 바로 연결하는 링크로 대체했다 — mountTV()는 더 이상 없음) */
  document.querySelectorAll("[data-tabs]").forEach((box) => {
    box.querySelectorAll(".tb").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = btn.dataset.tab;
        box.querySelectorAll(".tb").forEach((b) => b.classList.toggle("on", b === btn));
        box.querySelectorAll(".tp").forEach((p) => p.classList.toggle("on", p.dataset.panel === t));
      });
    });
  });

  /* 뉴스 섹터 필터 + 노출 개수 제한을 하나의 로직으로 합친다.
     예전엔 필터 클릭과 "노출개수 캡"이 각자 따로 li.hidden을 건드려서 —
     특정 카테고리를 고르면 그 카테고리에 안 맞는 실시간 유입 기사까지
     "전체보기"를 누르면 죄다 다시 보이는 버그가 있었다. 이제 필터·캡·
     실시간 유입(MutationObserver) 전부 recompute() 한 곳에서 계산한다. */
  const fb = document.querySelector("[data-filters]");
  const nls = document.querySelectorAll("[data-newslist]");
  const NEWS_CAP = 8;
  let activeFilter = "all";
  const capOn = new Map();   // nl -> 아직 캡이 걸려있는지
  const moreBtn = new Map(); // nl -> "전체보기" 버튼 엘리먼트

  function matches(li) {
    return activeFilter === "all" || li.dataset.sector === activeFilter;
  }

  function recompute(nl) {
    const items = Array.from(nl.children);
    const total = items.filter(matches).length;
    const capped = capOn.get(nl);
    let shown = 0;
    items.forEach((li) => {
      if (!matches(li)) { li.hidden = true; return; }
      if (capped && shown >= NEWS_CAP) { li.hidden = true; return; }
      li.hidden = false;
      shown++;
    });

    let btn = moreBtn.get(nl);
    if (capped && total > NEWS_CAP) {
      if (!btn) {
        btn = document.createElement("button");
        btn.type = "button";
        btn.className = "more-news";
        btn.addEventListener("click", () => { capOn.set(nl, false); recompute(nl); });
        nl.insertAdjacentElement("afterend", btn);
        moreBtn.set(nl, btn);
      }
      btn.textContent = `전체보기 (총 ${total}건)`;
    } else if (btn) {
      btn.remove();
      moreBtn.delete(nl);
    }
  }

  nls.forEach((nl) => {
    capOn.set(nl, true);
    new MutationObserver(() => recompute(nl)).observe(nl, { childList: true });
    recompute(nl);
  });

  if (fb && nls.length) {
    fb.addEventListener("click", (e) => {
      const b = e.target.closest(".fb");
      if (!b) return;
      fb.querySelectorAll(".fb").forEach((x) => x.classList.toggle("on", x === b));
      activeFilter = b.dataset.f;
      nls.forEach(recompute);
    });
  }

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
