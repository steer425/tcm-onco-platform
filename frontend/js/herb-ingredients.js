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

let HERBS = [];
let currentHerbId = null;
let currentData = null;
let filter = 'all';

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
  const kw = ($('herbSearch').value || '').trim().toLowerCase();
  const rows = HERBS.filter(h => !kw || [h.herb_cn_name, h.herb_pinyin, h.herb_en_name, h.child_cn_name]
    .join(' ').toLowerCase().includes(kw));
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
    document.querySelectorAll('#toolbar button').forEach(b =>
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
      篩選門檻 OB ≥ ${d.thresholds.ob_min}%、DL ≥ ${d.thresholds.dl_min}　·
      <a class="code" href="tcmsp_query.html?herb=${h.herb_id}">在關聯查詢站開啟 →</a>
    </div>`;

  const pct = t.active ? Math.round((t.standardised / t.active) * 1000) / 10 : 0;
  $('kpi').innerHTML = `
    <div><b>${t.all_ingredients}</b><span>全部成分</span></div>
    <div class="hero"><b>${t.active}</b><span>活性成分（本頁母體）</span></div>
    <div><b>${t.standardised}</b><span>已標準化（${pct}%）</span></div>
    <div><b>${t.with_smiles}</b><span>有 SMILES</span></div>
    <div><b>${t.with_cas}</b><span>有 CAS</span></div>
    <div><b>${t.with_inchikey}</b><span>有 InChIKey</span></div>
    <div><b>${t.missing_adme}</b><span>ADME 缺值而排除</span></div>`;

  renderTable();

  const todo = d.items.filter(i => !ACCEPTED.includes(i.status)).length;
  $('disclaimer').innerHTML = `
    <b>怎麼讀這一頁：</b>「已標準化」只算<b>自動採用</b>與<b>已確認</b>兩種狀態——待確認是還沒審過的候選，
    拿它當成果會高估。分子量差欄位若標示「疑似苷元誤配」，代表名稱雖然對上、但查到的很可能是
    <b>帶糖基的另一個分子</b>，這種一律要人工判斷，不可直接採用。<br>
    <b>名稱來源：</b>成分名稱為 TCMSP 的英文原名。資料庫<b>沒有中文名稱與化學分類欄位</b>，本頁因此不提供。<br>
    ${todo ? `目前這味藥材還有 <b>${todo}</b> 個活性成分尚未完成標準化。` : '這味藥材的活性成分已全部完成標準化。'}<br>
    本平台為科研輔助工具，所有結果為公開資料庫的統計關聯，<b>不作為醫療診斷或治療建議</b>。`;
}

function renderTable() {
  const d = currentData;
  let rows = d.items;
  if (filter === 'done') rows = rows.filter(i => ACCEPTED.includes(i.status));
  if (filter === 'todo') rows = rows.filter(i => !ACCEPTED.includes(i.status));

  $('filterCount').textContent = rows.length === d.items.length
    ? `共 ${rows.length} 個活性成分` : `顯示 ${rows.length} / ${d.items.length} 個`;

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
      <th>#</th><th>Mol ID</th><th>成分名稱（TCMSP 英文原名）</th>
      <th>OB %</th><th>DL</th><th>分子量</th>
      <th>標準化狀態</th><th>PubChem CID</th>
      <th>SMILES</th><th>CAS</th><th>InChIKey</th><th>分子量差</th>
    </tr></thead><tbody>${body}</tbody>`;
}

/* ---------------------------------------------------------------- 事件 */

$('herbSearch').addEventListener('input', renderHerbList);
$('herbList').addEventListener('click', (e) => {
  const row = e.target.closest('.herbRow');
  if (row && row.dataset.id) selectHerb(parseInt(row.dataset.id, 10));
});
$('toolbar').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn || !btn.dataset.f) return;
  filter = btn.dataset.f;
  document.querySelectorAll('#toolbar button').forEach(b => b.classList.toggle('on', b === btn));
  renderTable();
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
