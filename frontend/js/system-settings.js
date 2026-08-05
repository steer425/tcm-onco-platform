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
loadDashboardWidgets();

// ---------- Dashboard 顯示規則（直接對應 F0-13-1 ~ F0-13-5，不用繞去角色管理）----------
const DASH_WIDGET_LABELS = {
  "F0-13-1": "🖥️ 主機資訊",
  "F0-13-2": "🏷️ 版本資訊",
  "F0-13-3": "📄 專案文件",
  "F0-13-4": "🎯 2026年工作目標",
  "F0-13-5": "📢 公告",
};

async function loadDashboardWidgets() {
  const tbody = document.getElementById("dashWidgetsBody");
  try {
    const features = await api("/features");
    const widgets = Object.keys(DASH_WIDGET_LABELS)
      .map(code => features.find(f => f.code === code))
      .filter(Boolean);
    tbody.innerHTML = widgets.map(f => `
      <tr data-id="${f.id}">
        <td>${DASH_WIDGET_LABELS[f.code] || f.name}</td>
        <td class="chk-cell"><input type="checkbox" data-field="enabled" ${f.enabled ? "checked" : ""}></td>
        <td class="chk-cell"><input type="checkbox" data-field="show_frontend" ${f.show_frontend ? "checked" : ""}></td>
        <td class="chk-cell"><input type="checkbox" data-field="show_backend" ${f.show_backend ? "checked" : ""}></td>
        <td><button onclick="saveDashWidget(this)">儲存</button></td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
}

window.saveDashWidget = async (btn) => {
  const tr = btn.closest("tr");
  const id = tr.dataset.id;
  const payload = {
    enabled: tr.querySelector('[data-field="enabled"]').checked,
    show_frontend: tr.querySelector('[data-field="show_frontend"]').checked,
    show_backend: tr.querySelector('[data-field="show_backend"]').checked,
  };
  const original = btn.textContent;
  btn.textContent = "儲存中..."; btn.disabled = true;
  try {
    await api(`/features/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    btn.textContent = "已儲存 ✓";
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1200);
  } catch (err) {
    alert("儲存失敗：" + err.message);
    btn.textContent = original; btn.disabled = false;
  }
};

// ---------- 查詢站預設項目（預設藥材／預設疾病）----------
let allHerbsCache = null;
let allDiseasesCache = null;

async function loadDefaultHerbState() {
  try {
    const [current, herbs] = await Promise.all([
      api("/system-settings/default-herb"),
      api("/tcmsp/herbs/public/list"),
    ]);
    allHerbsCache = herbs;
    const hint = document.getElementById("currentDefaultHerb");
    if (current.herb_id) {
      const h = herbs.find(x => x.herb_id === current.herb_id);
      hint.textContent = "目前預設：" + (h ? `${h.herb_cn_name || h.herb_en_name}（${h.herb_en_name || ""}）` : `herb_id=${current.herb_id}（找不到對應名稱）`);
    } else {
      hint.textContent = "目前預設：尚未設定（會自動退回搜尋「Panax Ginseng／人參」）";
    }
  } catch (err) {
    document.getElementById("currentDefaultHerb").textContent = "載入失敗：" + err.message;
  }
}

document.getElementById("defaultHerbSearch").addEventListener("input", (e) => {
  const kw = e.target.value.trim().toLowerCase();
  const resultsEl = document.getElementById("defaultHerbResults");
  if (!kw || !allHerbsCache) { resultsEl.style.display = "none"; return; }
  const matches = allHerbsCache.filter(h =>
    (h.herb_cn_name || "").toLowerCase().includes(kw) ||
    (h.herb_pinyin || "").toLowerCase().includes(kw) ||
    (h.herb_en_name || "").toLowerCase().includes(kw)
  ).slice(0, 30);
  resultsEl.innerHTML = matches.map(h =>
    `<div class="pick-result-row" onclick="chooseDefaultHerb(${h.herb_id})">${h.herb_cn_name || ""}（${h.herb_pinyin || ""}）· ${h.herb_en_name || ""}</div>`
  ).join("") || '<div class="pick-result-row" style="color:#999;">沒有符合的藥材</div>';
  resultsEl.style.display = "block";
});

window.chooseDefaultHerb = async (herbId) => {
  try {
    await api("/system-settings/default-herb", { method: "PUT", body: JSON.stringify({ herb_id: herbId }) });
    document.getElementById("defaultHerbSearch").value = "";
    document.getElementById("defaultHerbResults").style.display = "none";
    await loadDefaultHerbState();
  } catch (err) {
    alert("設定失敗：" + err.message);
  }
};

async function loadDefaultDiseaseState() {
  try {
    const [current, diseases] = await Promise.all([
      api("/system-settings/default-disease"),
      api("/tcmsp/diseases"),
    ]);
    allDiseasesCache = diseases;
    const hint = document.getElementById("currentDefaultDisease");
    if (current.dis_id) {
      const d = diseases.find(x => x.dis_id === current.dis_id);
      hint.textContent = "目前預設：" + (d ? `${d.disease_cn_name || d.disease_name}（${d.disease_name || ""}）` : `dis_id=${current.dis_id}（找不到對應名稱）`);
    } else {
      hint.textContent = "目前預設：尚未設定（會自動退回清單第一筆）";
    }
  } catch (err) {
    document.getElementById("currentDefaultDisease").textContent = "載入失敗：" + err.message;
  }
}

document.getElementById("defaultDiseaseSearch").addEventListener("input", (e) => {
  const kw = e.target.value.trim().toLowerCase();
  const resultsEl = document.getElementById("defaultDiseaseResults");
  if (!kw || !allDiseasesCache) { resultsEl.style.display = "none"; return; }
  const matches = allDiseasesCache.filter(d =>
    (d.disease_cn_name || "").toLowerCase().includes(kw) ||
    (d.disease_name || "").toLowerCase().includes(kw)
  ).slice(0, 30);
  resultsEl.innerHTML = matches.map(d =>
    `<div class="pick-result-row" onclick="chooseDefaultDisease('${d.dis_id}')">${d.disease_cn_name || ""}（${d.disease_name || ""}）</div>`
  ).join("") || '<div class="pick-result-row" style="color:#999;">沒有符合的疾病</div>';
  resultsEl.style.display = "block";
});

window.chooseDefaultDisease = async (disId) => {
  try {
    await api("/system-settings/default-disease", { method: "PUT", body: JSON.stringify({ dis_id: disId }) });
    document.getElementById("defaultDiseaseSearch").value = "";
    document.getElementById("defaultDiseaseResults").style.display = "none";
    await loadDefaultDiseaseState();
  } catch (err) {
    alert("設定失敗：" + err.message);
  }
};

loadDefaultHerbState();
loadDefaultDiseaseState();
