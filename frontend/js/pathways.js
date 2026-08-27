// 通路富集分析（KEGG／Reactome）— 功能代碼 F1-5
// KEGG／Reactome 的通路名稱是第三方內容，一律 esc() 之後才寫進 DOM

let isAdmin = false;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// p/q 值跨越好幾個數量級，固定小數位會把 1e-12 顯示成 0.000，
// 看起來像「沒有效果」，其實是最顯著的那一條
function fmtP(v) {
  if (v == null) return "-";
  if (v === 0) return "&lt;1e-300";
  if (v < 0.001) return v.toExponential(2);
  return v.toFixed(4);
}

function sigClass(q, p) {
  if (q != null && q < 0.05) return "sig-q";
  if (p != null && p < 0.05) return "sig-p";
  return "sig-no";
}

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
    isAdmin = (data.role_names || []).includes("管理者");
    document.getElementById("adminBox").style.display = isAdmin ? "flex" : "none";
  } catch (err) {}
}

// ---------------------------------------------------------------- 覆蓋率

async function loadStats() {
  const s = await api("/pathways/stats");
  const k = s.by_source.kegg, r = s.by_source.reactome;
  const boxes = [
    ["已標準化靶點", `${s.standardised_targets} / ${s.total_targets}`],
    ["KEGG 通路", k.pathways],
    ["KEGG 癌症相關", k.cancer_related],
    ["KEGG 已連結靶點", k.targets_with_pathway],
    ["Reactome 通路", r.pathways],
    ["Reactome 已連結靶點", r.targets_with_pathway],
  ];
  document.getElementById("statGrid").innerHTML = boxes.map(([lbl, num]) => `
    <div class="stat-box"><div class="num">${esc(num)}</div><div class="lbl">${esc(lbl)}</div></div>
  `).join("");

  const lines = [];
  for (const [name, d] of [["KEGG", k], ["Reactome", r]]) {
    lines.push(d.synced_at
      ? `${name}：${d.links} 條靶點↔通路關聯，背景基因 ${d.background_total}，最後同步 ${new Date(d.synced_at).toLocaleString()}`
      : `${name}：尚未同步`);
  }
  document.getElementById("syncLog").textContent = lines.join("\n");
}

async function runSync(source) {
  const msg = document.getElementById("syncMsg");
  const btns = [document.getElementById("syncKeggBtn"), document.getElementById("syncReactomeBtn")];
  btns.forEach(b => b.disabled = true);
  msg.textContent = source === "reactome"
    ? "同步中… Reactome 的對應檔有數十 MB，可能需要一兩分鐘，請不要關閉頁面。"
    : "同步中，請不要關閉頁面…";
  try {
    const r = await api("/pathways/sync", { method: "POST", body: JSON.stringify({ source }) });
    msg.textContent = `${source} 完成：新增 ${r.pathways_created} 條、更新 ${r.pathways_updated} 條，` +
                      `建立 ${r.links} 條靶點關聯（涵蓋 ${r.targets_with_pathway} 個靶點）。`;
    await loadStats();
  } catch (err) {
    msg.textContent = `同步失敗：${err.message || err}`;
  } finally {
    btns.forEach(b => b.disabled = false);
  }
}

// ---------------------------------------------------------------- 藥材搜尋
// 502 種藥材用下拉選單根本找不到（實際使用時捲不完），改成輸入即時模糊比對。
// 清單本來就整包載到前端了，所以比對純在瀏覽器端做，不用再打一次 API。

let allHerbs = [];
let selectedHerbId = null;
let activeIndex = -1;
let toCn = null;   // OpenCC 繁→簡轉換器

function initConverter() {
  // 藥材名稱在資料庫裡是簡體（猫爪草、鱼腥草）。使用者用繁體輸入「貓爪草」
  // 直接比對會找不到——這不是使用者輸錯，是我們的比對沒處理字形差異。
  // OpenCC 已經是全站語系機制在用的東西，這裡直接沿用。
  try {
    if (!toCn && window.OpenCC) toCn = OpenCC.Converter({ from: "tw", to: "cn" });
  } catch (e) { toCn = null; }
}

function normalize(text) {
  const t = String(text == null ? "" : text).toLowerCase().trim();
  if (!t) return "";
  try {
    return toCn ? toCn(t) : t;
  } catch (e) {
    return t;   // 轉換失敗就用原文比，不要讓搜尋整個壞掉
  }
}

function herbHaystack(h) {
  return [h.herb_cn_name, h.herb_en_name, h.herb_pinyin,
          h.child_cn_name, h.child_en_name].filter(Boolean).join(" ");
}

function searchHerbs(query) {
  const q = normalize(query);
  if (!q) return allHerbs.slice(0, 40);
  const scored = [];
  for (const h of allHerbs) {
    const hay = normalize(herbHaystack(h));
    const idx = hay.indexOf(q);
    if (idx < 0) continue;
    // 開頭命中排前面，其次才是出現在中間的；同分再依靶點數
    const name = normalize(h.herb_cn_name || h.herb_en_name || "");
    let score = 2;
    if (name === q) score = 0;
    else if (name.startsWith(q)) score = 1;
    scored.push({ h, score, idx });
  }
  scored.sort((a, b) => a.score - b.score || a.idx - b.idx
                        || (b.h.target_count || 0) - (a.h.target_count || 0));
  return scored.slice(0, 40).map(x => x.h);
}

function highlight(text, query) {
  const raw = String(text == null ? "" : text);
  const q = normalize(query);
  if (!q) return esc(raw);
  const idx = normalize(raw).indexOf(q);
  // 轉換後長度可能與原字串不同，只有長度一致時才安全地標記
  if (idx < 0 || normalize(raw).length !== raw.length) return esc(raw);
  return esc(raw.slice(0, idx)) + "<mark>" + esc(raw.slice(idx, idx + q.length)) +
         "</mark>" + esc(raw.slice(idx + q.length));
}

function renderHerbResults(query) {
  const box = document.getElementById("herbResults");
  const list = searchHerbs(query);
  activeIndex = -1;
  if (!list.length) {
    box.innerHTML = `<div class="herb-empty">找不到符合「${esc(query)}」的藥材。
      可以試中文、英文學名或拼音，例如「人參」「ginseng」「renshen」。</div>`;
    box.hidden = false;
    return;
  }
  box.innerHTML = list.map((h, i) => {
    const cn = h.herb_cn_name || "";
    const en = h.herb_en_name || "";
    const py = h.herb_pinyin || "";
    return `<div class="herb-item" data-herb-id="${esc(h.herb_id)}" data-idx="${i}">
      <b>${highlight(cn || en, query)}</b>
      <div class="sub">${highlight(en, query)}${py ? " · " + highlight(py, query) : ""}
        · 靶點 ${esc(h.target_count || 0)}（未篩選）</div>
    </div>`;
  }).join("");
  box.hidden = false;
  box.querySelectorAll("[data-herb-id]").forEach(el => {
    el.addEventListener("mousedown", ev => {
      // 用 mousedown 而不是 click：input 的 blur 會先關掉清單，click 就永遠觸發不到
      ev.preventDefault();
      chooseHerb(el.dataset.herbId);
    });
  });
}

function chooseHerb(herbId) {
  const h = allHerbs.find(x => String(x.herb_id) === String(herbId));
  if (!h) return;
  selectedHerbId = h.herb_id;
  document.getElementById("herbSearch").value = h.herb_cn_name || h.herb_en_name || "";
  document.getElementById("herbResults").hidden = true;
  runEnrichment();
}

function moveActive(delta) {
  const box = document.getElementById("herbResults");
  const items = [...box.querySelectorAll(".herb-item")];
  if (!items.length) return;
  activeIndex = (activeIndex + delta + items.length) % items.length;
  items.forEach((el, i) => el.classList.toggle("active", i === activeIndex));
  items[activeIndex].scrollIntoView({ block: "nearest" });
}

function bindHerbSearch() {
  const input = document.getElementById("herbSearch");
  const box = document.getElementById("herbResults");

  input.addEventListener("input", () => {
    selectedHerbId = null;      // 改過字就當作還沒選定，避免用舊的藥材去分析
    renderHerbResults(input.value);
  });
  input.addEventListener("focus", () => renderHerbResults(input.value));
  input.addEventListener("blur", () => setTimeout(() => { box.hidden = true; }, 120));
  input.addEventListener("keydown", ev => {
    if (box.hidden && ["ArrowDown", "ArrowUp"].includes(ev.key)) {
      renderHerbResults(input.value);
      return;
    }
    if (ev.key === "ArrowDown") { ev.preventDefault(); moveActive(1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); moveActive(-1); }
    else if (ev.key === "Escape") { box.hidden = true; }
    else if (ev.key === "Enter") {
      ev.preventDefault();
      const items = [...box.querySelectorAll("[data-herb-id]")];
      // 沒有用方向鍵選的話，Enter 就取第一筆——只有一筆結果時這是最順的操作
      const pick = activeIndex >= 0 ? items[activeIndex] : items[0];
      if (pick) chooseHerb(pick.dataset.herbId);
    }
  });
}

async function loadHerbs() {
  const input = document.getElementById("herbSearch");
  try {
    initConverter();
    allHerbs = await api("/tcmsp/herbs/public/list");
    allHerbs.sort((a, b) => (b.target_count || 0) - (a.target_count || 0));
    input.placeholder = `輸入藥材名稱搜尋（共 ${allHerbs.length} 種，可用中文／英文／拼音）`;
  } catch (err) {
    input.placeholder = "藥材清單載入失敗";
    input.disabled = true;
  }
}

// ---------------------------------------------------------------- 富集分析

function renderIngredientNote(r) {
  // 成分篩掉多少一定要看得見。使用者需要知道「這個結果是根據幾個成分算出來的」，
  // 而不是預設有篩就當作沒事——篩太兇導致樣本剩沒幾個，結論一樣不可信。
  const box = document.getElementById("admeNote");
  const m = r.ingredients || {};
  if (!r.apply_adme) {
    box.innerHTML = `<b style="color:#a83232;">未套用活性成分篩選。</b>
      這個藥材全部 ${esc(m.total || 0)} 個成分的靶點都被納入。
      TCMSP 收錄的是偵測得到的所有化合物，多數到不了體內靶點——
      這個結果只適合當對照，<b>不適合當成正式分析</b>。`;
    return;
  }
  const pct = m.total ? Math.round((m.passed_count / m.total) * 100) : 0;
  box.innerHTML = `<b>活性成分篩選：OB ≥ ${esc(m.ob_min)}%、DL ≥ ${esc(m.dl_min)}。</b>
    ${esc(m.total || 0)} 個成分中有 <b>${esc(m.passed_count || 0)}</b> 個通過（${esc(pct)}%），
    對應 <b>${esc(r.herb ? r.herb.target_count : 0)}</b> 個靶點。
    ${m.missing_adme ? `另有 ${esc(m.missing_adme)} 個成分因為 ADME 資料缺值而排除
       （缺值不等於不活性，只是 TCMSP 沒收錄這個數字）。` : ""}`;
}


function renderBackgroundNote(background, backgroundTotal, studyGeneCount) {
  // 母體選了什麼，結論就跟著變。畫面上一定要講清楚現在算的是哪一種，
  // 不然使用者看到的 p 值不知道在跟什麼比。
  const common = `這次分析的樣本是這個藥材的 <b>${studyGeneCount}</b> 個有通路註解的靶點基因，` +
                 `母體 <b>${backgroundTotal}</b> 個基因。`;
  document.getElementById("bgNote").innerHTML = background === "tcmsp"
    ? `<b>母體：全部已標準化的中藥靶點。</b>${common}
       回答的是「這條通路在<b>這個</b>藥材裡，是否比在中藥靶點整體裡更常出現」。
       這會消掉「TCMSP 的靶點本來就偏向可成藥蛋白」造成的系統性偏差，適合拿來比較不同藥材；
       但不是學界慣例，寫進論文要額外說明。`
    : `<b>母體：該資料庫收錄的全部人類基因（學界慣例）。</b>${common}
       回答的是「這條通路在這個藥材的靶點裡，是否比在全人類基因裡更常出現」。
       注意 TCMSP 的靶點本身就偏向傳統可成藥的蛋白（受體、酶、離子通道），
       所以訊號傳導與代謝類通路會被系統性高估——想消掉這個偏差請改用另一種母體。`;
}

async function runEnrichment() {
  const herbId = selectedHerbId;
  const hint = document.getElementById("enrichHint");
  const body = document.getElementById("enrichBody");
  if (!herbId) {
    hint.textContent = "請先在上方輸入並選擇一個藥材。";
    body.innerHTML = "";
    return;
  }

  const source = document.getElementById("sourceSelect").value;
  const background = document.getElementById("bgSelect").value;
  const cancerOnly = document.getElementById("cancerOnly").checked;
  const applyAdme = document.getElementById("applyAdme").checked;
  const excludeDisease = document.getElementById("excludeDisease").checked;
  const btn = document.getElementById("runBtn");
  btn.disabled = true;
  hint.textContent = "分析中…";
  try {
    const params = new URLSearchParams({
      source, background, cancer_only: cancerOnly, apply_adme: applyAdme,
      exclude_noncancer_disease: excludeDisease, limit: 100,
    });
    const r = await api(`/pathways/herb/${encodeURIComponent(herbId)}?${params}`);

    renderIngredientNote(r);
    renderBackgroundNote(r.background, r.background_total, r.study_gene_count);

    if (!r.items || !r.items.length) {
      hint.textContent = r.note || "這個藥材在目前的通路資料下沒有可分析的結果（可能是通路目錄尚未同步）。";
      body.innerHTML = "";
      return;
    }
    const sig = r.significant_count != null ? r.significant_count
              : r.items.filter(i => i.q_value != null && i.q_value < 0.05).length;
    const dropped = r.excluded_disease_pathways
      ? `（已排除 ${r.excluded_disease_pathways} 條非癌症疾病類通路）` : "";
    hint.innerHTML = `${esc(r.herb.herb_cn_name || r.herb.herb_en_name)}：` +
      `共檢定 ${r.total_tested} 條通路${esc(dropped)}，其中 <b>${sig}</b> 條達 FDR q&lt;0.05；` +
      `以下顯示前 ${r.items.length} 條。`;

    body.innerHTML = r.items.map(i => `
      <tr>
        <td><span class="pill pill-${esc(r.source)}">${esc(i.pathway_id)}</span></td>
        <td>${esc(i.name_tw || i.name)}
          ${i.is_cancer_related ? '<span class="pill pill-cancer" style="margin-left:6px;">癌症相關</span>' : ""}
          ${i.category ? `<div class="hint-msg">${esc(i.category)}</div>` : ""}</td>
        <td><b>${esc(i.hit_count)}</b></td>
        <td>${esc(i.pathway_gene_count)}</td>
        <td>${i.fold_enrichment == null ? "-" : esc(i.fold_enrichment)}</td>
        <td class="mono ${sigClass(i.q_value, i.p_value)}">${fmtP(i.p_value)}</td>
        <td class="mono ${sigClass(i.q_value, i.p_value)}">${fmtP(i.q_value)}</td>
        <td class="syms">${esc((i.hit_symbols || []).join("、"))}</td>
      </tr>`).join("");
  } catch (err) {
    hint.textContent = `分析失敗：${err.message || err}`;
    body.innerHTML = "";
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- 初始化

document.addEventListener("DOMContentLoaded", async () => {
  await loadUserInfo();
  document.getElementById("refreshBtn").addEventListener("click", loadStats);
  document.getElementById("syncKeggBtn").addEventListener("click", () => runSync("kegg"));
  document.getElementById("syncReactomeBtn").addEventListener("click", () => runSync("reactome"));
  document.getElementById("runBtn").addEventListener("click", runEnrichment);
  bindHerbSearch();

  try {
    await Promise.all([loadStats(), loadHerbs()]);
  } catch (err) {
    document.getElementById("syncLog").textContent = `載入失敗：${err.message || err}`;
  }
});
