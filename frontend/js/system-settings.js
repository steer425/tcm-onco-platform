async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

// 主題色票預覽（與 css/style.css 裡 [data-theme="xxx"] 的定義保持一致）
const THEME_SWATCHES = {
  forest: ["#2f6f4f", "#1f4f37", "#f5f7f5"],
  ocean: ["#2563a8", "#173f6b", "#f2f6fa"],
  sunset: ["#c97a2f", "#8a4f1f", "#faf6f0"],
  slate: ["#52606d", "#323f4b", "#f4f5f6"],
};

async function loadThemes() {
  const grid = document.getElementById("themeGrid");
  try {
    const data = await api("/system-settings/theme");
    grid.innerHTML = data.available.map((t) => {
      const colors = THEME_SWATCHES[t.id] || ["#ccc", "#999", "#eee"];
      const isActive = t.id === data.theme;
      return `
        <div class="theme-option ${isActive ? "active" : ""}" onclick="applyTheme('${t.id}')">
          <div class="theme-swatch">${colors.map(c => `<div style="background:${c};"></div>`).join("")}</div>
          <div style="font-weight:600; font-size:13px;">${t.name}</div>
          ${isActive ? '<div class="host-detail">目前使用中</div>' : ''}
        </div>
      `;
    }).join("");
  } catch (err) {
    grid.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

window.applyTheme = async (themeId) => {
  try {
    await api("/system-settings/theme", { method: "PUT", body: JSON.stringify({ theme: themeId }) });
    document.documentElement.setAttribute("data-theme", themeId);
    await loadThemes();
  } catch (err) {
    alert("切換失敗：" + err.message);
  }
};

loadUserInfo();
loadThemes();
