let rankingData = [];
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

function rankClass(idx) {
  if (idx === 0) return "top1";
  if (idx === 1) return "top2";
  if (idx === 2) return "top3";
  return "";
}

async function loadRanking() {
  document.getElementById("statsBody").innerHTML = '<tr><td colspan="6" class="hint-msg">載入中...</td></tr>';
  try {
    const data = await api("/dna/patients/ranking");
    rankingData = data.patients;
    document.getElementById("statPatientTotal").textContent = data.total;
    if (data.patients.length) {
      document.getElementById("statMaxCount").textContent = data.patients[0].dark_gene_count;
      document.getElementById("statTopPatient").textContent = data.patients[0].patient_name;
    } else {
      document.getElementById("statMaxCount").textContent = "0";
      document.getElementById("statTopPatient").textContent = "-";
    }
    renderTable();
  } catch (err) {
    document.getElementById("statsBody").innerHTML = `<tr><td colspan="6" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
}

function renderTable() {
  const kw = document.getElementById("searchInput").value.trim().toLowerCase();
  let rows = rankingData;
  if (kw) {
    rows = rows.filter(p => (p.patient_name || "").toLowerCase().includes(kw) || (p.patient_display_id || "").toLowerCase().includes(kw));
  }
  document.getElementById("countHint").textContent = `顯示 ${rows.length} / ${rankingData.length} 筆`;

  const rankMap = new Map(rankingData.map((p, idx) => [p.patient_id, idx + 1]));

  rows = [...rows].sort((a, b) => {
    const va = a[sortState.col], vb = b[sortState.col];
    if (typeof va === "string") return va.localeCompare(vb) * sortState.dir;
    return (va - vb) * sortState.dir;
  });

  document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
    const arrow = th.querySelector(".sort-arrow");
    arrow.textContent = th.dataset.sort === sortState.col ? (sortState.dir === 1 ? "▲" : "▼") : "";
  });

  document.getElementById("statsBody").innerHTML = rows.map((p) => {
    const rank = rankMap.get(p.patient_id);
    return `
    <tr class="patient-row" onclick="window.open('dna-report.html', '_blank')">
      <td><span class="rank-badge ${rankClass(rank - 1)}">${rank}</span></td>
      <td><b>${escapeHtml(p.patient_name)}</b></td>
      <td>${escapeHtml(p.patient_display_id)}</td>
      <td><span style="color:var(--primary); font-weight:700;">${p.dark_gene_count}</span></td>
      <td>${p.total_variants}</td>
      <td>${(p.gene_symbols || []).map(s => `<span class="gene-tag">${escapeHtml(s)}</span>`).join("")}</td>
    </tr>
  `;
  }).join("") || '<tr><td colspan="6" class="hint-msg">沒有符合條件的病患</td></tr>';
}

document.querySelectorAll("#statsTable th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (sortState.col === col) { sortState.dir *= -1; }
    else { sortState.col = col; sortState.dir = col === "patient_name" || col === "patient_display_id" ? 1 : -1; }
    renderTable();
  });
});

document.getElementById("searchInput").addEventListener("input", renderTable);

loadUserInfo();
loadRanking();
