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
//
// ## 段落翻譯（v1.50.0）
//
// 上面的逐節點比對有兩個翻不過去的情況：
//   1. 段落裡有 <b>、<a> 等標籤 → 一句話被切成好幾個文字節點，每一段都對不上字典；
//   2. 句子裡混著數字 → 「目前還有 3 個成分…」永遠不會跟字典完全相同。
// 所以說明性的長段落另外走「段落翻譯」：元素加上 `data-i18n-block`，
// 以整段的文字（textContent）去查 window.I18N_BLOCKS（frontend/js/i18n-blocks.js），
// 查到就把整段 innerHTML 換成翻好的 HTML（保留粗體、換行）。字典的 key 可以用 {0}、{1} 當佔位，
// 對應位置的實際文字會**跳脫後**填回譯文（那些文字可能來自資料庫）。
//
// 規則：
//   - 只標在**純說明文字**上。整段 innerHTML 會被換掉，裡面若有綁了事件的按鈕、帶參數的連結會消失。
//   - 比對前兩邊都會正規化：連續空白縮成一個、中文字與全形標點旁的空白拿掉——
//     HTML 原始碼換行縮排造成的空白不影響比對。
//   - 簡體模式下，段落內的字形轉換也由這裡處理（不交給下面的逐節點轉換），
//     這樣才分得出「是程式重新畫了這一段」還是「是我們自己改的」。

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

  // ---------------------------------------------------------------- 段落翻譯
  const BLOCK_SEL = "[data-i18n-block]";
  const blockOrig = new WeakMap();     // 元素 → 原始（繁體）innerHTML
  const blockShown = new WeakMap();    // 元素 → 我們最後一次寫進去的 innerHTML
  const CJK = "\u3000-\u303f\u4e00-\u9fff\uff00-\uffef";
  const SPACE_NEAR_CJK = new RegExp(`\\s+(?=[${CJK}])|(?<=[${CJK}])\\s+`, "g");
  const blockIndex = {};               // lang → { exact: Map, templates: [{ re, value }] }

  function normKey(text) {
    return String(text || "").replace(/\s+/g, " ").replace(SPACE_NEAR_CJK, "").trim();
  }
  function escHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function getBlockIndex(lang) {
    if (blockIndex[lang]) return blockIndex[lang];
    const src = (window.I18N_BLOCKS && window.I18N_BLOCKS[lang]) || {};
    const idx = { exact: new Map(), templates: [] };
    Object.keys(src).forEach((k) => {
      const nk = normKey(k);
      if (/\{\d\}/.test(nk)) {
        const pattern = nk.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\\\{(\d)\\\}/g, "(.+?)");
        const order = (nk.match(/\{(\d)\}/g) || []).map((m) => Number(m[1]));
        idx.templates.push({ re: new RegExp(`^${pattern}$`), order, value: src[k] });
      } else {
        idx.exact.set(nk, src[k]);
      }
    });
    // 長的範本先試：短範本最後一個佔位是「.+?」錨定到結尾，會把後面整段吞進去
    // （例：單行的「KEGG：{0}條…最後同步{2}」會吃掉 KEGG＋Reactome 兩行的那一句）
    idx.templates.sort((a, b) => b.re.source.length - a.re.source.length);
    blockIndex[lang] = idx;
    return idx;
  }
  // plain=true：給一般文字節點用（見 convertText）——只接受不含 HTML 標籤的譯文，填回的值不跳脫
  function lookupBlock(lang, text, plain) {
    const idx = getBlockIndex(lang);
    const key = normKey(text);
    if (idx.exact.has(key)) {
      const v = idx.exact.get(key);
      return plain && /</.test(v) ? null : v;
    }
    for (const t of idx.templates) {
      if (plain && /</.test(t.value)) continue;
      const m = key.match(t.re);
      if (!m) continue;
      const vals = {};
      t.order.forEach((n, i) => { vals[n] = plain ? m[i + 1] : escHtml(m[i + 1]); });
      return t.value.replace(/\{(\d)\}/g, (_, n) => (n in vals ? vals[n] : ""));
    }
    return null;
  }
  // 瀏覽器序列化後的樣子（例：譯文裡的「&」讀回來會是「&amp;」）。
  // **比較一定要用這個**：直接拿譯文字串跟 el.innerHTML 比，只要有一個字元序列化後不同，
  // 就會「寫入 → 觸發 MutationObserver → 又不相等 → 再寫入」無窮迴圈，整頁卡死
  // （v1.51.0 兩岸中藥典頁的免責聲明有「usage & dosage」，英文模式一開就當機）。
  const normCache = new Map();
  function normHtml(html) {
    if (normCache.has(html)) return normCache.get(html);
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    const out = tpl.innerHTML;
    if (normCache.size > 2000) normCache.clear();
    normCache.set(html, out);
    return out;
  }
  function textOfHtml(html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    return tpl.content.textContent;
  }
  function applyBlock(el) {
    const current = el.innerHTML;
    // 跟我們上次寫進去的不一樣 → 頁面程式重新畫過這一段（或第一次遇到），現在的內容就是新的原文
    if (blockShown.get(el) !== current) blockOrig.set(el, current);
    const orig = blockOrig.get(el);
    let html = orig;
    if (siteLang === "en" || siteLang === "ko") {
      const text = textOfHtml(orig);
      let t = lookupBlock(siteLang, text);
      if (t == null) {
        // 段落字典沒有，再查逐詞字典（例：還沒載入資料前的分頁按鈕「選擇性靶點」）。那是純文字，要跳脫
        const dict = (window.I18N_DICT && window.I18N_DICT[siteLang]) || {};
        const w = dict[text.trim()] || dict[normKey(text)];
        if (w) t = escHtml(w);
      }
      if (t != null) html = t;
    }
    if (el.innerHTML !== normHtml(html)) el.innerHTML = html;
    if (siteLang === "cn" && convToCn) {
      const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = w.nextNode())) {
        if (/[\u4e00-\u9fff]/.test(n.nodeValue)) {
          const c = convToCn(n.nodeValue);
          if (c !== n.nodeValue) n.nodeValue = c;
        }
      }
    }
    blockShown.set(el, el.innerHTML);   // 讀回瀏覽器序列化後的值，下次比對才準
  }
  function applyBlocksIn(root) {
    if (!root || root.nodeType !== 1) return;
    if (root.matches && root.matches(BLOCK_SEL)) applyBlock(root);
    root.querySelectorAll(BLOCK_SEL).forEach(applyBlock);
  }
  function insideBlock(node) {
    const el = node.nodeType === 1 ? node : node.parentElement;
    return el ? el.closest(BLOCK_SEL) : null;
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
        // v1.50.0：再試段落字典裡「不含 HTML 標籤」的條目，主要是帶數字的短句範本（例：「共 {0} 種藥材」）。
        // 文字節點是用 nodeValue 寫回，不會被當成 HTML 解析，所以填回的值不需要跳脫。
        const t = lookupBlock(siteLang, trimmed, true);
        if (t != null) return leading + t + trailing;
        return text; // 字典裡沒有這個詞條，維持原文（繁體中文）
      }
      return text; // tw：原始語言，不用轉
    } catch (e) { return text; }
  }

  function convertNodeText(node, original) {
    const keep = siteLang !== "cn" && node.parentElement && node.parentElement.closest('[translate="no"]');
    return keep ? original : convertText(original);
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
        if (insideBlock(node)) return NodeFilter.FILTER_REJECT;   // 段落翻譯自己處理（見檔頭）

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
      // 標了 translate="no" 的是資料（藥材名、藥典原文）：英韓模式維持原文、簡體照常轉字形。
      // 不能直接跳過不處理——先切簡體再切英文時，要靠這裡把它還原回繁體（v1.51.0）。
      // 不標的話，字典裡剛好有「人參」就只有這一味變成英文，清單前後不一致
      const converted = convertNodeText(node, original);
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
      // 段落：同一批異動裡同一個段落只處理一次。我們自己寫入造成的異動，
      // 在 applyBlock 裡會因為「跟上次寫的一樣」而不做任何事，不會無窮迴圈。
      const blocks = new Set();
      mutations.forEach((m) => {
        const b = insideBlock(m.target);
        if (b) blocks.add(b);
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) node.querySelectorAll && node.querySelectorAll(BLOCK_SEL).forEach((x) => blocks.add(x));
          if (node.nodeType === 1 && node.matches && node.matches(BLOCK_SEL)) blocks.add(node);
        });
      });
      blocks.forEach((b) => { if (b.isConnected) applyBlock(b); });
      mutations.forEach((m) => {
        if (insideBlock(m.target)) return;
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) walkAndConvert(node);
          else if (node.nodeType === 3) {
            const original = getOriginalText(node);
            if (original && /[\u4e00-\u9fff]/.test(original)) {
              const converted = convertNodeText(node, original);
              if (converted !== node.nodeValue) node.nodeValue = converted;
            }
          }
        });
        // characterData 變化：一樣要用原始文字重新轉換，不能用 m.target.nodeValue（目前值），理由同上
        if (m.type === "characterData" && m.target.nodeType === 3) {
          const original = getOriginalText(m.target);
          if (original && /[\u4e00-\u9fff]/.test(original)) {
            const converted = convertNodeText(m.target, original);
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
    applyBlocksIn(document.body);   // 先換段落，下面的逐節點轉換會跳過段落內部
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
