let allDiseases = [];

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

function classificationClass(c) {
  if (c === "Definitive") return "cls-definitive";
  if (c === "Strong") return "cls-strong";
  if (c === "Moderate") return "cls-moderate";
  if (c === "Limited" || c === "Disputed Evidence" || c === "Refuted Evidence") return "cls-limited";
  return "cls-other";
}

async function loadDiseases() {
  const kw = document.getElementById("searchInput").value.trim();
  const cls = document.getElementById("classificationFilter").value;
  if (!kw && !cls) {
    document.getElementById("countHint").textContent = "請輸入搜尋關鍵字或選擇信心等級篩選（資料量太大，不會預設列出全部）";
    document.getElementById("tableBody").innerHTML = "";
    allDiseases = [];
    return;
  }
  const params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (cls) params.set("classification", cls);
  allDiseases = await api(`/gencc-diseases?${params.toString()}`);
  renderTable();
}

function renderTable() {
  document.getElementById("countHint").textContent = `共 ${allDiseases.length} 筆（最多顯示 500 筆）`;
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = allDiseases.map(d => `
    <tr data-id="${d.id}">
      <td><b>${escapeHtml(d.gene_symbol)}</b><div class="hint-msg">${escapeHtml(d.sgc_id)}</div></td>
      <td>${escapeHtml(d.disease_title || "")}</td>
      <td>${escapeHtml(d.disease_cn_name || "")}</td>
      <td>${escapeHtml(d.disease_name_cn || "")}</td>
      <td>${escapeHtml(d.disease_name_ko || "")}</td>
      <td>${d.classification_title ? `<span class="cls-pill ${classificationClass(d.classification_title)}">${escapeHtml(d.classification_title)}</span>` : '<span class="hint-msg">-</span>'}</td>
      <td>${escapeHtml(d.moi_title || "")}</td>
      <td class="yn-cell">${d.has_tcmsp_target ? "✓" : ""}</td>
      <td><span class="status-pill ${d.status === 'active' ? 'status-active' : 'status-inactive'}">${d.status === 'active' ? '使用中' : '已刪除'}</span></td>
      <td class="actions">
        <button class="secondary" onclick="openEdit('${d.id}')">編輯</button>
      </td>
    </tr>
  `).join("");
}

function openEdit(id) {
  const d = allDiseases.find(x => x.id === id);
  if (!d) return;
  document.getElementById("diseaseModalTitle").textContent = "編輯疾病資料";
  document.getElementById("diseaseId").value = d.id;
  document.getElementById("diseaseSgcId").value = d.sgc_id;
  document.getElementById("diseaseGeneSymbol").value = d.gene_symbol;
  document.getElementById("diseaseTitle").value = d.disease_title || "";
  document.getElementById("diseaseCnName").value = d.disease_cn_name || "";
  document.getElementById("diseaseNameCn").value = d.disease_name_cn || "";
  document.getElementById("diseaseNameKo").value = d.disease_name_ko || "";
  document.getElementById("diseaseClassification").value = d.classification_title || "";
  document.getElementById("diseaseMoi").value = d.moi_title || "";
  document.getElementById("diseaseStatus").value = d.status;
  document.getElementById("diseaseNotes").value = d.notes || "";
  document.getElementById("diseaseModalMsg").textContent = "";
  document.getElementById("diseaseModal").style.display = "flex";
}

document.getElementById("diseaseModalCancel").addEventListener("click", () => {
  document.getElementById("diseaseModal").style.display = "none";
});

document.getElementById("diseaseModalSave").addEventListener("click", async () => {
  const id = document.getElementById("diseaseId").value;
  const payload = {
    disease_cn_name: document.getElementById("diseaseCnName").value.trim() || null,
    disease_name_cn: document.getElementById("diseaseNameCn").value.trim() || null,
    disease_name_ko: document.getElementById("diseaseNameKo").value.trim() || null,
    classification_title: document.getElementById("diseaseClassification").value.trim() || null,
    moi_title: document.getElementById("diseaseMoi").value.trim() || null,
    status: document.getElementById("diseaseStatus").value,
    notes: document.getElementById("diseaseNotes").value.trim() || null,
  };
  try {
    await api(`/gencc-diseases/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    document.getElementById("diseaseModal").style.display = "none";
    await loadDiseases();
  } catch (err) {
    document.getElementById("diseaseModalMsg").textContent = "儲存失敗：" + err.message;
  }
});

document.getElementById("searchBtn").addEventListener("click", loadDiseases);
document.getElementById("searchInput").addEventListener("keydown", (e) => { if (e.key === "Enter") loadDiseases(); });
document.getElementById("classificationFilter").addEventListener("change", loadDiseases);

loadUserInfo();
