async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

const statusLabel = { pending: "審核中", approved: "已核准", rejected: "已駁回" };

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
      ? `<button onclick="reviewApp('${a.id}', true)">核准</button>
         <button class="danger" onclick="reviewApp('${a.id}', false)">駁回</button>`
      : `<button class="danger" onclick="deleteApp('${a.id}')">刪除紀錄</button>`;
    tr.innerHTML = `
      <td>${a.account}</td>
      <td><span class="tag">${statusLabel[a.status] || a.status}</span></td>
      <td>${a.notes || ""}</td>
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
