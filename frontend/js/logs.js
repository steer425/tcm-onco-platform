async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    ["audit", "login", "backup"].forEach((t) => {
      document.getElementById(`tab-${t}`).style.display = (t === btn.dataset.tab) ? "block" : "none";
    });
  });
});

async function loadAudit() {
  const kw = document.getElementById("auditFilter").value.trim();
  const params = new URLSearchParams();
  if (kw) params.set("actor_account", kw);
  const list = await api(`/audit-logs?${params.toString()}`);
  const tbody = document.getElementById("auditBody");
  tbody.innerHTML = "";
  list.forEach((l) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${new Date(l.created_at).toLocaleString()}</td>
      <td>${l.actor_account || "系統"}</td>
      <td>${l.action}</td>
      <td>${l.target_type || ""} ${l.target_id ? l.target_id.slice(0,8) : ""}</td>
      <td>${l.detail || ""}</td>
      <td>${l.notes || ""}</td>
      <td><button class="secondary" onclick="editNote('audit-logs','${l.id}', '${(l.notes||'').replace(/'/g,"\\'")}')">補充備注</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadLogin() {
  const kw = document.getElementById("loginFilter").value.trim();
  const params = new URLSearchParams();
  if (kw) params.set("account", kw);
  const list = await api(`/login-logs?${params.toString()}`);
  const tbody = document.getElementById("loginBody");
  tbody.innerHTML = "";
  list.forEach((l) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${l.account}</td>
      <td>${l.ip_address || ""}</td>
      <td>${l.device_id || ""}</td>
      <td>${new Date(l.login_at).toLocaleString()}</td>
      <td>${l.logout_at ? new Date(l.logout_at).toLocaleString() : "尚未登出"}</td>
      <td>${l.duration_seconds ?? ""}</td>
      <td>${l.notes || ""}</td>
      <td><button class="secondary" onclick="editNote('login-logs','${l.id}', '${(l.notes||'').replace(/'/g,"\\'")}')">補充備注</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadBackup() {
  const list = await api("/backup-jobs");
  const tbody = document.getElementById("backupBody");
  tbody.innerHTML = "";
  const statusLabel = { running: "執行中", success: "成功", failed: "失敗" };
  list.forEach((b) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${new Date(b.started_at).toLocaleString()}</td>
      <td>${b.finished_at ? new Date(b.finished_at).toLocaleString() : ""}</td>
      <td><span class="tag">${statusLabel[b.status] || b.status}</span></td>
      <td>${b.file_path || ""}</td>
      <td>${b.notes || ""}</td>
      <td>
        <button class="secondary" onclick="editNote('backup-jobs','${b.id}', '${(b.notes||'').replace(/'/g,"\\'")}')">補充備注</button>
        <button class="danger" onclick="deleteBackup('${b.id}')">刪除紀錄</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.editNote = async (resource, id, current) => {
  const notes = prompt("備注內容：", current || "");
  if (notes === null) return;
  try {
    await api(`/${resource}/${id}/notes`, { method: "PUT", body: JSON.stringify({ notes }) });
    if (resource === "audit-logs") await loadAudit();
    if (resource === "login-logs") await loadLogin();
    if (resource === "backup-jobs") await loadBackup();
  } catch (err) {
    alert("更新失敗：" + err.message);
  }
};

window.deleteBackup = async (id) => {
  if (!confirm("確定刪除此備份紀錄？（僅刪除紀錄，不影響實際備份檔案）")) return;
  try {
    await api(`/backup-jobs/${id}`, { method: "DELETE" });
    await loadBackup();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

document.getElementById("triggerBackupBtn").addEventListener("click", async () => {
  try {
    await api("/backup-jobs/trigger", { method: "POST" });
    await loadBackup();
  } catch (err) {
    alert("觸發失敗：" + err.message);
  }
});

document.getElementById("auditFilter").addEventListener("input", loadAudit);
document.getElementById("loginFilter").addEventListener("input", loadLogin);

loadUserInfo();
loadAudit();
loadLogin();
loadBackup();
