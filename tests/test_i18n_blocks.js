/* 段落翻譯字典（frontend/js/i18n-blocks.js）與逐詞字典（i18n-dict.js）的驗收腳本（v1.50.0）。
 *
 * 用 node 直接跑：node tests/test_i18n_blocks.js（python -m tests.run_all 會自動帶到）。
 *
 * 檢查的是「畫面上看不出來、但一錯就整段退回中文或出安全問題」的東西：
 *   1. en 與 ko 的 key 完全相同（v1.31.x 起 en／ko 覆蓋率不一致出過好幾次）
 *   2. 每個 key 的 {0}、{1}… 佔位，在 en 與 ko 的譯文裡都有、而且沒多出來
 *   3. 譯文是會直接塞進 innerHTML 的 HTML：不得有 <script>、on…= 事件屬性、javascript: 連結；<b> 要成對
 *   4. 正規化後沒有兩個 key 撞在一起（後面那個會默默蓋掉前面那個）
 *   5. **靜態 HTML 裡每一個 data-i18n-block 段落，字典裡都找得到**——
 *      改了頁面上的中文卻忘了改字典，這裡會紅，不會等到英韓使用者回報才發現
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
global.window = {};
require(path.join(ROOT, "frontend/js/i18n-blocks.js"));
require(path.join(ROOT, "frontend/js/i18n-dict.js"));
const BLOCKS = window.I18N_BLOCKS;
const DICT = window.I18N_DICT;

let fail = 0;
function check(label, cond, extra) {
  console.log(`  ${cond ? "✅" : "❌"} ${label}${extra !== undefined && extra !== "" ? "  " + JSON.stringify(extra).slice(0, 300) : ""}`);
  if (!cond) fail++;
}

// 與 frontend/js/site-lang.js 的 normKey() 相同
const CJK = "　-〿一-鿿＀-￯";
const SPACE_NEAR_CJK = new RegExp(`\\s+(?=[${CJK}])|(?<=[${CJK}])\\s+`, "g");
const normKey = (t) => String(t || "").replace(/\s+/g, " ").replace(SPACE_NEAR_CJK, "").trim();
const holes = (s) => [...new Set((String(s).match(/\{\d\}/g) || []))].sort().join(",");

console.log("\n【en／ko 對等】");
const enK = Object.keys(BLOCKS.en), koK = Object.keys(BLOCKS.ko);
check("段落字典 en 與 ko 的 key 完全相同",
      enK.length === koK.length && enK.every((k) => k in BLOCKS.ko),
      enK.filter((k) => !(k in BLOCKS.ko)).concat(koK.filter((k) => !(k in BLOCKS.en))));
const dEn = Object.keys(DICT.en), dKo = Object.keys(DICT.ko);
check("逐詞字典 en 與 ko 的 key 完全相同",
      dEn.length === dKo.length && dEn.every((k) => k in DICT.ko),
      dEn.filter((k) => !(k in DICT.ko)).concat(dKo.filter((k) => !(k in DICT.en))).slice(0, 10));

console.log("\n【佔位】");
const badHoles = [];
for (const k of enK) {
  for (const lang of ["en", "ko"]) {
    if (holes(k) !== holes(BLOCKS[lang][k])) badHoles.push(`${lang}: ${k.slice(0, 40)}`);
  }
}
check("每個 key 的 {n} 佔位在 en／ko 譯文裡都一致", badHoles.length === 0, badHoles);

console.log("\n【譯文的 HTML 安全】");
const unsafe = [], unbalanced = [];
for (const lang of ["en", "ko"]) {
  for (const [k, v] of Object.entries(BLOCKS[lang])) {
    if (/<\s*script|\son\w+\s*=|javascript:|<\s*iframe|<\s*img/i.test(v)) unsafe.push(`${lang}: ${k.slice(0, 40)}`);
    for (const tag of ["b", "p", "span", "h4", "code"]) {
      const open = (v.match(new RegExp(`<${tag}(\\s[^>]*)?>`, "g")) || []).length;
      const close = (v.match(new RegExp(`</${tag}>`, "g")) || []).length;
      if (open !== close) unbalanced.push(`${lang} <${tag}> ${open}/${close}: ${k.slice(0, 30)}`);
    }
  }
}
check("譯文沒有 <script>、事件屬性、javascript: 連結、iframe、img", unsafe.length === 0, unsafe);
check("譯文的 <b>／<p>／<span>／<h4>／<code> 都成對", unbalanced.length === 0, unbalanced);

console.log("\n【正規化後不重複】");
const seen = new Map(), dup = [];
for (const k of enK) {
  const n = normKey(k);
  if (seen.has(n)) dup.push(k.slice(0, 40));
  seen.set(n, k);
}
check("正規化後沒有兩個 key 撞在一起", dup.length === 0, dup);

console.log("\n【靜態 HTML 的段落都在字典裡】");
const decode = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
// 段落翻譯查不到時會退到逐詞字典（site-lang.js applyBlock），所以兩邊都算
const exact = new Set(enK.map(normKey).concat(dEn.map(normKey)));
const templates = enK.filter((k) => /\{\d\}/.test(k)).map((k) => {
  const nk = normKey(k);
  return new RegExp("^" + nk.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\\\{(\d)\\\}/g, "(.+?)") + "$");
});
const missing = [];
let staticCount = 0;
for (const f of fs.readdirSync(path.join(ROOT, "frontend")).filter((x) => x.endsWith(".html"))) {
  const html = fs.readFileSync(path.join(ROOT, "frontend", f), "utf8");
  const re = /<(p|div|span|h3|h4|button)\b[^>]*\bdata-i18n-block\b[^>]*>([\s\S]*?)<\/\1>/g;
  let m;
  while ((m = re.exec(html))) {
    const text = normKey(decode(m[2].replace(/<[^>]+>/g, "")));
    if (!text || !/[一-鿿]/.test(text)) continue;   // 空的（由 JS 填）或沒有中文的跳過
    staticCount++;
    if (!exact.has(text) && !templates.some((t) => t.test(text))) missing.push(`${f}: ${text.slice(0, 50)}`);
  }
}
check(`靜態 HTML 的 ${staticCount} 個段落都在段落字典裡`, missing.length === 0 && staticCount > 0, missing);

console.log("\n" + "=".repeat(60));
if (fail) {
  console.log(`❌ 有 ${fail} 項未通過`);
  process.exit(1);
}
console.log(`✅ 段落翻譯字典驗證全部通過（段落 ${enK.length} 條、逐詞 ${dEn.length} 條）`);
