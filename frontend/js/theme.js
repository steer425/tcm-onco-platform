// 共用主題套用邏輯：讀取後端目前設定的配色主題，套用到 <html data-theme="...">。
// 刻意不依賴 api.js（可以放在 <head> 提早執行，避免頁面先顯示預設色再閃一次），
// 後端網址請跟 js/api.js 的 API_BASE 保持一致。
(function () {
  var THEME_API_BASE = "https://tcm-onco-backend.onrender.com";
  fetch(THEME_API_BASE + "/system-settings/theme")
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (data) {
      document.documentElement.setAttribute("data-theme", (data && data.theme) || "forest");
    })
    .catch(function () {
      document.documentElement.setAttribute("data-theme", "forest");
    });
})();
