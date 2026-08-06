let herbStatsData = [];
let sortState = { col: "dark_gene_count", dir: -1 };

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

// 淺色/深色主題已在其他查詢站頁面實作繁簡轉換，這裡藥材中文名稱直接顯示資料庫原文（多為簡體），
// 如需要繁簡切換可視需求再擴充，這裡先聚焦排行榜功能本身。

async function loadHerbStats() {
  document.getElementById("statsBody").innerHTML = '<tr><td colspan="6" class="hint-msg">載入中...</td></tr>';
  try {
    const data = await api("/dark-genes/public/herb-stats");
    herbStatsData = data.herbs;
    document.getElementById("statHerbTotal").textContent = data.total;
    if (data.herbs.length) {
      document.getElementById("statMaxCount").textContent = data.herbs[0].dark_gene_count;
      document.getElementById("statTopHerb").textContent = data.herbs[0].herb_cn_name || data.herbs[0].herb_en_name;
    }
    renderTable();
  } catch (err) {
    document.getElementById("statsBody").innerHTML = `<tr><td colspan="6" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
}

function rankClass(idx) {
  if (idx === 0) return "top1";
  if (idx === 1) return "top2";
  if (idx === 2) return "top3";
  return "";
}

function renderTable() {
  const kw = document.getElementById("herbSearchInput").value.trim().toLowerCase();
  let rows = herbStatsData;
  if (kw) {
    rows = rows.filter(h => [h.herb_cn_name, h.herb_pinyin, h.herb_en_name].some(v => (v || "").toLowerCase().includes(kw)));
  }
  document.getElementById("herbCountHint").textContent = `顯示 ${rows.length} / ${herbStatsData.length} 筆`;

  // 排序時保留原始排名（依全體資料的 dark_gene_count 排序後的名次），不是依搜尋結果重新編號
  const rankMap = new Map(herbStatsData.map((h, idx) => [h.herb_id, idx + 1]));

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

  document.getElementById("statsBody").innerHTML = rows.map((h) => {
    const rank = rankMap.get(h.herb_id);
    return `
    <tr class="herb-row" onclick="window.open('tcmsp_query.html?herb=${h.herb_id}', '_blank')">
      <td><span class="rank-badge ${rankClass(rank - 1)}">${rank}</span></td>
      <td><b>${escapeHtml(h.herb_cn_name || "")}</b></td>
      <td>${escapeHtml(h.herb_pinyin || "")}</td>
      <td>${escapeHtml(h.herb_en_name || "")}</td>
      <td><span class="count-num">${h.dark_gene_count}</span></td>
      <td>${(h.gene_symbols || []).map(s => `<span class="gene-tag">${escapeHtml(s)}</span>`).join("")}</td>
    </tr>
  `;
  }).join("") || '<tr><td colspan="6" class="hint-msg">沒有符合條件的藥材</td></tr>';
}

document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (sortState.col === col) { sortState.dir *= -1; }
    else { sortState.col = col; sortState.dir = col === "dark_gene_count" ? -1 : 1; }
    renderTable();
  });
});

document.getElementById("herbSearchInput").addEventListener("input", renderTable);

loadUserInfo();
loadHerbStats();
