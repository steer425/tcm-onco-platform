// 通路富集分析（KEGG／Reactome）— 功能代碼 F1-5
// KEGG／Reactome 的通路名稱是第三方內容，一律 esc() 之後才寫進 DOM

let isAdmin = false;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// p/q 值跨越好幾個數量級，固定小數位會把 1e-12 顯示成 0.000，
// 看起來像「沒有效果」，其實是最顯著的那一條
function fmtP(v) {
  if (v == null) return "-";
  if (v === 0) return "&lt;1e-300";
  if (v < 0.001) return v.toExponential(2);
  return v.toFixed(4);
}

function sigClass(q, p) {
  if (q != null && q < 0.05) return "sig-q";
  if (p != null && p < 0.05) return "sig-p";
  return "sig-no";
}

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
    isAdmin = (data.role_names || []).includes("管理者");
    document.getElementById("adminBox").style.display = isAdmin ? "flex" : "none";
  } catch (err) {}
}



// ---------------------------------------------------------------- 外部通路圖連結

// KEGG 的通路圖網址可以在後面接基因編號把它們標紅：
//   https://www.kegg.jp/pathway/hsa04082+367+2099
// 對研究者來說這才是關鍵——不是「這條通路顯著」，而是「這些靶點落在圖上哪裡」。
//
// Reactome 用 PathwayBrowser，基本網址一定可用；`FLG` 參數用來標示實體，
// 若語法不被接受，最差的情況是通路照常開啟、只是沒有標示（不會壞掉）。
function pathwayUrl(source, pathwayId, keggGenes, symbols) {
  const pid = encodeURIComponent(String(pathwayId || "").trim());
  if (!pid) return null;
  if (source === "kegg") {
    // 只收純數字的基因編號，其餘一律丟掉——網址是要交給外部網站的，不能夾帶意外內容
    const genes = (keggGenes || []).filter(g => /^\d+$/.test(String(g))).slice(0, 60);
    return `https://www.kegg.jp/pathway/${pid}` + (genes.length ? "+" + genes.join("+") : "");
  }
  const flags = (symbols || []).filter(x => /^[A-Za-z0-9_.-]+$/.test(String(x))).slice(0, 40);
  return `https://reactome.org/PathwayBrowser/#/${pid}` +
         (flags.length ? `&FLG=${encodeURIComponent(flags.join(","))}` : "");
}

// ---------------------------------------------------------------- 欄位說明
// 這個平台的使用者包含生技研發與醫院研究單位，不見得熟悉 ORA 的判讀陷阱。
// 把說明放在欄位旁邊而不是另開文件——會去翻文件的人，通常是已經知道要小心的人。
// `{n}`／`{N}` 會用目前這次分析的實際數字替換，抽象說明遠不如具體數字有用。

let lastStats = { n: "（樣本數）", N: "（母體）", tested: "（受檢通路數）" };

const HELP = {
  overview: {
    title: "這張表在做什麼：通路富集分析",
    html: `<p>回答一個問題：<b>這個藥材打到的蛋白，有沒有不成比例地集中在某些生物過程上？</b></p>
      <p>用彈珠來想：袋子裡有 <b>{N}</b> 顆彈珠（母體＝該資料庫收錄的全部基因），
      其中某條通路佔了其中幾顆（＝「通路基因」欄）。你閉眼抓出 <b>{n}</b> 顆
      （＝這個藥材有通路註解的靶點基因）。如果抓到的數量遠多於隨機預期，
      這條通路就是「富集」了。</p>
      <p>整份分析就是把這件事對 <b>{tested}</b> 條通路各做一次，再排序。</p>`,
  },
  rank: {
    title: "# — 名次",
    html: `<p>目前排序方式下的名次。<b>綠色</b>代表這一列達 FDR q&lt;0.05。</p>
      <p>切成「依富集倍率」排序時，序號下方會多一行小字 <code>p #12</code>，
      那是它在統計顯著性排序裡的名次。<b>兩種排序都看一次比較不會漏</b>——
      理由見「倍率」欄的說明。</p>`,
  },
  pathway: {
    title: "通路 — 識別碼",
    html: `<p>KEGG 或 Reactome 給這條通路的唯一編號。<code>hsa</code> 代表人類（Homo sapiens）。</p>
      <p><b>點一下編號就會在新分頁開啟原始通路圖。</b></p>
      <p>KEGG 的連結會把<b>這個藥材命中的基因直接標紅</b>——
      不只是「這條通路顯著」，而是看得到這些靶點落在通路圖的哪個位置、
      彼此的上下游關係是什麼。那才是判斷機轉是否說得通的依據。</p>
      <p>Reactome 的連結會開啟 PathwayBrowser。</p>`,
  },
  name: {
    title: "名稱 — 這條通路在做什麼",
    html: `<p>通路名稱。底下灰字是資料庫自己的<b>分類階層</b>，例如
      <code>Environmental Information Processing / Signaling molecules and interaction</code>
      前半是大類、後半是次類。</p>
      <p>分類很有用：一眼分辨這是核心訊號通路、代謝通路、還是疾病通路。
      標成 <b>癌症相關</b> 的是 KEGG 官方癌症分類，加上本平台另外標記的核心腫瘤訊號通路。</p>
      <p>標成 <b>重複</b> 的，代表它命中的基因有 80% 以上已經出現在更高名次的通路裡——
      <span class="warn">那不是一項獨立發現</span>，詳見「命中的基因」欄說明。</p>`,
  },
  hit: {
    title: "命中 — 這個藥材打中這條通路的幾個基因",
    html: `<p>這個藥材的 <b>{n}</b> 個靶點基因裡，有幾個落在這條通路內。</p>
      <p>它跟「通路基因」一起決定後面所有的數字。<b>命中數太少（例如 2、3 個）時，
      就算倍率很高也不穩</b>——換一份資料很可能就不見了。</p>`,
  },
  size: {
    title: "通路基因 — 這條通路總共有幾個基因",
    html: `<p>這條通路在母體裡的總成員數，也就是富集計算的分母之一。</p>
      <p><b>這個數字會隨你選的母體改變。</b>選「全人類基因」時是該通路在全基因體中的大小；
      選「全部中藥靶點」時，只算其中有被中藥靶點涵蓋到的部分，所以會小很多。
      兩者不能直接互相比較。</p>`,
  },
  fold: {
    title: "倍率 — 效果有多強",
    html: `<p>實際命中數 ÷ 隨機抽樣的期望命中數。</p>
      <span class="formula">倍率 =（命中 ÷ {n}）÷（通路基因 ÷ {N}）</span>
      <p>倍率 1.0 表示跟隨機一樣、完全沒有富集；3.0 表示比隨機預期多了三倍。</p>
      <p><b>倍率是「效果有多強」，p 值是「有多不可能是巧合」——這兩件事最常被混為一談。</b>
      一條有五百個基因的大通路很容易命中很多、p 值很小，但倍率可能只有兩倍。</p>
      <p class="warn">注意：p 值同時取決於倍率與絕對命中數，而命中數多則統計檢定力高，
      所以<b>依 p 值排序會系統性偏袒基因數多的大通路</b>，把高特異性的小通路往後推。
      這是富集分析的固有特性，不是程式問題——所以本頁提供「依倍率排序」。</p>`,
  },
  p: {
    title: "p 值 — 有多不可能是巧合",
    html: `<p>如果這個藥材的靶點其實是隨機抽的，抓到這麼多（或更多）命中的機率有多大。
      用的是超幾何分布。</p>
      <p><code>1.73e-9</code> 就是 0.00000000173，約十億分之 1.7——
      機率極低，代表「隨機碰巧」這個解釋站不住腳。</p>
      <p class="warn"><b>但判讀時請不要用 p 值，要用 q 值。</b>原因見下一欄。</p>`,
  },
  q: {
    title: "q 值（FDR）— 判讀請看這一欄",
    html: `<p>p 值有一個陷阱：你不是只檢驗一條通路，這次同時檢驗了 <b>{tested}</b> 條。</p>
      <p>如果用 p&lt;0.05 當標準，<b>就算這些通路全部都是雜訊</b>，光靠運氣也會有
      約 5% 通過。你會很開心地把它們寫進報告——而它們全是假的。</p>
      <p>q 值（false discovery rate，Benjamini–Hochberg 校正）已經把
      「你做了 {tested} 次檢定」這件事算進去了。</p>
      <span class="formula">判讀規則：看 q 值，不看 p 值。q &lt; 0.05 才算顯著。</span>
      <p>q 值一定大於或等於同一列的 p 值，這是校正的本質。</p>`,
  },
  genes: {
    title: "命中的基因 — 以及為什麼「顯著通路數」會騙人",
    html: `<p>這條通路裡被這個藥材打中的基因。<b>粗體綠色</b>是新出現的、
      <span class="sym-old">灰色</span>是更高名次已經出現過的，下方標「新增 N / M 個基因」。</p>
      <p><b>為什麼要這樣標：</b>KEGG／Reactome 的通路定義大量重疊，
      同一組基因會同時落在好幾條通路裡。實測人參的例子：</p>
      <span class="formula">Apoptosis 命中　BAX、BCL2、CASP3、CASP8、CASP9、MAPK8
p53 signaling　BAX、BCL2、CASP3、CASP8、CASP9、CDK1
　　　　　　　→ 六個裡有五個完全相同</span>
      <p>並列成兩項發現會被讀成交叉印證，<span class="warn">實際上是同一個觀察被算了兩次</span>。</p>
      <p>所以摘要行除了「顯著通路數」還會給「<b>獨立發現數</b>」——
      扣掉與更高名次重疊 ≥80% 的之後還剩幾條。
      <b class="warn">寫進報告要引用的是獨立發現數，不是顯著通路數。</b></p>`,
  },
};

const HELP_ORDER = ["overview", "rank", "pathway", "name", "hit", "size",
                    "fold", "p", "q", "genes"];

function fillHelpNumbers(html) {
  return html.replace(/\{n\}/g, esc(lastStats.n))
             .replace(/\{N\}/g, esc(lastStats.N))
             .replace(/\{tested\}/g, esc(lastStats.tested));
}

function openHelp(key) {
  const body = document.getElementById("helpBody");
  body.innerHTML = HELP_ORDER.map(k => `
    <div class="help-sec" id="help-${k}">
      <h4>${esc(HELP[k].title)}</h4>
      ${fillHelpNumbers(HELP[k].html)}
    </div>`).join("");
  document.getElementById("helpModal").style.display = "flex";
  const target = document.getElementById(`help-${key}`);
  if (target) {
    target.scrollIntoView({ block: "start" });
    target.classList.add("flash");
    setTimeout(() => target.classList.remove("flash"), 1500);
  }
}

function bindHelp() {
  document.querySelectorAll("[data-help]").forEach(btn => {
    btn.addEventListener("click", ev => {
      ev.preventDefault();
      openHelp(btn.dataset.help);
    });
  });
  document.getElementById("helpClose").addEventListener("click", () => {
    document.getElementById("helpModal").style.display = "none";
  });
  document.getElementById("helpModal").addEventListener("click", ev => {
    // 點背景關閉，但點到內容區不要關
    if (ev.target.id === "helpModal") ev.target.style.display = "none";
  });
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape") document.getElementById("helpModal").style.display = "none";
  });
}

// ---------------------------------------------------------------- 覆蓋率

async function loadStats() {
  const s = await api("/pathways/stats");
  const k = s.by_source.kegg, r = s.by_source.reactome;
  const boxes = [
    ["已標準化靶點", `${s.standardised_targets} / ${s.total_targets}`],
    ["KEGG 通路", k.pathways],
    ["KEGG 癌症相關", k.cancer_related],
    ["KEGG 已連結靶點", k.targets_with_pathway],
    ["Reactome 通路", r.pathways],
    ["Reactome 已連結靶點", r.targets_with_pathway],
  ];
  document.getElementById("statGrid").innerHTML = boxes.map(([lbl, num]) => `
    <div class="stat-box"><div class="num">${esc(num)}</div><div class="lbl">${esc(lbl)}</div></div>
  `).join("");

  const lines = [];
  for (const [name, d] of [["KEGG", k], ["Reactome", r]]) {
    lines.push(d.synced_at
      ? `${name}：${d.links} 條靶點↔通路關聯，背景基因 ${d.background_total}，最後同步 ${new Date(d.synced_at).toLocaleString()}`
      : `${name}：尚未同步`);
  }
  document.getElementById("syncLog").textContent = lines.join("\n");
}

async function runSync(source) {
  const msg = document.getElementById("syncMsg");
  const btns = [document.getElementById("syncKeggBtn"), document.getElementById("syncReactomeBtn")];
  btns.forEach(b => b.disabled = true);
  msg.textContent = source === "reactome"
    ? "同步中… Reactome 的對應檔有數十 MB，可能需要一兩分鐘，請不要關閉頁面。"
    : "同步中，請不要關閉頁面…";
  try {
    const r = await api("/pathways/sync", { method: "POST", body: JSON.stringify({ source }) });
    msg.textContent = `${source} 完成：新增 ${r.pathways_created} 條、更新 ${r.pathways_updated} 條，` +
                      `建立 ${r.links} 條靶點關聯（涵蓋 ${r.targets_with_pathway} 個靶點）。`;
    await loadStats();
  } catch (err) {
    msg.textContent = `同步失敗：${err.message || err}`;
  } finally {
    btns.forEach(b => b.disabled = false);
  }
}

// ---------------------------------------------------------------- 藥材搜尋
// 502 種藥材用下拉選單根本找不到（實際使用時捲不完），改成輸入即時模糊比對。
// 清單本來就整包載到前端了，所以比對純在瀏覽器端做，不用再打一次 API。

let allHerbs = [];
let selectedHerbId = null;
let activeIndex = -1;
let toCn = null;   // OpenCC 繁→簡轉換器

function initConverter() {
  // 藥材名稱在資料庫裡是簡體（猫爪草、鱼腥草）。使用者用繁體輸入「貓爪草」
  // 直接比對會找不到——這不是使用者輸錯，是我們的比對沒處理字形差異。
  // OpenCC 已經是全站語系機制在用的東西，這裡直接沿用。
  try {
    if (!toCn && window.OpenCC) toCn = OpenCC.Converter({ from: "tw", to: "cn" });
  } catch (e) { toCn = null; }
}

function normalize(text) {
  const t = String(text == null ? "" : text).toLowerCase().trim();
  if (!t) return "";
  try {
    return toCn ? toCn(t) : t;
  } catch (e) {
    return t;   // 轉換失敗就用原文比，不要讓搜尋整個壞掉
  }
}

function herbHaystack(h) {
  return [h.herb_cn_name, h.herb_en_name, h.herb_pinyin,
          h.child_cn_name, h.child_en_name].filter(Boolean).join(" ");
}

function searchHerbs(query) {
  const q = normalize(query);
  if (!q) return allHerbs.slice(0, 40);
  const scored = [];
  for (const h of allHerbs) {
    const hay = normalize(herbHaystack(h));
    const idx = hay.indexOf(q);
    if (idx < 0) continue;
    // 開頭命中排前面，其次才是出現在中間的；同分再依靶點數
    const name = normalize(h.herb_cn_name || h.herb_en_name || "");
    let score = 2;
    if (name === q) score = 0;
    else if (name.startsWith(q)) score = 1;
    scored.push({ h, score, idx });
  }
  scored.sort((a, b) => a.score - b.score || a.idx - b.idx
                        || (b.h.target_count || 0) - (a.h.target_count || 0));
  return scored.slice(0, 40).map(x => x.h);
}

function highlight(text, query) {
  const raw = String(text == null ? "" : text);
  const q = normalize(query);
  if (!q) return esc(raw);
  const idx = normalize(raw).indexOf(q);
  // 轉換後長度可能與原字串不同，只有長度一致時才安全地標記
  if (idx < 0 || normalize(raw).length !== raw.length) return esc(raw);
  return esc(raw.slice(0, idx)) + "<mark>" + esc(raw.slice(idx, idx + q.length)) +
         "</mark>" + esc(raw.slice(idx + q.length));
}

function renderHerbResults(query) {
  const box = document.getElementById("herbResults");
  const list = searchHerbs(query);
  activeIndex = -1;
  if (!list.length) {
    box.innerHTML = `<div class="herb-empty">找不到符合「${esc(query)}」的藥材。
      可以試中文、英文學名或拼音，例如「人參」「ginseng」「renshen」。</div>`;
    box.hidden = false;
    return;
  }
  box.innerHTML = list.map((h, i) => {
    const cn = h.herb_cn_name || "";
    const en = h.herb_en_name || "";
    const py = h.herb_pinyin || "";
    return `<div class="herb-item" data-herb-id="${esc(h.herb_id)}" data-idx="${i}">
      <b>${highlight(cn || en, query)}</b>
      <div class="sub">${highlight(en, query)}${py ? " · " + highlight(py, query) : ""}
        · 靶點 ${esc(h.target_count || 0)}（未篩選）</div>
    </div>`;
  }).join("");
  box.hidden = false;
  box.querySelectorAll("[data-herb-id]").forEach(el => {
    el.addEventListener("mousedown", ev => {
      // 用 mousedown 而不是 click：input 的 blur 會先關掉清單，click 就永遠觸發不到
      ev.preventDefault();
      chooseHerb(el.dataset.herbId);
    });
  });
}

function chooseHerb(herbId) {
  const h = allHerbs.find(x => String(x.herb_id) === String(herbId));
  if (!h) return;
  selectedHerbId = h.herb_id;
  document.getElementById("herbSearch").value = h.herb_cn_name || h.herb_en_name || "";
  document.getElementById("herbResults").hidden = true;
  runEnrichment();
}

function moveActive(delta) {
  const box = document.getElementById("herbResults");
  const items = [...box.querySelectorAll(".herb-item")];
  if (!items.length) return;
  activeIndex = (activeIndex + delta + items.length) % items.length;
  items.forEach((el, i) => el.classList.toggle("active", i === activeIndex));
  items[activeIndex].scrollIntoView({ block: "nearest" });
}

function bindHerbSearch() {
  const input = document.getElementById("herbSearch");
  const box = document.getElementById("herbResults");

  input.addEventListener("input", () => {
    selectedHerbId = null;      // 改過字就當作還沒選定，避免用舊的藥材去分析
    renderHerbResults(input.value);
  });
  input.addEventListener("focus", () => renderHerbResults(input.value));
  input.addEventListener("blur", () => setTimeout(() => { box.hidden = true; }, 120));
  input.addEventListener("keydown", ev => {
    if (box.hidden && ["ArrowDown", "ArrowUp"].includes(ev.key)) {
      renderHerbResults(input.value);
      return;
    }
    if (ev.key === "ArrowDown") { ev.preventDefault(); moveActive(1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); moveActive(-1); }
    else if (ev.key === "Escape") { box.hidden = true; }
    else if (ev.key === "Enter") {
      ev.preventDefault();
      const items = [...box.querySelectorAll("[data-herb-id]")];
      // 沒有用方向鍵選的話，Enter 就取第一筆——只有一筆結果時這是最順的操作
      const pick = activeIndex >= 0 ? items[activeIndex] : items[0];
      if (pick) chooseHerb(pick.dataset.herbId);
    }
  });
}

async function loadHerbs() {
  const input = document.getElementById("herbSearch");
  try {
    initConverter();
    allHerbs = await api("/tcmsp/herbs/public/list");
    allHerbs.sort((a, b) => (b.target_count || 0) - (a.target_count || 0));
    input.placeholder = `輸入藥材名稱搜尋（共 ${allHerbs.length} 種，可用中文／英文／拼音）`;
  } catch (err) {
    input.placeholder = "藥材清單載入失敗";
    input.disabled = true;
  }
}

// ---------------------------------------------------------------- 富集分析

function renderIngredientNote(r) {
  // 成分篩掉多少一定要看得見。使用者需要知道「這個結果是根據幾個成分算出來的」，
  // 而不是預設有篩就當作沒事——篩太兇導致樣本剩沒幾個，結論一樣不可信。
  const box = document.getElementById("admeNote");
  const m = r.ingredients || {};
  if (!r.apply_adme) {
    box.innerHTML = `<b style="color:#a83232;">未套用活性成分篩選。</b>
      這個藥材全部 ${esc(m.total || 0)} 個成分的靶點都被納入。
      TCMSP 收錄的是偵測得到的所有化合物，多數到不了體內靶點——
      這個結果只適合當對照，<b>不適合當成正式分析</b>。`;
    return;
  }
  const pct = m.total ? Math.round((m.passed_count / m.total) * 100) : 0;
  box.innerHTML = `<b>活性成分篩選：OB ≥ ${esc(m.ob_min)}%、DL ≥ ${esc(m.dl_min)}。</b>
    ${esc(m.total || 0)} 個成分中有 <b>${esc(m.passed_count || 0)}</b> 個通過（${esc(pct)}%），
    對應 <b>${esc(r.herb ? r.herb.target_count : 0)}</b> 個靶點。
    ${m.missing_adme ? `另有 ${esc(m.missing_adme)} 個成分因為 ADME 資料缺值而排除
       （缺值不等於不活性，只是 TCMSP 沒收錄這個數字）。` : ""}`;
}


function renderBackgroundNote(background, backgroundTotal, studyGeneCount) {
  // 母體選了什麼，結論就跟著變。畫面上一定要講清楚現在算的是哪一種，
  // 不然使用者看到的 p 值不知道在跟什麼比。
  const common = `這次分析的樣本是這個藥材的 <b>${studyGeneCount}</b> 個有通路註解的靶點基因，` +
                 `母體 <b>${backgroundTotal}</b> 個基因。`;
  document.getElementById("bgNote").innerHTML = background === "tcmsp"
    ? `<b>母體：全部已標準化的中藥靶點。</b>${common}
       回答的是「這條通路在<b>這個</b>藥材裡，是否比在中藥靶點整體裡更常出現」。
       這會消掉「TCMSP 的靶點本來就偏向可成藥蛋白」造成的系統性偏差，適合拿來比較不同藥材；
       但不是學界慣例，寫進論文要額外說明。`
    : `<b>母體：該資料庫收錄的全部人類基因（學界慣例）。</b>${common}
       回答的是「這條通路在這個藥材的靶點裡，是否比在全人類基因裡更常出現」。
       注意 TCMSP 的靶點本身就偏向傳統可成藥的蛋白（受體、酶、離子通道），
       所以訊號傳導與代謝類通路會被系統性高估——想消掉這個偏差請改用另一種母體。`;
}

async function runEnrichment() {
  const herbId = selectedHerbId;
  const hint = document.getElementById("enrichHint");
  const body = document.getElementById("enrichBody");
  if (!herbId) {
    hint.textContent = "請先在上方輸入並選擇一個藥材。";
    body.innerHTML = "";
    return;
  }

  const source = document.getElementById("sourceSelect").value;
  const background = document.getElementById("bgSelect").value;
  const sort = document.getElementById("sortSelect").value;
  const cancerOnly = document.getElementById("cancerOnly").checked;
  const applyAdme = document.getElementById("applyAdme").checked;
  const excludeDisease = document.getElementById("excludeDisease").checked;
  const btn = document.getElementById("runBtn");
  btn.disabled = true;
  hint.textContent = "分析中…";
  try {
    const params = new URLSearchParams({
      source, background, sort, cancer_only: cancerOnly, apply_adme: applyAdme,
      exclude_noncancer_disease: excludeDisease, limit: 100,
    });
    const r = await api(`/pathways/herb/${encodeURIComponent(herbId)}?${params}`);

    lastStats = { n: r.study_gene_count, N: r.background_total, tested: r.total_tested };
    renderIngredientNote(r);
    renderBackgroundNote(r.background, r.background_total, r.study_gene_count);

    if (!r.items || !r.items.length) {
      hint.textContent = r.note || "這個藥材在目前的通路資料下沒有可分析的結果（可能是通路目錄尚未同步）。";
      body.innerHTML = "";
      return;
    }
    const sig = r.significant_count != null ? r.significant_count
              : r.items.filter(i => i.q_value != null && i.q_value < 0.05).length;
    const dropped = r.excluded_disease_pathways
      ? `（已排除 ${r.excluded_disease_pathways} 條非癌症疾病類通路）` : "";
    // 「獨立發現數」比「顯著通路數」誠實：KEGG 的通路定義大量重疊，
    // 同一組基因會同時落在好幾條通路，顯著數本身是被灌水的
    const indep = r.independent_count;
    const indepText = (indep != null && sig > 0)
      ? `其中 <b>${indep}</b> 條是獨立的基因組合（其餘與更高名次重疊 ≥80%，
         並列在報告裡會高估證據強度）；` : "";
    hint.innerHTML = `${esc(r.herb.herb_cn_name || r.herb.herb_en_name)}：` +
      `共檢定 ${r.total_tested} 條通路${esc(dropped)}，<b>${sig}</b> 條達 FDR q&lt;0.05，` +
      indepText + `以下依${r.sort === "fold" ? "富集倍率" : "統計顯著性"}排序，` +
      `顯示前 ${r.items.length} 條。`;

    body.innerHTML = r.items.map((i, idx) => {
      const isSig = i.q_value != null && i.q_value < 0.05;
      const newSet = new Set(i.new_symbols || []);
      // 新出現的基因加粗，已在更高名次出現過的變灰——
      // 一眼看得出這一列到底帶來多少新資訊
      const syms = (i.hit_symbols || []).map(sym =>
        `<span class="${newSet.has(sym) ? "sym-new" : "sym-old"}">${esc(sym)}</span>`).join("、");
      const dup = i.redundant_with;
      return `
      <tr>
        <td class="rank-cell ${isSig ? "rank-sig" : ""}">${esc(i.rank || idx + 1)}
          ${r.sort === "fold" && i.p_rank ? `<small>p #${esc(i.p_rank)}</small>` : ""}</td>
        <td>${(() => {
          const url = pathwayUrl(r.source, i.pathway_id, i.hit_kegg_genes, i.hit_symbols);
          const label = `<span class="pill pill-${esc(r.source)}">${esc(i.pathway_id)}</span>`;
          if (!url) return label;
          const tip = r.source === "kegg"
            ? `在 KEGG 開啟通路圖，命中的 ${i.hit_count} 個基因會標紅`
            : `在 Reactome 開啟通路瀏覽器`;
          return `<a class="pw-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer"
                     title="${esc(tip)}">${label}</a>`;
        })()}</td>
        <td>${esc(i.name_tw || i.name)}
          ${i.is_cancer_related ? '<span class="pill pill-cancer" style="margin-left:6px;">癌症相關</span>' : ""}
          ${dup ? `<span class="dup-tag">重複</span>` : ""}
          ${i.category ? `<div class="hint-msg">${esc(i.category)}</div>` : ""}
          ${dup ? `<div class="dup-note">命中基因與 #${esc(dup.rank)}
              ${esc(dup.name)} 重疊 ${esc(dup.shared)}/${esc(dup.total)}
              — 不是獨立證據</div>` : ""}</td>
        <td><b>${esc(i.hit_count)}</b></td>
        <td>${esc(i.pathway_gene_count)}</td>
        <td>${i.fold_enrichment == null ? "-" : esc(i.fold_enrichment)}</td>
        <td class="mono ${sigClass(i.q_value, i.p_value)}">${fmtP(i.p_value)}</td>
        <td class="mono ${sigClass(i.q_value, i.p_value)}">${fmtP(i.q_value)}</td>
        <td class="syms">${syms}
          <div class="newcount">新增 ${esc(newSet.size)} / ${esc((i.hit_symbols || []).length)} 個基因</div>
        </td>
      </tr>`;
    }).join("");
  } catch (err) {
    hint.textContent = `分析失敗：${err.message || err}`;
    body.innerHTML = "";
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- 初始化

document.addEventListener("DOMContentLoaded", async () => {
  await loadUserInfo();
  document.getElementById("refreshBtn").addEventListener("click", loadStats);
  document.getElementById("syncKeggBtn").addEventListener("click", () => runSync("kegg"));
  document.getElementById("syncReactomeBtn").addEventListener("click", () => runSync("reactome"));
  document.getElementById("runBtn").addEventListener("click", runEnrichment);
  document.getElementById("sortSelect").addEventListener("change", runEnrichment);
  bindHerbSearch();
  bindHelp();

  try {
    await Promise.all([loadStats(), loadHerbs()]);
  } catch (err) {
    document.getElementById("syncLog").textContent = `載入失敗：${err.message || err}`;
  }
});
