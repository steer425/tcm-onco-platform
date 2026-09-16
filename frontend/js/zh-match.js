/* 繁簡不敏感的中文比對 —— 全站唯一一份。
 *
 * ## 問題
 *
 * TCMSP 匯入的資料是**簡體**（当归、猫爪草、鱼腥草），但畫面上的語系預設是繁體，
 * 使用者自然會輸入「當歸」。直接字串比對永遠比不到，畫面上只會顯示「找不到」——
 * 看起來像資料庫沒有這味藥，實際上是我們的比對沒處理字形差異。
 *
 * 跟 v1.38.0 靶點標準化那次一樣，**失真是靜默的**：不會報錯，只會給一個看起來
 * 很合理的空結果。
 *
 * ## 為什麼是「兩邊都折成簡體」，不是「偵測輸入語系再轉換」
 *
 * 單向轉換（把使用者的輸入轉成簡體）只修好一半：
 *
 *   - 藥材名稱在庫裡是簡體 → 使用者打繁體，單向轉換有效 ✅
 *   - 疾病中文名稱是我們自己補的**繁體** → 使用者打簡體，單向轉換反而更找不到 ❌
 *
 * 而且「偵測語系」這件事本身就不可靠：「人参」兩個字簡繁同形，偵測不出來，
 * 也不需要偵測。**把比對的兩邊都折到同一個標準形（簡體）**，四種組合一次全部涵蓋，
 * 不需要知道誰是繁誰是簡。
 *
 * ## 退化行為
 *
 * OpenCC 由 CDN 載入，載不到時 zhNorm() 退回「只做 lowercase／trim」的原字串比對。
 * 搜尋會回到修正前的行為，但**不會壞掉**——不要讓一個 CDN 失敗把整個查詢站打死。
 */
(function () {
  let toCn = null;          // OpenCC 繁→簡轉換器
  let tried = false;        // 只嘗試建立一次，失敗就不要每次按鍵都重試
  const cache = new Map();  // 原字串 → 折疊後字串。清單頁每次按鍵都會掃過整份清單
  const CACHE_MAX = 20000;

  function converter() {
    if (!tried) {
      tried = true;
      try {
        if (window.OpenCC) toCn = OpenCC.Converter({ from: "tw", to: "cn" });
      } catch (e) { toCn = null; }
    }
    return toCn;
  }

  /** 折成比對用的標準形：小寫、去頭尾空白、繁體轉簡體。 */
  function zhNorm(text) {
    const raw = String(text == null ? "" : text);
    if (!raw) return "";
    const hit = cache.get(raw);
    if (hit !== undefined) return hit;

    let out = raw.toLowerCase().trim();
    const cc = converter();
    if (cc) {
      try { out = cc(out); } catch (e) { /* 轉換失敗就用原文，不要讓搜尋整個壞掉 */ }
    }
    if (cache.size >= CACHE_MAX) cache.clear();
    cache.set(raw, out);
    return out;
  }

  /** 折疊後的 indexOf，找不到回 -1。排序要用命中位置時用這支。 */
  function zhIndexOf(haystack, keyword) {
    const k = zhNorm(keyword);
    if (!k) return 0;
    return zhNorm(haystack).indexOf(k);
  }

  function zhIncludes(haystack, keyword) {
    return zhIndexOf(haystack, keyword) >= 0;
  }

  /** 任一欄位命中就算命中。傳進來的 null／undefined 會被忽略。 */
  function zhMatchAny(fields, keyword) {
    const k = zhNorm(keyword);
    if (!k) return true;
    return (fields || []).some(v => v && zhNorm(v).indexOf(k) >= 0);
  }

  /** 折疊後命中時把原字串裡對應的那一段包起來（給搜尋建議用）。 */
  function zhHighlight(text, keyword, esc) {
    const escape = esc || ((s) => s);
    const raw = String(text == null ? "" : text);
    const k = zhNorm(keyword);
    if (!k) return escape(raw);
    const folded = zhNorm(raw);
    const idx = folded.indexOf(k);
    // 折疊後長度可能與原字串不同（極少數一對多的字），只有長度一致時標記才對得準
    if (idx < 0 || folded.length !== raw.length) return escape(raw);
    return escape(raw.slice(0, idx)) + "<mark>" + escape(raw.slice(idx, idx + k.length)) +
           "</mark>" + escape(raw.slice(idx + k.length));
  }

  window.zhNorm = zhNorm;
  window.zhIndexOf = zhIndexOf;
  window.zhIncludes = zhIncludes;
  window.zhMatchAny = zhMatchAny;
  window.zhHighlight = zhHighlight;
})();
