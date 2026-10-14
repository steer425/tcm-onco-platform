/* 腫瘤細胞株依賴查詢站（F1-8，目標一 Step 6）
 *
 * 分析鏈路第五站「腫瘤細胞」的畫面。判定全部在後端 app/depmap_analysis.py，
 * 跟報表腳本 inspect_depmap 共用同一份——**前端不重算、不重新排序**。
 * 後端給的順序就是定案的順序（選擇性當門檻、效應量當排序，v1.41.3）。
 *
 * 刻意沒有的東西：
 *   - lineage 富集。人參的三個「顯著」lineage 經對照基因集檢定全部落在隨機範圍內，
 *     只放 q 值不放對照就是選擇性呈現（claude/BCL2結果的正確讀法_與對照檢定_2026-10-06.md）
 *   - 「有效」「抑制」這類字眼。依賴 ≠ 這個化合物會殺死那株細胞，見頁尾說明
 *
 * DepMap 資料是 CC BY 4.0：凡是顯示資料的地方都要標註來源與釋出版本（attribution）。
 */

const DEFAULT_HERB_ID = 336;      // 人参 Panax Ginseng C. A. Mey.（目標一指定的驗證藥材）

let HERBS = [];
let currentHerbId = null;
let currentData = null;
let currentTab = 'gated';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s)
  .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 3) => (v === null || v === undefined || !isFinite(v)) ? '—' : Number(v).toFixed(d);
const pct = (r) => (r === null || r === undefined) ? '—' : `${(r * 100).toFixed(1)}%`;

function effCell(v, strongCut) {
  if (v === null || v === undefined) return '<span class="na">—</span>';
  const cls = v <= strongCut ? 'eff-strong' : 'eff-weak';
  return `<span class="${cls}">${fmt(v)}</span>`;
}

function ingredientList(list) {
  if (!list || !list.length) return '<span class="na">—</span>';
  const names = [...new Map(list.map(i => [i.mol_id, i])).values()];
  return `<span class="small">${names.length} 個成分</span><ul class="ingList">` +
    names.slice(0, 4).map(i =>
      `<li><a class="code" href="tcmsp_query.html?herb=${currentHerbId}&mol=${encodeURIComponent(i.mol_id)}"
          title="在中藥關聯查詢站開啟這個成分">${esc(i.mol_id)}</a> ${esc(i.molecule_name || '')}</li>`).join('') +
    (names.length > 4 ? `<li>…另 ${names.length - 4} 個</li>` : '') + '</ul>';
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
  // 資料庫存簡體、畫面預設繁體，比對一律走 zh-match.js
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
  await loadDetail();
}

async function loadDetail() {
  $('herbHeader').innerHTML = '<div class="small">載入中…</div>';
  $('kpi').innerHTML = '';
  $('funnel').innerHTML = '';
  $('tabBody').innerHTML = '';
  const ratio = $('ratioSel').value;
  try {
    currentData = await api(`/depmap/herbs/${currentHerbId}/selective?max_ratio=${encodeURIComponent(ratio)}`);
    renderDetail();
  } catch (err) {
    const msg = err.message || String(err);
    $('herbHeader').innerHTML = `<div class="na">載入失敗：${esc(msg)}</div>`;
  }
}

/* ---------------------------------------------------------------- 明細 */

function renderDetail() {
  const d = currentData;
  const h = d.herb;
  const f = d.funnel;
  const p = d.params;

  $('herbHeader').innerHTML = `
    <h2>${esc(h.herb_cn_name || h.herb_en_name)}　<span class="small">herb_id ${h.herb_id}</span></h2>
    <div class="meta">${esc(h.herb_pinyin || '')}　${esc(h.herb_en_name || '')}　·
      DepMap ${esc(d.release)}　·
      <a class="code" href="herb-ingredients.html?herb=${h.herb_id}">活性成分與結構 →</a>
      <a class="code" href="tcmsp_query.html?herb=${h.herb_id}">關聯查詢站 →</a>
    </div>`;

  // 漏斗每一層都列：使用者要看得到這些數字是怎麼一路縮下來的
  const step = (n, label) => `<span><b>${n}</b> ${label}</span>`;
  const arrow = '<span class="arrow">→</span>';
  $('funnel').innerHTML = [
    step(f.active_ingredients, `活性成分（OB ≥ ${p.ob_min}%、DL ≥ ${p.dl_min}）`), arrow,
    step(f.targets, 'TCMSP 靶點'), arrow,
    step(f.symbols, '已標準化基因'), arrow,
    step(f.with_depmap, 'DepMap 有資料'), arrow,
    step(f.selective, '非泛必需且有依賴'), arrow,
    step(f.gated, '通過選擇性門檻'),
  ].join(' ');

  $('kpi').innerHTML = `
    <div class="hero"><b>${f.gated}</b><span>選擇性依賴靶點</span></div>
    <div><b>${f.gated_with_strong}</b><span>其中至少一株強依賴</span></div>
    <div><b>${f.dropped}</b><span>被選擇性門檻刷掉</span></div>
    <div><b>${f.common_essential}</b><span>泛必需（排除）</span></div>
    <div><b>${f.no_dependency}</b><span>任何細胞株都不依賴</span></div>`;

  $('paramNote').textContent =
    `有依賴：gene effect ≤ ${p.effect_threshold}；強依賴：≤ ${p.strong_effect}。換了門檻，數字的意義就不同，兩次結果不能直接比較。`;

  document.querySelectorAll('#tabs button').forEach(b => {
    const n = { gated: f.gated, dropped: f.dropped, essential: f.common_essential }[b.dataset.tab];
    b.textContent = { gated: '選擇性靶點', dropped: '被門檻刷掉', essential: '泛必需（已排除）' }[b.dataset.tab] + `（${n}）`;
    b.classList.toggle('on', b.dataset.tab === currentTab);
  });
  renderTab();

  const recep = d.gated.filter(r => r.receptor_warning).length;
  $('disclaimer').innerHTML = `
    <b>這張表不是「這味藥能治這些癌」。</b>它說的是：這味藥材的活性成分在 TCMSP 被註記為作用於這些靶點，
    而這些靶點在那些細胞株是選擇性依賴。兩件事之間還缺實際的結合與活性驗證——
    <b>TCMSP 的成分–靶點關係有相當比例是對接預測，不是實測結合</b>，目前尚未分層。<br>
    <b>⚠️ 方向性：</b>CRISPR 依賴量的是「<b>移除</b>這個基因，細胞會不會死」，要轉成治療假說，前提是化合物<b>抑制</b>該靶點；
    TCMSP 不記錄作用方向。${recep ? `本表有 <b>${recep}</b> 個標為「受體」——核受體與配體門控受體的天然配體通常是活化劑，方向反了效果可能相反。` : ''}
    受體標記是啟發式的，只用來提醒；沒被標記也不代表方向沒問題。<br>
    <b>強依賴株數為「—」的列請當成雜訊看待：</b>只在少數細胞、效應剛越過門檻的配對，在這個規模的矩陣裡本來就會隨機出現。<br>
    <b>CRISPR 敲除 ≠ 化合物抑制</b>；DepMap 只有腫瘤細胞株，這裡的「選擇性」是腫瘤株之間的比較，不是腫瘤 vs 正常細胞。<br>
    本頁不提供 lineage（癌別）富集：以人參為例，該富集經對照基因集檢定後落在隨機範圍內，不能解讀為這味藥材的特性。<br>
    本平台為科研輔助工具，所有結果為公開資料庫的統計關聯，<b>不作為醫療診斷或治療建議</b>。`;
  $('attrib').textContent = `資料來源：${d.attribution}`;
}

function renderTab() {
  const d = currentData;
  if (!d) return;
  const strongCut = d.params.strong_effect;

  if (currentTab === 'essential') {
    const list = d.excluded_essential;
    $('tabBody').innerHTML = list.length
      ? `<p class="small">這些基因在幾乎每一株細胞都是存活必需。任何有細胞毒性的物質都會「命中」它們，
           所以<b>不能</b>拿來當抗腫瘤機轉的證據。</p>
         <p>${list.map(s => `<a class="gene" data-gene="${esc(s)}">${esc(s)}</a>`).join('、')}</p>`
      : '<p class="na">沒有命中泛必需基因。</p>';
    return;
  }

  const rows = currentTab === 'gated' ? d.gated : d.dropped;
  if (!rows.length) {
    $('tabBody').innerHTML = `<p class="na">${currentTab === 'gated' ? '沒有通過選擇性門檻的靶點。' : '沒有被門檻刷掉的靶點。'}</p>`;
    return;
  }
  const head = currentTab === 'gated'
    ? `<tr><th>#</th><th>基因</th><th>強依賴株數</th><th>達門檻株數／母體</th><th>佔比</th>
         <th>最強效應</th><th>最依賴的細胞株</th><th>癌別</th><th>打到它的成分</th><th>方向</th></tr>`
    : `<tr><th>基因</th><th>達門檻株數／母體</th><th>佔比</th><th>為什麼刷掉</th><th>打到它的成分</th></tr>`;

  const body = rows.map((r, i) => {
    const gene = `<a class="gene" data-gene="${esc(r.gene_symbol)}" title="看依賴這個基因的所有細胞株">${esc(r.gene_symbol)}</a>`;
    const frac = `${r.n_dependent}／${r.n_lines_total}`;
    if (currentTab === 'dropped') {
      return `<tr><td>${gene}</td><td class="num">${frac}</td><td class="num">${pct(r.ratio)}</td>
        <td class="small">${esc(r.dropped_reason || '')}</td><td>${ingredientList(r.ingredients)}</td></tr>`;
    }
    const L = r.best_line;
    const line = L ? `<a class="line" data-line="${esc(L.depmap_id)}" title="看這株細胞依賴的其他靶點">${esc(L.cell_line_name || L.depmap_id)}</a>`
      : '<span class="na">—</span>';
    return `<tr>
      <td class="num small">${i + 1}</td>
      <td>${gene}</td>
      <td class="num">${r.n_strong ? r.n_strong : '<span class="noise">—</span>'}</td>
      <td class="num">${frac}</td>
      <td class="num">${pct(r.ratio)}</td>
      <td class="num">${effCell(r.min_effect, strongCut)}</td>
      <td>${line}</td>
      <td class="small">${esc(L ? (L.primary_disease || L.lineage || '') : '')}</td>
      <td>${ingredientList(r.ingredients)}</td>
      <td>${r.receptor_warning ? '<span class="warn" title="核受體／配體門控受體：化合物可能是活化劑而非抑制劑">⚠️ 受體</span>' : ''}</td>
    </tr>`;
  }).join('');
  const note = currentTab === 'dropped'
    ? `<p class="small">這些不是沒有訊號，而是<b>訊號不具選擇性</b>——在很多細胞株都依賴的基因，抑制它比較像細胞毒性而不是機轉。要看它們可以放寬上方的門檻。</p>`
    : `<p class="small">排序：通過選擇性門檻後，依<b>最強效應</b>由強到弱（不是依株數——株數多代表廣度，不是選擇性）。</p>`;
  $('tabBody').innerHTML = `${note}<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

/* ---------------------------------------------------------------- 下鑽視窗 */

function openModal(title, html) {
  $('detailTitle').textContent = title;
  $('detailBody').innerHTML = html;
  $('detailModal').style.display = 'flex';
}
function closeModal() { $('detailModal').style.display = 'none'; }

async function showGene(symbol) {
  openModal(`${symbol}：依賴它的細胞株`, '<p class="small">載入中…</p>');
  try {
    const r = await api(`/depmap/genes/${encodeURIComponent(symbol)}/lines?limit=200`);
    const s = r.summary;
    const cut = currentData ? currentData.params.strong_effect : -1;
    const rows = r.items.map((x, i) => `<tr>
      <td class="num small">${i + 1}</td>
      <td><a class="line" data-line="${esc(x.depmap_id)}">${esc(x.cell_line_name || x.depmap_id)}</a></td>
      <td class="small">${esc(x.primary_disease || '')}</td>
      <td class="small">${esc(x.lineage || '')}</td>
      <td class="num">${effCell(x.gene_effect, cut)}</td>
      <td><a class="code" href="${esc(x.depmap_url)}" target="_blank" rel="noopener">DepMap ↗</a></td></tr>`).join('');
    $('detailBody').innerHTML = `
      <p class="small">${s.is_common_essential ? '<span class="warn">泛必需基因</span>　' : ''}
        達門檻 ${s.n_dependent}／${s.n_lines_total} 株（${pct(s.ratio)}），強依賴 ${s.n_strong} 株，最強效應 ${fmt(s.min_effect)}　·
        <a class="code" href="${esc(s.depmap_url)}" target="_blank" rel="noopener">在 DepMap 開啟 ↗</a></p>
      <p class="small">${esc(r.note)}</p>
      ${rows ? `<table><thead><tr><th>#</th><th>細胞株</th><th>癌別</th><th>Lineage</th><th>gene effect</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
             : '<p class="na">沒有細胞株達依賴門檻。</p>'}
      <p class="attrib">資料來源：${esc(r.attribution)}</p>`;
  } catch (err) {
    $('detailBody').innerHTML = `<p class="na">載入失敗：${esc(err.message || err)}</p>`;
  }
}

async function showLine(depmapId) {
  openModal('細胞株', '<p class="small">載入中…</p>');
  try {
    const ratio = $('ratioSel').value;
    const r = await api(`/depmap/lines/${encodeURIComponent(depmapId)}?herb_id=${currentHerbId}&max_ratio=${encodeURIComponent(ratio)}`);
    const L = r.line;
    $('detailTitle').textContent = `${L.cell_line_name || L.depmap_id}（${L.depmap_id}）`;
    const cut = currentData ? currentData.params.strong_effect : -1;
    const rows = r.items.map(x => `<tr>
      <td><a class="gene" data-gene="${esc(x.gene_symbol)}">${esc(x.gene_symbol)}</a>
        ${x.receptor_warning ? '<span class="warn">⚠️ 受體</span>' : ''}</td>
      <td class="num">${effCell(x.gene_effect_in_line, cut)}</td>
      <td class="num">${x.n_dependent}／${x.n_lines_total}（${pct(x.ratio)}）</td>
      <td>${ingredientList(x.ingredients)}</td></tr>`).join('');
    const herbName = currentData ? (currentData.herb.herb_cn_name || currentData.herb.herb_en_name) : '';
    $('detailBody').innerHTML = `
      <p class="small">${esc(L.primary_disease || '')}${L.subtype ? '／' + esc(L.subtype) : ''}　·　Lineage：${esc(L.lineage || '—')}　·
        <a class="code" href="${esc(L.depmap_url)}" target="_blank" rel="noopener">在 DepMap 開啟 ↗</a></p>
      <p class="small">這株細胞依賴、而且是「${esc(herbName)}」選擇性靶點的基因（${r.total} 個），依這株的效應由強到弱：</p>
      ${rows ? `<table><thead><tr><th>基因</th><th>這株的 gene effect</th><th>全母體依賴範圍</th><th>打到它的成分</th></tr></thead><tbody>${rows}</tbody></table>`
             : '<p class="na">這株細胞不依賴本藥材的任何選擇性靶點。</p>'}
      <p class="attrib">資料來源：${esc(r.attribution)}</p>`;
  } catch (err) {
    $('detailBody').innerHTML = `<p class="na">載入失敗：${esc(err.message || err)}</p>`;
  }
}

/* ---------------------------------------------------------------- 事件 */

$('herbSearch').addEventListener('input', renderHerbList);
$('herbList').addEventListener('click', (e) => {
  const row = e.target.closest('.herbRow');
  if (row && row.dataset.id) selectHerb(parseInt(row.dataset.id, 10));
});
$('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn || !btn.dataset.tab) return;
  currentTab = btn.dataset.tab;
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b === btn));
  renderTab();
});
$('ratioSel').addEventListener('change', () => { if (currentHerbId) loadDetail(); });

// 下鑽連結在主表與視窗裡都會出現，一律用事件委派
document.addEventListener('click', (e) => {
  const g = e.target.closest('a.gene');
  if (g && g.dataset.gene) { e.preventDefault(); showGene(g.dataset.gene); return; }
  const l = e.target.closest('a.line');
  if (l && l.dataset.line) { e.preventDefault(); showLine(l.dataset.line); }
});
$('detailClose').addEventListener('click', closeModal);
$('detailModal').addEventListener('click', (e) => { if (e.target.id === 'detailModal') closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

/* 右上角登出（這一頁沒有掛 nav.js，自己綁；v1.45.0） */
$('platformLogout').addEventListener('click', async (e) => {
  e.preventDefault();
  try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: 'POST' }); } catch (err) { /* 失敗也照樣清掉本機登入狀態 */ }
  clearSession();
  window.location.href = 'index.html';
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
