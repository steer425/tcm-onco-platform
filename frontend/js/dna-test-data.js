let allPatients = [];

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

async function loadPatients() {
  try {
    allPatients = await api("/patients?status_filter=active");
    renderPicker();
  } catch (err) {
    document.getElementById("patientPicker").innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

function renderPicker(filter) {
  const kw = (filter || document.getElementById("patientSearch").value || "").trim().toLowerCase();
  const list = allPatients.filter(p => !kw || p.name.toLowerCase().includes(kw) || p.patient_id.toLowerCase().includes(kw));
  document.getElementById("patientPicker").innerHTML = list.map(p => `
    <label class="patient-row">
      <input type="checkbox" class="patient-cb" value="${p.id}">
      <span>${escapeHtml(p.name)}（${escapeHtml(p.patient_id)}）</span>
    </label>
  `).join("") || '<p class="hint-msg">沒有符合的病患</p>';
}

document.getElementById("patientSearch").addEventListener("input", () => renderPicker());
document.getElementById("selectAllBtn").addEventListener("click", () => {
  document.querySelectorAll(".patient-cb").forEach(cb => cb.checked = true);
});
document.getElementById("selectNoneBtn").addEventListener("click", () => {
  document.querySelectorAll(".patient-cb").forEach(cb => cb.checked = false);
});

document.getElementById("generateBtn").addEventListener("click", async () => {
  const msg = document.getElementById("generateMsg");
  const resultEl = document.getElementById("generateResult");
  const patientIds = Array.from(document.querySelectorAll(".patient-cb:checked")).map(cb => cb.value);
  if (!patientIds.length) { msg.textContent = "請至少選擇一位病患"; return; }

  msg.textContent = "產生中...";
  resultEl.innerHTML = "";
  try {
    const data = await api("/dna/test-data/generate", {
      method: "POST",
      body: JSON.stringify({
        patient_ids: patientIds,
        include_dark_genes: document.getElementById("includeDarkGenes").checked,
        variants_per_patient: parseInt(document.getElementById("variantsPerPatient").value, 10) || 10,
        dark_gene_ratio: parseFloat(document.getElementById("darkGeneRatio").value) || 0.4,
      }),
    });
    msg.textContent = `已為 ${data.batches.length} 位病患產生測試資料`;
    resultEl.innerHTML = `
      <table style="margin-top:10px;">
        <thead><tr><th>批次編號</th><th>變異筆數</th></tr></thead>
        <tbody>${data.batches.map(b => `<tr><td>${escapeHtml(b.batch_no)}</td><td>${b.variant_count}</td></tr>`).join("")}</tbody>
      </table>
      <p class="hint-msg" style="margin-top:10px;">可以到「DNA 資料管理」頁面選擇對應病患查看產生的批次與變異明細。</p>
    `;
  } catch (err) {
    msg.textContent = "產生失敗：" + err.message;
  }
});

loadUserInfo();
loadPatients();
