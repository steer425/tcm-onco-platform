let statsSummary = null;
let geneStatsData = [];
let sortState = { col: "target_count", dir: -1 };

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function geneTypeClass(t) {
  if (t === "ONCOGENE") return "type-oncogene";
  if (t === "TSG") return "type-tsg";
  if (t === "ONCOGENE_AND_TSG") return "type-both";
  if (t === "INSUFFICIENT_EVIDENCE") return "type-insufficient";
  if (!t) return "type-unclassified";
  return "type-neither";
}

// ---------- KPI 卡片（沿用類型彙總端點） ----------
async function loadSummary() {
  try {
    statsSummary = await api("/dark-genes/public/stats");
    document.getElementById("statTotal").textContent = statsSummary.total_genes;
    document.getElementById("statWithTarget").textContent = statsSummary.total_with_target;
    document.getElementById("statWithoutTarget").textContent = statsSummary.total_without_target;
  } catch (err) { /* KPI 卡片載入失敗不影響主表格 */ }
}

// ---------- 主表格：以 Hugo Symbol 為主的逐基因統計 ----------
async function loadGeneStats() {
  const onlyWithTarget = document.getElementById("onlyWithTargetFilter").checked;
  document.getElementById("statsBody").innerHTML = '<tr><td colspan="5" class="hint-msg">載入中...</td></tr>';
  try {
    const data = await api(`/dark-genes/public/gene-stats?only_with_target=${onlyWithTarget}`);
    geneStatsData = data.genes;
    renderStatsTable();
  } catch (err) {
    document.getElementById("statsBody").innerHTML = `<tr><td colspan="5" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
}

function renderStatsTable() {
  const kw = document.getElementById("geneSearchInput").value.trim().toLowerCase();
  let rows = geneStatsData;
  if (kw) {
    rows = rows.filter(g => (g.hugo_symbol || "").toLowerCase().includes(kw) || (g.gene_aliases || "").toLowerCase().includes(kw));
  }
  document.getElementById("geneCountHint").textContent = `顯示 ${rows.length} / ${geneStatsData.length} 筆`;

  rows = [...rows].sort((a, b) => {
    const va = a[sortState.col], vb = b[sortState.col];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "string") return va.localeCompare(vb) * sortState.dir;
    return (va - vb) * sortState.dir;
  });

  document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
    const arrow = th.querySelector(".sort-arrow");
    arrow.textContent = th.dataset.sort === sortState.col ? (sortState.dir === 1 ? "▲" : "▼") : "";
  });

  document.getElementById("statsBody").innerHTML = rows.map(g => `
    <tr>
      <td><b>${escapeHtml(g.hugo_symbol)}</b>${g.gene_aliases ? `<div class="hint-msg">${escapeHtml(g.gene_aliases)}</div>` : ''}</td>
      <td>${g.gene_type ? `<span class="gene-type-pill ${geneTypeClass(g.gene_type)}">${g.gene_type}</span>` : '<span class="hint-msg">未分類</span>'}</td>
      <td>${g.target_count > 0 ? `<span class="clickable-num" onclick="drilldownTargets('${g.id}','${escapeHtml(g.hugo_symbol)}')">${g.target_count}</span>` : '0'}</td>
      <td>${g.herb_count > 0 ? `<span class="clickable-num" onclick="drilldownHerbs('${g.id}','${escapeHtml(g.hugo_symbol)}')">${g.herb_count}</span>` : '0'}</td>
      <td>${escapeHtml(g.entrez_gene_id || "")}</td>
    </tr>
  `).join("") || '<tr><td colspan="5" class="hint-msg">沒有符合條件的基因</td></tr>';
}

document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (sortState.col === col) { sortState.dir *= -1; }
    else { sortState.col = col; sortState.dir = -1; }
    renderStatsTable();
  });
});

document.getElementById("geneSearchInput").addEventListener("input", renderStatsTable);
document.getElementById("onlyWithTargetFilter").addEventListener("change", loadGeneStats);

// ---------- 下鑽：靶點清單 ----------
window.drilldownTargets = async (geneId, symbol) => {
  const section = document.getElementById("drilldownSection");
  section.style.display = "block";
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });
  document.getElementById("drilldownBreadcrumb").innerHTML = `<a onclick="closeDrilldown()">← 回到統計總覽</a>`;
  document.getElementById("drilldownTitle").textContent = `${symbol} 的靶點統計`;
  document.getElementById("drilldownHead").innerHTML = '<tr><th>Tar ID</th><th>Target Name</th><th>DrugBank ID</th></tr>';
  document.getElementById("drilldownBody").innerHTML = '<tr><td colspan="3" class="hint-msg">載入中...</td></tr>';

  try {
    const data = await api(`/dark-genes/${geneId}/tcmsp-links`);
    document.getElementById("drilldownBody").innerHTML = data.matched_targets.map(t => `
      <tr><td>${t.tar_id}</td><td>${escapeHtml(t.target_name)}</td><td>${t.drugbank_id || '<span class="hint-msg">-</span>'}</td></tr>
    `).join("") || '<tr><td colspan="3" class="hint-msg">沒有比對到靶點</td></tr>';
  } catch (err) {
    document.getElementById("drilldownBody").innerHTML = `<tr><td colspan="3" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
};

// ---------- 下鑽：中藥清單 ----------
window.drilldownHerbs = async (geneId, symbol) => {
  const section = document.getElementById("drilldownSection");
  section.style.display = "block";
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });
  document.getElementById("drilldownBreadcrumb").innerHTML = `<a onclick="closeDrilldown()">← 回到統計總覽</a>`;
  document.getElementById("drilldownTitle").textContent = `${symbol} 比對到的候選中藥`;
  document.getElementById("drilldownHead").innerHTML = '<tr><th>中文名稱</th><th>拼音</th><th>English Name</th><th>關聯成分數</th><th></th></tr>';
  document.getElementById("drilldownBody").innerHTML = '<tr><td colspan="5" class="hint-msg">載入中...</td></tr>';

  try {
    const data = await api(`/dark-genes/${geneId}/tcmsp-links`);
    document.getElementById("drilldownBody").innerHTML = data.herbs.map(h => `
      <tr class="herb-item-row" onclick="window.open('tcmsp_query.html?herb=${h.herb_id}', '_blank')">
        <td>${escapeHtml(h.herb_cn_name || "")}</td>
        <td>${escapeHtml(h.herb_pinyin || "")}</td>
        <td>${escapeHtml(h.herb_en_name || "")}</td>
        <td>${h.matched_ingredient_count}</td>
        <td><a class="link" href="tcmsp_query.html?herb=${h.herb_id}" target="_blank" onclick="event.stopPropagation();">查看詳細說明 ↗</a></td>
      </tr>
    `).join("") || '<tr><td colspan="5" class="hint-msg">沒有比對到候選中藥</td></tr>';
  } catch (err) {
    document.getElementById("drilldownBody").innerHTML = `<tr><td colspan="5" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
};

window.closeDrilldown = () => {
  document.getElementById("drilldownSection").style.display = "none";
};

loadUserInfo();
loadSummary();
loadGeneStats();
