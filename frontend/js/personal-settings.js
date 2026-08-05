async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

const THEME_OPTIONS = [
  { id: "dark", name: "深色（預設）" },
  { id: "light", name: "淺色" },
];

async function loadQueryStationTheme() {
  const grid = document.getElementById("themeGrid");
  try {
    const data = await api("/user-preferences/query_station_theme");
    grid.innerHTML = THEME_OPTIONS.map((t) => {
      const isActive = t.id === data.value;
      return `
        <div class="theme-option ${isActive ? "active" : ""}" onclick="applyQueryStationTheme('${t.id}')">
          <div class="theme-preview ${t.id}"><span>Aa 範例文字</span></div>
          <div style="font-weight:600; font-size:13px;">${t.name}</div>
          ${isActive ? '<div class="host-detail">目前使用中</div>' : ''}
        </div>
      `;
    }).join("");
  } catch (err) {
    grid.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

window.applyQueryStationTheme = async (themeId) => {
  try {
    await api("/user-preferences/query_station_theme", { method: "PUT", body: JSON.stringify({ value: themeId }) });
    await loadQueryStationTheme();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
};

loadUserInfo();
loadQueryStationTheme();
