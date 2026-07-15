/* SMIM — 주말·휴장 안내.
   파이프라인이 아니라 방문 시점의 브라우저에서 시장별 요일을 계산한다.
   리빌드 없이 자정이 지나 평일이 되면 자동으로 사라진다.
   한국(Asia/Seoul)과 미국(America/New_York)은 주말 경계가 달라 각자 판단한다. */
(function () {
  "use strict";
  const MARKETS = {
    kr: { tz: "Asia/Seoul", label: "국내" },
    us: { tz: "America/New_York", label: "미국" },
  };

  // 이모지 국기는 OS·폰트에 따라 깨지므로 고정 SVG를 직접 그린다 (외부 데이터 아님 — innerHTML 안전).
  const FLAG_SVG = {
    kr: '<svg class="fico" viewBox="0 0 24 16"><rect width="24" height="16" rx="2" fill="#fff"/><path d="M12 3.8a4.2 4.2 0 0 1 0 8.4 2.1 2.1 0 0 1 0-4.2 2.1 2.1 0 0 0 0-4.2z" fill="#0047a0"/><path d="M12 12.2a4.2 4.2 0 0 1 0-8.4 2.1 2.1 0 0 1 0 4.2 2.1 2.1 0 0 0 0 4.2z" fill="#cd2e3a"/></svg>',
    us: '<svg class="fico" viewBox="0 0 24 16"><rect width="24" height="16" rx="2" fill="#fff"/><g fill="#B22234"><rect y="0" width="24" height="1.23"/><rect y="2.46" width="24" height="1.23"/><rect y="4.92" width="24" height="1.23"/><rect y="7.38" width="24" height="1.23"/><rect y="9.84" width="24" height="1.23"/><rect y="12.3" width="24" height="1.23"/><rect y="14.76" width="24" height="1.23"/></g><rect width="10" height="8.6" fill="#3C3B6E"/></svg>',
  };

  function isWeekend(tz) {
    const day = new Intl.DateTimeFormat("en-US", { timeZone: tz, weekday: "short" }).format(new Date());
    return day === "Sat" || day === "Sun";
  }

  function banner(mk, code) {
    const div = document.createElement("div");
    div.className = "market-closed";
    div.innerHTML =
      `<b>${FLAG_SVG[code]} ${mk.label} 증시 휴장 중</b>` +
      `<span>신규 판단은 다음 거래일 개장 전 갱신됩니다. 뉴스·시세는 휴장 중에도 실시간으로 계속 올라옵니다.</span>`;
    return div;
  }

  document.querySelectorAll(".market-tabs > [data-panel]").forEach((panel) => {
    const code = panel.dataset.panel;
    const mk = MARKETS[code];
    if (!mk || !isWeekend(mk.tz)) return;
    const hero = panel.querySelector(".hero");
    if (hero) hero.insertAdjacentElement("afterend", banner(mk, code));
    else panel.insertBefore(banner(mk, code), panel.firstChild);
  });
})();
