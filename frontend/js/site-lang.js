// 全站語系切換（繁體中文／简体中文）。
//
// 做法：不是逐頁維護一份翻譯字串對照表（全站頁面很多，維護成本太高，也容易漏掉新增的文字），
// 而是用 OpenCC 對整個頁面「已經渲染出來的文字節點」做即時繁簡轉換。
// 這樣不管是靜態 HTML 裡寫死的文字，還是 JS 動態產生的內容，都會被轉換到，
// 且新增頁面/新增文字完全不需要額外處理。
//
// 使用 MutationObserver 持續監看 DOM 變化（例如表格重新渲染、Modal 開啟等動態內容），
// 確保切換語系後，之後任何時間點新增進頁面的文字也會被套用。

(function () {
  const STORAGE_KEY = "tcm_site_lang_cache"; // 短暫快取最後一次成功查到的設定，避免每個頁面都要重新打一次 API 才能決定要不要轉換
  let siteLang = "tw";
  let convToTw = null, convToCn = null;
  let observer = null;

  function initOpenCCForSiteLang() {
    try {
      convToTw = OpenCC.Converter({ from: "cn", to: "tw" });
      convToCn = OpenCC.Converter({ from: "tw", to: "cn" });
    } catch (e) { /* CDN 載入失敗就不轉換，不影響其他功能 */ }
  }

  function convertText(text) {
    if (!text || !text.trim()) return text;
    try {
      return siteLang === "cn" ? (convToCn ? convToCn(text) : text) : text; // 預設繁體（tw）不需要轉換，只有切成簡體時才轉
    } catch (e) { return text; }
  }

  function walkAndConvert(root) {
    if (siteLang !== "cn") return; // 繁體是我們原始撰寫的語言，不需要轉換
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
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
    nodes.forEach((node) => { node.nodeValue = convertText(node.nodeValue); });

    // 常見會放中文的屬性也一併轉換（placeholder、title、value 按鈕文字等）
    root.querySelectorAll("[placeholder], [title]").forEach((el) => {
      if (el.placeholder && /[\u4e00-\u9fff]/.test(el.placeholder)) el.placeholder = convertText(el.placeholder);
      if (el.title && /[\u4e00-\u9fff]/.test(el.title)) el.title = convertText(el.title);
    });
  }

  function startObserving() {
    if (observer) observer.disconnect();
    if (siteLang !== "cn") return;
    observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) walkAndConvert(node);
          else if (node.nodeType === 3 && node.nodeValue && /[\u4e00-\u9fff]/.test(node.nodeValue)) {
            node.nodeValue = convertText(node.nodeValue);
          }
        });
        // characterData 變動（例如 el.textContent = '...' 直接改變既有文字節點）也要處理
        if (m.type === "characterData" && m.target.nodeValue) {
          m.target.nodeValue = convertText(m.target.nodeValue);
        }
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  window.applySiteLanguage = async function (lang) {
    siteLang = lang;
    if (siteLang === "cn" && (!convToTw || !convToCn)) initOpenCCForSiteLang();
    if (siteLang === "cn") {
      walkAndConvert(document.body);
      startObserving();
    } else if (observer) {
      observer.disconnect();
    }
  };

  window.loadAndApplySiteLanguage = async function () {
    let lang = "tw";
    try {
      const data = await api("/user-preferences/site_language");
      lang = data.value || "tw";
    } catch (e) { /* 拿不到設定就用預設繁體 */ }
    await window.applySiteLanguage(lang);
    return lang;
  };

  window.getCurrentSiteLanguage = () => siteLang;
})();
