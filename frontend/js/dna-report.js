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
  const patients = await api("/patients?status_filter=active");
  const sel = document.getElementById("patientSelect");
  sel.innerHTML = '<option value="">-- 請選擇病患 --</option>' +
    patients.map(p => `<option value="${p.id}">${escapeHtml(p.name)}（${escapeHtml(p.patient_id)}）</option>`).join("");
}

document.getElementById("genReportBtn").addEventListener("click", async () => {
  const patientId = document.getElementById("patientSelect").value;
  if (!patientId) { alert("請先選擇病患"); return; }

  document.getElementById("reportBody").style.display = "block";
  document.getElementById("printBtn").style.display = "none";
  document.getElementById("geneAlertList").innerHTML = '<p class="hint-msg">載入中...</p>';
  document.getElementById("herbTableBody").innerHTML = '<tr><td colspan="5" class="hint-msg">載入中...</td></tr>';

  try {
    const [summary, suggestion, patientInfo] = await Promise.all([
      api(`/dna/patients/${patientId}/dark-gene-summary`),
      api(`/dark-genes/patient-herb-suggestions/${patientId}`),
      api(`/patients?keyword=`).then(list => list.find(p => p.id === patientId)),
    ]);

    document.getElementById("reportPatientName").textContent = `${summary.patient_name} 的 DNA 檢測報告`;
    document.getElementById("reportPatientMeta").textContent =
      patientInfo ? `病患識別碼：${patientInfo.patient_id}　性別：${patientInfo.sex_code || "-"}　出生日期：${patientInfo.birth_date || "-"}` : "";
    document.getElementById("reportGenTime").textContent = `報告產生時間：${new Date().toLocaleString("zh-Hant")}`;

    document.getElementById("kpiTotalVariants").textContent = summary.total_variants;
    document.getElementById("kpiDarkGenes").textContent = summary.dark_gene_count;
    document.getElementById("kpiHerbs").textContent = suggestion.herbs.length;

    if (!summary.dark_genes.length) {
      document.getElementById("geneAlertList").innerHTML = '<p class="hint-msg">目前資料庫比對結果：沒有命中已知的暗黑基因（癌症相關基因）清單。</p>';
    } else {
      document.getElementById("geneAlertList").innerHTML = summary.dark_genes.map(g => `
        <div class="gene-alert-card">
          <b>⚠️ ${escapeHtml(g.hugo_symbol)}</b>　${g.gene_type ? `（${escapeHtml(g.gene_type)}）` : ''}
          <div class="hint-msg" style="margin-top:4px;">命中 ${g.variant_count} 筆變異紀錄。此基因屬於 OncoKB 癌症基因參考清單，實際臨床意義需醫師依完整病歷與正式基因檢測報告判斷。</div>
        </div>
      `).join("");
    }

    if (!suggestion.herbs.length) {
      document.getElementById("herbTableBody").innerHTML = '<tr><td colspan="5" class="hint-msg">目前沒有比對到候選中藥資料</td></tr>';
    } else {
      document.getElementById("herbTableBody").innerHTML = suggestion.herbs.map(h => `
        <tr>
          <td>${escapeHtml(h.herb_cn_name || "")}</td>
          <td>${escapeHtml(h.herb_pinyin || "")}</td>
          <td>${escapeHtml(h.herb_en_name || "")}</td>
          <td>${h.covered_gene_count}</td>
          <td>${(h.covered_genes || []).map(g => `<span class="herb-tag">${escapeHtml(g)}</span>`).join("")}</td>
        </tr>
      `).join("");
    }

    document.getElementById("printBtn").style.display = "inline-block";
  } catch (err) {
    document.getElementById("geneAlertList").innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
});

document.getElementById("printBtn").addEventListener("click", () => window.print());

loadUserInfo();
loadPatients();
