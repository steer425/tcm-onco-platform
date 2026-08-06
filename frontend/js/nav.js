// 共用動態導覽選單：依 /nav/menu 回傳的可見功能項目渲染側邊選單。
// 每個頁面只需要在 <nav id="navContainer"></nav> 裡放這個空容器，
// 並在 <body> 上加 data-current-page="xxx.html" 屬性標示目前頁面（用來加上 active 樣式），
// 其餘由這支腳本自動處理。
// 前台/後台兩個分區採開合式設計（可收合），展開狀態記在 localStorage，重新整理後維持使用者上次的選擇。

const NAV_COLLAPSE_KEY_PREFIX = "tcm_nav_collapsed_";

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
  html += navSection("frontend", "前台功能", frontendItems, currentPage);
  html += navSection("backend", "後台管理", backendItems, currentPage);
  html += `<a href="#" id="logoutLink" style="margin-top:10px;">登出</a>`;

  container.innerHTML = html;
  bindSectionToggles();
  bindLogout();
}

function navSection(key, label, sectionItems, currentPage) {
  if (!sectionItems.length) return "";
  // 如果目前頁面就在這個分區裡，強制展開（避免使用者身處某頁卻看不到自己在哪個分區）；
  // 否則沿用使用者上次收合/展開的狀態，預設展開。
  const containsCurrent = sectionItems.some(i => i.page_url === currentPage);
  const stored = localStorage.getItem(NAV_COLLAPSE_KEY_PREFIX + key);
  const collapsed = containsCurrent ? false : (stored === "1");
  return `
    <div class="nav-section" data-section="${key}">
      <div class="nav-section-label nav-section-toggle" data-section-toggle="${key}">
        <span class="nav-caret">${collapsed ? "▸" : "▾"}</span> ${label}
      </div>
      <div class="nav-section-items" data-section-items="${key}" style="${collapsed ? "display:none;" : ""}">
        ${sectionItems.map(i => navLink(i, currentPage)).join("")}
      </div>
    </div>
  `;
}

function navLink(item, currentPage) {
  const active = item.page_url === currentPage ? " active" : "";
  return `<a href="${item.page_url}" class="${active.trim()}">${escapeHtmlNav(item.nav_label)}</a>`;
}

function bindSectionToggles() {
  document.querySelectorAll("[data-section-toggle]").forEach((el) => {
    el.addEventListener("click", () => {
      const key = el.dataset.sectionToggle;
      const itemsEl = document.querySelector(`[data-section-items="${key}"]`);
      const caretEl = el.querySelector(".nav-caret");
      const isCollapsed = itemsEl.style.display === "none";
      itemsEl.style.display = isCollapsed ? "" : "none";
      caretEl.textContent = isCollapsed ? "▾" : "▸";
      localStorage.setItem(NAV_COLLAPSE_KEY_PREFIX + key, isCollapsed ? "0" : "1");
    });
  });
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
if (typeof loadAndApplySiteLanguage === "function") {
  loadAndApplySiteLanguage();
}
