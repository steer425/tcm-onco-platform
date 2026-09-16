/* frontend/js/zh-match.js 的驗收腳本（Node 直接跑，不需要瀏覽器）。
 *
 * 這支測試最重要的部分是**四種繁簡組合都要通過**。
 * 使用者回報的 bug 只是其中一種（庫裡簡體、輸入繁體），但疾病中文名稱是我們自己補的
 * 繁體，方向剛好相反——只修單向會留下另一半的洞。
 *
 * 跟其他驗收腳本一樣，用 node 執行：
 *   node tests/test_zh_match.js
 */
const fs = require("fs");
const path = require("path");

// 這個 repo 沒有 npm 依賴，不應該為了一支測試逼大家 npm install。
// 有裝 opencc-js 就用真的（連 OpenCC 的 API 用法一起驗），沒裝就用替身——
// **要驗的是我們的比對邏輯（兩邊都折疊、快取、退化、標記位置），不是 OpenCC 的轉換表。**
let OpenCC, MODE;
try {
  OpenCC = require("opencc-js");
  MODE = "真實 opencc-js";
} catch (e) {
  const TABLE = { "當": "当", "歸": "归", "貓": "猫", "魚": "鱼", "參": "参",
                  "類": "类", "風": "风", "濕": "湿", "節": "节", "黃": "黄", "連": "连" };
  OpenCC = { Converter: () => (t) => String(t).replace(/./g, c => TABLE[c] || c) };
  MODE = "替身轉換表（未安裝 opencc-js，如需完整驗證請執行 npm i opencc-js）";
}
console.log(`\n轉換器：${MODE}`);

// 用瀏覽器的方式載入：先掛上 window.OpenCC，再執行 zh-match.js
global.window = global;
global.OpenCC = OpenCC;
const src = fs.readFileSync(path.join(__dirname, "..", "frontend", "js", "zh-match.js"), "utf8");
eval(src);

const FAIL = [];
function check(label, cond, extra) {
  console.log(`  ${cond ? "✅" : "❌"} ${label}${extra !== undefined ? "  " + JSON.stringify(extra) : ""}`);
  if (!cond) FAIL.push(label);
}

// 資料庫裡的真實樣子：TCMSP 匯入的藥材名稱是簡體
const HERBS = [
  { herb_cn_name: "当归", herb_pinyin: "Danggui", herb_en_name: "Angelicae Sinensis Radix" },
  { herb_cn_name: "人参", herb_pinyin: "Renshen", herb_en_name: "Panax Ginseng C. A. Mey." },
  { herb_cn_name: "猫爪草", herb_pinyin: "Maozhaocao", herb_en_name: "Ranunculus Ternatus Radix" },
  { herb_cn_name: "鱼腥草", herb_pinyin: "Yuxingcao", herb_en_name: "Houttuyniae Herba" },
];
// 疾病中文名稱是平台自己補的，方向相反：庫裡是繁體
const DISEASES = [
  { disease_name: "Rheumatoid arthritis", disease_cn_name: "類風濕性關節炎", dis_id: "DIS00702" },
  { disease_name: "Breast cancer", disease_cn_name: "乳癌", dis_id: "DIS00117" },
];

const find = (rows, kw, fields) =>
  rows.filter(r => window.zhMatchAny(fields.map(f => r[f]), kw));

console.log("\n【使用者回報的情境：庫裡簡體、輸入繁體】");
check("**輸入「當歸」查得到 当归**",
  find(HERBS, "當歸", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);
check("輸入「貓爪草」查得到 猫爪草",
  find(HERBS, "貓爪草", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);
check("輸入「魚腥草」查得到 鱼腥草",
  find(HERBS, "魚腥草", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);

console.log("\n【修正前就能用的，不可以被弄壞】");
check("輸入簡體「当归」仍然查得到",
  find(HERBS, "当归", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);
check("拼音 Danggui 仍然查得到",
  find(HERBS, "danggui", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);
check("英文學名仍然查得到（大小寫不敏感）",
  find(HERBS, "GINSENG", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);
check("部分比對仍然有效（当 → 当归）",
  find(HERBS, "当", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 1);
check("空字串回全部，不是回零筆",
  find(HERBS, "", ["herb_cn_name"]).length === HERBS.length);
check("只有空白也回全部",
  find(HERBS, "   ", ["herb_cn_name"]).length === HERBS.length);

console.log("\n【簡繁同形的字不需要偵測語系】");
check("「人参」與「人參」查到同一筆",
  find(HERBS, "人参", ["herb_cn_name"]).length === 1 &&
  find(HERBS, "人參", ["herb_cn_name"]).length === 1);

console.log("\n【反方向：庫裡繁體、輸入簡體（單向轉換修不好的那一半）】");
check("**輸入簡體「类风湿」查得到 類風濕性關節炎**",
  find(DISEASES, "类风湿", ["disease_name", "disease_cn_name"]).length === 1,
  find(DISEASES, "类风湿", ["disease_name", "disease_cn_name"]).map(d => d.disease_cn_name));
check("輸入繁體「類風濕」也查得到",
  find(DISEASES, "類風濕", ["disease_name", "disease_cn_name"]).length === 1);
check("英文疾病名稱不受影響",
  find(DISEASES, "breast", ["disease_name", "disease_cn_name"]).length === 1);

console.log("\n【查不到的就是查不到，不可以亂命中】");
check("不存在的藥材回零筆",
  find(HERBS, "黃連", ["herb_cn_name", "herb_pinyin", "herb_en_name"]).length === 0);
check("不同的藥材不會互相命中",
  find(HERBS, "当归", ["herb_cn_name"])[0].herb_cn_name === "当归");

console.log("\n【zhNorm 與 zhIndexOf 本身】");
check("zhNorm 折成小寫簡體", window.zhNorm("當歸 Danggui") === "当归 danggui", window.zhNorm("當歸 Danggui"));
check("zhNorm 去掉頭尾空白", window.zhNorm("  當歸  ") === "当归");
check("zhNorm 對 null／undefined 回空字串", window.zhNorm(null) === "" && window.zhNorm(undefined) === "");
check("zhIndexOf 回命中位置（排序要用）", window.zhIndexOf("四物湯當歸", "當歸") === 3,
  window.zhIndexOf("四物湯當歸", "當歸"));
check("zhIndexOf 找不到回 -1", window.zhIndexOf("当归", "黄连") === -1);
check("zhIncludes 與 zhMatchAny 結果一致",
  window.zhIncludes("当归", "當歸") === true && window.zhMatchAny(["当归"], "當歸") === true);
check("zhMatchAny 忽略 null 欄位不會爆",
  window.zhMatchAny([null, undefined, "当归"], "當歸") === true);

console.log("\n【zhHighlight】");
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
check("繁體關鍵字標到簡體原文的正確位置",
  window.zhHighlight("当归", "當歸", esc) === "<mark>当归</mark>",
  window.zhHighlight("当归", "當歸", esc));
check("沒命中就原樣輸出（且有跳脫）",
  window.zhHighlight("<b>当归</b>", "黄连", esc) === "&lt;b&gt;当归&lt;/b&gt;");
check("空關鍵字原樣輸出", window.zhHighlight("当归", "", esc) === "当归");

console.log("\n【OpenCC 載不到時要退化，不是壞掉】");
delete global.OpenCC;
const sandbox = { window: null };
sandbox.window = sandbox;
(function () {
  const fn = new Function("window", src + "; return { zhMatchAny: window.zhMatchAny, zhNorm: window.zhNorm };");
  const api = fn(sandbox);
  check("沒有 OpenCC 時 zhNorm 仍可用（只做 lowercase／trim）", api.zhNorm("  ABC ") === "abc");
  check("沒有 OpenCC 時簡體輸入仍查得到（退回修正前的行為）",
    HERBS.filter(h => api.zhMatchAny([h.herb_cn_name], "当归")).length === 1);
  check("沒有 OpenCC 時不會丟例外", true);
})();

console.log("\n" + "=".repeat(60));
if (FAIL.length) {
  console.log(`❌ 有 ${FAIL.length} 項未通過：`);
  FAIL.forEach(f => console.log("   - " + f));
  process.exit(1);
}
console.log("✅ 繁簡比對驗證全部通過");
