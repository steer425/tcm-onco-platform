async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

const statusLabel = { pending: "審核中", approved: "已核准", rejected: "已駁回" };

// 外部輸入（申請人填的帳號、備註）一律跳脫後才放進畫面（v1.49.0）
const escHtml = (v) => String(v == null ? "" : v)
  .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function loadApplications() {
  const status = document.getElementById("statusFilter").value;
  const params = new URLSearchParams();
  if (status) params.set("status_filter", status);
  const list = await api(`/account-applications?${params.toString()}`);
  const tbody = document.getElementById("appTableBody");
  tbody.innerHTML = "";
  list.forEach((a) => {
    const tr = document.createElement("tr");
    const actions = a.status === "pending"
      ? `<button onclick="reviewApp('${escHtml(a.id)}', true)">核准</button>
         <button class="danger" onclick="reviewApp('${escHtml(a.id)}', false)">駁回</button>`
      : `<button class="danger" onclick="deleteApp('${escHtml(a.id)}')">刪除紀錄</button>`;
    tr.innerHTML = `
      <td>${escHtml(a.account)}</td>
      <td><span class="tag">${escHtml(statusLabel[a.status] || a.status)}</span></td>
      <td>${escHtml(a.notes || "")}</td>
      <td>${new Date(a.created_at).toLocaleString()}</td>
      <td class="actions">${actions}</td>
    `;
    tbody.appendChild(tr);
  });
}

window.reviewApp = async (id, approve) => {
  const notes = prompt(approve ? "核准備注（選填）：" : "駁回原因（選填）：", "");
  if (notes === null) return;
  try {
    await api(`/account-applications/${id}/review`, {
      method: "PUT", body: JSON.stringify({ approve, notes }),
    });
    await loadApplications();
  } catch (err) {
    alert("審核失敗：" + err.message);
  }
};

window.deleteApp = async (id) => {
  if (!confirm("確定刪除此申請紀錄？")) return;
  try {
    await api(`/account-applications/${id}`, { method: "DELETE" });
    await loadApplications();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

document.getElementById("statusFilter").addEventListener("change", loadApplications);

loadUserInfo();
loadApplications();
