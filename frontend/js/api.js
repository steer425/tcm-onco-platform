// 共用 API 呼叫工具
const API_BASE = "https://tcm-onco-backend.onrender.com"; // 已部署於 Render 的後端 API 網址

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

  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) {
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
