/* 文獻證據分級（F1-9，目標一 Step 5）
 *
 * 靶點清單＝腫瘤細胞株依賴查詢站（F1-8）通過選擇性門檻的那一份，由後端
 * app/depmap_analysis.select_herb_targets() 給，**前端不重算、不重新排序**。
 * 分級規則全部在 app/literature_evidence.py。
 *
 * 文章標題、共現句都是 PubMed 的外部文字——一律經 esc() 才寫進 DOM（rules.md 五之五）。
 *
 * 刻意的呈現選擇：
 *   - 「獨立證據」與總篇數分開顯示。總篇數裡有網絡藥理（與 TCMSP 同源）、綜述、撤稿、
 *     只靠索引命中的，拿總篇數當證據強度會高估
 *   - 只提到成分、沒提到這味藥的，跟藥材層級分開數（槲皮素的文獻多半跟這味藥無關）
 *   - 方向是啟發式，標「字詞」而不是「作用」
 */

const DEFAULT_HERB_ID = 336;      // 人参 Panax Ginseng C. A. Mey.（目標一指定的驗證藥材）

let HERBS = [];
let currentHerbId = null;
let currentData = null;
let busy = false;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s)
  .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 3) => (v === null || v === undefined || !isFinite(v)) ? '—' : Number(v).toFixed(d);

const LEVEL_LABEL = {
  meta: '系統性回顧／統合分析', trial: '臨床試驗', human_obs: '人體觀察研究', animal: '動物實驗',
  cell: '細胞實驗', computational: '計算預測', review: '綜述', unknown: '未判定',
};
const COMENTION_LABEL = { sentence: '同一句', abstract: '摘要各自提到', index_only: '只靠索引命中' };
const DIR_LABEL = { down: '下調字詞', up: '上調字詞', mixed: '方向混合' };
const FLAG_LABEL = {
  circular: '網絡藥理（與 TCMSP 同源）', includes_computational: '含計算預測', retracted: '已撤稿',
};

const levelPill = (code) => `<span class="lv lv-${esc(code)}">${esc(LEVEL_LABEL[code] || code)}</span>`;

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
  $('collectMsg').textContent = '';
  await loadDetail();
}

async function loadDetail() {
  $('herbHeader').innerHTML = '<div class="small">載入中…</div>';
  $('kpi').innerHTML = '';
  $('tabBody').innerHTML = '';
  try {
    currentData = await api(`/literature/herbs/${currentHerbId}`);
    renderDetail();
  } catch (err) {
    currentData = null;
    $('herbHeader').innerHTML = `<div class="na">載入失敗：${esc(err.message || err)}</div>`;
    updateCollectButton();
  }
}

/* ---------------------------------------------------------------- 明細 */

function summaryCells(g) {
  const s = g.summary, q = g.search;
  if (!q) return '<td colspan="5" class="na">尚未查詢</td>';
  if (q.status === 'error') {
    return `<td colspan="5"><span class="pill st-error">查詢失敗</span> <span class="small">${esc(q.error || '')}</span></td>`;
  }
  if (q.status === 'empty' || !s || !s.n) {
    return `<td class="num">0</td><td colspan="4" class="na">PubMed 查無共同出現的文獻</td>`;
  }
  const dir = s.directions;
  const dirTxt = [
    dir.down ? `<span class="dir-down"><span>下調</span> ${dir.down}</span>` : '',
    dir.up ? `<span class="dir-up"><span>上調</span> ${dir.up}</span>` : '',
    dir.mixed ? `<span class="dir-mixed"><span>混合</span> ${dir.mixed}</span>` : '',
  ].filter(Boolean).join('　') || '<span class="na">—</span>';
  return `
    <td class="num">${q.total_count}<div class="small"><span>抓回</span> ${q.n_fetched}</div></td>
    <td>${s.best_level ? levelPill(s.best_level) : '<span class="na">無獨立證據</span>'}</td>
    <td class="num"><b>${s.independent}</b>／${s.n}
      <div class="small"><span>提到藥材</span> ${s.herb_level}・<span>只提成分</span> ${s.ingredient_only}</div></td>
    <td>${dirTxt}<div class="small"><span>同句共現</span> ${s.same_sentence}</div></td>
    <td class="num">${s.circular ? `<span class="warn">${s.circular}</span>` : '0'}</td>`;
}

function renderDetail() {
  const d = currentData, h = d.herb, c = d.counts;
  $('herbHeader').innerHTML = `
    <h2>${esc(h.herb_cn_name || h.herb_en_name)}　<span class="small">herb_id ${h.herb_id}</span></h2>
    <div class="meta">${esc(h.herb_pinyin || '')}　${esc(h.herb_en_name || '')}　·
      <span>靶點來自</span> DepMap ${esc(d.release)}　<span>選擇性門檻</span> ≤ ${(d.params.max_ratio * 100).toFixed(0)}%　·
      <a class="code" href="tumor-cells.html?herb=${h.herb_id}">腫瘤細胞株依賴 →</a></div>`;

  const indep = d.genes.reduce((n, g) => n + (g.summary ? g.summary.independent : 0), 0);
  const withIndep = d.genes.filter(g => g.summary && g.summary.independent > 0).length;
  $('kpi').innerHTML = `
    <div><b>${c.genes}</b><span>選擇性靶點</span></div>
    <div><b>${c.searched}</b><span>已查詢</span></div>
    <div><b>${c.remaining}</b><span>尚未查詢</span></div>
    <div class="hero"><b>${withIndep}</b><span>有獨立文獻的靶點</span></div>
    <div><b>${indep}</b><span>獨立證據篇數</span></div>`;

  const rows = d.genes.map(g => `
    <tr class="${g.search ? 'clickable' : ''}" data-gene="${esc(g.gene_symbol)}">
      <td><b>${esc(g.gene_symbol)}</b>${g.receptor_warning ? ' <span class="warn">⚠️ 受體</span>' : ''}
        <div class="small">${esc(g.protein_name || '')}</div></td>
      <td class="num">${fmt(g.min_effect)}<div class="small">${g.n_dependent}／${g.n_lines_total}</div></td>
      <td class="small">${g.ingredients.map(i => esc(i.molecule_name || i.mol_id)).slice(0, 4).join('、')}${g.ingredients.length > 4 ? `…等 ${g.ingredients.length} 個` : ''}</td>
      ${summaryCells(g)}
    </tr>`).join('');
  $('tabBody').innerHTML = d.genes.length ? `
    <table><thead><tr>
      <th>靶點</th><th>最強依賴</th><th>打到它的活性成分</th>
      <th>PubMed 命中</th><th>最高獨立證據</th><th>獨立／抓回</th><th>方向字詞</th><th>網絡藥理</th>
    </tr></thead><tbody>${rows}</tbody></table>
    <p class="small">點有查詢紀錄的列，看查詢式與逐篇分級。</p>`
    : '<p class="na">這味藥材沒有通過選擇性門檻的靶點，沒有可查詢的組合。</p>';

  $('disclaimer').innerHTML = `<b>怎麼讀這一頁</b><br>${esc(d.disclaimer)}<br>` +
    '<span>「獨立證據」排除：網絡藥理學（與 TCMSP 同源）、綜述、已撤稿、標題摘要裡找不到藥材／成分或靶點名稱（只靠 PubMed 索引命中）。</span><br>' +
    '<span>「方向字詞」只看靶點所在子句裡最近的上調／下調字詞，是讀文獻的線索，不是作用方向的結論。</span>';
  updateCollectButton();
}

function updateCollectButton() {
  // 沒有執行權限就不顯示查詢列（後端 POST /collect 也會擋；這裡只是不讓人按了才看到 403）。
  // can_collect 由後端用與 POST 相同的權限判定算好，前端不自己猜角色。
  const allowed = !!(currentData && currentData.can_collect);
  $('collectBar').style.display = allowed ? '' : 'none';
  $('collectNote').style.display = (!allowed && currentData && currentData.counts.remaining) ? '' : 'none';
  const rem = currentData ? currentData.counts.remaining : 0;
  $('collectBtn').disabled = busy || !currentData || rem === 0;
  if (!busy && currentData && rem === 0 && currentData.counts.genes) {
    $('collectMsg').textContent = $('collectMsg').textContent || '全部靶點都查過了。';
  }
}

async function runCollect() {
  if (busy || !currentData) return;
  busy = true;
  updateCollectButton();
  const limit = parseInt($('collectLimit').value, 10);
  $('collectMsg').textContent = `查詢中（${limit} 個靶點，每個約 1 秒）…`;
  let finalMsg = '';
  try {
    const r = await api(`/literature/herbs/${currentHerbId}/collect`,
      { method: 'POST', body: JSON.stringify({ limit }) });
    const ok = r.results.filter(x => x.status === 'ok').length;
    const empty = r.results.filter(x => x.status === 'empty').length;
    const bad = r.results.filter(x => x.status === 'error');
    finalMsg = `完成 ${r.processed} 個：有文獻 ${ok}、查無 ${empty}` +
      (bad.length ? `、失敗 ${bad.length}（${bad.map(x => x.gene_symbol).join('、')}）` : '') +
      `；尚未查詢 ${r.remaining} 個。`;
    await loadDetail();
  } catch (err) {
    finalMsg = `查詢失敗：${err.message || err}`;
  } finally {
    busy = false;
    $('collectMsg').textContent = finalMsg;
    updateCollectButton();
  }
}

/* ---------------------------------------------------------------- 逐篇 */

function openModal(title, html) {
  $('detailTitle').textContent = title;
  $('detailBody').innerHTML = html;
  $('detailModal').style.display = 'flex';
}
function closeModal() { $('detailModal').style.display = 'none'; }

async function showGene(symbol) {
  openModal(symbol, '<p class="small">載入中…</p>');
  try {
    const r = await api(`/literature/herbs/${currentHerbId}/genes/${encodeURIComponent(symbol)}`);
    const rows = r.articles.map(a => {
      const ents = a.matched_entities.map(e => `${e.kind === 'herb' ? '藥材' : '成分'}：${esc(e.term)}`).join('、');
      const flags = a.flags.map(f => `<span class="flag${f === 'includes_computational' ? ' soft' : ''}">${esc(FLAG_LABEL[f] || f)}</span>`).join('');
      return `<tr>
        <td>${levelPill(a.level)}</td>
        <td class="num">${a.year || '—'}</td>
        <td><a class="code" href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>${flags}
          <div class="small">${esc(a.journal || '')}　PMID ${esc(a.pmid)}</div>
          ${a.evidence_sentence ? `<div class="sent">${esc(a.evidence_sentence)}</div>` : ''}</td>
        <td class="small">${esc(COMENTION_LABEL[a.comention] || a.comention)}<div>${ents || '<span class="na">—</span>'}</div></td>
        <td class="small">${a.direction ? esc(DIR_LABEL[a.direction]) : '—'}</td>
      </tr>`;
    }).join('');
    const s = r.search;
    $('detailBody').innerHTML = `
      <p class="small">PubMed 命中 ${s.total_count} 篇，依相關度抓回前 ${s.n_fetched} 篇並分級。
        查詢時間 ${esc((s.searched_at || '').replace('T', ' ').slice(0, 16))}（UTC）${s.stale_grading ? '　<span class="warn">分級規則已更新，建議重查</span>' : ''}</p>
      <div class="q">${esc(r.query_term)}</div>
      <p class="small"><a class="code" href="${esc(r.pubmed_search_url)}" target="_blank" rel="noopener">在 PubMed 重跑這條查詢式 ↗</a></p>
      ${rows ? `<table><thead><tr><th>研究設計</th><th>年</th><th>文章</th><th>共現</th><th>方向字詞</th></tr></thead><tbody>${rows}</tbody></table>`
             : '<p class="na">沒有抓回文章。</p>'}
      <p class="small">${esc(r.disclaimer)}</p>`;
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
$('tabBody').addEventListener('click', (e) => {
  const tr = e.target.closest('tr.clickable');
  if (tr && tr.dataset.gene) showGene(tr.dataset.gene);
});
$('collectBtn').addEventListener('click', runCollect);
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
