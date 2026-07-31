requireLogin();

let allRoles = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) { /* ignore */ }
}

document.getElementById("logoutLink").addEventListener("click", async (e) => {
  e.preventDefault();
  try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: "POST" }); } catch (e) {}
  clearSession();
  window.location.href = "index.html";
});

async function loadRoles() {
  allRoles = await api("/roles");
  renderRoles(allRoles);
}

function renderRoles(list) {
  const tbody = document.getElementById("roleTableBody");
  tbody.innerHTML = "";
  list.forEach((role) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${role.name}</td>
      <td>${role.description || ""}</td>
      <td>${role.notes || ""}</td>
      <td>${role.user_count}</td>
      <td>${role.is_system ? '<span class="tag">系統內建</span>' : ''}</td>
      <td class="actions">
        <button class="secondary" onclick="openEditRole('${role.id}')">編輯</button>
        <button class="secondary" onclick="openPermModal('${role.id}','${role.name}')">權限矩陣</button>
        <button class="secondary" onclick="openUsersModal('${role.id}','${role.name}')">查看帳號</button>
        ${role.is_system ? '' : `<button class="danger" onclick="deleteRole('${role.id}')">刪除</button>`}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById("searchInput").addEventListener("input", (e) => {
  const kw = e.target.value.trim().toLowerCase();
  renderRoles(allRoles.filter(r => r.name.toLowerCase().includes(kw)));
});

// ---- 新增 / 編輯角色 ----
document.getElementById("newRoleBtn").addEventListener("click", () => {
  document.getElementById("roleModalTitle").textContent = "新增角色";
  document.getElementById("roleId").value = "";
  document.getElementById("roleName").value = "";
  document.getElementById("roleDesc").value = "";
  document.getElementById("roleNotes").value = "";
  document.getElementById("roleModalMsg").textContent = "";
  document.getElementById("roleModal").style.display = "flex";
});

window.openEditRole = (id) => {
  const role = allRoles.find(r => r.id === id);
  document.getElementById("roleModalTitle").textContent = "編輯角色";
  document.getElementById("roleId").value = role.id;
  document.getElementById("roleName").value = role.name;
  document.getElementById("roleDesc").value = role.description || "";
  document.getElementById("roleNotes").value = role.notes || "";
  document.getElementById("roleModalMsg").textContent = "";
  document.getElementById("roleModal").style.display = "flex";
};

document.getElementById("roleModalCancel").addEventListener("click", () => {
  document.getElementById("roleModal").style.display = "none";
});

document.getElementById("roleModalSave").addEventListener("click", async () => {
  const id = document.getElementById("roleId").value;
  const payload = {
    name: document.getElementById("roleName").value.trim(),
    description: document.getElementById("roleDesc").value.trim(),
    notes: document.getElementById("roleNotes").value.trim(),
  };
  const msg = document.getElementById("roleModalMsg");
  try {
    if (id) {
      await api(`/roles/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/roles", { method: "POST", body: JSON.stringify(payload) });
    }
    document.getElementById("roleModal").style.display = "none";
    await loadRoles();
  } catch (err) {
    msg.textContent = err.message;
  }
});

window.deleteRole = async (id) => {
  if (!confirm("確定要刪除此角色嗎？")) return;
  try {
    await api(`/roles/${id}`, { method: "DELETE" });
    await loadRoles();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

// ---- 權限矩陣 ----
window.openPermModal = async (roleId, roleName) => {
  document.getElementById("permRoleName").textContent = roleName;
  document.getElementById("permModal").dataset.roleId = roleId;
  document.getElementById("permMsg").textContent = "";
  const perms = await api(`/roles/${roleId}/permissions`);
  const list = document.getElementById("permList");
  list.innerHTML = "";
  perms.forEach((p) => {
    const row = document.createElement("div");
    row.className = "perm-row";
    row.innerHTML = `
      <span>${p.feature_code} ${p.feature_name}</span>
      <span>
        <label style="display:inline;"><input type="checkbox" data-feature="${p.feature_id}" data-type="view" ${p.can_view ? "checked" : ""}/> 可見</label>
        &nbsp;
        <label style="display:inline;"><input type="checkbox" data-feature="${p.feature_id}" data-type="execute" ${p.can_execute ? "checked" : ""}/> 可執行</label>
      </span>
    `;
    list.appendChild(row);
  });
  document.getElementById("permModal").style.display = "flex";
};

document.getElementById("permCancel").addEventListener("click", () => {
  document.getElementById("permModal").style.display = "none";
});

document.getElementById("permSave").addEventListener("click", async () => {
  const roleId = document.getElementById("permModal").dataset.roleId;
  const checkboxes = document.querySelectorAll("#permList input[type=checkbox]");
  const byFeature = {};
  checkboxes.forEach((cb) => {
    const fid = cb.dataset.feature;
    byFeature[fid] = byFeature[fid] || { feature_id: fid, can_view: false, can_execute: false };
    if (cb.dataset.type === "view") byFeature[fid].can_view = cb.checked;
    if (cb.dataset.type === "execute") byFeature[fid].can_execute = cb.checked;
  });
  const permissions = Object.values(byFeature);
  try {
    await api(`/roles/${roleId}/permissions`, {
      method: "PUT",
      body: JSON.stringify({ role_id: roleId, permissions }),
    });
    document.getElementById("permModal").style.display = "none";
    await loadRoles();
  } catch (err) {
    document.getElementById("permMsg").textContent = err.message;
  }
});

// ---- 角色底下帳號 ----
window.openUsersModal = async (roleId, roleName) => {
  document.getElementById("usersRoleName").textContent = roleName;
  const users = await api(`/roles/${roleId}/users`);
  const tbody = document.getElementById("usersListBody");
  tbody.innerHTML = "";
  if (users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="2" style="color:#6b7a70;">目前尚無帳號設定此角色</td></tr>`;
  }
  users.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${u.account}</td><td><span class="tag">${u.status}</span></td>`;
    tbody.appendChild(tr);
  });
  document.getElementById("usersModal").style.display = "flex";
};

document.getElementById("usersCancel").addEventListener("click", () => {
  document.getElementById("usersModal").style.display = "none";
});

loadUserInfo();
loadRoles();
