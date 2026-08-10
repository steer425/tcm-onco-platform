// ---------- 登入頁語系切換（預設英文） ----------
const LOGIN_LANG_STORAGE_KEY = "tcm_login_lang";
let loginConvToTw = null, loginConvToCn = null;
function initLoginOpenCC() {
  try {
    loginConvToTw = OpenCC.Converter({ from: "cn", to: "tw" });
    loginConvToCn = OpenCC.Converter({ from: "tw", to: "cn" });
  } catch (e) { /* CDN 載入失敗就不轉換 */ }
}
function convertLoginText(text, lang) {
  if (!text || !text.trim()) return text;
  try {
    if (lang === "cn") return loginConvToCn ? loginConvToCn(text) : text;
    if (lang === "en" || lang === "ko") {
      const dict = window.I18N_DICT && window.I18N_DICT[lang];
      if (!dict) return text;
      const trimmed = text.trim();
      const leading = text.slice(0, text.indexOf(trimmed));
      const trailing = text.slice(text.indexOf(trimmed) + trimmed.length);
      return dict[trimmed] ? leading + dict[trimmed] + trailing : text;
    }
    return text; // tw：原文
  } catch (e) { return text; }
}
function applyLoginLanguage(lang) {
  if (lang === "tw") return; // 原文就是繁體中文，不用轉換，重新整理頁面即可還原
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      const tag = node.parentElement && node.parentElement.tagName;
      if (tag === "SCRIPT" || tag === "STYLE") return NodeFilter.FILTER_REJECT;
      if (!node.nodeValue || !/[\u4e00-\u9fff]/.test(node.nodeValue)) return NodeFilter.FILTER_SKIP;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);
  nodes.forEach((node) => { node.nodeValue = convertLoginText(node.nodeValue, lang); });
}

initLoginOpenCC();
const langSelect = document.getElementById("langSelect");
const savedLoginLang = localStorage.getItem(LOGIN_LANG_STORAGE_KEY) || "en"; // 預設英文
langSelect.value = savedLoginLang;
applyLoginLanguage(savedLoginLang);
langSelect.addEventListener("change", (e) => {
  localStorage.setItem(LOGIN_LANG_STORAGE_KEY, e.target.value);
  window.location.reload(); // 重新載入頁面確保原文（繁體中文）狀態一致，再套用新語系，避免重複轉換疊加
});

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const account = document.getElementById("account").value.trim();
  const password = document.getElementById("password").value;
  const errorMsg = document.getElementById("errorMsg");
  errorMsg.textContent = "";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ account, password, device_id: getDeviceFingerprint() }),
    });
    setSession(data.access_token, data.login_log_id);
    // 登入成功後，把登入頁選定的語系存回這個帳號的個人化設定，之後登入系統其他頁面都會沿用這個語系
    try {
      await api("/user-preferences/site_language", {
        method: "PUT",
        body: JSON.stringify({ value: langSelect.value }),
      });
    } catch (prefErr) { /* 存語系偏好失敗不影響登入本身 */ }
    window.location.href = "dashboard.html";
  } catch (err) {
    errorMsg.textContent = err.message;
  }
});

document.getElementById("applyBtn").addEventListener("click", () => {
  document.getElementById("applyModal").style.display = "flex";
});
document.getElementById("applyCancel").addEventListener("click", () => {
  document.getElementById("applyModal").style.display = "none";
});
document.getElementById("applySubmit").addEventListener("click", async () => {
  const account = document.getElementById("applyAccount").value.trim();
  const password = document.getElementById("applyPassword").value;
  const notes = document.getElementById("applyNotes").value;
  const msg = document.getElementById("applyMsg");
  msg.textContent = "送出中...";
  try {
    await api("/auth/apply", {
      method: "POST",
      body: JSON.stringify({ account, password, notes }),
    });
    msg.textContent = "申請已送出，請等待管理者審核通過後再登入。";
  } catch (err) {
    msg.textContent = "申請失敗：" + err.message;
  }
});

// 檢查 Google / Facebook 登入是否已啟用（後端有設定對應金鑰才會顯示按鈕）。
// Render 免費方案閒置一段時間會休眠，喚醒需要 30~60 秒，第一次查詢很可能會失敗——
// 這裡加上重試機制，避免使用者誤以為「沒有整合第三方登入」。
async function checkOAuthEnabled(path, wrapId, maxRetries = 6, retryDelayMs = 8000) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const data = await api(path);
      if (data.enabled) {
        document.getElementById(wrapId).style.display = "block";
      }
      return; // 查到明確結果（不管是否啟用），結束重試
    } catch (err) {
      if (attempt === 0) {
        // 第一次失敗時，先給使用者一個提示，說明可能是伺服器正在喚醒中
        const hint = document.getElementById("thirdPartyLoginHint");
        if (hint) hint.style.display = "block";
      }
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, retryDelayMs));
      }
    }
  }
  // 重試多次仍失敗，隱藏提示（可能後端真的有問題，但不阻擋一般帳密登入）
  const hint = document.getElementById("thirdPartyLoginHint");
  if (hint) hint.style.display = "none";
}

checkOAuthEnabled("/auth/google/enabled", "googleLoginWrap");
checkOAuthEnabled("/auth/facebook/enabled", "facebookLoginWrap");

document.getElementById("googleLoginBtn").addEventListener("click", () => {
  window.location.href = (API_BASE || "") + "/auth/google/login";
});

document.getElementById("facebookLoginBtn").addEventListener("click", () => {
  window.location.href = (API_BASE || "") + "/auth/facebook/login";
});

// 顯示 Google/Facebook 登入失敗/待審核等錯誤訊息（從 oauth_callback.html 轉導回登入頁時帶的參數）
(() => {
  const params = new URLSearchParams(window.location.search);
  const err = params.get("google_error");
  if (!err) return;
  const messages = {
    pending_review: "帳號審核中，請等待管理者審核通過後再登入。",
    suspended: "此帳號已被停用，請聯繫管理者。",
    google_denied: "已取消 Google 登入授權。",
    facebook_denied: "已取消 Facebook 登入授權。",
    facebook_no_email: "這個 Facebook 帳號沒有提供 email，無法建立系統帳號，請改用其他登入方式。",
    invalid_state: "登入驗證逾時或失效，請重新嘗試。",
    missing_code: "第三方服務沒有回傳授權碼，請重新嘗試。",
    token_exchange_failed: "與第三方服務交換登入憑證失敗，請重新嘗試。",
    missing_profile: "無法取得帳號資訊，請確認已授權必要的權限。",
  };
  document.getElementById("errorMsg").textContent = messages[err] || ("第三方登入失敗：" + err);
})();
