/* L.SPACE Biz Radar — 공고 목록 렌더 · 필터 · D-day.
   데이터: data/notices.json (공고), data/meta.json (마지막 실행). 상태(접수예정/접수중/임박/마감)는 저장하지 않고 여기서 계산한다. */
(function () {
  "use strict";

  const TYPES = { rnd: "국가R&D", support: "지원사업", bid: "SW입찰" };
  const FIT = { high: "적합도 높음", mid: "적합도 보통" };
  const MARK = { ok: ["✓", "충족"], partial: ["△", "부분"], no: ["✗", "불충족"], check: ["?", "확인 필요"] };
  const SHORT = { "분야": "분야", "주관 자격": "주관", "지역": "지역", "부담·조건": "부담" };
  const URGENT_DAYS = 7;
  const STALE_HOURS = 26; // 매일 07:00 수집 — 이보다 오래되면 자동 수집이 멈춘 것으로 본다
  // 수집 소스 (collect.py SOURCES 와 같은 이름). 상태는 meta.json sources 에서 온다
  const SOURCES = [
    ["ntis", "NTIS", "국가R&D 통합공고", "https://www.ntis.go.kr/rndgate/eg/un/ra/mng.do"],
    ["iris", "IRIS", "범부처통합연구지원시스템", "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do"],
    ["bizinfo", "기업마당", "정부 지원사업 통합공고", "https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do"],
    ["nipa", "NIPA", "정보통신산업진흥원 사업공고", "https://www.nipa.kr/home/2-2"],
    ["rims", "중소조선연구원", "사업공고 · 입찰공고", "https://www.rims.re.kr/bbs/board.php?bo_table=m0602"],
    ["btp", "부산테크노파크", "사업공고", "https://www.btp.or.kr/kor/CMS/Board/Board.do?mCode=MN013"],
    ["gntp", "경남테크노파크", "지원사업 신청", "https://www.gntp.or.kr/biz/apply"],
    ["ccei_bs", "부산창조경제혁신센터", "공지사항 · 입찰공고", "https://ccei.creativekorea.or.kr/busan/custom/notice_list.do"],
    ["ccei_gn", "경남창조경제혁신센터", "사업공고 · 입찰공고", "https://ccei.creativekorea.or.kr/gyeongnam/allim/allim_list.do?div_code=1"],
  ];
  const $ = (s, el = document) => el.querySelector(s);

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // KST 기준 지금 (YYYY-MM-DDTHH:MM) — 앞 10자리가 오늘
  function nowKST() {
    return new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 16);
  }
  function dayDiff(a, b) {
    return Math.round((Date.parse(b) - Date.parse(a)) / 86400e3);
  }
  const md = (d) => (d ? d.slice(5, 10).replace("-", ".") : "");
  const wd = (d) => "일월화수목금토"[new Date(d.slice(0, 10) + "T00:00Z").getUTCDay()];

  // 마감 상태: closed / urgent(D-7 이내) / open / soon(접수 시작 전) / always(마감일 없음)
  // 마감 시각이 있으면 그 시각이 지나는 순간 마감, 날짜만 있으면 그날 자정이 지나야 마감.
  function stateOf(n, now) {
    const today = now.slice(0, 10);
    const end = n.deadline ? n.deadline.slice(0, 10) : "";
    if (!end) return { key: "always", label: "상시", sub: "마감일 공고문 확인" };
    const left = dayDiff(today, end);
    const hasTime = n.deadline.length > 10;
    const sub = `${md(end)}${hasTime ? " " + n.deadline.slice(11, 16) : ""} 마감`;
    if (left < 0 || (hasTime && now >= n.deadline.slice(0, 16))) return { key: "closed", label: "마감", sub, left };
    if (n.start && n.start > today) return { key: "soon", label: `접수 ${md(n.start)}~`, sub, left };
    if (left <= URGENT_DAYS) return { key: "urgent", label: left === 0 ? "D-DAY" : `D-${left}`, sub, left };
    return { key: "open", label: `D-${left}`, sub, left };
  }

  const state = { type: "all", status: "open", tag: "", fit: "", q: "", sort: "deadline", only: "" };
  let notices = [];
  let meta = {};
  let newDate = "";

  function readParams() {
    const p = new URLSearchParams(location.search);
    for (const k of Object.keys(state)) if (p.has(k)) state[k] = p.get(k);
  }
  function writeParams() {
    const p = new URLSearchParams();
    const def = { type: "all", status: "open", sort: "deadline" };
    for (const [k, v] of Object.entries(state)) if (v && v !== def[k]) p.set(k, v);
    const qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  }

  function matches(n, opts = {}) {
    const st = n._state.key;
    if (!opts.ignoreType && state.type !== "all" && n.type !== state.type) return false;
    if (state.status === "open" && st === "closed") return false;
    if (state.status === "closed" && st !== "closed") return false;
    if (state.only === "new" && n.added !== newDate && n.updated !== newDate) return false;
    if (state.only === "urgent" && st !== "urgent") return false;
    if (state.tag && !n.tags.includes(state.tag)) return false;
    if (state.fit && n.fit !== state.fit) return false;
    if (state.q) {
      const hay = [n.title, n.agency, n.summary, n.why, ...(n.fit_analysis || []).map((a) => a.note), n.budget, n.source, ...(n.conditions || []), ...(n.tags || [])].join(" ").toLowerCase();
      if (!state.q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function sortList(list) {
    const endKey = (n) => (n.deadline ? n.deadline : "9999");
    const by = {
      deadline: (a, b) => (a._state.key === "closed") - (b._state.key === "closed") ||
        (a._state.key === "closed" ? endKey(b).localeCompare(endKey(a)) : endKey(a).localeCompare(endKey(b))),
      new: (a, b) => b.added.localeCompare(a.added) || b.posted.localeCompare(a.posted),
      budget: (a, b) => (b.budget_won || 0) - (a.budget_won || 0) || endKey(a).localeCompare(endKey(b)),
    };
    return list.sort(by[state.sort] || by.deadline);
  }

  function factRow(label, value) {
    return `<dt>${label}</dt><dd>${value ? esc(value) : '<em class="unknown">공고문 확인</em>'}</dd>`;
  }

  function renderNotice(n) {
    const s = n._state;
    const isNew = n.added === newDate;
    const isUpd = !isNew && n.updated === newDate;
    const bid = n.bid || {};
    const facts = [
      factRow("기관", n.agency),
      factRow("규모", n.budget),
      factRow("접수", (n.start ? n.start + " ~ " : "") + (n.deadline ? n.deadline.replace("T", " ") : "")),
      factRow("공고일", n.posted),
    ];
    if (n.type === "bid") {
      facts.push(factRow("계약방법", bid.method));
      if (bid.big_corp_limit !== undefined) facts.push(factRow("대기업 참여", bid.big_corp_limit ? "제한" : "제한 없음"));
      if (bid.joint) facts.push(factRow("공동수급", bid.joint));
      if (bid.briefing) facts.push(factRow("설명회", bid.briefing));
    }
    // 목록(항상 보임): 적합도 판정 막대 · 규모 · 마감
    // 펼침: 기회(why) → 적합도 분석 → 공고 내용(요약·핵심 조건 | 개요)
    return `
<article class="notice${s.key === "closed" ? " is-closed" : ""}" id="n-${esc(n.id)}" data-type="${esc(n.type)}">
  <button class="notice-head" type="button" aria-expanded="false">
    <span class="notice-meta">
      <span class="type-badge">${TYPES[n.type] || ""}</span>
      <span>${esc(n.agency)}</span>
      ${isNew ? '<span class="badge-new">NEW</span>' : ""}${isUpd ? '<span class="badge-upd">업데이트</span>' : ""}
    </span>
    <h2 class="notice-title">${esc(n.title)}</h2>
    <span class="verdict">
      <span class="fit-pill ${esc(n.fit)}">${FIT[n.fit] || ""}</span>
      ${renderScorebar(n)}
      <span class="verdict-budget"><small>규모</small>${n.budget ? esc(n.budget) : "공고문 확인"}</span>
    </span>
    <span class="dday ${s.key}"><strong>${esc(s.label)}</strong><span>${esc(s.sub)}</span></span>
    <span class="chevron" aria-hidden="true"></span>
  </button>
  <div class="notice-body">
    ${n.why ? `<p class="notice-why">${esc(n.why)}</p>` : ""}
    ${renderFit(n)}
    <section class="detail-sec">
      <h3>공고 내용</h3>
      <div class="detail-grid">
        <div>
          <p class="summary">${esc(n.summary)}</p>
          ${n.conditions && n.conditions.length ? `<h4>핵심 조건</h4><ul class="cond-list">${n.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
        </div>
        <dl class="facts">${facts.join("")}</dl>
      </div>
      ${n.note ? `<p class="note">ⓘ ${esc(n.note)}</p>` : ""}
    </section>
    <div class="body-foot">
      <div class="tags">${(n.tags || []).map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}<span class="tag">출처 ${esc(n.source)}</span></div>
      <div class="links">
        <a class="btn primary" href="${esc(n.url)}" target="_blank" rel="noopener">원문 공고 ↗</a>
        <button class="btn" type="button" data-copy="${esc(n.id)}">링크 복사</button>
      </div>
    </div>
  </div>
</article>`;
  }

  // 4칸 판정 막대: 칸 색 = 판정, 칸 글자 = 항목 약칭 + 기호
  function renderScorebar(n) {
    const fa = n.fit_analysis || [];
    if (!fa.length) return "";
    const cells = fa.map((a) => {
      const m = MARK[a.result] || ["", ""];
      return `<span class="score-cell ${esc(a.result)}" title="${esc(a.item)}: ${m[1]}"><i>${m[0]}</i>${esc(SHORT[a.item] || a.item)}</span>`;
    });
    return `<span class="scorebar" aria-label="적합도 판정">${cells.join("")}</span>`;
  }

  function renderFit(n) {
    const rows = (n.fit_analysis || []).map((a) => {
      const m = MARK[a.result] || ["", ""];
      return `<li class="fit-row ${esc(a.result)}"><span class="fit-mark" title="${m[1]}">${m[0]}</span><b>${esc(a.item)}</b><span>${esc(a.note)}</span></li>`;
    });
    if (!rows.length) return "";
    return `<section class="fit-sec"><h3>적합도 분석 <span class="fit-pill ${esc(n.fit)}">${FIT[n.fit] || ""}</span></h3><ul class="fit-list">${rows.join("")}</ul></section>`;
  }

  function renderStats() {
    const open = notices.filter((n) => n._state.key !== "closed");
    const tiles = [
      { n: open.length, label: "접수중·예정 공고", act: { only: "", status: "open" } },
      { n: notices.filter((n) => n.added === newDate).length, label: `${md(newDate) || "최근"} 신규`, cls: "is-new", act: { only: "new", status: "all" } },
      { n: open.filter((n) => n._state.key === "urgent").length, label: `${URGENT_DAYS}일 내 마감`, cls: "is-urgent", act: { only: "urgent", status: "open" } },
      { n: open.filter((n) => n.fit === "high").length, label: "적합도 높음", act: { only: "", fit: "high", status: "open" } },
    ];
    $("#stats").innerHTML = tiles.map((t, i) => `<button class="stat ${t.cls || ""}" type="button" data-i="${i}"><b>${t.n}</b><span>${t.label}</span></button>`).join("");
    $("#stats").onclick = (e) => {
      const b = e.target.closest(".stat");
      if (!b) return;
      Object.assign(state, { type: "all", tag: "", fit: "", q: "", only: "" }, tiles[b.dataset.i].act);
      syncControls();
      render();
    };
  }

  function renderTabs() {
    const counts = { all: 0 };
    for (const n of notices) {
      if (!matches(n, { ignoreType: true })) continue;
      counts.all++;
      counts[n.type] = (counts[n.type] || 0) + 1;
    }
    $("#tabs").innerHTML = [["all", "전체"], ...Object.entries(TYPES)]
      .map(([k, label]) => `<button class="tab" type="button" data-type="${k}" aria-pressed="${state.type === k}">${label}<span class="n">${counts[k] || 0}</span></button>`)
      .join("");
  }

  function renderChips() {
    const tags = [...new Set(notices.flatMap((n) => n.tags || []))].sort((a, b) => a.localeCompare(b, "ko"));
    $("#chips").innerHTML = tags.map((t) => `<button class="chip" type="button" data-tag="${esc(t)}" aria-pressed="${state.tag === t}">#${esc(t)}</button>`).join("");
  }

  function render() {
    renderTabs();
    renderChips();
    const list = sortList(notices.filter((n) => matches(n)));
    const extra = state.only === "new" ? " · 신규·업데이트만" : state.only === "urgent" ? ` · ${URGENT_DAYS}일 내 마감만` : "";
    $("#count").textContent = `${list.length}건${extra}`;
    $("#list").innerHTML = list.length ? list.map(renderNotice).join("") : '<p class="empty">조건에 맞는 공고가 없습니다.</p>';
    writeParams();
  }

  function syncControls() {
    $("#q").value = state.q;
    $("#status").value = state.status;
    $("#fit").value = state.fit;
    $("#sort").value = state.sort;
  }

  function openFromHash() {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id.startsWith("n-")) return;
    let el = document.getElementById(id);
    if (!el) {
      // 필터에 가려졌으면 풀고 다시 그린다
      Object.assign(state, { type: "all", status: "all", tag: "", fit: "", q: "", only: "" });
      syncControls();
      render();
      el = document.getElementById(id);
    }
    if (el) {
      toggle(el, true);
      el.scrollIntoView({ block: "start" });
    }
  }

  function toggle(el, open) {
    const on = open === undefined ? !el.classList.contains("is-open") : open;
    el.classList.toggle("is-open", on);
    $(".notice-head", el).setAttribute("aria-expanded", on);
  }

  function bind() {
    $("#tabs").onclick = (e) => {
      const b = e.target.closest(".tab");
      if (!b) return;
      state.type = b.dataset.type;
      render();
    };
    $("#chips").onclick = (e) => {
      const b = e.target.closest(".chip");
      if (!b) return;
      state.tag = state.tag === b.dataset.tag ? "" : b.dataset.tag;
      render();
    };
    let t;
    $("#q").oninput = (e) => {
      clearTimeout(t);
      t = setTimeout(() => { state.q = e.target.value.trim(); render(); }, 150);
    };
    for (const k of ["status", "fit", "sort"]) {
      $("#" + k).onchange = (e) => { state[k] = e.target.value; render(); };
    }
    $("#list").onclick = (e) => {
      const copy = e.target.closest("[data-copy]");
      if (copy) {
        const url = location.origin + location.pathname + "#n-" + copy.dataset.copy;
        navigator.clipboard && navigator.clipboard.writeText(url).then(() => {
          copy.textContent = "복사됨";
          setTimeout(() => (copy.textContent = "링크 복사"), 1500);
        });
        return;
      }
      const head = e.target.closest(".notice-head");
      if (head) toggle(head.closest(".notice"));
    };
    window.addEventListener("hashchange", openFromHash);
  }

  async function load() {
    const root = document.body.dataset.root || "";
    const v = "?t=" + Math.floor(Date.now() / 600e3); // Pages 캐시(10분) 우회
    const [ns, m] = await Promise.all([
      fetch(root + "data/notices.json" + v).then((r) => r.json()),
      fetch(root + "data/meta.json" + v).then((r) => r.json()).catch(() => ({})),
    ]);
    notices = ns;
    meta = m;
    newDate = (meta.last_run || "").slice(0, 10) || notices.reduce((a, n) => (n.added > a ? n.added : a), "");
    refreshStates();
    renderScan();
  }

  // 최종 수집 시각(헤더)과 소스별 수집 현황
  function renderScan() {
    const run = meta.last_run || "";
    const hours = run ? (Date.now() - Date.parse(run)) / 3600e3 : Infinity;
    const stale = hours > STALE_HOURS;
    const when = run ? `${md(run)}(${wd(run)}) ${run.slice(11, 16)}` : "기록 없음";
    $("#updated").innerHTML = `<span class="upd-label">최종 수집 </span>${run ? `${md(run)} ${run.slice(11, 16)}` : "—"}`;
    $("#updated").classList.toggle("is-stale", stale);

    const src = meta.sources || {};
    const rows = SOURCES.map(([id, name, desc, url]) => {
      const s = src[id] || {};
      const [cls, text] =
        s.status === "ok" ? ["ok", s.total ? `${s.total}건 확인 · 후보 ${s.kept}` : "새 공고 없음"]
        : s.status === "error" ? ["error", "접속 실패"]
        : s.status === "skip" ? ["skip", "보류"]
        : ["none", "기록 없음"];
      return { cls, html: `<li class="scan-src ${cls}"><i></i><a href="${esc(url)}" target="_blank" rel="noopener"><b>${esc(name)}</b> ↗</a><span class="scan-desc">${esc(desc)}</span><span class="scan-res">${text}</span></li>` };
    });
    const cnt = (c) => rows.filter((r) => r.cls === c).length;
    const parts = [`수집 사이트 ${SOURCES.length}곳`, cnt("ok") && `정상 ${cnt("ok")}`, cnt("error") && `실패 ${cnt("error")}`, cnt("skip") && `보류 ${cnt("skip")}`].filter(Boolean);
    const head = stale
      ? `<b>최종 수집 ${when}</b> — ${run ? `${Math.floor(hours / 24)}일째 새 수집 기록이 없습니다. 자동 수집이 멈췄을 수 있습니다.` : "수집 기록이 없습니다."}`
      : `<b>최종 수집 ${when}</b> · 신규 ${meta.new || 0} · 갱신 ${meta.updated || 0}`;
    $("#scan").className = "scan" + (stale ? " is-stale" : "");
    $("#scan").innerHTML = `<details><summary><i></i><span class="scan-head">${head}</span><span class="scan-sum">${parts.join(" · ")}</span></summary>
      <ul class="scan-list">${rows.map((r) => r.html).join("")}</ul>
      <p class="scan-note">매일 07:00(KST) 위 사이트를 자동으로 확인합니다. 새 공고가 없어도 수집 시각은 갱신됩니다.</p></details>`;
  }

  // 상태를 다시 계산하고 바뀐 공고가 있으면 true
  function refreshStates() {
    const now = nowKST();
    let changed = false;
    for (const n of notices) {
      const st = stateOf(n, now);
      if (!n._state || n._state.key !== st.key || n._state.label !== st.label) changed = true;
      n._state = st;
    }
    return changed;
  }

  // 페이지를 열어 둔 채 마감 시각이 지나도 바로 반영되도록 1분마다 다시 계산한다(펼친 공고는 유지)
  function tick() {
    if (!refreshStates()) return;
    const open = [...document.querySelectorAll(".notice.is-open")].map((el) => el.id);
    renderStats();
    render();
    for (const id of open) {
      const el = document.getElementById(id);
      if (el) toggle(el, true);
    }
  }

  readParams();
  bind();
  load()
    .then(() => {
      syncControls();
      renderStats();
      render();
      openFromHash();
      setInterval(tick, 60e3);
    })
    .catch((e) => {
      $("#list").innerHTML = `<p class="empty">공고 데이터를 불러오지 못했습니다. (${esc(e.message)})</p>`;
    });
})();
