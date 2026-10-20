/* 藥材活性成分與結構標準化（F1-7）
 *
 * 這一頁回答的問題，跟後台 F1-6「成分標準化」不一樣：
 *   F1-6 → 全庫還有多少成分沒解析（批次作業用）
 *   F1-7 → 這一味藥材的活性成分，是不是每一個都拿到化學結構了（驗收用）
 * 全庫覆蓋率 49.5% 可能代表某味藥 22 筆全中，也可能一筆都沒中，
 * 兩者在 F1-6 的卡片上長得一模一樣，所以要逐筆列出來看。
 *
 * ⚠️ 成分名稱只有 TCMSP 的英文原名——資料庫沒有中文名稱，也沒有化學分類欄位。
 *    不要在前端硬湊，那會變成一個沒人維護、也查不到出處的對照表。
 *
 * v1.49.2：
 *   - 新增「非活性成分」分頁：OB／DL 沒過或 ADME 缺值的成分，原因由後端 pathways.active_ingredients() 判定，
 *     這裡只負責顯示，不要在前端再比一次門檻。非活性成分不計入上方任何 KPI（已標準化、有 SMILES…都只算活性成分）。
 *   - 新增「IUPAC 系統名稱」欄。使用者要的是「拉丁文名稱」，但化合物沒有拉丁文名稱
 *     （拉丁學名是給生物物種用的，例如藥材的 Panax ginseng），化合物的國際標準命名是 IUPAC 系統名，
 *     資料來自 PubChem 標準化時存下的 iupac_name，只有已對應到 CID 的成分才有。
 */

const DEFAULT_HERB_ID = 336;      // 人参 Panax Ginseng C. A. Mey.（目標一指定的驗證藥材）
const PUBCHEM = 'https://pubchem.ncbi.nlm.nih.gov/compound/';

// 糖基殘基質量。分子量差是這些的整數倍時，多半是「苷元誤配」——
// 名稱清理把 _qt（苷元）當雜訊剝掉，結果查到帶糖基的母體苷。
const SUGARS = [
  { name: '己糖', mass: 162.14 },
  { name: '去氧己糖', mass: 146.14 },
  { name: '戊糖', mass: 132.12 },
];
const PROTON = 1.008;

const STATUS_CN = {
  auto: '自動採用', confirmed: '已確認', pending: '待確認',
  rejected: '已否決', unresolved: '查無結果', error: '連線失敗',
  untouched: '尚未處理',
};
const ACCEPTED = ['auto', 'confirmed'];

/* 四個識別碼的欄位說明。**這一頁的重點就是「本地編號 → 國際編號」**，
 * 不講清楚 Mol ID 只在 TCMSP 裡有意義，使用者會以為它跟 CID 一樣可以拿去別的資料庫查。
 * 沿用 tcmsp_query.html 的同一套說明視窗（class term-link + #termInfoModal），不要另外發明一套。 */
const TERM_INFO = {
  mol_id: {
    title: 'Mol ID（TCMSP 成分編號）',
    body: 'TCMSP 自己發給每個成分的編號，格式是 MOL 加 6 碼數字（例如 MOL000098）。'
        + '它只在 TCMSP 這一套系統裡有意義——拿 Mol ID 去 PubChem、UniProt 或任何其他資料庫都查不到東西，'
        + '也沒有化學結構的資訊在裡面。正因為如此，本平台才要做「成分標準化」，'
        + '把每個 Mol ID 對應到下面那三個國際通用的編號。點編號可到中藥關聯查詢站看這個成分的靶點與疾病關聯。'
  },
  cid: {
    title: 'PubChem CID — PubChem Compound ID（化合物編號）',
    body: '美國國家生物技術資訊中心（NCBI）旗下 PubChem 資料庫發給每個化合物的編號，是一串純數字。'
        + '這是國際通用的編號，拿著它可以到 PubChem 查到分子結構、物化性質、生物活性試驗與文獻。'
        + '本頁的 CID 是由成分名稱比對後對應過來的，狀態要是「自動採用」或「已確認」才算數。'
  },
  inchikey: {
    title: 'InChIKey — International Chemical Identifier Key（國際化學標識符雜湊碼）',
    body: '由 IUPAC（國際純化學暨應用化學聯合會）制定，直接從分子結構算出來的 27 碼固定長度指紋，'
        + '格式是 14 碼-10 碼-1 碼。它不是誰發的號碼，而是結構的計算結果，'
        + '所以同一個分子在任何資料庫算出來都一樣，是跨資料庫比對最可靠的鍵值，也可以直接丟進 Google 搜尋。'
  },
  smiles: {
    title: 'SMILES — Simplified Molecular Input Line Entry System（簡化分子線性輸入規範）',
    body: '用一行文字描述分子結構的寫法：原子用元素符號（C、N、O…），單鍵省略、雙鍵寫 =、三鍵寫 #，'
        + '括號表示分支，數字表示環的開合。例如乙醇是 CCO，苯是 c1ccccc1（小寫代表芳香環）。\n\n'
        + '有了 SMILES，就能把分子畫出來、算物化性質、做結構相似性比對與分子對接，'
        + '是後續結構分析與 AI 模型的輸入格式。同一個分子可以有好幾種寫法，'
        + '所以跨資料庫比對請用 InChIKey，不要直接比 SMILES 字串。\n\n'
        + '本欄 ✓ 表示這個成分已從 PubChem 取得 SMILES（只算標準化狀態為「自動採用」或「已確認」的那一筆）；'
        + '✗ 表示尚未對應到結構。點 PubChem CID 可以看到完整的 SMILES 與結構圖。'
  },
  iupac: {
    title: 'IUPAC 系統名稱 — IUPAC Systematic Name',
    body: '由 IUPAC（國際純化學暨應用化學聯合會）規則從分子結構推導出來的標準化學名稱，'
        + '全世界通用，看名稱就能還原出結構。\n\n'
        + '關於「拉丁文名稱」：拉丁學名是給生物物種用的（例如藥材人參的學名 Panax ginseng C. A. Mey.），'
        + '化合物本身沒有拉丁文名稱；化合物的國際標準命名就是這個 IUPAC 系統名稱。\n\n'
        + '資料來自 PubChem，只有已對應到 PubChem CID 的成分才有。天然物（皂苷、多醣類）的系統名稱'
        + '常常很長，表格只顯示前三行，滑鼠移上去可看全文。'
  },
  reason: {
    title: '未納入原因',
    body: '這個成分沒有被列為活性成分的原因：\n'
        + '・OB 未達：口服生物利用度低於門檻，吃下去大多吸收不到。\n'
        + '・DL 未達：類藥性低於門檻，結構不像一般藥物分子。\n'
        + '・OB、DL 皆未達：兩道門檻都沒過。\n'
        + '・ADME 缺值：TCMSP 沒有這個成分的 OB 或 DL 數值，無法判定，一律排除（不是因為數值低）。\n\n'
        + '門檻值顯示在頁面上方，由管理者在系統設定調整。非活性成分不進入後續的靶點、通路與細胞株分析，'
        + '但其中有些可能經腸道菌代謝後才轉為活性形式，研究上仍可參考。'
  },
  cas: {
    title: 'CAS 號 — CAS Registry Number（化學文摘社登記號）',
    body: '美國化學文摘社（Chemical Abstracts Service，隸屬美國化學會）發給每一個已登錄物質的編號，'
        + '格式是「數字-數字-檢查碼」（例如 50-00-0）。化工、法規、安全資料表（SDS）與採購上最常用這個編號，'
        + '要跟法規清單或試劑供應商對照時，CAS 號通常比 CID 更通用。它是商業資料庫，並非所有化合物都有登錄號。'
  },
};

/* 欄位名稱旁的驚嘆號標記 */
function help(key) {
  return ` <a class="term-link" onclick="showTermInfo('${key}')" title="欄位說明">❗</a>`;
}

function showTermInfo(key) {
  const info = TERM_INFO[key];
  if (!info) return;
  $('termInfoTitle').textContent = info.title;
  $('termInfoBody').textContent = info.body;
  $('termInfoModal').style.display = 'flex';
}
function closeTermInfo() {
  $('termInfoModal').style.display = 'none';
}
window.showTermInfo = showTermInfo;
window.closeTermInfo = closeTermInfo;

let HERBS = [];
let currentHerbId = null;
let currentData = null;
let filter = 'all';
let listTab = 'active';   // active＝活性成分、inactive＝非活性成分（v1.49.2）

const REASON_CN = { ob: 'OB 未達', dl: 'DL 未達', both: 'OB、DL 皆未達', missing: 'ADME 缺值' };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s)
  .replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* 差值的成因提示。先判糖基再判水合物——162.14 與 9 個水只差 0.035，
 * 先判水合物會把苷元誤配講成水合物，而水合物暗示「同一個化合物」，
 * 那會把審核的人往「按確認」推，比沒有提示更糟。 */
function deltaHint(d) {
  const v = Math.abs(Number(d));
  if (!isFinite(v) || v <= 0.5) return '';
  if (Math.abs(v - PROTON) <= 0.2) return '≈ 1 個氫（酸式／陰離子式）';
  for (const s of SUGARS) {
    for (let n = 1; n <= 4; n++) {
      if (Math.abs(v - s.mass * n) <= 0.6) return `≈ ${n} 個${s.name}（疑似苷元誤配）`;
    }
  }
  return '';
}

function tick(ok) {
  return ok ? '<span class="tick">✓</span>' : '<span class="cross">✗</span>';
}

/* ---------------------------------------------------------------- 藥材清單 */

async function loadHerbs() {
  HERBS = await api('/tcmsp/herbs/public/list');
  HERBS.sort((a, b) => (a.herb_id || 0) - (b.herb_id || 0));
  $('herbStats').textContent = `共 ${HERBS.length} 種藥材`;
  renderHerbList();

  const urlHerb = parseInt(new URLSearchParams(location.search).get('herb'), 10);
  const initial = (urlHerb && HERBS.some(h => h.herb_id === urlHerb)) ? urlHerb
    : (HERBS.some(h => h.herb_id === DEFAULT_HERB_ID) ? DEFAULT_HERB_ID
      : (HERBS[0] && HERBS[0].herb_id));
  if (initial) selectHerb(initial);
}

function renderHerbList() {
  // 資料庫存的是簡體、畫面預設繁體，比對一律走 zh-match.js（見那支檔案開頭的說明）
  const kw = ($('herbSearch').value || '').trim();
  const rows = HERBS.filter(h => window.zhMatchAny(
    [h.herb_cn_name, h.herb_pinyin, h.herb_en_name, h.child_cn_name], kw));
  $('herbList').innerHTML = rows.map(h => `
    <div class="herbRow${h.herb_id === currentHerbId ? ' active' : ''}" data-id="${h.herb_id}">
      <div class="name">${esc(h.herb_cn_name || h.herb_en_name || h.herb_id)}</div>
      <div class="meta">${esc(h.herb_pinyin || '')} ${esc(h.herb_en_name || '')}</div>
    </div>`).join('') || '<div class="herbRow"><span class="na">沒有符合的藥材</span></div>';
}

async function selectHerb(herbId) {
  currentHerbId = herbId;
  renderHerbList();
  $('emptyState').style.display = 'none';
  $('detail').style.display = '';
  $('herbHeader').innerHTML = '<div class="small">載入中…</div>';
  $('kpi').innerHTML = '';
  $('tbl').innerHTML = '';
  try {
    currentData = await api(`/tcmsp/herbs/public/${herbId}/active-ingredients`);
    filter = 'all';
    document.querySelectorAll('#toolbar button[data-f]').forEach(b =>
      b.classList.toggle('on', b.dataset.f === 'all'));
    renderDetail();
  } catch (err) {
    $('herbHeader').innerHTML = `<div class="na">載入失敗：${esc(err.message || err)}</div>`;
  }
}

/* ---------------------------------------------------------------- 明細 */

function renderDetail() {
  const d = currentData;
  const h = d.herb;
  const t = d.totals;

  $('herbHeader').innerHTML = `
    <h2>${esc(h.herb_cn_name || h.herb_en_name)}　<span class="small">herb_id ${h.herb_id}</span></h2>
    <div class="meta">${esc(h.herb_pinyin || '')}　${esc(h.herb_en_name || '')}　·
      <span>篩選門檻 OB ≥ ${d.thresholds.ob_min}%、DL ≥ ${d.thresholds.dl_min}</span>　·
      <a class="code" href="tcmsp_query.html?herb=${h.herb_id}">在關聯查詢站開啟 →</a>
    </div>`;

  const pct = t.active ? Math.round((t.standardised / t.active) * 1000) / 10 : 0;
  $('kpi').innerHTML = `
    <div><b>${t.all_ingredients}</b><span>全部成分</span></div>
    <div class="hero"><b>${t.active}</b><span>活性成分（本頁母體）</span></div>
    <div><b>${t.inactive == null ? '—' : t.inactive}</b><span>非活性成分</span></div>
    <div><b>${t.standardised}</b><span>已標準化（${pct}%）</span></div>
    <div><b>${t.with_smiles}</b><span>有 SMILES</span></div>
    <div><b>${t.with_cas}</b><span>有 CAS</span></div>
    <div><b>${t.with_inchikey}</b><span>有 InChIKey</span></div>
    <div><b>${t.missing_adme}</b><span>ADME 缺值而排除</span></div>`;

  renderTable();

  const todo = d.items.filter(i => !ACCEPTED.includes(i.status)).length;
  // 每一段各自一個 data-i18n-block（v1.50.0）：英韓翻譯以「整段」比對，
  // 分段後靜態的段落可以完全比對，只有帶數字的那一段需要用 {0} 佔位的範本。
  $('disclaimer').innerHTML = `
    <div data-i18n-block><b>怎麼讀這一頁：</b>「已標準化」只算<b>自動採用</b>與<b>已確認</b>兩種狀態——待確認是還沒審過的候選，
    拿它當成果會高估。分子量差欄位若標示「疑似苷元誤配」，代表名稱雖然對上、但查到的很可能是
    <b>帶糖基的另一個分子</b>，這種一律要人工判斷，不可直接採用。</div>
    <div data-i18n-block><b>名稱來源：</b>成分名稱為 TCMSP 的英文原名；「IUPAC 系統名稱」來自 PubChem，只有已對應到 CID 的成分才有。
    化合物沒有拉丁文名稱（拉丁學名是給藥材物種用的），化合物的國際標準命名就是 IUPAC 系統名稱。
    資料庫<b>沒有中文名稱與化學分類欄位</b>，本頁因此不提供。</div>
    <div data-i18n-block><b>非活性成分：</b>上方的「已標準化、有 SMILES」等數字<b>只算活性成分</b>；非活性成分另列在「非活性成分」分頁，
    不進入後續的靶點、通路與細胞株分析。</div>
    <div data-i18n-block>${todo ? `目前這味藥材還有 <b>${todo}</b> 個活性成分尚未完成標準化。` : '這味藥材的活性成分已全部完成標準化。'}</div>
    <div data-i18n-block>本平台為科研輔助工具，所有結果為公開資料庫的統計關聯，<b>不作為醫療診斷或治療建議</b>。</div>`;
}

function renderTable() {
  const d = currentData;
  const inactive = listTab === 'inactive';
  const all = inactive ? (d.inactive_items || []) : d.items;
  let rows = all;
  if (filter === 'done') rows = rows.filter(i => ACCEPTED.includes(i.status));
  if (filter === 'todo') rows = rows.filter(i => !ACCEPTED.includes(i.status));

  const noun = inactive ? '非活性成分' : '活性成分';
  $('filterCount').textContent = rows.length === all.length
    ? `共 ${rows.length} 個${noun}` : `顯示 ${rows.length} / ${all.length} 個`;

  if (!rows.length) {
    $('tbl').innerHTML = '<tbody><tr><td class="na">沒有符合的成分。</td></tr></tbody>';
    return;
  }

  const body = rows.map((i, n) => {
    const hint = deltaHint(i.mw_delta);
    const deltaCell = (i.mw_delta === null || i.mw_delta === undefined) ? '<span class="na">—</span>'
      : `<span class="${hint ? 'delta-flag' : ''}">${esc(i.mw_delta)}</span>${hint ? `<br><span class="small">${esc(hint)}</span>` : ''}`;
    const cid = i.cid
      ? `<a class="code" href="${PUBCHEM}${encodeURIComponent(i.cid)}" target="_blank" rel="noopener">${esc(i.cid)}</a>`
      : '<span class="na">—</span>';
    return `<tr>
      <td class="num small">${n + 1}</td>
      <td><a class="code" href="tcmsp_query.html?herb=${d.herb.herb_id}&mol=${encodeURIComponent(i.mol_id)}"
             title="在中藥關聯查詢站開啟這個成分">${esc(i.mol_id)}</a></td>
      <td>${esc(i.molecule_name || '—')}</td>
      <td class="iupac">${i.iupac_name ? `<div class="clip" title="${esc(i.iupac_name)}">${esc(i.iupac_name)}</div>` : '<span class="na">—</span>'}</td>
      ${inactive ? `<td><span class="rs${i.reason === 'missing' ? ' rs-missing' : ''}">${esc(REASON_CN[i.reason] || i.reason || '—')}</span></td>` : ''}
      <td class="num">${i.ob == null ? '—' : esc(i.ob)}</td>
      <td class="num">${i.dl == null ? '—' : esc(i.dl)}</td>
      <td class="num">${i.mw == null ? '—' : esc(i.mw)}</td>
      <td><span class="pill st-${esc(i.status)}">${esc(STATUS_CN[i.status] || i.status)}</span></td>
      <td>${cid}</td>
      <td style="text-align:center">${tick(i.has_smiles)}</td>
      <td style="text-align:center">${tick(i.has_cas)}</td>
      <td style="text-align:center">${tick(i.has_inchikey)}</td>
      <td class="num">${deltaCell}</td>
    </tr>`;
  }).join('');

  $('tbl').innerHTML = `<thead><tr>
      <th>#</th><th>Mol ID${help('mol_id')}</th><th>成分名稱（TCMSP 英文原名）</th>
      <th>IUPAC 系統名稱${help('iupac')}</th>
      ${inactive ? `<th>未納入原因${help('reason')}</th>` : ''}
      <th>OB %</th><th>DL</th><th>分子量</th>
      <th>標準化狀態</th><th>PubChem CID${help('cid')}</th>
      <th>SMILES${help('smiles')}</th><th>CAS${help('cas')}</th><th>InChIKey${help('inchikey')}</th><th>分子量差</th>
    </tr></thead><tbody>${body}</tbody>`;
  if (qsTable) qsTable.afterRender();
}

/* ---------------------------------------------------------------- 版面調整（v1.45.0）
 * 與藥材關聯查詢站同一套（js/qs-ui.js）：左側藥材清單可收合；表格可篩選、選欄位、
 * 點表頭排序、拉成獨立視窗。這一頁沒有關聯圖與勾選欄，所以沒有那兩項。 */
QSUI.collapsiblePanel({ panel: 'herbPanel', key: 'tcm_hi_panel_collapsed', label: '藥材清單' });
const qsTable = QSUI.tableTools({
  wrap: 'tableWrap', tabsBar: '#toolbar', key: 'tcm_hi_table',
  // 兩個分頁欄位不同（非活性多一欄「未納入原因」），各自記住隱藏的欄位；活性沿用舊鍵，使用者先前的設定不會掉
  getTab: () => (listTab === 'inactive' ? 'inactive' : 'ingredients'),
  title: () => {
    const noun = listTab === 'inactive' ? '非活性成分' : '活性成分';
    return currentData ? (currentData.herb.herb_cn_name || currentData.herb.herb_en_name) + '・' + noun : noun;
  },
});

/* 右上角登出（這一頁沒有掛 nav.js，自己綁） */
document.getElementById('platformLogout').addEventListener('click', async (e) => {
  e.preventDefault();
  try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: 'POST' }); } catch (err) { /* 失敗也照樣清掉本機登入狀態 */ }
  clearSession();
  window.location.href = 'index.html';
});

/* ---------------------------------------------------------------- 事件 */

$('herbSearch').addEventListener('input', renderHerbList);
$('herbList').addEventListener('click', (e) => {
  const row = e.target.closest('.herbRow');
  if (row && row.dataset.id) selectHerb(parseInt(row.dataset.id, 10));
});
$('toolbar').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.tab) {
    listTab = btn.dataset.tab;
    document.querySelectorAll('#toolbar button[data-tab]').forEach(b => b.classList.toggle('on', b === btn));
    if (currentData) renderTable();
    return;
  }
  if (!btn.dataset.f) return;
  filter = btn.dataset.f;
  document.querySelectorAll('#toolbar button[data-f]').forEach(b => b.classList.toggle('on', b === btn));
  renderTable();
});

$('termInfoModal').addEventListener('click', (e) => {
  if (e.target.id === 'termInfoModal') closeTermInfo();   // 點視窗外面關掉
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeTermInfo();
});

/* 查詢站類頁面沒有掛 nav.js，語系要自己呼叫（見 rules.md 第五之二章） */
const langSel = $('uiLangSelect');
langSel.addEventListener('change', () => {
  const lang = langSel.value;
  try { localStorage.setItem('siteLang', lang); } catch (e) { /* 私密視窗會丟例外 */ }
  window.applySiteLanguage(lang);
});

(async function init() {
  try {
    const saved = localStorage.getItem('siteLang');
    if (saved) { langSel.value = saved; window.applySiteLanguage(saved); }
  } catch (e) { /* 取不到就用預設繁體 */ }
  try {
    await loadHerbs();
  } catch (err) {
    $('herbStats').textContent = '載入失敗';
    $('emptyState').textContent = `藥材清單載入失敗：${err.message || err}`;
  }
})();
