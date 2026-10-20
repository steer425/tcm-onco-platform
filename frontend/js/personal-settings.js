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

const LANG_OPTIONS = [
  { id: "tw", name: "繁體中文（預設）" },
  { id: "cn", name: "简体中文" },
  { id: "en", name: "English" },
  { id: "ko", name: "한국어" },
];

async function loadSiteLanguage() {
  const grid = document.getElementById("langGrid");
  try {
    const data = await api("/user-preferences/site_language");
    grid.innerHTML = LANG_OPTIONS.map((l) => {
      const isActive = l.id === data.value;
      return `
        <div class="theme-option ${isActive ? "active" : ""}" onclick="applySiteLanguagePref('${l.id}')">
          <div style="font-weight:600; font-size:14px; padding:10px 0;">${l.name}</div>
          ${isActive ? '<div class="host-detail">目前使用中</div>' : ''}
        </div>
      `;
    }).join("");
  } catch (err) {
    grid.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

window.applySiteLanguagePref = async (lang) => {
  try {
    await api("/user-preferences/site_language", { method: "PUT", body: JSON.stringify({ value: lang }) });
    if (typeof applySiteLanguage === "function") await applySiteLanguage(lang);
    await loadSiteLanguage();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
};

/* ------------------------------------------------------------------
 * 個人資訊（v1.44.0）：個人資訊、密碼設定、登入紀錄、異動紀錄
 * 後端是 /me/*，**只回傳本人的資料**，這裡不需要也不可以傳 user_id。
 * user_agent、異動說明都可能含使用者輸入或外部內容，一律經 esc() 再寫進畫面。
 * ------------------------------------------------------------------ */
const esc = (s) => String(s == null ? "" : s)
  .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtTime(iso) {
  if (!iso) return "—";
  // 後端存 UTC 且不帶時區，補上 Z 讓瀏覽器換成本地時間
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
  if (isNaN(d)) return esc(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fmtDuration(sec) {
  if (sec == null) return "—";
  if (sec < 60) return `${sec} 秒`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m} 分`;
  return `${Math.floor(m / 60)} 小時 ${m % 60} 分`;
}

const STATUS_LABEL = { active: "啟用中", pending: "審核中", suspended: "已停用" };
const PROVIDER_LABEL = { google: "Google", facebook: "Facebook", xiaohongshu: "小紅書", wechat: "WeChat" };
const METHOD_LABEL = { password: "帳號密碼", google: "Google", facebook: "Facebook" };
// 只翻跟帳號本身有關的；其餘照原代碼顯示，旁邊的說明欄是中文
const ACTION_LABEL = {
  login: "登入", logout: "登出", login_google: "Google 登入", login_facebook: "Facebook 登入",
  change_own_password: "自行變更密碼", update_user: "更新帳號資料", create_user: "建立帳號",
  delete_user_soft: "停用／刪除帳號", review_application: "帳號申請審核", apply_account: "申請帳號",
  link_oauth: "綁定第三方登入", unlink_oauth: "解除第三方綁定",
  google_oauth_link: "首次以 Google 登入", facebook_oauth_link: "首次以 Facebook 登入",
};

async function loadProfile() {
  const grid = document.getElementById("profileGrid");
  try {
    const p = await api("/me/profile");
    const item = (k, v) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`;
    const prev = p.previous_login;
    grid.innerHTML = [
      item("帳號", esc(p.account)),
      item("帳號狀態", esc(STATUS_LABEL[p.status] || p.status)),
      item("角色", p.roles.length ? p.roles.map((r) => `<span class="tag">${esc(r)}</span>`).join(" ") : "無角色"),
      item("帳號建立時間", fmtTime(p.created_at)),
      item("上一次登入", prev ? `${fmtTime(prev.login_at)}${prev.ip_address ? `<br><span class="hint-msg" style="margin:0;">${esc(prev.ip_address)}</span>` : ""}` : "（這是第一次登入）"),
      item("累計登入次數", esc(p.login_count)),
      item("最近一次自行變更密碼", p.password_changed_at ? fmtTime(p.password_changed_at) : "從未變更"),
      item("第三方登入綁定", p.oauth_accounts.length
        ? p.oauth_accounts.map((o) => `${esc(PROVIDER_LABEL[o.provider] || o.provider)}（${fmtTime(o.linked_at)}）`).join("<br>")
        : "未綁定"),
    ].join("");
    // 第三方登入自動建立的帳號，本機密碼是系統產生的隨機值，本人不知道「目前密碼」
    const hint = document.getElementById("pwOauthHint");
    if (p.oauth_accounts.length && !p.password_changed_at) {
      hint.style.display = "";
      hint.textContent = "如果你的帳號是用 Google／Facebook 登入時自動建立的，系統替你設的是隨機密碼，你不會知道「目前密碼」。"
        + "需要以帳號密碼登入時，請聯絡管理者重設。";
    }
    if (!p.password_changed_at && p.account === "admin") {
      const msg = document.getElementById("pwMsg");
      msg.className = "error-msg";
      msg.textContent = "⚠️ 管理者帳號從未變更過密碼。若仍是系統預設值，請立即變更。";
    }
  } catch (err) {
    grid.innerHTML = `<p class="hint-msg">載入失敗：${esc(err.message)}</p>`;
  }
}

let loginLimit = 20;
async function loadLoginLogs() {
  const table = document.getElementById("loginTable");
  try {
    const r = await api(`/me/login-logs?limit=${loginLimit}`);
    document.getElementById("loginTotal").textContent = `共 ${r.total} 筆，顯示最近 ${r.items.length} 筆`;
    document.getElementById("loginMore").style.display = r.total > r.items.length ? "" : "none";
    table.innerHTML = r.items.length ? `
      <thead><tr><th>登入時間</th><th>登出時間</th><th>停留</th><th>方式</th><th>IP</th><th>瀏覽器／裝置</th></tr></thead>
      <tbody>${r.items.map((l, i) => `<tr>
        <td>${fmtTime(l.login_at)}${i === 0 ? ' <span class="tag">本次</span>' : ""}</td>
        <td>${l.logout_at ? fmtTime(l.logout_at) : '<span class="hint-msg" style="margin:0;">未登出</span>'}</td>
        <td>${fmtDuration(l.duration_seconds)}</td>
        <td>${esc(METHOD_LABEL[l.method] || l.method)}</td>
        <td>${esc(l.ip_address || "—")}</td>
        <td class="ua">${esc(l.user_agent || "—")}</td></tr>`).join("")}</tbody>`
      : "<tbody><tr><td>沒有登入紀錄。</td></tr></tbody>";
  } catch (err) {
    table.innerHTML = `<tbody><tr><td class="hint-msg">載入失敗：${esc(err.message)}</td></tr></tbody>`;
  }
}

let auditLimit = 20;
async function loadAuditLogs() {
  const table = document.getElementById("auditTable");
  const incl = document.getElementById("auditIncludeLogin").checked;
  try {
    const r = await api(`/me/audit-logs?limit=${auditLimit}&include_login=${incl}`);
    document.getElementById("auditTotal").textContent = `共 ${r.total} 筆，顯示最近 ${r.items.length} 筆`;
    document.getElementById("auditMore").style.display = r.total > r.items.length ? "" : "none";
    table.innerHTML = r.items.length ? `
      <thead><tr><th>時間</th><th>操作</th><th>執行者</th><th>說明</th></tr></thead>
      <tbody>${r.items.map((a) => `<tr>
        <td>${fmtTime(a.created_at)}</td>
        <td><span class="tag ${a.action === "change_own_password" ? "pw" : ""}">${esc(ACTION_LABEL[a.action] || a.action)}</span></td>
        <td>${a.by_me ? "本人" : `<span class="tag other">他人操作</span> ${esc(a.actor_account || "")}`}</td>
        <td>${esc(a.detail || "")}</td></tr>`).join("")}</tbody>`
      : "<tbody><tr><td>沒有異動紀錄。</td></tr></tbody>";
  } catch (err) {
    table.innerHTML = `<tbody><tr><td class="hint-msg">載入失敗：${esc(err.message)}</td></tr></tbody>`;
  }
}

document.getElementById("pwForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("pwMsg");
  const btn = document.getElementById("pwSubmit");
  const cur = document.getElementById("pwCurrent").value;
  const nw = document.getElementById("pwNew").value;
  const cf = document.getElementById("pwConfirm").value;
  msg.className = "error-msg";
  if (nw !== cf) { msg.textContent = "兩次輸入的新密碼不一致"; return; }
  btn.disabled = true;
  try {
    const r = await api("/me/password", {
      method: "PUT",
      body: JSON.stringify({ current_password: cur, new_password: nw, confirm_password: cf }),
    });
    msg.className = "ok-msg";
    msg.textContent = `${r.message}${r.note ? "　" + r.note : ""}`;
    document.getElementById("pwForm").reset();
    // v1.49.0：改密碼後所有登入（包含這一個）都已失效，留在這頁只會一直 401；停 3 秒讓人看到訊息再回登入頁
    if (r.relogin) {
      try { sessionStorage.setItem("tcm_logout_reason", r.message); } catch (e) { /* 私密視窗 */ }
      setTimeout(() => { clearSession(); window.location.href = "index.html"; }, 3000);
      return;
    }
    loadProfile();
    loadAuditLogs();
  } catch (err) {
    msg.className = "error-msg";
    msg.textContent = err.message || "變更失敗";
  } finally {
    btn.disabled = false;
  }
});
// v1.49.0：登出所有裝置（懷疑帳號被盜用時用；這一台也會登出）
document.getElementById("logoutAllBtn").addEventListener("click", async () => {
  if (!confirm("確定要登出所有裝置嗎？包含這一台，之後要重新登入。")) return;
  const m = document.getElementById("logoutAllMsg");
  try {
    const r = await api("/me/logout-all", { method: "POST" });
    m.textContent = r.message;
    try { sessionStorage.setItem("tcm_logout_reason", r.message); } catch (e) { /* 私密視窗 */ }
    setTimeout(() => { clearSession(); window.location.href = "index.html"; }, 2000);
  } catch (err) {
    m.textContent = "失敗：" + err.message;
  }
});
document.getElementById("loginMore").addEventListener("click", () => { loginLimit += 50; loadLoginLogs(); });
document.getElementById("auditMore").addEventListener("click", () => { auditLimit += 50; loadAuditLogs(); });
document.getElementById("auditIncludeLogin").addEventListener("change", () => { auditLimit = 20; loadAuditLogs(); });

loadUserInfo();
loadProfile();
loadLoginLogs();
loadAuditLogs();
loadSiteLanguage();
loadQueryStationTheme();
