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

// 檢查 Google / Facebook 登入是否已啟用（後端有設定對應金鑰才會顯示按鈕）
(async () => {
  try {
    const data = await api("/auth/google/enabled");
    if (data.enabled) {
      document.getElementById("googleLoginWrap").style.display = "block";
    }
  } catch (err) {
    // 查詢失敗就不顯示按鈕，不影響一般帳密登入
  }
  try {
    const data = await api("/auth/facebook/enabled");
    if (data.enabled) {
      document.getElementById("facebookLoginWrap").style.display = "block";
    }
  } catch (err) {
    // 查詢失敗就不顯示按鈕，不影響一般帳密登入
  }
})();

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
