let allGenes = [];

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
  return "type-neither";
}

async function loadGenes() {
  const kw = document.getElementById("searchInput").value.trim();
  const typeFilter = document.getElementById("typeFilter").value;
  const statusFilter = document.getElementById("statusFilter").value;
  const params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (typeFilter) params.set("gene_type", typeFilter);
  if (statusFilter) params.set("status_filter", statusFilter);
  allGenes = await api(`/dark-genes?${params.toString()}`);
  renderTable();
}

function renderTable() {
  document.getElementById("countHint").textContent = `共 ${allGenes.length} 筆`;
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = allGenes.map(g => `
    <tr data-id="${g.id}">
      <td><b>${escapeHtml(g.hugo_symbol)}</b>${g.gene_aliases ? `<div class="hint-msg">${escapeHtml(g.gene_aliases)}</div>` : ''}</td>
      <td>${g.gene_type ? `<span class="gene-type-pill ${geneTypeClass(g.gene_type)}">${g.gene_type}</span>` : '<span class="hint-msg">-</span>'}</td>
      <td>${escapeHtml(g.entrez_gene_id || "")}</td>
      <td>${g.occurrence_count ?? ""}</td>
      <td class="yn-cell">${g.oncokb_annotated ? "✓" : ""}</td>
      <td class="yn-cell">${g.msk_impact ? "✓" : ""}</td>
      <td class="yn-cell">${g.cosmic_cgc ? "✓" : ""}</td>
      <td><span class="status-pill ${g.status === 'active' ? 'status-active' : 'status-inactive'}">${g.status === 'active' ? '使用中' : '已刪除'}</span></td>
      <td class="actions">
        <button class="secondary" onclick="viewGeneLinks('${g.id}','${escapeHtml(g.hugo_symbol)}')">靶點關聯</button>
        <button class="secondary" onclick="openEdit('${g.id}')">編輯</button>
        ${g.status === 'active' ? `<button class="danger" onclick="deleteGene('${g.id}')">刪除</button>` : ''}
      </td>
    </tr>
  `).join("");
}

document.getElementById("searchInput").addEventListener("input", loadGenes);
document.getElementById("typeFilter").addEventListener("change", loadGenes);
document.getElementById("statusFilter").addEventListener("change", loadGenes);

function clearGeneForm() {
  ["geneSymbol", "geneEntrez", "geneOccurrence", "geneGrch37Iso", "geneGrch37Ref",
   "geneGrch38Iso", "geneGrch38Ref", "geneAliases", "geneNotes"].forEach(id => { document.getElementById(id).value = ""; });
  document.getElementById("geneType").value = "";
  ["geneOncoKB", "geneMskImpact", "geneMskHeme", "geneF1", "geneF1Heme", "geneVogelstein", "geneCosmic"]
    .forEach(id => { document.getElementById(id).checked = false; });
}

document.getElementById("newBtn").addEventListener("click", () => {
  document.getElementById("geneModalTitle").textContent = "新增基因";
  document.getElementById("geneId").value = "";
  clearGeneForm();
  document.getElementById("geneSymbol").disabled = false;
  document.getElementById("geneModalMsg").textContent = "";
  document.getElementById("geneModal").style.display = "flex";
});

window.openEdit = (geneId) => {
  const g = allGenes.find(x => x.id === geneId);
  if (!g) return;
  document.getElementById("geneModalTitle").textContent = "編輯基因";
  document.getElementById("geneId").value = g.id;
  document.getElementById("geneSymbol").value = g.hugo_symbol;
  document.getElementById("geneSymbol").disabled = true; // Hugo Symbol 是唯一鍵，不允許事後修改
  document.getElementById("geneEntrez").value = g.entrez_gene_id || "";
  document.getElementById("geneType").value = g.gene_type || "";
  document.getElementById("geneOccurrence").value = g.occurrence_count ?? "";
  document.getElementById("geneGrch37Iso").value = g.grch37_isoform || "";
  document.getElementById("geneGrch37Ref").value = g.grch37_refseq || "";
  document.getElementById("geneGrch38Iso").value = g.grch38_isoform || "";
  document.getElementById("geneGrch38Ref").value = g.grch38_refseq || "";
  document.getElementById("geneAliases").value = g.gene_aliases || "";
  document.getElementById("geneOncoKB").checked = g.oncokb_annotated;
  document.getElementById("geneMskImpact").checked = g.msk_impact;
  document.getElementById("geneMskHeme").checked = g.msk_heme;
  document.getElementById("geneF1").checked = g.foundation_one;
  document.getElementById("geneF1Heme").checked = g.foundation_one_heme;
  document.getElementById("geneVogelstein").checked = g.vogelstein;
  document.getElementById("geneCosmic").checked = g.cosmic_cgc;
  document.getElementById("geneNotes").value = g.notes || "";
  document.getElementById("geneModalMsg").textContent = "";
  document.getElementById("geneModal").style.display = "flex";
};

document.getElementById("geneModalCancel").addEventListener("click", () => {
  document.getElementById("geneModal").style.display = "none";
});

function buildGenePayload() {
  return {
    entrez_gene_id: document.getElementById("geneEntrez").value.trim() || null,
    gene_type: document.getElementById("geneType").value || null,
    occurrence_count: document.getElementById("geneOccurrence").value ? parseInt(document.getElementById("geneOccurrence").value, 10) : null,
    grch37_isoform: document.getElementById("geneGrch37Iso").value.trim() || null,
    grch37_refseq: document.getElementById("geneGrch37Ref").value.trim() || null,
    grch38_isoform: document.getElementById("geneGrch38Iso").value.trim() || null,
    grch38_refseq: document.getElementById("geneGrch38Ref").value.trim() || null,
    gene_aliases: document.getElementById("geneAliases").value.trim() || null,
    oncokb_annotated: document.getElementById("geneOncoKB").checked,
    msk_impact: document.getElementById("geneMskImpact").checked,
    msk_heme: document.getElementById("geneMskHeme").checked,
    foundation_one: document.getElementById("geneF1").checked,
    foundation_one_heme: document.getElementById("geneF1Heme").checked,
    vogelstein: document.getElementById("geneVogelstein").checked,
    cosmic_cgc: document.getElementById("geneCosmic").checked,
    notes: document.getElementById("geneNotes").value.trim() || null,
  };
}

document.getElementById("geneModalSave").addEventListener("click", async () => {
  const geneId = document.getElementById("geneId").value;
  const msg = document.getElementById("geneModalMsg");
  try {
    if (geneId) {
      await api(`/dark-genes/${geneId}`, { method: "PUT", body: JSON.stringify(buildGenePayload()) });
    } else {
      const symbol = document.getElementById("geneSymbol").value.trim();
      if (!symbol) { msg.textContent = "Hugo Symbol 為必填"; return; }
      await api("/dark-genes", { method: "POST", body: JSON.stringify({ hugo_symbol: symbol, ...buildGenePayload() }) });
    }
    document.getElementById("geneModal").style.display = "none";
    await loadGenes();
  } catch (err) {
    msg.textContent = "儲存失敗：" + err.message;
  }
});

window.deleteGene = async (geneId) => {
  if (!confirm("確定要刪除這個基因資料嗎？（軟刪除）")) return;
  try {
    await api(`/dark-genes/${geneId}`, { method: "DELETE" });
    await loadGenes();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

// ---------- 匯入 ----------
const dropZone = document.getElementById("importDropZone");
const fileInput = document.getElementById("importFileInput");
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.style.borderColor = "var(--primary)"; });
dropZone.addEventListener("dragleave", () => { dropZone.style.borderColor = ""; });
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.style.borderColor = "";
  if (e.dataTransfer.files.length) doImport(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) doImport(fileInput.files[0]);
});

async function doImport(file) {
  const msg = document.getElementById("importMsg");
  msg.textContent = `正在匯入 ${file.name}...`;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const token = getToken();
    const res = await fetch((API_BASE || "") + "/dark-genes/import", {
      method: "POST",
      headers: { "Authorization": "Bearer " + token },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    msg.textContent = `匯入完成：新增 ${data.created} 筆、更新 ${data.updated} 筆`;
    fileInput.value = "";
    await loadGenes();
  } catch (err) {
    msg.textContent = "匯入失敗：" + err.message;
  }
}

loadUserInfo();
loadGenes();

// ---------- 暗黑基因-靶點關聯 ----------
window.viewGeneLinks = async (geneId, symbol) => {
  document.getElementById("linksModalTitle").textContent = `暗黑基因-靶點關聯：${symbol}`;
  document.getElementById("linksModalBody").innerHTML = "載入中...";
  document.getElementById("linksModal").style.display = "flex";
  try {
    const data = await api(`/dark-genes/${geneId}/tcmsp-links`);
    renderLinksBody(data);
  } catch (err) {
    document.getElementById("linksModalBody").innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
};

function renderLinksBody(data) {
  const body = document.getElementById("linksModalBody");
  if (!data.matched_targets.length) {
    body.innerHTML = `<p class="hint-msg">這個基因（含別名）目前沒有比對到任何 TCMSP 靶點名稱，代表 TCMSP 資料庫裡沒有直接對應的候選藥材資料。</p>`;
    return;
  }

  body.innerHTML = `
    <h4 style="margin-bottom:6px;">比對到的 TCMSP 靶點（${data.matched_targets.length} 個）</h4>
    <table style="margin-bottom:16px;">
      <thead><tr><th>Tar ID</th><th>Target Name</th><th>DrugBank ID</th></tr></thead>
      <tbody>
        ${data.matched_targets.map(t => `<tr><td>${t.tar_id}</td><td>${escapeHtml(t.target_name)}</td><td>${t.drugbank_id || '<span class="hint-msg">-</span>'}</td></tr>`).join("")}
      </tbody>
    </table>

    <h4 style="margin-bottom:6px;">候選藥材（共 ${data.herbs.length} 種，依關聯成分數排序）</h4>
    ${data.herbs.length ? `
      <table>
        <thead><tr><th>中文名稱</th><th>拼音</th><th>English Name</th><th>關聯成分數</th></tr></thead>
        <tbody>
          ${data.herbs.map(h => `<tr>
            <td>${escapeHtml(h.herb_cn_name || "")}</td>
            <td>${escapeHtml(h.herb_pinyin || "")}</td>
            <td>${escapeHtml(h.herb_en_name || "")}</td>
            <td>${h.matched_ingredient_count}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    ` : '<p class="hint-msg">比對到靶點，但目前沒有已下架以外的候選藥材資料。</p>'}

    <p class="hint-msg" style="margin-top:10px;">共 ${data.ingredients.length} 個相關成分。這份清單可以到「TCMSP 藥材關聯查詢站」搜尋任一藥材名稱進一步查看完整關聯與網絡圖。</p>
  `;
}

document.getElementById("linksModalClose").addEventListener("click", () => {
  document.getElementById("linksModal").style.display = "none";
});
