/* SMIM — 실시간 뉴스.
   F5 없이 새 기사가 계속 올라오고, "n분 전 → 방금" 표시도 계속 갱신된다.
   /api/live-news가 이제 제목 기반 섹터·영향·짧은 이유를 붙여서 보내준다(45초 엣지 캐시
   덕분에 방문자 수와 무관하게 태깅 호출은 45초에 한 번뿐 — live-news.js 상단 주석 참고).
   본문을 읽는 깊은 "AI 해설"은 여전히 다음 정기 발행 때 채워진다.
   워치리스트 종목 연관 표시는 AI 호출 없이 문자열 매칭만으로 그 자리에서 붙인다. */
(function () {
  "use strict";
  const lists = {};
  document.querySelectorAll("[data-newslist]").forEach((el) => {
    lists[el.dataset.newslist === "us" ? "US" : "KR"] = el;
  });
  if (!Object.keys(lists).length) return;

  const seen = new Set();
  Object.values(lists).forEach((list) => {
    list.querySelectorAll("li[data-url]").forEach((li) => seen.add(li.dataset.url));
  });

  const watchNames = {};
  document.querySelectorAll("[data-watch-name]").forEach((el) => {
    watchNames[el.dataset.watchName] = el.dataset.watchCode;
  });

  // 이모지 국기는 OS·폰트에 따라 깨지므로 고정 SVG를 직접 그린다 (외부 데이터 아님 — innerHTML 안전).
  const FLAG_SVG = {
    KR: '<svg class="fico" viewBox="0 0 24 16"><rect width="24" height="16" rx="2" fill="#fff"/><g fill="#000"><rect x="1.8" y="1.4" width="5.4" height="0.8"/><rect x="1.8" y="2.8" width="5.4" height="0.8"/><rect x="1.8" y="4.2" width="5.4" height="0.8"/><rect x="16.8" y="1.4" width="2.05" height="0.8"/><rect x="18.15" y="1.4" width="2.05" height="0.8"/><rect x="16.8" y="2.8" width="5.4" height="0.8"/><rect x="16.8" y="4.2" width="2.05" height="0.8"/><rect x="18.15" y="4.2" width="2.05" height="0.8"/><rect x="1.8" y="11.0" width="5.4" height="0.8"/><rect x="1.8" y="12.4" width="2.05" height="0.8"/><rect x="3.15" y="12.4" width="2.05" height="0.8"/><rect x="1.8" y="13.8" width="5.4" height="0.8"/><rect x="16.8" y="11.0" width="2.05" height="0.8"/><rect x="18.15" y="11.0" width="2.05" height="0.8"/><rect x="16.8" y="12.4" width="2.05" height="0.8"/><rect x="18.15" y="12.4" width="2.05" height="0.8"/><rect x="16.8" y="13.8" width="2.05" height="0.8"/><rect x="18.15" y="13.8" width="2.05" height="0.8"/></g><path d="M12 3.8a4.2 4.2 0 0 1 0 8.4 2.1 2.1 0 0 1 0-4.2 2.1 2.1 0 0 0 0-4.2z" fill="#0047a0"/><path d="M12 12.2a4.2 4.2 0 0 1 0-8.4 2.1 2.1 0 0 1 0 4.2 2.1 2.1 0 0 0 0 4.2z" fill="#cd2e3a"/></svg>',
    US: '<svg class="fico" viewBox="0 0 24 16"><rect width="24" height="16" rx="2" fill="#fff"/><g fill="#B22234"><rect y="0" width="24" height="1.23"/><rect y="2.46" width="24" height="1.23"/><rect y="4.92" width="24" height="1.23"/><rect y="7.38" width="24" height="1.23"/><rect y="9.84" width="24" height="1.23"/><rect y="12.3" width="24" height="1.23"/><rect y="14.76" width="24" height="1.23"/></g><rect width="10" height="8.6" fill="#3C3B6E"/></svg>',
  };

  const IMPACT_KO = { strong_positive: "매우 긍정", positive: "긍정", neutral: "중립", negative: "부정", strong_negative: "매우 부정" };

  function relTime(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const sec = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (sec < 60) return "방금";
    if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
    return `${Math.floor(sec / 86400)}일 전`;
  }

  function related(title) {
    for (const name in watchNames) {
      if (name && title.includes(name)) return { name, code: watchNames[name] };
    }
    return null;
  }

  // 뉴스 제목·링크는 외부 API(네이버·Yahoo)에서 온 신뢰할 수 없는 문자열이라
  // innerHTML로 합치지 않고 DOM을 직접 만든다 (XSS 방지).
  function renderItem(n) {
    const li = document.createElement("li");
    li.className = "ni live-ni" + (n.impact ? ` im-${n.impact}` : "");
    li.dataset.url = n.url;
    li.dataset.sector = n.sector || "기타"; // AI 태깅 실패 시(키 미설정 등) 폴백

    const a = document.createElement("a");
    a.className = "nt";
    a.href = n.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = n.title;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ext");
    svg.setAttribute("viewBox", "0 0 12 12");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = '<path d="M4 2h6v6M10 2L3 9" fill="none" stroke="currentColor" stroke-width="1.3"/>';
    a.appendChild(svg);
    li.appendChild(a);

    const meta = document.createElement("div");
    meta.className = "nmeta";
    if (n.sector) {
      const sectorChip = document.createElement("span");
      sectorChip.className = "chipx";
      sectorChip.textContent = n.sector;
      meta.appendChild(sectorChip);
    }
    if (n.impact) {
      const impChip = document.createElement("span");
      impChip.className = `imp im-${n.impact}`;
      impChip.textContent = IMPACT_KO[n.impact] || "중립";
      meta.appendChild(impChip);
    }
    const badge = document.createElement("span");
    badge.className = "chipx live";
    badge.innerHTML = FLAG_SVG[n.market === "US" ? "US" : "KR"];
    badge.append(" 실시간");
    const time = document.createElement("time");
    time.className = "rt";
    time.dataset.published = n.published;
    time.textContent = relTime(n.published);
    meta.append(badge, time);
    li.appendChild(meta);

    if (n.why) {
      const why = document.createElement("p");
      why.className = "nwhy";
      why.textContent = n.why;
      li.appendChild(why);
    }

    const rel = related(n.title);
    if (rel) {
      const p = document.createElement("p");
      p.className = "nlink";
      p.append("Watchlist 연관");
      const link = document.createElement("a");
      link.href = `/stock/${rel.code}/`;
      link.textContent = rel.name;
      p.appendChild(link);
      li.appendChild(p);
    }
    return li;
  }

  async function poll() {
    try {
      const r = await fetch("/api/live-news", { cache: "no-store" });
      if (!r.ok) return;
      const j = await r.json();
      const fresh = (j.items || []).filter((n) => n.url && n.title && !seen.has(n.url));
      fresh.reverse().forEach((n) => {
        const list = lists[n.market === "US" ? "US" : "KR"];
        if (!list) return; // 이 페이지에 해당 시장 목록이 없으면(다른 페이지) 무시
        seen.add(n.url);
        list.insertBefore(renderItem(n), list.firstChild);
      });
    } catch (e) { /* 실패해도 화면에 있는 기사는 그대로 유지 */ }
  }

  function tickClocks() {
    document.querySelectorAll("time.rt[data-published]").forEach((t) => {
      t.textContent = relTime(t.dataset.published);
    });
  }

  poll();
  setInterval(poll, 60000);
  setInterval(tickClocks, 30000);
})();
