/* 靶點相關欄位的「來源資料庫連結」—— 全站唯一一份。
 *
 * ## 為什麼不是每個 ID 都直接串一條網址
 *
 * 這三個欄位看起來都像外部識別碼，實際上只有一個真的是：
 *
 * | 欄位 | 是什麼 | 能不能連外 |
 * |---|---|---|
 * | `Tar ID`（TAR04620） | **TCMSP 自己的編號**，跟 Mol ID 同性質 | 只能連到 TCMSP 的靶點瀏覽表 |
 * | `Target Name` | 蛋白質名稱 | **標準化過的可以直接連 UniProt 條目** ← 真正有用的那一條 |
 * | `DrugBank ID`（h001） | **不是 DrugBank 編號** | 格式對才連，否則不連 |
 *
 * ### DrugBank ID 這一欄為什麼要驗格式
 *
 * `models.TcmspTargetUniprot` 的說明早就寫過：TCMSP 的 `drugbank_id`
 * 「其實是流水號（3、7、16…）不是 DrugBank ID」，實際資料裡也出現過 `h001` 這種值。
 * 真正的 DrugBank 藥物編號是 `DB` + 5 碼數字，生物實體編號是 `BE` + 7 碼數字。
 *
 * **盲目串上去會得到一整欄 404。** 連結壞掉比沒有連結更糟——
 * 使用者會以為是資料庫沒收錄，而不是我們把識別碼接錯地方。
 * 所以這裡只在格式符合時才連，未來資料若換成真的 DrugBank ID，連結會自動亮起來。
 *
 * ### ⚠️ 不要用 tcmspsearch.php 那組網址
 *
 * repo 裡 `tcmsp_query.html` 的 `tcmspHerbUrl()` 是
 * `tcmspsearch.php?qr=...&qsr=...&token=<STATIC_TOKEN>`。
 * 2026-09-17 實測：那個 token 已經失效，不管查藥材還是靶點都回
 * 「Error querying database..」。**新的連結一律不要建在它上面**，
 * `browse.php?qc=targets` 則仍然正常。
 */
(function () {
  const TCMSP_TARGETS = 'https://www.tcmsp-e.com/browse.php?qc=targets';
  const UNIPROT_ENTRY = 'https://www.uniprot.org/uniprotkb/';
  const UNIPROT_SEARCH = 'https://www.uniprot.org/uniprotkb?query=';
  const DRUGBANK_DRUG = 'https://go.drugbank.com/drugs/';
  const DRUGBANK_BIO = 'https://go.drugbank.com/bio_entities/';

  const DB_DRUG_RE = /^DB\d{5}$/i;      // 藥物：DB00945
  const DB_BIO_RE = /^BE\d{7}$/i;       // 生物實體（靶點）：BE0000048

  const esc = (s) => String(s == null ? '' : s)
    .replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const NA = '<span class="hint-msg">-</span>';

  function out(href, text, title) {
    return `<a class="src-link" href="${esc(href)}" target="_blank" rel="noopener"`
         + `${title ? ` title="${esc(title)}"` : ''}>${esc(text)} ↗</a>`;
  }

  /** Tar ID → TCMSP 靶點瀏覽表。TCMSP 沒有單一靶點的固定網址，只能連到那張表。 */
  function tarId(value) {
    if (!value) return NA;
    return out(TCMSP_TARGETS, value,
      'TCMSP 自有的靶點編號，只在 TCMSP 內有意義。點擊開啟 TCMSP 的 All targets 瀏覽表。');
  }

  /** 蛋白質靶點 → UniProt。有標準化過的登錄號就直連條目，沒有就用名稱搜尋。 */
  function uniprot(accession, name) {
    const label = name || accession || '';
    if (!label) return NA;
    if (accession) {
      return out(UNIPROT_ENTRY + encodeURIComponent(accession) + '/entry', label,
        `UniProt ${accession} — 本平台靶點標準化比對到的蛋白質條目`);
    }
    // 還沒標準化：用名稱搜尋人類蛋白，總比沒有入口好，但要講清楚這是搜尋不是確定的對應
    return out(UNIPROT_SEARCH + encodeURIComponent(`"${label}" AND organism_id:9606`), label,
      '這個靶點尚未完成 UniProt 標準化，連結為名稱搜尋結果，不是已確認的對應');
  }

  /** DrugBank ID：只有格式對得上才連結，否則原樣顯示並說明。 */
  function drugbank(value) {
    const v = String(value == null ? '' : value).trim();
    if (!v) return NA;
    if (DB_DRUG_RE.test(v)) return out(DRUGBANK_DRUG + v.toUpperCase(), v, 'DrugBank 藥物條目');
    if (DB_BIO_RE.test(v)) return out(DRUGBANK_BIO + v.toUpperCase(), v, 'DrugBank 生物實體條目');
    return `<span class="src-plain" title="TCMSP 這一欄存的不是 DrugBank 編號（真正的格式是 DB+5 碼或 BE+7 碼），`
         + `是 TCMSP 內部的參照值，因此不提供外部連結">${esc(v)}</span>`;
  }

  window.srcLinks = { tarId, uniprot, drugbank };
})();
