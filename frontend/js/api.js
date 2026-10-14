// 共用 API 呼叫工具
// 測試站（staging）功能目前暫停使用，先固定指向正式站後端。
// 之後要恢復雙站環境時，可以參考 CHANGELOG v1.7.0 的 resolveApiBase() 寫法。
const API_BASE = "https://tcm-onco-backend.onrender.com";

function getToken() {
  return localStorage.getItem("tcm_token");
}

function getLoginLogId() {
  return localStorage.getItem("tcm_login_log_id");
}

function setSession(token, loginLogId) {
  localStorage.setItem("tcm_token", token);
  localStorage.setItem("tcm_login_log_id", loginLogId);
}

function clearSession() {
  localStorage.removeItem("tcm_token");
  localStorage.removeItem("tcm_login_log_id");
}

function requireLogin() {
  if (!getToken()) {
    window.location.href = "index.html";
  }
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;

  let res;
  try {
    res = await fetch(API_BASE + path, { ...options, headers });
  } catch (netErr) {
    // 網路斷線、伺服器沒回應（Render 喚醒失敗時常見）：給看得懂的訊息，不要丟出瀏覽器的 "Failed to fetch"
    throw new Error("無法連線到伺服器，請稍後再試");
  }
  // 401 只有在「帶著登入憑證卻被拒」時才代表登入過期，這時才清掉並導回登入頁。
  // 登入本身帳密錯誤也是 401——如果照樣導回登入頁，頁面會立刻重新載入，
  // 錯誤訊息一閃而過、使用者根本看不到（v1.46.2 實際回報）。
  if (res.status === 401 && token && !path.startsWith("/auth/login")) {
    clearSession();
    window.location.href = "index.html";
    throw new Error("未登入或登入已過期");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const msg = (data && data.detail) ? data.detail : `發生錯誤 (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

// 產生一個簡易裝置指紋，作為 device_id 傳給後端（無法取得真實網卡 MAC 位址，此為瀏覽器隱私限制下的替代方案）
function getDeviceFingerprint() {
  let fp = localStorage.getItem("tcm_device_fp");
  if (!fp) {
    fp = "web-" + Math.random().toString(36).slice(2) + "-" + Date.now();
    localStorage.setItem("tcm_device_fp", fp);
  }
  return fp;
}
