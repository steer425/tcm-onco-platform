// 全站語系切換（繁體中文／简体中文／English／한국어）。
//
// 兩種不同的技術手法，因為繁簡轉換跟真正的翻譯是完全不同的問題：
//   - 繁體 tw／簡體 cn：用 OpenCC 對文字節點做「字形轉換」，不管什麼句子都能轉，不需要維護字典。
//   - 英文 en／韓文 ko：需要「真正翻譯」，OpenCC 完全幫不上忙。做法是拿 window.I18N_DICT
//     （frontend/js/i18n-dict.js）裡的翻譯字典，逐一比對頁面上的文字節點，
//     如果整段文字剛好完全對應字典裡的某個詞條，就換成翻譯後的文字；比對不到的文字
//     （尤其是「共 502 種藥材」這種文字裡混著動態資料的句子）會維持原本的繁體中文，
//     這是字典比對法本身的限制，不是 bug——要完整覆蓋所有頁面所有句子，
//     需要持續往 i18n-dict.js 擴充詞條，不需要更動這支檔案的邏輯。
//
// 使用 MutationObserver 持續監看 DOM 變化，確保切換語系後，之後任何時間點新增進頁面的文字也會被套用。

(function () {
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
      if (siteLang === "cn") return convToCn ? convToCn(text) : text;
      if (siteLang === "en" || siteLang === "ko") {
        const dict = window.I18N_DICT && window.I18N_DICT[siteLang];
        if (!dict) return text;
        const trimmed = text.trim();
        const leading = text.slice(0, text.indexOf(trimmed));
        const trailing = text.slice(text.indexOf(trimmed) + trimmed.length);
        if (dict[trimmed]) return leading + dict[trimmed] + trailing; // 保留原本前後的空白/換行，避免排版跑掉
        return text; // 字典裡沒有這個詞條，維持原文（繁體中文）
      }
      return text; // tw：原始語言，不用轉
    } catch (e) { return text; }
  }

  function needsConversion() {
    return siteLang === "cn" || siteLang === "en" || siteLang === "ko";
  }

  function walkAndConvert(root) {
    if (!needsConversion()) return;
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
    if (!needsConversion()) return;
    observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) walkAndConvert(node);
          else if (node.nodeType === 3 && node.nodeValue && /[\u4e00-\u9fff]/.test(node.nodeValue)) {
            node.nodeValue = convertText(node.nodeValue);
          }
        });
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
    if (needsConversion()) {
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
