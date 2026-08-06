let statsData = null;
let sortState = { col: "total", dir: -1 };

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
  if (t === "（未分類）") return "type-unclassified";
  return "type-neither";
}

async function loadStats() {
  try {
    statsData = await api("/dark-genes/public/stats");
  } catch (err) {
    document.getElementById("statsBody").innerHTML = `<tr><td colspan="5" class="hint-msg">載入失敗：${err.message}</td></tr>`;
    return;
  }
  document.getElementById("statTotal").textContent = statsData.total_genes;
  document.getElementById("statWithTarget").textContent = statsData.total_with_target;
  document.getElementById("statWithoutTarget").textContent = statsData.total_without_target;
  renderStatsTable();
}

function renderStatsTable() {
  const rows = [...statsData.by_type].sort((a, b) => {
    const va = a[sortState.col], vb = b[sortState.col];
    if (typeof va === "string") return va.localeCompare(vb) * sortState.dir;
    return (va - vb) * sortState.dir;
  });

  document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
    const arrow = th.querySelector(".sort-arrow");
    arrow.textContent = th.dataset.sort === sortState.col ? (sortState.dir === 1 ? "▲" : "▼") : "";
  });

  document.getElementById("statsBody").innerHTML = rows.map(r => `
    <tr>
      <td><span class="gene-type-pill ${geneTypeClass(r.gene_type)}">${escapeHtml(r.gene_type)}</span></td>
      <td>${r.total}</td>
      <td><span class="clickable-num" onclick="drilldownGenes('${escapeHtml(r.gene_type)}', true)">${r.with_target}</span></td>
      <td><span class="clickable-num" onclick="drilldownGenes('${escapeHtml(r.gene_type)}', false)">${r.without_target}</span></td>
      <td>${r.percent_with_target}%</td>
    </tr>
  `).join("");
}

document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (sortState.col === col) {
      sortState.dir *= -1;
    } else {
      sortState.col = col;
      sortState.dir = -1;
    }
    renderStatsTable();
  });
});

// ---------- 第二層：基因清單下鑽 ----------
window.drilldownGenes = async (geneType, hasTarget) => {
  const section = document.getElementById("drilldownSection");
  const body = document.getElementById("drilldownBody");
  document.getElementById("herbSection").style.display = "none";
  section.style.display = "block";
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });

  document.getElementById("drilldownBreadcrumb").innerHTML = `<a onclick="backToStats()">← 回到統計總覽</a>`;
  document.getElementById("drilldownTitle").textContent =
    `${geneType === "（未分類）" ? "未分類" : geneType}　${hasTarget ? "有中藥靶點" : "無中藥靶點"}　的基因清單`;
  body.innerHTML = '<tr><td colspan="4" class="hint-msg">載入中...</td></tr>';

  const params = new URLSearchParams();
  if (geneType !== "（未分類）") params.set("gene_type", geneType);
  params.set("has_tcmsp_target", hasTarget);

  try {
    let genes = await api(`/dark-genes/public/list?${params.toString()}`);
    if (geneType === "（未分類）") genes = genes.filter(g => !g.gene_type);
    if (!genes.length) {
      body.innerHTML = '<tr><td colspan="4" class="hint-msg">沒有符合條件的基因</td></tr>';
      return;
    }
    body.innerHTML = genes.map(g => `
      <tr class="gene-item-row" onclick="drilldownHerbs('${g.id}', '${escapeHtml(g.hugo_symbol)}')">
        <td><b>${escapeHtml(g.hugo_symbol)}</b></td>
        <td>${g.gene_type ? `<span class="gene-type-pill ${geneTypeClass(g.gene_type)}">${g.gene_type}</span>` : '<span class="hint-msg">-</span>'}</td>
        <td>${escapeHtml(g.entrez_gene_id || "")}</td>
        <td>${escapeHtml(g.gene_aliases || "")}</td>
      </tr>
    `).join("");
  } catch (err) {
    body.innerHTML = `<tr><td colspan="4" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
};

window.backToStats = () => {
  document.getElementById("drilldownSection").style.display = "none";
  document.getElementById("herbSection").style.display = "none";
};

// ---------- 第三層：中藥清單下鑽 ----------
window.drilldownHerbs = async (geneId, symbol) => {
  const section = document.getElementById("herbSection");
  const body = document.getElementById("herbBody");
  section.style.display = "block";
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });

  document.getElementById("herbBreadcrumb").innerHTML =
    `<a onclick="backToStats()">← 回到統計總覽</a>　<a onclick="document.getElementById('herbSection').style.display='none'">← 回到基因清單</a>`;
  document.getElementById("herbTitle").textContent = `${symbol} 比對到的候選藥材`;
  body.innerHTML = '<tr><td colspan="5" class="hint-msg">載入中...</td></tr>';

  try {
    const data = await api(`/dark-genes/${geneId}/tcmsp-links`);
    if (!data.herbs.length) {
      body.innerHTML = '<tr><td colspan="5" class="hint-msg">這個基因目前沒有比對到候選藥材</td></tr>';
      return;
    }
    body.innerHTML = data.herbs.map(h => `
      <tr class="herb-item-row" onclick="window.open('tcmsp_query.html?herb=${h.herb_id}', '_blank')">
        <td>${escapeHtml(h.herb_cn_name || "")}</td>
        <td>${escapeHtml(h.herb_pinyin || "")}</td>
        <td>${escapeHtml(h.herb_en_name || "")}</td>
        <td>${h.matched_ingredient_count}</td>
        <td><a class="link" href="tcmsp_query.html?herb=${h.herb_id}" target="_blank" onclick="event.stopPropagation();">查看詳細說明 ↗</a></td>
      </tr>
    `).join("");
  } catch (err) {
    body.innerHTML = `<tr><td colspan="5" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
};

loadUserInfo();
loadStats();
