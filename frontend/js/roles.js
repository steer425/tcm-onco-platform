let allRoles = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) { /* ignore */ }
}

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

// ---- 權限矩陣（含全站功能設定）----
window.openPermModal = async (roleId, roleName) => {
  document.getElementById("permRoleName").textContent = roleName;
  document.getElementById("permModal").dataset.roleId = roleId;
  document.getElementById("permMsg").textContent = "";
  const perms = await api(`/roles/${roleId}/permissions`);
  const list = document.getElementById("permList");

  const rows = perms.map(p => `
    <tr data-feature="${p.feature_id}">
      <td>
        <div style="font-weight:600;">${p.feature_code}</div>
        <div class="host-detail">${p.feature_name}</div>
        ${p.page_url ? `<div class="host-detail">路徑：frontend\\${p.page_url}</div>` : '<div class="host-detail">（Dashboard 小工具，非獨立頁面）</div>'}
      </td>
      <td class="chk-cell"><input type="checkbox" data-field="can_view" ${p.can_view ? "checked" : ""}></td>
      <td class="chk-cell"><input type="checkbox" data-field="can_execute" ${p.can_execute ? "checked" : ""}></td>
      <td class="chk-cell"><input type="checkbox" data-field="enabled" ${p.enabled ? "checked" : ""}></td>
      <td class="chk-cell"><input type="checkbox" data-field="show_frontend" ${p.show_frontend ? "checked" : ""}></td>
      <td class="chk-cell"><input type="checkbox" data-field="show_backend" ${p.show_backend ? "checked" : ""}></td>
      <td><input type="text" data-field="nav_label" value="${p.nav_label || ""}" style="width:110px;" placeholder="(用名稱)"></td>
      <td><input type="number" data-field="sort_order" value="${p.sort_order}" style="width:56px;"></td>
    </tr>
  `).join("");

  list.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>功能項目</th>
          <th>可見<br><span class="host-detail">（此角色）</span></th>
          <th>可執行<br><span class="host-detail">（此角色）</span></th>
          <th>啟用<br><span class="host-detail">（全站）</span></th>
          <th>前台<br><span class="host-detail">（全站）</span></th>
          <th>後台<br><span class="host-detail">（全站）</span></th>
          <th>導覽文字<br><span class="host-detail">（全站）</span></th>
          <th>排序<br><span class="host-detail">（全站）</span></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  document.getElementById("permModal").style.display = "flex";
};

document.getElementById("permCancel").addEventListener("click", () => {
  document.getElementById("permModal").style.display = "none";
});

document.getElementById("permSave").addEventListener("click", async () => {
  const roleId = document.getElementById("permModal").dataset.roleId;
  const rows = document.querySelectorAll("#permList tbody tr");
  const permissions = Array.from(rows).map((tr) => ({
    feature_id: tr.dataset.feature,
    can_view: tr.querySelector('[data-field="can_view"]').checked,
    can_execute: tr.querySelector('[data-field="can_execute"]').checked,
    enabled: tr.querySelector('[data-field="enabled"]').checked,
    show_frontend: tr.querySelector('[data-field="show_frontend"]').checked,
    show_backend: tr.querySelector('[data-field="show_backend"]').checked,
    nav_label: tr.querySelector('[data-field="nav_label"]').value || null,
    sort_order: parseInt(tr.querySelector('[data-field="sort_order"]').value, 10) || 0,
  }));
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
