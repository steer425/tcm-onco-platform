// 共用動態導覽選單：依 /nav/menu 回傳的可見功能項目渲染側邊選單。
// 每個頁面只需要在 <nav id="navContainer"></nav> 裡放這個空容器，
// 並在 <body> 上加 data-current-page="xxx.html" 屬性標示目前頁面（用來加上 active 樣式），
// 其餘由這支腳本自動處理。

async function renderNav() {
  const container = document.getElementById("navContainer");
  if (!container) return;

  let items = [];
  try {
    items = await api("/nav/menu");
  } catch (err) {
    container.innerHTML = `<a href="dashboard.html">Dashboard</a><a href="#" id="logoutLink">登出</a>`;
    bindLogout();
    return;
  }

  const currentPage = document.body.dataset.currentPage || "";
  const pageItems = items.filter(i => i.page_url);

  const frontendItems = pageItems.filter(i => i.show_frontend);
  const backendItems = pageItems.filter(i => i.show_backend);

  let html = "";
  if (frontendItems.length) {
    html += `<div class="nav-section-label">前台功能</div>`;
    html += frontendItems.map(i => navLink(i, currentPage)).join("");
  }
  if (backendItems.length) {
    html += `<div class="nav-section-label">後台管理</div>`;
    html += backendItems.map(i => navLink(i, currentPage)).join("");
  }
  html += `<a href="#" id="logoutLink" style="margin-top:10px;">登出</a>`;

  container.innerHTML = html;
  bindLogout();
}

function navLink(item, currentPage) {
  const active = item.page_url === currentPage ? " active" : "";
  return `<a href="${item.page_url}" class="${active.trim()}">${escapeHtmlNav(item.nav_label)}</a>`;
}

function escapeHtmlNav(s) {
  return (s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function bindLogout() {
  const link = document.getElementById("logoutLink");
  if (!link) return;
  link.addEventListener("click", async (e) => {
    e.preventDefault();
    try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: "POST" }); } catch (err) {}
    clearSession();
    window.location.href = "index.html";
  });
}

requireLogin();
renderNav();
