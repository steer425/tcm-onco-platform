requireLogin();

(async () => {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {
    console.error(err);
  }
})();

document.getElementById("logoutLink").addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: "POST" });
  } catch (err) {
    // 即使登出 API 失敗，也讓使用者可以離開前端
  }
  clearSession();
  window.location.href = "index.html";
});
