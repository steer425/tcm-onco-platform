let allPatients = [];
let currentPatientId = null;
let allBatches = [];
let checkedBatchIds = new Set();

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
  allPatients = await api("/patients?status_filter=active");
  const sel = document.getElementById("patientSelect");
  sel.innerHTML = '<option value="">-- 請選擇病患 --</option>' +
    allPatients.map(p => `<option value="${p.id}">${escapeHtml(p.name)}（${escapeHtml(p.patient_id)}）</option>`).join("");
}

document.getElementById("patientSelect").addEventListener("change", (e) => {
  currentPatientId = e.target.value || null;
  document.getElementById("batchSection").style.display = currentPatientId ? "block" : "none";
  document.getElementById("variantSection").style.display = "none";
  document.getElementById("compareSection").style.display = "none";
  checkedBatchIds = new Set();
  if (currentPatientId) loadBatches();
});

async function loadBatches() {
  allBatches = await api(`/dna/batches?patient_id=${currentPatientId}`);
  renderBatches();
}

function renderBatches() {
  document.getElementById("batchBody").innerHTML = allBatches.map(b => `
    <tr>
      <td><input type="checkbox" data-batch-id="${b.id}" ${checkedBatchIds.has(b.id) ? "checked" : ""}></td>
      <td>${escapeHtml(b.batch_no)}</td>
      <td><span class="status-pill ${b.source_type === 'synthetic' ? 'source-synthetic' : 'source-import'}">${b.source_type === 'synthetic' ? '測試資料' : '真實匯入'}</span></td>
      <td>${b.variant_count}</td>
      <td>${escapeHtml(b.platform || "")} ${escapeHtml(b.panel || "")}</td>
      <td>${new Date(b.created_at).toLocaleString("zh-Hant")}</td>
      <td><button class="secondary" onclick="viewVariants('${b.id}','${escapeHtml(b.batch_no)}')">查看變異</button></td>
    </tr>
  `).join("") || '<tr><td colspan="7" class="hint-msg">尚無匯入批次</td></tr>';

  document.querySelectorAll('[data-batch-id]').forEach(cb => {
    cb.addEventListener("change", () => {
      if (cb.checked) checkedBatchIds.add(cb.dataset.batchId);
      else checkedBatchIds.delete(cb.dataset.batchId);
    });
  });
}

window.viewVariants = async (batchId, batchNo) => {
  document.getElementById("variantSection").style.display = "block";
  document.getElementById("variantTitle").textContent = `變異清單：${batchNo}`;
  document.getElementById("variantBody").innerHTML = '<tr><td colspan="7" class="hint-msg">載入中...</td></tr>';
  try {
    const variants = await api(`/dna/batches/${batchId}/variants`);
    document.getElementById("variantBody").innerHTML = variants.map(v => `
      <tr class="${v.is_dark_gene ? 'dark-gene-row' : ''}">
        <td>${escapeHtml(v.chromosome || "")}</td>
        <td>${escapeHtml(v.position || "")}</td>
        <td>${escapeHtml(v.ref_allele || "")}&gt;${escapeHtml(v.alt_allele || "")}</td>
        <td>${escapeHtml(v.gene_symbol || "")} ${v.is_dark_gene ? "⚠️" : ""}</td>
        <td>${v.depth ?? ""}</td>
        <td>${escapeHtml(v.allele_fraction || "")}</td>
        <td>${escapeHtml(v.qc_status || "")}</td>
      </tr>
    `).join("") || '<tr><td colspan="7" class="hint-msg">此批次沒有變異資料</td></tr>';
  } catch (err) {
    document.getElementById("variantBody").innerHTML = `<tr><td colspan="7" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
};

// ---------- 手動新增批次 ----------
let nbRowCount = 0;
function addVariantRow() {
  nbRowCount++;
  const div = document.createElement("div");
  div.className = "nb-row";
  div.style.cssText = "display:grid; grid-template-columns:repeat(5,1fr); gap:6px; margin-bottom:6px;";
  div.innerHTML = `
    <input placeholder="染色體" class="nb-chr" />
    <input placeholder="位置" class="nb-pos" />
    <input placeholder="Ref" class="nb-ref" />
    <input placeholder="Alt" class="nb-alt" />
    <input placeholder="基因符號（Hugo Symbol）" class="nb-gene" />
  `;
  document.getElementById("nbVariantRows").appendChild(div);
}

document.getElementById("newBatchBtn").addEventListener("click", () => {
  document.getElementById("nbNo").value = "";
  document.getElementById("nbPlatform").value = "";
  document.getElementById("nbPanel").value = "";
  document.getElementById("nbRefGenome").value = "";
  document.getElementById("nbVariantRows").innerHTML = "";
  document.getElementById("nbMsg").textContent = "";
  addVariantRow();
  document.getElementById("newBatchModal").style.display = "flex";
});
document.getElementById("nbAddRowBtn").addEventListener("click", addVariantRow);
document.getElementById("nbCancel").addEventListener("click", () => {
  document.getElementById("newBatchModal").style.display = "none";
});
document.getElementById("nbSave").addEventListener("click", async () => {
  const msg = document.getElementById("nbMsg");
  const no = document.getElementById("nbNo").value.trim();
  if (!no) { msg.textContent = "請填寫批次編號"; return; }
  const variants = [];
  document.querySelectorAll("#nbVariantRows .nb-row").forEach(row => {
    const gene = row.querySelector(".nb-gene").value.trim();
    if (!gene) return;
    variants.push({
      chromosome: row.querySelector(".nb-chr").value.trim() || null,
      position: row.querySelector(".nb-pos").value.trim() || null,
      ref_allele: row.querySelector(".nb-ref").value.trim() || null,
      alt_allele: row.querySelector(".nb-alt").value.trim() || null,
      gene_symbol: gene,
    });
  });
  try {
    await api("/dna/batches", {
      method: "POST",
      body: JSON.stringify({
        batch_no: no, patient_id: currentPatientId,
        platform: document.getElementById("nbPlatform").value.trim() || null,
        panel: document.getElementById("nbPanel").value.trim() || null,
        reference_genome: document.getElementById("nbRefGenome").value.trim() || null,
        variants,
      }),
    });
    document.getElementById("newBatchModal").style.display = "none";
    await loadBatches();
  } catch (err) {
    msg.textContent = "儲存失敗：" + err.message;
  }
});

// ---------- 上傳 CSV ----------
document.getElementById("uploadBatchBtn").addEventListener("click", () => {
  document.getElementById("ubNo").value = "";
  document.getElementById("ubPlatform").value = "";
  document.getElementById("ubPanel").value = "";
  document.getElementById("ubFile").value = "";
  document.getElementById("ubMsg").textContent = "";
  document.getElementById("uploadBatchModal").style.display = "flex";
});
document.getElementById("ubCancel").addEventListener("click", () => {
  document.getElementById("uploadBatchModal").style.display = "none";
});
document.getElementById("ubSave").addEventListener("click", async () => {
  const msg = document.getElementById("ubMsg");
  const no = document.getElementById("ubNo").value.trim();
  const fileInput = document.getElementById("ubFile");
  if (!no || !fileInput.files.length) { msg.textContent = "請填寫批次編號並選擇檔案"; return; }
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  const params = new URLSearchParams({
    patient_id: currentPatientId, batch_no: no,
    platform: document.getElementById("ubPlatform").value.trim(),
    panel: document.getElementById("ubPanel").value.trim(),
  });
  try {
    const token = getToken();
    const res = await fetch((API_BASE || "") + `/dna/batches/upload?${params.toString()}`, {
      method: "POST", headers: { "Authorization": "Bearer " + token }, body: formData,
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    document.getElementById("uploadBatchModal").style.display = "none";
    await loadBatches();
  } catch (err) {
    msg.textContent = "上傳失敗：" + err.message;
  }
});

// ---------- 比較 ----------
document.getElementById("compareBtn").addEventListener("click", async () => {
  if (checkedBatchIds.size < 2) { alert("請至少勾選 2 個批次才能比較"); return; }
  const section = document.getElementById("compareSection");
  section.style.display = "block";
  const ids = Array.from(checkedBatchIds);
  try {
    const data = await api(`/dna/patients/${currentPatientId}/compare?batch_ids=${ids.join(",")}`);
    document.getElementById("compareBatchLabels").textContent =
      "比較批次：" + data.batches.map(b => b.batch_no).join("　vs　");
    const table = document.getElementById("compareTable");
    table.innerHTML = `
      <thead><tr><th>基因</th><th>染色體:位置</th><th>Ref&gt;Alt</th>
        ${data.batches.map(b => `<th>${escapeHtml(b.batch_no)}</th>`).join("")}
        <th>全部批次都有</th></tr></thead>
      <tbody>
        ${data.variants.map(v => `
          <tr class="${v.is_dark_gene ? 'dark-gene-row' : ''}">
            <td>${escapeHtml(v.gene_symbol || "")} ${v.is_dark_gene ? "⚠️" : ""}</td>
            <td>${escapeHtml(v.chromosome || "")}:${escapeHtml(v.position || "")}</td>
            <td>${escapeHtml(v.ref_allele || "")}&gt;${escapeHtml(v.alt_allele || "")}</td>
            ${data.batches.map(b => `<td class="${v.presence[b.id] ? 'compare-yes' : 'compare-no'}">${v.presence[b.id] ? '✓' : '－'}</td>`).join("")}
            <td>${v.in_all_batches ? '✓' : ''}</td>
          </tr>
        `).join("")}
      </tbody>
    `;
    section.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    alert("比較失敗：" + err.message);
  }
});

loadUserInfo();
loadPatients();
