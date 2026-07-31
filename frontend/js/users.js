requireLogin();

let allUsers = [];
let allRolesCache = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

document.getElementById("logoutLink").addEventListener("click", async (e) => {
  e.preventDefault();
  try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: "POST" }); } catch (e) {}
  clearSession();
  window.location.href = "index.html";
});

const statusLabel = { pending: "審核中", active: "啟用", suspended: "停用中" };

async function loadRolesForSelect() {
  allRolesCache = await api("/roles");
  const sel = document.getElementById("userRoles");
  sel.innerHTML = "";
  allRolesCache.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.id; opt.textContent = r.name;
    sel.appendChild(opt);
  });
}

async function loadUsers() {
  const params = new URLSearchParams();
  const kw = document.getElementById("searchInput").value.trim();
  const status = document.getElementById("statusFilter").value;
  if (kw) params.set("keyword", kw);
  if (status) params.set("status_filter", status);
  allUsers = await api(`/users?${params.toString()}`);
  renderUsers();
}

function renderUsers() {
  const tbody = document.getElementById("userTableBody");
  tbody.innerHTML = "";
  allUsers.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${u.account}</td>
      <td><span class="tag">${statusLabel[u.status] || u.status}</span></td>
      <td>${(u.role_names || []).join("、")}</td>
      <td>${u.suspend_reason || ""}</td>
      <td>${u.notes || ""}</td>
      <td class="actions">
        <button class="secondary" onclick="openEditUser('${u.id}')">編輯</button>
        <button class="danger" onclick="deleteUser('${u.id}')">刪除</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById("searchInput").addEventListener("input", loadUsers);
document.getElementById("statusFilter").addEventListener("change", loadUsers);

document.getElementById("newUserBtn").addEventListener("click", async () => {
  document.getElementById("userModalTitle").textContent = "新增帳號";
  document.getElementById("userId").value = "";
  document.getElementById("userAccount").value = "";
  document.getElementById("userAccount").disabled = false;
  document.getElementById("userPassword").value = "";
  document.getElementById("pwHint").textContent = "（必填）";
  document.getElementById("userStatus").value = "active";
  document.getElementById("userSuspendReason").value = "";
  document.getElementById("userNotes").value = "";
  document.getElementById("userModalMsg").textContent = "";
  await loadRolesForSelect();
  document.getElementById("userModal").style.display = "flex";
});

window.openEditUser = async (id) => {
  const u = allUsers.find(x => x.id === id);
  document.getElementById("userModalTitle").textContent = "編輯帳號";
  document.getElementById("userId").value = u.id;
  document.getElementById("userAccount").value = u.account;
  document.getElementById("userAccount").disabled = true;
  document.getElementById("userPassword").value = "";
  document.getElementById("pwHint").textContent = "（留空表示不變更）";
  document.getElementById("userStatus").value = u.status;
  document.getElementById("userSuspendReason").value = u.suspend_reason || "";
  document.getElementById("userNotes").value = u.notes || "";
  document.getElementById("userModalMsg").textContent = "";
  await loadRolesForSelect();
  const sel = document.getElementById("userRoles");
  Array.from(sel.options).forEach(opt => {
    opt.selected = (u.role_names || []).includes(opt.textContent);
  });
  document.getElementById("userModal").style.display = "flex";
};

document.getElementById("userModalCancel").addEventListener("click", () => {
  document.getElementById("userModal").style.display = "none";
});

document.getElementById("userModalSave").addEventListener("click", async () => {
  const id = document.getElementById("userId").value;
  const selectedRoles = Array.from(document.getElementById("userRoles").selectedOptions).map(o => o.value);
  const msg = document.getElementById("userModalMsg");
  try {
    if (id) {
      const payload = {
        status: document.getElementById("userStatus").value,
        suspend_reason: document.getElementById("userSuspendReason").value,
        notes: document.getElementById("userNotes").value,
        role_ids: selectedRoles,
      };
      const pw = document.getElementById("userPassword").value;
      if (pw) payload.password = pw;
      await api(`/users/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      const payload = {
        account: document.getElementById("userAccount").value.trim(),
        password: document.getElementById("userPassword").value,
        role_ids: selectedRoles,
        notes: document.getElementById("userNotes").value,
      };
      await api("/users", { method: "POST", body: JSON.stringify(payload) });
    }
    document.getElementById("userModal").style.display = "none";
    await loadUsers();
  } catch (err) {
    msg.textContent = err.message;
  }
});

window.deleteUser = async (id) => {
  const reason = prompt("請輸入停用（軟刪除）原因：", "後台刪除");
  if (reason === null) return;
  try {
    await api(`/users/${id}?reason=${encodeURIComponent(reason)}`, { method: "DELETE" });
    await loadUsers();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

loadUserInfo();
loadUsers();
