let allDiseases = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

async function loadDiseases() {
  const kw = document.getElementById("searchInput").value.trim();
  const missingOnly = document.getElementById("missingOnlyFilter").checked;
  const params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (missingOnly) params.set("missing_cn_only", "true");
  allDiseases = await api(`/tcmsp/diseases?${params.toString()}`);
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById("tableBody");
  const total = allDiseases.length;
  const missing = allDiseases.filter(d => !d.disease_cn_name).length;
  document.getElementById("countHint").textContent = `共 ${total} 筆，其中 ${missing} 筆尚無中文名稱`;

  tbody.innerHTML = allDiseases.map(d => `
    <tr data-id="${d.dis_id}">
      <td>${d.dis_id}</td>
      <td>${escapeHtml(d.disease_name || "")}</td>
      <td><input class="cn-name-input" data-field="cn_name" value="${escapeHtml(d.disease_cn_name || "")}" placeholder="尚無翻譯"></td>
      <td><span class="status-pill ${d.disease_cn_name ? 'status-has' : 'status-missing'}">${d.disease_cn_name ? '已有翻譯' : '待補充'}</span></td>
      <td><input data-field="notes" value="${escapeHtml(d.notes || "")}" placeholder="備注（選填）" style="width:140px;"></td>
      <td><button onclick="saveDisease(this)">儲存</button></td>
    </tr>
  `).join("");
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

window.saveDisease = async (btn) => {
  const tr = btn.closest("tr");
  const disId = tr.dataset.id;
  const payload = {
    disease_cn_name: tr.querySelector('[data-field="cn_name"]').value.trim(),
    notes: tr.querySelector('[data-field="notes"]').value.trim(),
  };
  const original = btn.textContent;
  btn.textContent = "儲存中..."; btn.disabled = true;
  try {
    await api(`/tcmsp/diseases/${disId}`, { method: "PUT", body: JSON.stringify(payload) });
    btn.textContent = "已儲存 ✓";
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1200);
    await loadDiseases();
  } catch (err) {
    alert("儲存失敗：" + err.message);
    btn.textContent = original; btn.disabled = false;
  }
};

document.getElementById("searchInput").addEventListener("input", loadDiseases);
document.getElementById("missingOnlyFilter").addEventListener("change", loadDiseases);

loadUserInfo();
loadDiseases();
