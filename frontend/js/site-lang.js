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

  // 重要：一定要記住每個文字節點「最原始」的內容（第一次遇到這個節點時的值），
  // 之後不管切換幾次語言，永遠都是從這個原始值重新轉換，不能拿「畫面上目前顯示的文字」去轉。
  //
  // 這是真實踩過的 bug（v1.31.5）：如果先切到簡體中文（把文字從繁體轉成簡體），
  // 再切到韓文，convertText() 會拿「已經是簡體」的文字去查字典——但字典的 key 是繁體中文，
  // 簡體字完全比對不到，導致文字卡在簡體狀態出不來，永遠沒辦法真的變成韓文。
  // tw/cn 之間用 OpenCC 轉換方向性沒那麼嚴格還可能看起來正常，但只要牽涉到 en/ko 這種
  // 字典比對法，「不是從原始文字轉換」這件事就會直接讓翻譯失效。
  const originalTextMap = new WeakMap();
  function getOriginalText(node) {
    if (!originalTextMap.has(node)) {
      originalTextMap.set(node, node.nodeValue);
    }
    return originalTextMap.get(node);
  }

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
    // 注意：這裡不能因為 siteLang === 'tw' 就整段跳過不執行！
    // tw 也需要照樣掃過一次，convertText() 對 tw 會直接回傳原始文字，
    // 這正是「把之前被轉換成簡體/英文/韓文的文字還原回原始繁體中文」所需要的動作——
    // 如果因為「tw 不需要轉換」就跳過，等於切回繁體中文時畫面完全不會更新，
    // 文字會卡在切換前的語言狀態出不來（這是真實踩過的 bug，v1.31.5）。
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        const tag = node.parentElement && node.parentElement.tagName;
        if (tag === "SCRIPT" || tag === "STYLE") return NodeFilter.FILTER_REJECT;
        // 用「原始文字」（第一次遇到這個節點時記下來的值）判斷有沒有中文可以轉，
        // 不能用 node.nodeValue（目前畫面上的值）判斷——如果這個節點之前已經被轉成
        // 韓文/英文（沒有中文字元了），用目前值判斷會直接被 FILTER_SKIP 跳過，
        // 之後永遠沒有機會被重新轉換成其他語言。
        const original = getOriginalText(node);
        if (!original || !/[\u4e00-\u9fff]/.test(original)) return NodeFilter.FILTER_SKIP;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    // 重要：只在轉換後的文字「真的不一樣」才賦值。
    // MutationObserver 監看 characterData 變化的同時，這個函式也會修改 node.nodeValue，
    // 如果不管值有沒有變都賦值，瀏覽器會把「賦值」本身視為一次新的異動，
    // 又觸發同一個 observer 的回呼，回呼又再賦值一次……形成無窮迴圈，把主執行緒卡死
    // （這是真實發生過的 bug：使用者切換到韓文/英文後整個系統當機、跳出「網頁無回應」）。
    //
    // 同樣重要：轉換的來源永遠是 getOriginalText(node)（原始繁體中文），不是 node.nodeValue
    // （目前畫面上的值）——這是真實踩過的 bug（v1.31.5）：如果先切到簡體、再切到韓文，
    // 拿「已經是簡體」的文字去查韓文字典（字典 key 是繁體），會完全比對不到，
    // 文字就卡在簡體狀態出不來。一律從原始文字重新轉換，才能保證來回切換語言都正確。
    nodes.forEach((node) => {
      const original = getOriginalText(node);
      const converted = convertText(original);
      if (converted !== node.nodeValue) node.nodeValue = converted;
    });

    // 常見會放中文的屬性也一併轉換（placeholder、title、value 按鈕文字等）
    root.querySelectorAll("[placeholder], [title]").forEach((el) => {
      if (el.placeholder) {
        if (!el.dataset.i18nOrigPlaceholder) el.dataset.i18nOrigPlaceholder = el.placeholder;
        const orig = el.dataset.i18nOrigPlaceholder;
        if (/[\u4e00-\u9fff]/.test(orig)) {
          const converted = convertText(orig);
          if (converted !== el.placeholder) el.placeholder = converted;
        }
      }
      if (el.title) {
        if (!el.dataset.i18nOrigTitle) el.dataset.i18nOrigTitle = el.title;
        const orig = el.dataset.i18nOrigTitle;
        if (/[\u4e00-\u9fff]/.test(orig)) {
          const converted = convertText(orig);
          if (converted !== el.title) el.title = converted;
        }
      }
    });
  }

  function startObserving() {
    if (observer) observer.disconnect();
    if (!needsConversion()) return;
    observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) walkAndConvert(node);
          else if (node.nodeType === 3) {
            const original = getOriginalText(node);
            if (original && /[\u4e00-\u9fff]/.test(original)) {
              const converted = convertText(original);
              if (converted !== node.nodeValue) node.nodeValue = converted;
            }
          }
        });
        // characterData 變化：一樣要用原始文字重新轉換，不能用 m.target.nodeValue（目前值），理由同上
        if (m.type === "characterData" && m.target.nodeType === 3) {
          const original = getOriginalText(m.target);
          if (original && /[\u4e00-\u9fff]/.test(original)) {
            const converted = convertText(original);
            if (converted !== m.target.nodeValue) m.target.nodeValue = converted;
          }
        }
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  window.applySiteLanguage = async function (lang) {
    siteLang = lang;
    if (siteLang === "cn" && (!convToTw || !convToCn)) initOpenCCForSiteLang();
    // 不管切到哪種語言都要跑一次 walkAndConvert——包括 tw：
    // 如果之前切換過簡體/英文/韓文，畫面上的文字已經被改掉了，
    // 切回 tw 時要靠這次呼叫，用「原始文字」（getOriginalText）把它們還原回來，
    // 不能因為「tw 是原始語言不用轉」就跳過這個步驟（v1.31.5 修過的真實 bug）。
    walkAndConvert(document.body);
    if (needsConversion()) {
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
