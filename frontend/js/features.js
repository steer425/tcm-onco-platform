let allFeatures = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

async function loadFeatures() {
  allFeatures = await api("/features");
  renderFeatures();
}

function renderFeatures() {
  const tbody = document.getElementById("featureTableBody");
  tbody.innerHTML = "";
  allFeatures
    .slice()
    .sort((a, b) => (a.sort_order - b.sort_order) || a.code.localeCompare(b.code))
    .forEach((f) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${f.code}</td>
        <td><span class="module-badge">${f.module}</span></td>
        <td>${f.name}</td>
        <td><input class="nav-label-input" data-field="nav_label" value="${f.nav_label || ""}" placeholder="(用名稱)"></td>
        <td>${f.page_url ? f.page_url : '<span class="hint-msg">（小工具，非頁面）</span>'}</td>
        <td class="chk-cell"><input type="checkbox" data-field="enabled" ${f.enabled ? "checked" : ""}></td>
        <td class="chk-cell"><input type="checkbox" data-field="show_frontend" ${f.show_frontend ? "checked" : ""} ${f.page_url ? "" : "disabled"}></td>
        <td class="chk-cell"><input type="checkbox" data-field="show_backend" ${f.show_backend ? "checked" : ""} ${f.page_url ? "" : "disabled"}></td>
        <td><input class="sort-input" type="number" data-field="sort_order" value="${f.sort_order}"></td>
        <td><button onclick="saveFeature('${f.id}', this)">儲存</button></td>
      `;
      tbody.appendChild(tr);
    });
}

window.saveFeature = async (id, btn) => {
  const tr = btn.closest("tr");
  const payload = {
    nav_label: tr.querySelector('[data-field="nav_label"]').value || null,
    enabled: tr.querySelector('[data-field="enabled"]').checked,
    show_frontend: tr.querySelector('[data-field="show_frontend"]').checked,
    show_backend: tr.querySelector('[data-field="show_backend"]').checked,
    sort_order: parseInt(tr.querySelector('[data-field="sort_order"]').value, 10) || 0,
  };
  const originalText = btn.textContent;
  btn.textContent = "儲存中...";
  btn.disabled = true;
  try {
    await api(`/features/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    btn.textContent = "已儲存 ✓";
    setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 1200);
    await loadFeatures();
  } catch (err) {
    alert("儲存失敗：" + err.message);
    btn.textContent = originalText;
    btn.disabled = false;
  }
};

loadUserInfo();
loadFeatures();
