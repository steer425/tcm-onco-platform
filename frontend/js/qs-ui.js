/* 查詢站共用版面工具（v1.45.0）
 *
 * 把「TCMSP 藥材關聯查詢站」在 v1.42.5～v1.42.8 做的版面調整，做成其他查詢站可以共用的一份：
 *   collapsiblePanel  左側清單可向左收合（常駐窄軌）              ← v1.42.5
 *   pickerSearch      勾選欄加搜尋（只收窄顯示，不改勾選）           ← v1.42.5
 *   networkToggle     關聯圖可隱藏，讓表格吃滿高度                   ← v1.42.6
 *   tableTools        表格的 ⚙ 篩選（可收合＋chip）、▦ 欄位、⤢ 獨立視窗、點表頭排序 ← v1.42.7–8
 *
 * tcmsp_query.html 沒有改用這一份——它那幾個功能跟成分 ADME 篩選綁得很深，硬拆風險比收益大。
 * 新的查詢站請用這一份，**不要再各自複製一套**。
 *
 * 從 tcmsp_query 那幾版學到、這裡照做的規則（rules.md 第五之一章）：
 *   1. 要活過狀態變化的東西（收合把手、搜尋框、篩選面板）一律是被 innerHTML 換掉的容器的**兄弟**
 *   2. 隱藏中的關聯圖不能建立 vis-network 實例（0×0 畫布，之後顯示是一片空白）
 *   3. 收起來的篩選器一定要用 chip 把生效條件顯示出來
 *   4. 獨立視窗不能讓文件裡同時有兩組一樣的 id——這裡是把**同一個** #tableWrap 搬進視窗、
 *      關閉時再搬回原位，所以頁面原本的 renderTable()、欄寬拖拉都不用改
 */
(function () {
  const LS = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 私密視窗 */ } },
  };
  const $el = (x) => (typeof x === "string" ? document.getElementById(x) : x);
  const esc = (s) => String(s == null ? "" : s)
    .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function injectCss() {
    if (document.getElementById("qs-ui-css")) return;
    const st = document.createElement("style");
    st.id = "qs-ui-css";
    st.textContent = `
.qs-collapsible{overflow:hidden;transition:width .18s ease;}
body.qs-panel-collapsed .qs-collapsible{width:0!important;min-width:0!important;border-right:0!important;}
.qs-rail{width:16px;flex-shrink:0;background:#1c1f26;border-right:1px solid #2a2d34;display:flex;align-items:center;
  justify-content:center;cursor:pointer;color:#6b7480;font-size:13px;user-select:none;}
.qs-rail:hover{background:#242830;color:#7db8e8;}
.qs-net-hidden .qs-net{display:none!important;}
.qs-picker-wrap{display:flex;flex-direction:column;min-height:0;flex-shrink:0;border-right:1px solid #2a2d34;}
.qs-picker-wrap > .qs-picker-col{flex:1;min-height:0;overflow-y:auto;width:auto!important;border-right:0!important;}
.qs-picker-bar{padding:8px 8px 6px;border-bottom:1px solid #2a2d34;flex-shrink:0;}
.qs-picker-bar input{width:100%;box-sizing:border-box;margin:0;padding:6px 8px;background:#1c1f26;border:1px solid #3a3d44;
  color:#eee;border-radius:6px;font-size:12px;}
.qs-picker-count{margin-top:5px;font-size:11px;color:#8a8f98;}
.qs-picker-empty{padding:14px 12px;font-size:11.5px;color:#8a8f98;}
button.qs-on{background:#2f5c8a!important;border-color:#3d70a3!important;}
/* 分頁列多了三顆按鈕，加上原本的版面預設控制項，窄螢幕會把按鈕擠成直排文字；改成換行 */
.qs-tabs{flex-wrap:wrap;row-gap:6px;align-items:center;}
.qs-tabs > button,.qs-tabs > select,.qs-tabs > input,.qs-tabs > span{white-space:nowrap;flex-shrink:0;}
.qs-panel{display:none;padding:8px 16px;border-bottom:1px solid #2a2d34;background:#12151b;font-size:12px;}
.qs-panel.open{display:block;}
.qs-panel .row{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;}
.qs-panel label{display:inline-flex;gap:5px;align-items:center;color:#cfd6dd;font-size:12px;margin:0;}
.qs-panel input[type=search],.qs-panel input[type=number]{background:#1c1f26;border:1px solid #3a3d44;color:#eee;
  border-radius:6px;padding:4px 6px;font-size:12px;}
.qs-panel input[type=number]{width:74px;}
.qs-panel .grp{display:inline-flex;gap:4px;align-items:center;}
.qs-panel .grp b{font-weight:600;color:#bcd;min-width:52px;}
.qs-chips{display:none;padding:4px 16px;font-size:11.5px;color:#8a8f98;gap:6px;flex-wrap:wrap;align-items:center;}
.qs-chips.show{display:flex;}
.qs-chip{background:#2a3546;color:#cfe3f7;border-radius:999px;padding:1px 8px;}
.qs-chips a{color:#7db8e8;cursor:pointer;}
th.qs-sortable{cursor:pointer;}
th .qs-sort{color:#7db8e8;margin-left:3px;font-size:10px;}
#qsTableModal{display:none;position:fixed;inset:0;z-index:9998;flex-direction:column;background:#0b0d11;}
#qsTableModalBar{display:flex;gap:8px;align-items:center;padding:10px 16px;border-bottom:1px solid #2a2d34;flex-shrink:0;}
#qsTableModalBar b{color:#eee;font-size:14px;}
#qsTableModalBody{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden;}
#qsTableModalBody > .qs-table-wrap{flex:1!important;min-height:0!important;max-height:none!important;height:auto!important;overflow:auto!important;}
body[data-page-theme="light"] .qs-rail{background:#eef2ef;color:#6b7a70;border-right-color:#dfe5e0;}
body[data-page-theme="light"] .qs-panel{background:#f3f6f4;border-color:#dfe5e0;}
body[data-page-theme="light"] .qs-panel label{color:#24312a;}
body[data-page-theme="light"] .qs-panel input,body[data-page-theme="light"] .qs-picker-bar input{background:#fff;color:#24312a;border-color:#cfd8d2;}
body[data-page-theme="light"] .qs-chip{background:#e3edf7;color:#1f4f7a;}
body[data-page-theme="light"] #qsTableModal{background:#f7faf8;}
body[data-page-theme="light"] #qsTableModalBar b{color:#24312a;}
@media (max-width:820px){.qs-rail{display:none;} body.qs-panel-collapsed .qs-collapsible{width:auto!important;}}
`;
    document.head.appendChild(st);
  }

  /* ------------------------------------------------------------ 左側清單收合 */
  function collapsiblePanel({ panel, key, label = "清單", onToggle }) {
    injectCss();
    const p = $el(panel);
    if (!p) return null;
    p.classList.add("qs-collapsible");
    // 把手放在面板**外面**：放裡面的話收合後跟著消失，使用者再也點不開
    const rail = document.createElement("div");
    rail.className = "qs-rail";
    rail.innerHTML = '<span class="qs-rail-icon">‹</span>';
    p.parentNode.insertBefore(rail, p.nextSibling);
    const set = (collapsed) => {
      document.body.classList.toggle("qs-panel-collapsed", collapsed);
      rail.querySelector(".qs-rail-icon").textContent = collapsed ? "›" : "‹";
      rail.title = collapsed ? `展開${label}` : `收合${label}`;
      LS.set(key, collapsed ? "1" : "0");
      // vis-network 的 autoResize 只看視窗大小、不看容器；等 .18s 轉場跑完再叫頁面重畫
      if (onToggle) setTimeout(() => onToggle(collapsed), 220);
    };
    rail.addEventListener("click", () => set(!document.body.classList.contains("qs-panel-collapsed")));
    if (LS.get(key) === "1") set(true); else rail.title = `收合${label}`;
    return { set };
  }

  /* ------------------------------------------------------------ 關聯圖隱藏 */
  function networkToggle({ network, extra = [], toolbar, after, key, onHide, onShow }) {
    injectCss();
    const net = $el(network);
    if (!net) return null;
    [net, ...extra.map($el)].forEach((e) => e && e.classList.add("qs-net"));
    const btn = document.createElement("button");
    btn.type = "button";
    const sync = () => {
      const hidden = document.body.classList.contains("qs-net-hidden");
      btn.textContent = hidden ? "⊞ 顯示關聯圖" : "⊟ 隱藏關聯圖";
      btn.title = hidden ? "把關聯圖叫回來" : "把關聯圖收起來，讓下面的表格用滿整個高度";
      btn.classList.toggle("qs-on", hidden);
    };
    const set = (hidden) => {
      document.body.classList.toggle("qs-net-hidden", hidden);
      LS.set(key, hidden ? "1" : "0");
      sync();
      if (hidden) { if (onHide) onHide(); } else if (onShow) onShow();
    };
    btn.addEventListener("click", () => set(!document.body.classList.contains("qs-net-hidden")));
    const afterEl = $el(after);
    if (afterEl && afterEl.parentNode) afterEl.parentNode.insertBefore(btn, afterEl.nextSibling);
    else $el(toolbar).appendChild(btn);
    if (LS.get(key) === "1") document.body.classList.add("qs-net-hidden");
    sync();
    return { set, isHidden: () => document.body.classList.contains("qs-net-hidden") };
  }

  /* ------------------------------------------------------------ 勾選欄搜尋 */
  function pickerSearch({ col, placeholder = "搜尋…", selectedCount }) {
    injectCss();
    const c = $el(col);
    if (!c) return null;
    const w = c.getBoundingClientRect().width || parseInt(getComputedStyle(c).width, 10) || 250;
    // 搜尋框與計數放在 #pickerCol 的**兄弟**：renderPicker() 是 innerHTML 整個換掉 #pickerCol
    const wrap = document.createElement("div");
    wrap.className = "qs-picker-wrap";
    wrap.style.width = w + "px";
    c.parentNode.insertBefore(wrap, c);
    const bar = document.createElement("div");
    bar.className = "qs-picker-bar";
    bar.innerHTML = `<input type="search" autocomplete="off" placeholder="${esc(placeholder)}"><div class="qs-picker-count"></div>`;
    const empty = document.createElement("div");
    empty.className = "qs-picker-empty";
    empty.style.display = "none";
    empty.textContent = "沒有符合的項目。";
    wrap.appendChild(bar);
    wrap.appendChild(c);
    wrap.appendChild(empty);
    c.classList.add("qs-picker-col");
    const input = bar.querySelector("input");
    const countEl = bar.querySelector(".qs-picker-count");
    let kw = "";
    const norm = (s) => (s || "").toLowerCase();
    function apply() {
      const rows = Array.from(c.querySelectorAll(".pick-row"));
      let shown = 0;
      rows.forEach((r) => {
        const hay = norm(r.textContent + " " + (r.dataset.search || ""));
        const ok = !kw || hay.includes(norm(kw))
          || (window.zhMatchAny && window.zhMatchAny([r.textContent], kw));
        r.style.display = ok ? "" : "none";
        if (ok) shown++;
      });
      empty.style.display = rows.length && !shown ? "" : "none";
      const sel = selectedCount ? selectedCount() : null;
      // 搜尋只收窄顯示，不改勾選——講清楚，免得以為「搜到一個就只會顯示一個」
      countEl.textContent = (kw ? `顯示 ${shown}／${rows.length} 項` : `共 ${rows.length} 項`)
        + (sel == null ? "" : `・已勾選 ${sel} 個（不受搜尋影響）`);
    }
    input.addEventListener("input", () => { kw = input.value.trim(); apply(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { input.value = ""; kw = ""; apply(); }
      if (e.key === "Enter") e.preventDefault();
    });
    return { apply };
  }

  /* ------------------------------------------------------------ 表格工具 */
  function tableTools({ wrap, tabsBar, key, getTab, title, onModalChange }) {
    injectCss();
    const W = $el(wrap);
    const bar = typeof tabsBar === "string" ? document.querySelector(tabsBar) : tabsBar;
    if (!W || !bar) return null;
    W.classList.add("qs-table-wrap");
    bar.classList.add("qs-tabs");
    const tab = () => (getTab ? getTab() : "default") || "default";
    const state = {};                     // { tab: { kw, ranges:{label:{min,max}}, sort:{label,dir} } }
    const st = () => (state[tab()] = state[tab()] || { kw: "", ranges: {}, sort: null });
    const hiddenKey = () => `${key}_hidden_${tab()}`;
    const getHidden = () => { try { return new Set(JSON.parse(LS.get(hiddenKey()) || "[]")); } catch (e) { return new Set(); } };
    const setHidden = (s) => LS.set(hiddenKey(), JSON.stringify(Array.from(s)));

    // 按鈕放在分頁列裡、分頁按鈕的後面
    const mk = (txt, ttl) => { const b = document.createElement("button"); b.type = "button"; b.textContent = txt; b.title = ttl; return b; };
    const bFilter = mk("⚙ 篩選", "依關鍵字或數值範圍篩選表格（收起來時以標籤顯示生效中的條件）");
    const bCols = mk("▦ 欄位", "勾選要顯示的欄位（每個分頁各自記住）");
    const bPop = mk("⤢ 獨立視窗", "讓資料表佔滿整個畫面（Esc 關閉）");
    const tabBtns = bar.querySelectorAll("button[data-tab]");
    const anchor = tabBtns.length ? tabBtns[tabBtns.length - 1] : null;
    // 有分頁按鈕就緊接在最後一顆後面（倒序插入才會是 篩選→欄位→獨立視窗），沒有就依序加在最後
    if (anchor) [bPop, bCols, bFilter].forEach((b) => anchor.parentNode.insertBefore(b, anchor.nextSibling));
    else [bFilter, bCols, bPop].forEach((b) => bar.appendChild(b));

    // 面板與 chip 都是 #tableWrap 的兄弟：renderTable() 用 innerHTML 換掉 #tableWrap 不會清到它們
    const pFilter = document.createElement("div"); pFilter.className = "qs-panel";
    const pCols = document.createElement("div"); pCols.className = "qs-panel";
    const chips = document.createElement("div"); chips.className = "qs-chips";
    [pFilter, pCols, chips].forEach((x) => W.parentNode.insertBefore(x, W));

    let cols = [];        // [{ label, numeric }]
    const num = (t) => {
      const s = (t || "").replace(/,/g, "").trim();
      if (!s || s === "-" || s === "—") return null;
      const v = Number(s);
      return Number.isFinite(v) ? v : null;
    };

    function readTable() {
      const table = W.querySelector("table");
      if (!table) return null;
      const ths = Array.from(table.querySelectorAll("thead th"));
      const rows = Array.from(table.querySelectorAll("tbody tr")).filter((r) => !(r.cells.length === 1 && r.cells[0].colSpan > 1));
      ths.forEach((th) => {
        if (th.dataset.qsLabel == null) th.dataset.qsLabel = (th.textContent || "").replace(/[ⓘ❗◦▲▼]/g, "").trim();
      });
      cols = ths.map((th, i) => {
        const vals = rows.map((r) => r.cells[i] ? r.cells[i].textContent : "").filter((t) => t && t.trim() && t.trim() !== "-");
        const nums = vals.filter((t) => num(t) != null).length;
        return { label: th.dataset.qsLabel, numeric: vals.length > 0 && nums / vals.length >= 0.8 };
      });
      return { table, ths, rows };
    }

    function buildFilterPanel() {
      const s = st();
      const numCols = cols.filter((c) => c.numeric && c.label);
      pFilter.innerHTML = `<div class="row">
          <label>關鍵字 <input type="search" data-kw value="${esc(s.kw)}" placeholder="任何欄位包含…"></label>
          ${numCols.map((c) => {
            const r = s.ranges[c.label] || {};
            return `<span class="grp"><b>${esc(c.label)}</b>
              <input type="number" step="any" data-min="${esc(c.label)}" placeholder="≥" value="${r.min ?? ""}">
              <input type="number" step="any" data-max="${esc(c.label)}" placeholder="≤" value="${r.max ?? ""}"></span>`;
          }).join("")}
          <button type="button" data-clear>清除</button>
        </div>`;
      pFilter.querySelector("[data-kw]").addEventListener("input", (e) => { st().kw = e.target.value.trim(); apply(); });
      pFilter.querySelectorAll("[data-min],[data-max]").forEach((inp) => {
        inp.addEventListener("input", () => {
          const lab = inp.dataset.min || inp.dataset.max;
          const r = st().ranges[lab] = st().ranges[lab] || {};
          const v = inp.value === "" ? null : Number(inp.value);
          if (inp.dataset.min) r.min = v; else r.max = v;
          apply();
        });
      });
      pFilter.querySelector("[data-clear]").addEventListener("click", clearFilter);
    }

    function buildColsPanel() {
      const hidden = getHidden();
      pCols.innerHTML = `<div class="row">
          ${cols.map((c) => c.label ? `<label><input type="checkbox" data-col="${esc(c.label)}" ${hidden.has(c.label) ? "" : "checked"}> ${esc(c.label)}</label>` : "").join("")}
          <button type="button" data-all>全部顯示</button></div>`;
      pCols.querySelectorAll("[data-col]").forEach((cb) => cb.addEventListener("change", () => {
        const h = getHidden();
        if (cb.checked) h.delete(cb.dataset.col); else h.add(cb.dataset.col);
        setHidden(h); apply();
      }));
      pCols.querySelector("[data-all]").addEventListener("click", () => { setHidden(new Set()); buildColsPanel(); apply(); });
    }

    function clearFilter() {
      const s = st(); s.kw = ""; s.ranges = {};
      buildFilterPanel(); apply();
    }

    function activeConds() {
      const s = st();
      const out = [];
      if (s.kw) out.push(`含「${s.kw}」`);
      Object.entries(s.ranges).forEach(([lab, r]) => {
        if (r.min != null) out.push(`${lab} ≥ ${r.min}`);
        if (r.max != null) out.push(`${lab} ≤ ${r.max}`);
      });
      return out;
    }

    // 每次頁面 renderTable() 之後呼叫：重新套用欄位隱藏、篩選、排序
    function apply() {
      const t = readTable();
      if (!t) { chips.classList.remove("show"); return; }
      const { table, ths, rows } = t;
      const s = st();
      const hidden = getHidden();
      const hideIdx = new Set(ths.map((th, i) => hidden.has(th.dataset.qsLabel) ? i : -1).filter((i) => i >= 0));
      table.querySelectorAll("tr").forEach((tr) => {
        Array.from(tr.cells).forEach((cell, i) => { if (!(tr.cells.length === 1 && cell.colSpan > 1)) cell.style.display = hideIdx.has(i) ? "none" : ""; });
      });
      // 篩選
      const kw = (s.kw || "").toLowerCase();
      const idxOf = (lab) => ths.findIndex((th) => th.dataset.qsLabel === lab);
      let shown = 0;
      rows.forEach((r) => {
        let ok = !kw || r.textContent.toLowerCase().includes(kw)
          || (window.zhMatchAny && window.zhMatchAny([r.textContent], s.kw));
        if (ok) {
          for (const [lab, rg] of Object.entries(s.ranges)) {
            if (rg.min == null && rg.max == null) continue;
            const i = idxOf(lab);
            const v = i >= 0 && r.cells[i] ? num(r.cells[i].textContent) : null;
            if (v == null || (rg.min != null && v < rg.min) || (rg.max != null && v > rg.max)) { ok = false; break; }
          }
        }
        r.style.display = ok ? "" : "none";
        if (ok) shown++;
      });
      // 排序（數值欄依數值，其餘依文字）
      ths.forEach((th, i) => {
        th.classList.add("qs-sortable");
        const old = th.querySelector(".qs-sort"); if (old) old.remove();
        if (s.sort && s.sort.label === th.dataset.qsLabel) {
          const sp = document.createElement("span"); sp.className = "qs-sort"; sp.textContent = s.sort.dir > 0 ? "▲" : "▼";
          th.appendChild(sp);
        }
        if (!th.dataset.qsBound) {
          th.dataset.qsBound = "1";
          th.addEventListener("click", (e) => {
            if (e.target.closest(".col-resizer,a,button,input")) return;
            const cur = st().sort;
            st().sort = cur && cur.label === th.dataset.qsLabel ? { label: cur.label, dir: -cur.dir } : { label: th.dataset.qsLabel, dir: 1 };
            apply();
          });
        }
      });
      if (s.sort) {
        const i = idxOf(s.sort.label);
        if (i >= 0) {
          const numeric = cols[i] && cols[i].numeric;
          const tbody = table.tBodies[0];
          const sorted = rows.slice().sort((a, b) => {
            const ta = a.cells[i] ? a.cells[i].textContent.trim() : "", tb = b.cells[i] ? b.cells[i].textContent.trim() : "";
            if (numeric) {
              const va = num(ta), vb = num(tb);
              if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1;
              return (va - vb) * s.sort.dir;
            }
            return ta.localeCompare(tb, "zh-Hant") * s.sort.dir;
          });
          sorted.forEach((r) => tbody.appendChild(r));
        }
      }
      // chip：篩選器收起來時也要看得到有哪些條件在生效
      const conds = activeConds();
      const hiddenN = hideIdx.size;
      if (conds.length || hiddenN) {
        chips.innerHTML = conds.map((c) => `<span class="qs-chip">${esc(c)}</span>`).join("")
          + (conds.length ? ` 顯示 ${shown}／${rows.length} 列 <a data-x>清除篩選</a>` : "")
          + (hiddenN ? `<span>・隱藏 ${hiddenN} 欄</span>` : "");
        chips.classList.add("show");
        const x = chips.querySelector("[data-x]"); if (x) x.addEventListener("click", clearFilter);
      } else chips.classList.remove("show");
      bFilter.classList.toggle("qs-on", conds.length > 0 || pFilter.classList.contains("open"));
      bCols.classList.toggle("qs-on", hiddenN > 0 || pCols.classList.contains("open"));
    }

    // 換分頁時面板內容要跟著換（各分頁的欄位不同）
    function refreshPanels() {
      readTable();
      if (pFilter.classList.contains("open")) buildFilterPanel();
      if (pCols.classList.contains("open")) buildColsPanel();
    }

    bFilter.addEventListener("click", () => {
      pFilter.classList.toggle("open");
      if (pFilter.classList.contains("open")) { readTable(); buildFilterPanel(); }
      apply();
    });
    bCols.addEventListener("click", () => {
      pCols.classList.toggle("open");
      if (pCols.classList.contains("open")) { readTable(); buildColsPanel(); }
      apply();
    });

    /* ---- 獨立視窗：把同一組元素搬進視窗，關閉時搬回原位 ---- */
    let modal = document.getElementById("qsTableModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "qsTableModal";
      modal.innerHTML = `<div id="qsTableModalBar"><b id="qsTableModalTitle">資料表</b><span style="flex:1"></span>
        <span style="font-size:11px;color:#8a8f98;">按 Esc 也可以關閉</span>
        <button type="button" id="qsTableModalClose" class="primary">✕ 關閉，回主頁</button></div>
        <div id="qsTableModalBody"></div>`;
      document.body.appendChild(modal);
    }
    const moving = [bar, pFilter, pCols, chips, W];
    let marks = null;
    const isOpen = () => modal.style.display === "flex";
    function open() {
      if (isOpen()) return;
      marks = moving.map((elx) => { const m = document.createComment("qs"); elx.parentNode.insertBefore(m, elx); return m; });
      const body = document.getElementById("qsTableModalBody");
      moving.forEach((elx) => body.appendChild(elx));
      document.getElementById("qsTableModalTitle").textContent = title ? title() : "資料表";
      modal.style.display = "flex";
      bPop.textContent = "⤡ 回主頁";
      if (onModalChange) onModalChange(true);
    }
    function close() {
      if (!isOpen()) return;
      moving.forEach((elx, i) => marks[i].parentNode.insertBefore(elx, marks[i]));
      marks.forEach((m) => m.remove());
      marks = null;
      modal.style.display = "none";
      bPop.textContent = "⤢ 獨立視窗";
      if (onModalChange) onModalChange(false);
    }
    bPop.addEventListener("click", () => (isOpen() ? close() : open()));
    document.getElementById("qsTableModalClose").addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !isOpen()) return;
      // 關聯圖的放大視窗在上面時，先讓它自己處理
      const nm = document.getElementById("networkModal");
      if (nm && getComputedStyle(nm).display !== "none") return;
      close();
    });

    return {
      afterRender() { refreshPanels(); apply(); if (isOpen() && title) document.getElementById("qsTableModalTitle").textContent = title(); },
      open, close, isOpen,
    };
  }

  /* ------------------------------------------------------------ 成分表（14 欄 ADME） */
  // 與 tcmsp_query 的 ING_COLS 同一組欄位與順序；◦ 標記模型預測值（不是從結構算出來的）
  const ING_COLS = [
    ["mol_id", "Mol ID"], ["molecule_name", "Molecule Name"], ["mw", "MW"], ["ob", "OB% ◦"], ["dl", "DL"],
    ["alogp", "ALogP"], ["hdon", "Hdon"], ["hacc", "Hacc"], ["tpsa", "TPSA"], ["rbn", "RBN"],
    ["caco2", "Caco-2 ◦"], ["bbb", "BBB ◦"], ["halflife", "HL ◦"], ["fasa", "FASA−"],
  ];
  function ingredientTable(list, emptyText) {
    const na = '<span class="na">-</span>';
    const cell = (v) => (v === null || v === undefined || v === "" ? na : esc(v));
    const head = ING_COLS.map(([, l]) => `<th title="${l.includes("◦") ? "◦ 模型預測值" : ""}">${esc(l)}</th>`).join("");
    const body = (list || []).map((i) => `<tr>${ING_COLS.map(([k]) => `<td>${cell(i[k])}</td>`).join("")}</tr>`).join("")
      || `<tr><td colspan="${ING_COLS.length}" class="small">${esc(emptyText || "無資料")}</td></tr>`;
    return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  window.QSUI = { collapsiblePanel, networkToggle, pickerSearch, tableTools, ingredientTable, ING_COLS };
})();
