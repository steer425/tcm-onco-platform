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
