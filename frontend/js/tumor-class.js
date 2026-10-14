// 疾病的腫瘤分類標籤（v1.46.0）——各查詢站共用一份。
// 判定規則在後端 app/disease_tumor.py；這裡只負責顯示，代碼與中文名稱要跟那邊的 TUMOR_CLASS_LABELS 一致。
// 文字一律走 i18n-dict.js 的精確字串對照，所以 en／ko 要在那邊各補一份。
(function () {
  const LABELS = {
    malignant: "惡性腫瘤",
    in_situ: "原位癌",
    benign: "良性腫瘤",
    uncertain: "性質未明的腫瘤",
    unspecified: "腫瘤（未分良惡性）",
  };
  const BASIS = { icd10: "依 ICD-10 判定", icd9: "依 ICD-9 判定", name: "依病名判定", manual: "管理者指定" };
  // 半透明底色，深色／淺色主題都看得清楚
  const COLORS = {
    malignant: ["rgba(214,69,69,.18)", "#e06666", "rgba(214,69,69,.45)"],
    in_situ: ["rgba(230,126,34,.18)", "#e8913a", "rgba(230,126,34,.45)"],
    benign: ["rgba(52,152,219,.16)", "#4ea3dc", "rgba(52,152,219,.4)"],
    uncertain: ["rgba(201,162,39,.18)", "#c9a227", "rgba(201,162,39,.45)"],
    unspecified: ["rgba(142,110,190,.18)", "#a68bd4", "rgba(142,110,190,.45)"],
  };
  const ORDER = ["malignant", "in_situ", "uncertain", "benign", "unspecified"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function label(cls) { return cls ? (LABELS[cls] || cls) : "非腫瘤"; }
  function basis(b) { return BASIS[b] || ""; }

  // 小標籤：非腫瘤不顯示任何東西（837 筆裡大多數是非腫瘤，每列都標「非腫瘤」只是雜訊）
  function badge(d, opts) {
    if (!d || !d.tumor_class) return "";
    const c = COLORS[d.tumor_class] || COLORS.unspecified;
    const title = basis(d.tumor_basis);
    const small = opts && opts.small;
    return `<span class="tumor-badge" title="${esc(title)}" style="display:inline-block;background:${c[0]};color:${c[1]};` +
      `border:1px solid ${c[2]};border-radius:4px;padding:0 6px;font-size:${small ? "10.5px" : "11.5px"};` +
      `font-weight:600;margin-left:6px;white-space:nowrap;vertical-align:1px;">${esc(label(d.tumor_class))}</span>`;
  }

  // 一行說明：「腫瘤分類：惡性腫瘤（依 ICD-10 判定）」；非腫瘤也要說，詳情頁不能讓人以為是漏標
  function describe(d) {
    if (!d) return "";
    const b = basis(d.tumor_basis);
    return `<span class="tumor-describe">腫瘤分類：</span>${d.tumor_class ? badge(d) : `<span>非腫瘤</span>`}` +
      (b ? ` <span class="tumor-basis" style="opacity:.75;font-size:11.5px;">（<span>${esc(b)}</span>）</span>` : "");
  }

  // 篩選用：value 是 select 的值
  function matches(d, value) {
    if (!value) return true;
    if (value === "tumor") return !!d.tumor_class;
    if (value === "non_tumor") return !d.tumor_class;
    return d.tumor_class === value;
  }

  // 篩選下拉選單的選項。刻意不把筆數寫進選項文字：en／ko 是整段文字查字典，
  // 「惡性腫瘤（212）」這種混了數字的字串永遠翻不過去。筆數另外用 counts() 顯示
  function filterOptionsHtml(list, current) {
    const opt = (v, text) => `<option value="${v}"${v === current ? " selected" : ""}>${esc(text)}</option>`;
    return opt("", "全部疾病") + opt("tumor", "只看腫瘤") +
      ORDER.filter(c => list.some(d => d.tumor_class === c)).map(c => opt(c, LABELS[c])).join("") +
      opt("non_tumor", "非腫瘤");
  }
  function counts(list) {
    const out = { total: list.length, tumor: 0 };
    ORDER.forEach(c => { out[c] = 0; });
    list.forEach(d => { if (d.tumor_class) { out.tumor++; out[d.tumor_class] = (out[d.tumor_class] || 0) + 1; } });
    return out;
  }

  window.TumorClass = { LABELS, ORDER, label, basis, badge, describe, matches, filterOptionsHtml, counts };
})();
