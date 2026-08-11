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

// ---------- 查詢站關聯網絡圖：節點數量上限預設值 ----------
async function loadGraphLimits() {
  try {
    const data = await api("/system-settings/graph-limits");
    document.getElementById("graphLimit1").value = data.graph_limit_level1;
    document.getElementById("graphLimit2").value = data.graph_limit_level2;
    document.getElementById("graphLimit3").value = data.graph_limit_level3;
  } catch (err) {
    document.getElementById("graphLimitsMsg").textContent = "載入失敗：" + err.message;
  }
}

document.getElementById("saveGraphLimitsBtn").addEventListener("click", async () => {
  const msg = document.getElementById("graphLimitsMsg");
  try {
    await api("/system-settings/graph-limits", {
      method: "PUT",
      body: JSON.stringify({
        graph_limit_level1: parseInt(document.getElementById("graphLimit1").value, 10),
        graph_limit_level2: parseInt(document.getElementById("graphLimit2").value, 10),
        graph_limit_level3: parseInt(document.getElementById("graphLimit3").value, 10),
      }),
    });
    msg.textContent = "已儲存 ✓";
    setTimeout(() => { msg.textContent = ""; }, 1500);
  } catch (err) {
    msg.textContent = "儲存失敗：" + err.message;
  }
});

loadGraphLimits();

// ---------- 資料庫備份到本機 ----------
function formatBytes(bytes) {
  if (bytes == null) return "-";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

async function loadBackupJobs() {
  const tbody = document.getElementById("backupJobsBody");
  try {
    const jobs = await api("/backup-jobs");
    tbody.innerHTML = jobs.map(j => `
      <tr>
        <td>${new Date(j.started_at).toLocaleString("zh-Hant")}</td>
        <td>${j.status === 'success' ? '✓ 成功' : j.status === 'failed' ? '✗ 失敗' : '進行中'}</td>
        <td>${formatBytes(j.size_bytes)}</td>
        <td>${j.notes || ""}</td>
        <td>${j.status === 'success' ? `<a href="#" onclick="downloadBackup('${j.id}'); return false;">下載</a>` : ""}</td>
      </tr>
    `).join("") || '<tr><td colspan="5" class="hint-msg">尚無備份紀錄</td></tr>';
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="hint-msg">載入失敗：${err.message}</td></tr>`;
  }
}

window.downloadBackup = async (jobId) => {
  try {
    const token = getToken();
    const res = await fetch((API_BASE || "") + `/system-settings/backup-database/${jobId}/download`, {
      headers: { "Authorization": "Bearer " + token },
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="(.+?)"/);
    const filename = match ? match[1] : "backup.enc";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  } catch (err) {
    alert("下載失敗：" + err.message);
  }
};

document.getElementById("createBackupBtn").addEventListener("click", async () => {
  const btn = document.getElementById("createBackupBtn");
  const msg = document.getElementById("backupMsg");
  btn.disabled = true;
  msg.textContent = "已送出備份請求，正在背景處理中...";
  try {
    const job = await api("/system-settings/backup-database", { method: "POST" });
    await loadBackupJobs();

    // 備份是在背景執行的（避免正式環境資料量大時，同步等待整個HTTP請求逾時），
    // 這裡改成輪詢查詢這筆紀錄的狀態，最多等 2 分鐘，每 2 秒查一次
    const jobId = job.id;
    let finalStatus = null;
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const jobs = await api("/backup-jobs");
      const current = jobs.find(j => j.id === jobId);
      if (current && current.status !== "running") {
        finalStatus = current;
        break;
      }
      msg.textContent = `背景處理中，已等待 ${(i + 1) * 2} 秒...`;
    }
    await loadBackupJobs();

    if (!finalStatus) {
      msg.textContent = "備份仍在處理中，請稍後重新整理頁面查看結果（背景作業會持續執行，不受這個頁面影響）";
    } else if (finalStatus.status === "success") {
      msg.textContent = "備份完成 ✓ 正在自動下載...";
      await window.downloadBackup(finalStatus.id);
      setTimeout(() => { msg.textContent = ""; }, 3000);
    } else {
      msg.textContent = "備份失敗：" + (finalStatus.notes || "未知錯誤");
    }
  } catch (err) {
    msg.textContent = "備份失敗：" + err.message;
  } finally {
    btn.disabled = false;
  }
});

loadBackupJobs();

// ---------- 唯讀模式（連線本機端資料庫） ----------
function formatLocalCacheInfo(cache) {
  if (!cache) return "目前還沒有本機端查詢快取。";
  return `本機端查詢快取建立於：${new Date(cache.built_at).toLocaleString("zh-Hant")}，大小 ${formatBytes(cache.size_bytes)}`;
}

async function loadReadOnlyMode() {
  try {
    const data = await api("/system-settings/read-only-mode");
    document.getElementById("readOnlyModeCheckbox").checked = data.enabled;
    document.getElementById("localCacheInfo").textContent = formatLocalCacheInfo(data.local_cache);
  } catch (err) { /* 載入失敗就維持預設不勾選 */ }

  // 主動檢查是否已經有成功的備份，沒有的話先在畫面上提示，
  // 不用等使用者按了勾選框、被後端擋下來才知道要先備份
  try {
    const jobs = await api("/backup-jobs");
    const hasSuccess = jobs.some(j => j.status === "success");
    if (!hasSuccess) {
      document.getElementById("readOnlyModeMsg").textContent = "尚未完成過任何資料庫備份，請先在上方建立備份，才能啟用唯讀模式。";
    }
  } catch (err) { /* 忽略，交給實際勾選時的錯誤訊息處理 */ }
}

document.getElementById("readOnlyModeCheckbox").addEventListener("change", async (e) => {
  const enabled = e.target.checked;
  const msg = document.getElementById("readOnlyModeMsg");
  const confirmText = enabled
    ? "啟用後，藥材/疾病/暗黑基因查詢站會改讀本機端快取（用最新一次成功的備份重建），並且全站（前台+後台，所有登入使用者）都無法執行任何新增/編輯/刪除操作，確定要啟用嗎？"
    : "確定要關閉唯讀模式，恢復正常的新增/編輯/刪除功能、查詢站改回讀取即時的雲端資料庫嗎？";
  if (!confirm(confirmText)) {
    e.target.checked = !enabled; // 使用者取消，checkbox 狀態要復原
    return;
  }
  msg.textContent = enabled ? "啟用中，正在用最新備份重建本機端查詢快取，可能需要幾秒鐘..." : "關閉中...";
  try {
    const result = await api("/system-settings/read-only-mode", { method: "PUT", body: JSON.stringify({ enabled }) });
    if (enabled) {
      msg.textContent = `已啟用唯讀模式 ✓ 本機端查詢快取已重建（${result.local_cache_row_count} 筆資料）`;
    } else {
      msg.textContent = "已關閉唯讀模式 ✓";
    }
    await loadReadOnlyMode();
    setTimeout(() => { msg.textContent = ""; }, 5000);
  } catch (err) {
    msg.textContent = "設定失敗：" + err.message;
    e.target.checked = !enabled;
  }
});

loadReadOnlyMode();

// ---------- 統計欄位重算 ----------
document.getElementById("recomputeStatsBtn").addEventListener("click", async () => {
  const btn = document.getElementById("recomputeStatsBtn");
  const msg = document.getElementById("recomputeStatsMsg");
  btn.disabled = true;
  msg.textContent = "重算中，可能需要幾秒鐘...";
  try {
    await api("/system-settings/recompute-stats", { method: "POST" });
    msg.textContent = "已完成 ✓";
    setTimeout(() => { msg.textContent = ""; }, 3000);
  } catch (err) {
    msg.textContent = "重算失敗：" + err.message;
  } finally {
    btn.disabled = false;
  }
});
