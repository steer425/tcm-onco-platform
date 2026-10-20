/* F1-10 兩岸中藥典比較（v1.51.0）
 *
 * 左：臺灣中藥典第四版品項清單（搜尋＋篩選）；右：臺灣中藥典 ↔ TCMSP 對照、114 年修正公告、15 欄全文。
 *
 * ⚠️ 畫面上的用語要精確：
 *   - 「中國側」是 TCMSP 藥材編號，代表中國藥典 2010 年版收載品項；**不是**中國藥典官方編號，也沒有中國藥典專論內容。
 *   - 比對狀態：auto（中文名＋學名都對上）、pending（只對上一邊，待人工確認）、confirmed、rejected。
 *   - 同名異物（same_name_diff_species）要醒目——兩岸同一個中文名可能是不同物種，是這一頁最重要的發現。
 * 所有內容（藥典原文、TCMSP 名稱、審核備註）一律跳脫後才放進 innerHTML。
 */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s)
  .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const FIELD_LABELS = [
  ['origin', '基原'], ['content', '含量'], ['description', '性狀'], ['identification', '鑑別'],
  ['impurity', '雜質檢查及其它規定'], ['assay', '含量測定'], ['storage', '貯藏法'], ['category', '用途分類'],
  ['nature_meridian', '性味與歸經'], ['functions', '功能'], ['usage_dosage', '用法與用量'], ['precautions', '注意事項'],
];
const CLINICAL = new Set(['functions', 'usage_dosage', 'precautions']);
const EXTRA_LABELS = { '出典': '出典', '處方': '處方', '效能': '效能', '適應症': '適應症' };
const KIND_CN = { herb: '藥材', processed: '飲片', preparation: '濃縮製劑' };
const STATUS_CN = { auto: '自動採用', confirmed: '已確認', pending: '待確認', rejected: '已否決' };
const METHOD_CN = { name: '中文名', species: '基原學名', english: '英文名稱', latin: '拉丁生藥名稱', manual: '人工指定' };
// v1.51.2：名稱比對結果（後端 app/thp.py name_compare）。中文名相同時先比英文名稱，不同再比拉丁生藥名稱，皆不分大小寫
const CMP_CN = { same: '相同（不分大小寫）', same_words: '字詞相同（順序不同）', partial: '部分字詞相同', different: '不同', na: '無資料' };
function nameCompare(c) {
  if (!c) return '';
  // 標籤、結果各自一個文字節點（英韓逐詞字典才翻得到）；名稱本身是資料，translate=no
  const row = (label, key, thp, res) => `<div class="nc${c.used === key ? ' used' : ''}">
      <span class="nl">${label}</span><span translate="no">${esc(thp || '—')}</span> ↔ <span translate="no">${esc(c.tcmsp_en || '—')}</span>
      <span class="res r-${esc(res)}">${esc(CMP_CN[res] || res)}</span>${c.used === key ? ' <span class="pill k-used">以此比對</span>' : ''}</div>`;
  return `<div class="ncmp">${row('英文名稱', 'english', c.thp_en, c.english)}${row('拉丁生藥名稱', 'latin', c.thp_latin, c.latin)}</div>`;
}
const FLAG_CN = {
  same_name_diff_species: '同名異物', diff_name_same_species: '異名同物', processed: '飲片',
};

let DATA = null;          // /pharmacopeia/thp
let CN_ONLY = [];         // /pharmacopeia/tcmsp-only
let filter = 'all';
let current = null;       // { type: 'thp', seq } | { type: 'herb', herb_id }
const molCache = new Map();

/* ---------------------------------------------------------------- 分類 */
function live(m) { return m.status !== 'rejected'; }
function classOf(it) {
  const ms = it.matches.filter(live);
  return {
    matched: ms.some((m) => m.status === 'auto' || m.status === 'confirmed'),
    pending: ms.some((m) => m.status === 'pending'),
    diff: ms.some((m) => m.flags.includes('same_name_diff_species')),
    none: it.kind !== 'preparation' && ms.length === 0,
  };
}

/* ---------------------------------------------------------------- 載入 */
async function load() {
  DATA = await api('/pharmacopeia/thp');
  try { CN_ONLY = (await api('/pharmacopeia/tcmsp-only')).items; } catch (e) { CN_ONLY = []; }
  renderKpi();
  renderList();
}

function renderKpi() {
  const s = DATA.stats;
  const box = (n, label, f) => `<div${f ? ` class="clk" data-f="${f}"` : ''}><b>${esc(n)}</b><span>${label}</span></div>`;
  $('kpi').innerHTML =
    box(s.comparable, '臺灣中藥典品項', 'all') +
    box(s.matched, '兩邊都有', 'matched') +
    box(s.pending_only, '只有待確認', 'pending') +
    box(s.same_name_diff_species, '同名異物', 'diff') +
    box(s.thp_only, '只在臺灣中藥典', 'twonly') +
    box(`${s.tcmsp_matched} / ${s.tcmsp_herbs}`, 'TCMSP 藥材已對上', 'cnonly') +
    box(s.review_queue, '待審核比對', 'pending');
}

/* ---------------------------------------------------------------- 清單 */
function matchKw(it, kw) {
  if (!kw) return true;
  const hay = [it.site_no, it.name_zh, it.latin_name, it.en_name, ...(it.species || [])]
    .filter(Boolean).join(' ').toLowerCase();
  if (hay.includes(kw.toLowerCase())) return true;
  return window.zhMatchAny ? window.zhMatchAny([it.name_zh], kw) : false;
}

function renderList() {
  const kw = ($('search').value || '').trim();
  document.querySelectorAll('#filters button').forEach((b) => b.classList.toggle('on', b.dataset.f === filter));
  if (filter === 'cnonly') {
    const rows = CN_ONLY.filter((h) => !kw || window.zhMatchAny([h.herb_cn_name, h.herb_pinyin, h.herb_en_name], kw)
      || String(h.herb_id) === kw);
    $('listStats').textContent = `TCMSP 有、臺灣中藥典沒有對應：${rows.length} 味`;
    $('list').innerHTML = rows.map((h) => `
      <div class="row${current && current.type === 'herb' && current.herb_id === h.herb_id ? ' active' : ''}" data-herb="${h.herb_id}">
        <span class="no">#${esc(h.herb_id)}</span>
        <span class="nm" translate="no">${esc(h.herb_cn_name || h.herb_en_name)}<span class="sub">${esc(h.herb_en_name || '')}</span></span>
      </div>`).join('') || '<div class="row"><span class="na">沒有符合的藥材</span></div>';
    return;
  }
  const rows = DATA.items.filter((it) => {
    const c = classOf(it);
    if (filter === 'prep') { if (it.kind !== 'preparation') return false; }
    else if (it.kind === 'preparation' && filter !== 'all') return false;
    if (filter === 'matched' && !c.matched) return false;
    if (filter === 'pending' && !(c.pending && !c.matched)) return false;
    if (filter === 'diff' && !c.diff) return false;
    if (filter === 'twonly' && !c.none) return false;
    if (filter === 'amended' && !it.amended) return false;
    return matchKw(it, kw);
  });
  $('listStats').textContent = `顯示 ${rows.length} / ${DATA.items.length} 項`;
  $('list').innerHTML = rows.map((it) => {
    const c = classOf(it);
    const badges = [
      it.kind !== 'herb' ? `<span class="pill k-${it.kind}">${KIND_CN[it.kind]}</span>` : '',
      c.diff ? '<span class="pill fl-warn">同名異物</span>' : '',
      c.matched ? '<span class="pill st-auto">✓</span>' : (c.pending ? '<span class="pill st-pending">?</span>' : ''),
      it.amended ? '<span class="pill amd">修</span>' : '',
    ].join('');
    return `<div class="row${current && current.type === 'thp' && current.seq === it.seq ? ' active' : ''}" data-seq="${it.seq}">
      <span class="no">${esc(it.site_no || '—')}</span>
      <span class="nm" translate="no">${esc(it.name_zh)}<span class="sub">${esc(it.latin_name || '')}</span></span>
      <span class="badges">${badges}</span></div>`;
  }).join('') || '<div class="row"><span class="na">沒有符合的品項</span></div>';
}

/* ---------------------------------------------------------------- 詳細：臺灣中藥典品項 */
async function selectThp(seq) {
  current = { type: 'thp', seq };
  renderList();
  $('emptyState').style.display = 'none';
  $('detail').style.display = '';
  $('detail').innerHTML = '<div class="na">載入中…</div>';
  try {
    const d = await api(`/pharmacopeia/thp/${seq}`);
    renderThp(d);
    try { history.replaceState(null, '', `?item=${encodeURIComponent(d.site_no || 'seq' + d.seq)}`); } catch (e) { /* file:// */ }
  } catch (err) {
    $('detail').innerHTML = `<div class="na">載入失敗：${esc(err.message || err)}</div>`;
  }
}

function matchCard(m) {
  const flags = (m.flags || []).map((f) => `<span class="pill ${f === 'same_name_diff_species' ? 'fl-warn' : 'k-processed'}">${esc(FLAG_CN[f] || f)}</span>`).join(' ');
  // 每個字詞各自一個文字節點，英韓逐詞字典才翻得到（整串「比對依據：中文名＋基原學名」對不上字典）
  const method = String(m.method || '').split('+').filter(Boolean)
    .map((x) => `<span>${esc(METHOD_CN[x] || x)}</span>`).join('＋');
  const acts = DATA.can_review && m.status !== 'confirmed' && m.status !== 'rejected'
    ? `<button class="ok" data-review="${esc(m.map_id)}" data-action="confirm">確認</button>
       <button class="no" data-review="${esc(m.map_id)}" data-action="reject">否決</button>` : '';
  const undo = DATA.can_review && m.status === 'rejected'
    ? `<button class="ok" data-review="${esc(m.map_id)}" data-action="confirm">改為確認</button>` : '';
  return `<div class="match">
    <div><span class="hn" translate="no">TCMSP #${esc(m.herb_id)}　${esc(m.herb_cn_name || '')}</span>
      <span class="pill st-${esc(m.status)}">${esc(STATUS_CN[m.status] || m.status)}</span> ${flags}</div>
    <div class="en">${esc(m.herb_en_name || '')}</div>
    ${nameCompare(m.name_compare)}
    <div class="small"><span>比對依據：</span>${method}${m.note ? `　·　<span>備註：</span>${esc(m.note)}` : ''}</div>
    <div class="acts">
      <button data-mol="${esc(m.herb_id)}">展開成分（MOL）</button>
      <a class="ext" href="tcmsp_query.html?herb=${encodeURIComponent(m.herb_id)}">中藥關聯查詢站 →</a>
      <a class="ext" href="herb-ingredients.html?herb=${encodeURIComponent(m.herb_id)}">活性成分與結構 →</a>
      ${acts}${undo}
    </div>
    <div class="mol" id="mol-${esc(m.herb_id)}" style="display:none;"></div>
  </div>`;
}

function renderThp(d) {
  const amend = d.amendment ? `
    <div class="amend">
      <h3>114-07-30 修正公告（與下方原文不同處以此為準）</h3>
      <div class="note"><b>修正說明：</b><span translate="no">${esc(d.amendment.note)}</span></div>
      <div class="pre" translate="no">${esc(d.amendment.content)}</div>
    </div>` : '';
  const official = d.official_url
    ? `<a class="ext" href="${esc(d.official_url)}" target="_blank" rel="noopener">臺灣中藥典資訊網官方頁（項次 ${esc(d.site_no)}）↗</a>`
    : '<span class="na">濃縮製劑沒有資訊網單獨頁面</span>';
  const rel = [
    d.parent ? `<span>所屬藥材：</span><a class="ext" href="#" data-goto="${d.parent.seq}">${esc(d.parent.site_no)} ${esc(d.parent.name_zh)}</a>` : '',
    d.children.length ? `<span>飲片：</span>${d.children.map((c) => `<a class="ext" href="#" data-goto="${c.seq}">${esc(c.site_no)} ${esc(c.name_zh)}</a>`).join('、')}` : '',
  ].filter(Boolean).join('　·　');

  const cnSide = d.kind === 'preparation'
    ? '<div class="small">濃縮製劑為複方或單方製劑，不與 TCMSP 藥材比對。</div>'
    : (d.matches.length
      ? d.matches.map(matchCard).join('')
      : '<div class="small">沒有對到任何 TCMSP 藥材——可能 TCMSP（中國藥典 2010 收載品項）未收載，或名稱與學名都不同。</div>');
  const manual = DATA.can_review && d.kind !== 'preparation' ? `
    <div class="manual"><span>人工指定 TCMSP 藥材編號</span>
      <input type="number" id="manualHerb" min="1" placeholder="例：336" />
      <button id="manualBtn">指定</button></div>` : '';

  const rows = [
    ['中文名', esc(d.name_zh)],
    ['拉丁生藥名', d.latin_name ? `<span class="latin">${esc(d.latin_name)}</span>` : '<span class="na">—</span>'],
    ['英文名', esc(d.en_name || '—')],
    ...FIELD_LABELS.map(([k, label]) => {
      let v = d.fields[k];
      let html = v ? `<div class="pre">${esc(v)}</div>` : '<span class="na">（本品項未列此欄）</span>';
      if (k === 'origin' && d.origin_inherited) html = `<div class="small">（飲片，同原藥材）</div>${html}`;
      return [label, html, CLINICAL.has(k)];
    }),
  ];
  if (d.extra) {
    Object.entries(d.extra).forEach(([k, v]) => rows.push([EXTRA_LABELS[k] || k, `<div class="pre">${esc(v)}</div>`]));
  }

  $('detail').innerHTML = `
    <h2><span class="no">${esc(d.site_no || '—')}</span><span translate="no">${esc(d.name_zh)}</span>
      <span class="pill k-${esc(d.kind)}">${esc(KIND_CN[d.kind] || d.kind)}</span>
      ${d.amendment ? '<span class="pill amd">有修正公告</span>' : ''}</h2>
    <div class="meta"><span class="latin">${esc(d.latin_name || '')}</span>　${esc(d.en_name || '')}
      ${d.book_page ? `　·　<span>原書第 ${esc(d.book_page)} 頁</span>` : ''}</div>
    <div class="meta">${official}${rel ? '　·　' + rel : ''}</div>
    ${amend}
    <div class="cmp">
      <div class="card tw"><h3>臺灣中藥典第四版</h3>
        <div><span>項次</span> <b>${esc(d.site_no || '—')}</b>　<span translate="no">${esc(d.name_zh)}</span></div>
        <div class="latin">${esc(d.latin_name || '')}</div>
        <div class="small" style="margin-top:6px;"><span>基原學名：</span>${d.species.length ? d.species.map((s) => `<i>${esc(s)}</i>`).join('、') : '<span>（無，礦物或製劑）</span>'}</div>
      </div>
      <div class="card cn"><h3>${esc(d.cn_side_label)}</h3>
        ${cnSide}${manual}
      </div>
    </div>
    <table class="f"><tbody>
      ${rows.map(([l, h, clin]) => `<tr${clin ? ' class="clinical"' : ''}><th>${esc(l)}</th><td translate="no">${h}</td></tr>`).join('')}
    </tbody></table>
    <div class="disclaimer" data-i18n-block>${esc(d.disclaimer)}</div>`;
}

/* ---------------------------------------------------------------- 詳細：只在 TCMSP 的藥材 */
async function selectHerb(herbId) {
  current = { type: 'herb', herb_id: herbId };
  renderList();
  $('emptyState').style.display = 'none';
  $('detail').style.display = '';
  const h = CN_ONLY.find((x) => x.herb_id === herbId) || { herb_id: herbId };
  $('detail').innerHTML = `
    <h2><span class="no">TCMSP #${esc(h.herb_id)}</span>${esc(h.herb_cn_name || '')}</h2>
    <div class="meta">${esc(h.herb_pinyin || '')}　${esc(h.herb_en_name || '')}</div>
    <div class="card cn"><h3>${esc(DATA.cn_side_label)}</h3>
      <div class="small">臺灣中藥典第四版沒有對應品項（或比對已被否決）。</div>
      <div class="match">
        <div class="acts">
          <button data-mol="${esc(h.herb_id)}">展開成分（MOL）</button>
          <a class="ext" href="tcmsp_query.html?herb=${encodeURIComponent(h.herb_id)}">中藥關聯查詢站 →</a>
          <a class="ext" href="herb-ingredients.html?herb=${encodeURIComponent(h.herb_id)}">活性成分與結構 →</a>
        </div>
        <div class="mol" id="mol-${esc(h.herb_id)}" style="display:none;"></div>
      </div>
    </div>
    <div class="disclaimer" data-i18n-block>${esc(DATA.disclaimer)}</div>`;
}

/* ---------------------------------------------------------------- 成分（MOL）展開 */
async function toggleMol(herbId, btn) {
  const box = $(`mol-${herbId}`);
  if (!box) return;
  if (box.style.display !== 'none') { box.style.display = 'none'; return; }
  box.style.display = '';
  if (!molCache.has(herbId)) {
    box.innerHTML = '<div class="na" style="padding:8px;">載入中…</div>';
    try { molCache.set(herbId, await api(`/pharmacopeia/tcmsp-herbs/${herbId}/ingredients`)); } catch (err) {
      box.innerHTML = `<div class="na" style="padding:8px;">載入失敗：${esc(err.message || err)}</div>`; return;
    }
  }
  const r = molCache.get(herbId);
  box.innerHTML = `<table><thead><tr><th>Mol ID</th><th>成分名稱（TCMSP 英文原名）</th><th>OB %</th><th>DL</th><th>活性</th></tr></thead><tbody>
    ${r.items.map((i) => `<tr><td><a class="ext" href="tcmsp_query.html?herb=${encodeURIComponent(herbId)}&mol=${encodeURIComponent(i.mol_id)}">${esc(i.mol_id)}</a></td>
      <td>${esc(i.molecule_name || '—')}</td><td class="num">${esc(i.ob ?? '—')}</td><td class="num">${esc(i.dl ?? '—')}</td>
      <td>${i.active ? '<span class="act">✓</span>' : ''}</td></tr>`).join('') || '<tr><td colspan="5" class="na">TCMSP 沒有這味藥的成分資料</td></tr>'}
  </tbody></table>
  <div class="small" style="padding:6px 8px;">共 ${esc(r.total)} 個成分，其中 ${esc(r.active)} 個為活性成分（OB ≥ ${esc(r.thresholds.ob_min)}%、DL ≥ ${esc(r.thresholds.dl_min)}）</div>`;
  if (btn) btn.blur();
}

/* ---------------------------------------------------------------- 審核 */
async function review(mapId, action) {
  const note = action === 'reject' ? (prompt('否決原因（選填）') || '') : '';
  try {
    await api(`/pharmacopeia/map/${encodeURIComponent(mapId)}/review`, { method: 'POST', body: JSON.stringify({ action, note: note || null }) });
  } catch (err) { alert(`沒有成功：${err.message || err}`); return; }
  await reloadKeep();
}
async function manualAssign() {
  const herbId = parseInt(($('manualHerb') || {}).value, 10);
  if (!herbId || !current || current.type !== 'thp') return;
  try {
    await api('/pharmacopeia/map', { method: 'POST', body: JSON.stringify({ thp_seq: current.seq, herb_id: herbId }) });
  } catch (err) { alert(`沒有成功：${err.message || err}`); return; }
  await reloadKeep();
}
async function reloadKeep() {
  const keep = current;
  await load();
  if (keep && keep.type === 'thp') selectThp(keep.seq);
}

/* ---------------------------------------------------------------- 事件 */
$('search').addEventListener('input', renderList);
$('filters').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-f]');
  if (!b) return;
  filter = b.dataset.f;
  renderList();
});
$('kpi').addEventListener('click', (e) => {
  const b = e.target.closest('[data-f]');
  if (!b) return;
  filter = b.dataset.f;
  renderList();
});
$('list').addEventListener('click', (e) => {
  const r = e.target.closest('.row');
  if (!r) return;
  if (r.dataset.seq) selectThp(parseInt(r.dataset.seq, 10));
  else if (r.dataset.herb) selectHerb(parseInt(r.dataset.herb, 10));
});
$('detail').addEventListener('click', (e) => {
  const mol = e.target.closest('[data-mol]');
  if (mol) { toggleMol(parseInt(mol.dataset.mol, 10), mol); return; }
  const rv = e.target.closest('[data-review]');
  if (rv) { review(rv.dataset.review, rv.dataset.action); return; }
  const go = e.target.closest('[data-goto]');
  if (go) { e.preventDefault(); selectThp(parseInt(go.dataset.goto, 10)); return; }
  if (e.target.id === 'manualBtn') manualAssign();
});

QSUI.collapsiblePanel({ panel: 'listPanel', key: 'tcm_pc_panel_collapsed', label: '品項清單' });

$('platformLogout').addEventListener('click', async (e) => {
  e.preventDefault();
  try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: 'POST' }); } catch (err) { /* 照樣清 */ }
  clearSession();
  window.location.href = 'index.html';
});

const langSel = $('uiLangSelect');
langSel.addEventListener('change', () => {
  const lang = langSel.value;
  try { localStorage.setItem('siteLang', lang); } catch (e) { /* 私密視窗 */ }
  window.applySiteLanguage(lang);
});

(async function init() {
  try {
    const saved = localStorage.getItem('siteLang');
    if (saved) { langSel.value = saved; window.applySiteLanguage(saved); }
  } catch (e) { /* 預設繁體 */ }
  try {
    await load();
  } catch (err) {
    $('emptyState').textContent = `載入失敗：${err.message || err}`;
    return;
  }
  if (!DATA.items.length) {
    $('emptyState').textContent = '臺灣中藥典資料尚未載入（伺服器啟動時會自動載入，請稍後重新整理）。';
    return;
  }
  const q = new URLSearchParams(location.search).get('item');
  let seq = null;
  if (q) {
    const hit = q.startsWith('seq') ? DATA.items.find((i) => String(i.seq) === q.slice(3)) : DATA.items.find((i) => i.site_no === q.padStart(3, '0'));
    if (hit) seq = hit.seq;
  }
  selectThp(seq || DATA.items[0].seq);
})();
