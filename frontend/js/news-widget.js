/**
 * Dashboard「每日重點新聞」小工具（功能代碼 F0-13-6）
 *
 * 中藥與腫瘤｜10 個權威官方來源，每日 04:00（台北）自動彙整當日 10 篇。
 * 使用者可勾選「保留」，管理者於「公告管理 → 新聞管理」分頁維護。
 *
 * ⚠️ 安全性：新聞內容來自第三方網站（WHO / NCI / PubMed / 中國官方站等），
 *    標題與摘要一律經過 escNews() 跳脫後才寫入 DOM。
 *    這點與站內自建的公告不同，公告是管理者自己輸入的內容。
 */

(function () {
  const CARD_ID = "cardNews";

  const EVIDENCE_LABEL = {
    policy_global: "政策與全球標準",
    clinical_evidence: "癌症臨床與實證",
    research_policy: "研究政策與資助",
    natural_product: "天然物研究與安全",
    literature_index: "學術文獻索引",
    trial_registry: "臨床試驗登錄",
    cancer_center: "癌症中心臨床實務",
    herb_safety: "草藥安全與交互作用",
    national_policy: "國家衛生政策",
    tcm_policy: "中醫藥國家政策",
  };

  // 對應追蹤指南「正確解讀方式」表，顯示為 title tooltip
  const EVIDENCE_CAVEAT = {
    policy_global: "代表主管機關方向，不等同於特定中藥已通過療效驗證。",
    clinical_evidence: "優先查看原始研究設計，並分清治療腫瘤與改善副作用。",
    research_policy: "代表研究方向與資助，不代表已有臨床療效結論。",
    natural_product: "著重原料鑑別、批次一致性、毒理與交互作用。",
    literature_index: "文獻可被檢索不保證研究品質，仍需做偏差風險評估。",
    trial_registry: "代表正在或曾經研究；應查看是否完成、結果與不良事件。",
    cancer_center: "優先查看原始研究設計，並分清治療腫瘤與改善副作用。",
    herb_safety: "主要用於安全與交互作用警示，不應自動轉換成處方建議。",
    national_policy: "政策支持與個別方劑的臨床療效證明必須分開解讀。",
    tcm_policy: "政策支持與個別方劑的臨床療效證明必須分開解讀。",
  };

  const TAG_LABEL = {
    safety: "安全訊號", preclinical: "臨床前", human_evidence: "人體證據",
    recruiting: "招募中", completed_trial: "試驗已完成", halted_trial: "試驗已終止",
  };

  const ENTITY_LABEL = { herb: "藥材", ingredient: "成分", target: "靶點", disease: "疾病" };

  let newsData = null;
  let newsFilter = "all";
  let newsViewMode = "daily"; // "daily"（本日精選）｜"archive"（歷史瀏覽，對接 /news/archive）

  function escNews(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtNewsDate(iso) {
    if (!iso) return "日期未提供";
    return new Date(iso).toLocaleDateString("zh-Hant",
      { year: "numeric", month: "2-digit", day: "2-digit" });
  }

  function entityChip(e) {
    const label = `${ENTITY_LABEL[e.type] || e.type}：${escNews(e.name)}`;
    const title = e.matched_text ? `原文命中「${escNews(e.matched_text)}」` : "";
    if (e.link) {
      return `<a class="news-chip news-chip-${e.type}" href="${escNews(e.link)}" title="${title}">${label}</a>`;
    }
    if (e.type === "target" && e.tar_id) {
      // 靶點沒有專屬查詢站頁面，改開彈窗顯示關聯藥材與疾病
      return `<button type="button" class="news-chip news-chip-target"
                title="${title}" onclick="openNewsTarget('${escNews(e.tar_id)}')">${label}</button>`;
    }
    return `<span class="news-chip news-chip-${e.type}" title="${title}">${label}</span>`;
  }

  function renderNewsItem(it) {
    const badges = [];
    if (it.rank) badges.push(`<span class="news-rank">#${it.rank}</span>`);
    if (it.is_pinned) badges.push(`<span class="news-badge news-badge-info">置頂</span>`);
    if (it.is_embargoed) badges.push(`<span class="news-badge news-badge-info"
      title="未達正式解禁時間，僅限有權限者提前查看">未解禁・提前存取</span>`);
    badges.push(`<span class="news-badge ${it.is_safety_signal ? "news-badge-warn" : ""}"
                   title="${escNews(EVIDENCE_CAVEAT[it.evidence_level] || "")}"
                 >${escNews(EVIDENCE_LABEL[it.evidence_level] || it.evidence_level)}</span>`);
    (it.tags || []).forEach((t) => {
      const cls = t === "safety" ? "news-badge-warn" : (t === "preclinical" ? "news-badge-muted" : "");
      badges.push(`<span class="news-badge ${cls}">${escNews(TAG_LABEL[t] || t)}</span>`);
    });

    const entities = (it.entities || []).map(entityChip).join("");
    const meta = [
      `<a href="${escNews(it.source.homepage)}" target="_blank" rel="noopener">${escNews(it.source.name_zh)}</a>`,
      fmtNewsDate(it.published_at),
      it.journal ? escNews(it.journal) : "",
      it.study_design ? escNews(it.study_design) : "",
      it.external_id ? `<code>${escNews(it.external_id)}</code>` : "",
      it.doi ? `<a href="https://doi.org/${encodeURIComponent(it.doi)}" target="_blank" rel="noopener">DOI</a>` : "",
      it.bookmark_count > 0 ? `${it.bookmark_count} 人保留` : "",
    ].filter(Boolean).join(" ・ ");

    return `
      <div class="news-item" data-id="${escNews(it.id)}">
        <label class="news-keep">
          <input type="checkbox" ${it.is_bookmarked ? "checked" : ""}
                 onchange="toggleNewsKeep('${escNews(it.id)}', this)">
          <span>保留</span>
        </label>
        <div class="news-body">
          <div class="news-badges">${badges.join("")}</div>
          <div class="news-title">
            <a href="${escNews(it.url)}" target="_blank" rel="noopener">${escNews(it.title_zh || it.title)}</a>
          </div>
          ${it.title_zh ? `<div class="news-orig">${escNews(it.title)}</div>` : ""}
          ${newsSummaryBlock(it)}
          ${it.caveat_zh ? `<div class="news-caveat">解讀注意：${escNews(it.caveat_zh)}</div>` : ""}
          ${entities ? `<div class="news-entities">${entities}</div>` : ""}
          <div class="news-meta">${meta}</div>
        </div>
      </div>`;
  }

  function applyNewsFilter(items) {
    if (newsFilter === "safety") return items.filter((i) => i.is_safety_signal);
    if (newsFilter === "human") return items.filter((i) => (i.tags || []).includes("human_evidence"));
    if (newsFilter === "kept") return items.filter((i) => i.is_bookmarked);
    return items;
  }

  // 目前的全站語系（tw/cn/en/ko）。site-lang.js 還沒初始化完就先當繁中，
  // 摘要只是輔助資訊，不值得為了它把整張卡片的載入卡住。
  function newsSiteLang() {
    try {
      return (window.getCurrentSiteLanguage && window.getCurrentSiteLanguage()) || "tw";
    } catch (e) { return "tw"; }
  }

  const NEWS_SUMMARY_LABEL = {
    tw: "中文摘要", cn: "中文摘要", en: "English summary", ko: "한국어 요약",
  };

  // 原文與譯文並列。
  //
  // 為什麼要並列而不是只顯示譯文：這是科研查證用途，讀者需要能立刻對照原文用字，
  // 尤其是劑量、樣本數、統計顯著性這類「翻譯一旦失準就會誤導」的地方。
  // 只顯示譯文等於逼使用者每次都得點開原文連結才能確認。
  //
  // 右欄沒有內容時，刻意寫明「為什麼沒有」，而不是默默拿英文原文填進去——
  // 那會讓使用者以為系統把英文當成中文摘要，反而更難查出問題。
  function newsSummaryBlock(it) {
    const lang = newsSiteLang();
    const label = NEWS_SUMMARY_LABEL[lang] || "摘要";
    const original = it.abstract || "";
    // 中文語系下，若收集時產的 summary_zh 真的是中文（有 API key 時才會是），
    // 就先拿它墊著，不必等隨選摘要補上。用「含不含中日韓文字」判斷，
    // 是因為沒有 API key 時 summary_zh 其實是英文原文的截斷，拿它當中文摘要會誤導。
    const zhFallback = (lang === "tw" || lang === "cn") &&
      it.summary_zh && /[\u4e00-\u9fff]/.test(it.summary_zh) ? it.summary_zh : "";
    const translated = it.summary || zhFallback;
    const notAi = it.summary && it.summary_is_ai === false;

    const right = translated
      ? `<div class="news-col-body">${escNews(translated)}</div>` +
        (notAi ? `<div class="news-col-note">未經 AI 翻譯，這是直接截斷原文的結果（後台未設定 ANTHROPIC_API_KEY）。</div>` : "")
      : `<div class="news-col-body is-empty">尚未產生。請確認後台已設定 ANTHROPIC_API_KEY，並於「摘要與模組設定」按重產。</div>`;

    // 沒有原文可對照時（部分公告類來源沒有內文），就不要硬擠出一個空白左欄
    if (!original) {
      return `<div class="news-summary" data-summary-for="${escNews(it.id)}">${right}</div>`;
    }
    return `<div class="news-cols" data-summary-for="${escNews(it.id)}">
        <div>
          <div class="news-col-label">原文摘要</div>
          <div class="news-col-body">${escNews(original)}</div>
        </div>
        <div>
          <div class="news-col-label">${escNews(label)}</div>
          ${right}
        </div>
      </div>`;
  }

  // 畫面先出來，缺的語系摘要之後再補。
  //
  // 為什麼不在 /news/daily 裡順便產：那支端點每次開 Dashboard 都會打到，
  // 若順手產摘要，第一個開頁的人就要等 N 次 AI 呼叫才看得到新聞。
  // 這裡改成非同步補件，補不到就維持原本的繁中摘要，不影響閱讀。
  async function fillMissingSummaries(items) {
    const lang = newsSiteLang();
    const need = items.filter((i) => !i.summary).map((i) => i.id).slice(0, 12);
    if (!need.length) return;
    try {
      const r = await api("/news/summaries", {
        method: "POST",
        body: JSON.stringify({ article_ids: need, lang }),
      });
      if (!r || r.enabled === false) return;
      Object.entries(r.summaries || {}).forEach(([id, v]) => {
        if (!v || !v.summary) return;
        const hit = items.find((x) => x.id === id);
        if (hit) {
          hit.summary = v.summary;          // 存回記憶體，切換篩選重繪時就不必再要一次
          hit.summary_is_ai = !!v.is_ai;
        }
        const el = document.querySelector(`[data-summary-for="${CSS.escape(id)}"]`);
        if (!el || !hit) return;
        // 整塊重繪而不是只改文字：右欄可能要從「尚未產生」的提示切換成正文＋註記，
        // 結構不同，逐一改文字節點反而更容易漏掉狀態。
        el.outerHTML = newsSummaryBlock(hit);
      });
    } catch (e) { /* 補不到就算了，原本的繁中摘要仍在 */ }
  }

  function renderNews() {
    const body = document.getElementById("newsList");
    if (!body || !newsData) return;

    const items = applyNewsFilter(newsData.items || []);
    if (!items.length) {
      const emptyMsg = (newsData.items || []).length > 0
        ? "目前篩選條件下沒有項目。"
        : (newsViewMode === "archive"
            ? "這個條件下沒有歷史新聞。"
            : "尚未產生重點新聞。每日清晨 4:00（台北時間）自動收集。");
      body.innerHTML = `<div class="news-empty">${emptyMsg}</div>`;
      return;
    }
    body.innerHTML = items.map(renderNewsItem).join("");
    fillMissingSummaries(items);
  }

  function renderNewsHeader() {
    const sel = document.getElementById("newsDateSelect");
    if (sel && newsData) {
      sel.innerHTML = (newsData.available_dates || []).map(
        (d) => `<option value="${escNews(d)}" ${d === newsData.digest_date ? "selected" : ""}>${escNews(d)}</option>`
      ).join("");
      sel.style.display = (newsData.available_dates || []).length ? "" : "none";
    }
    const safety = (newsData.items || []).filter((i) => i.is_safety_signal).length;
    const badge = document.getElementById("newsSafetyBadge");
    if (badge) {
      badge.textContent = safety ? `${safety} 則安全訊號` : "";
      badge.style.display = safety ? "" : "none";
    }
    const dis = document.getElementById("newsDisclaimer");
    if (dis && newsData.disclaimer) dis.textContent = "免責聲明：" + newsData.disclaimer;
  }

  window.loadNewsWidget = async function (date) {
    const body = document.getElementById("newsList");
    if (!body) return;
    body.innerHTML = "載入中...";
    try {
      const qs = new URLSearchParams({ lang: newsSiteLang() });
      if (date) qs.set("date", date);
      newsData = await api("/news/daily?" + qs.toString());
      renderNewsHeader();
      renderNews();
    } catch (err) {
      body.innerHTML = `<div class="news-empty">載入失敗：${escNews(err.message)}</div>`;
    }
  };

  // 歷史瀏覽（對接 /news/archive，目前全站唯一的呼叫端）。跟本日精選共用
  // renderNewsItem()/entityChip()/toggleNewsKeep()，回傳的文章物件形狀一致，不需要另外處理。
  window.loadNewsArchive = async function () {
    const body = document.getElementById("newsList");
    if (!body) return;
    body.innerHTML = "載入中...";
    const days = parseInt(document.getElementById("newsArchiveDays")?.value, 10) || 30;
    const safetyOnly = document.getElementById("newsArchiveSafety")?.checked || false;
    const q = document.getElementById("newsArchiveQ")?.value.trim() || "";
    const params = new URLSearchParams({ days: String(days), limit: "50", lang: newsSiteLang() });
    if (safetyOnly) params.set("safety_only", "true");
    if (q) params.set("q", q);
    try {
      newsData = await api("/news/archive?" + params.toString());
      const badge = document.getElementById("newsSafetyBadge");
      if (badge) badge.style.display = "none";  // 「今日安全訊號數」對歷史瀏覽沒有意義，不沿用
      renderNews();
    } catch (err) {
      body.innerHTML = `<div class="news-empty">載入失敗：${escNews(err.message)}</div>`;
    }
  };

  window.applyNewsArchiveFilter = function () {
    window.loadNewsArchive();
  };

  window.showNewsDaily = function () {
    if (newsViewMode === "daily") return;
    newsViewMode = "daily";
    newsFilter = "all";
    document.getElementById("newsModeDailyBtn")?.classList.add("active");
    document.getElementById("newsModeArchiveBtn")?.classList.remove("active");
    document.getElementById("newsDailyBar").style.display = "";
    document.getElementById("newsArchiveBar").style.display = "none";
    window.loadNewsWidget();
  };

  window.showNewsArchive = function () {
    if (newsViewMode === "archive") return;
    newsViewMode = "archive";
    newsFilter = "all";
    // 重置本日精選那排的分類篩選按鈕外觀，這樣下次切回本日精選時是從「全部」開始，
    // 不會卡在切去歷史瀏覽之前選的分類上
    document.querySelectorAll("#newsDailyBar .news-filter").forEach((b) => b.classList.remove("active"));
    document.querySelector("#newsDailyBar .news-filter")?.classList.add("active");
    document.getElementById("newsModeArchiveBtn")?.classList.add("active");
    document.getElementById("newsModeDailyBtn")?.classList.remove("active");
    document.getElementById("newsDailyBar").style.display = "none";
    document.getElementById("newsArchiveBar").style.display = "";
    window.loadNewsArchive();
  };

  window.setNewsFilter = function (key, btn) {
    newsFilter = key;
    document.querySelectorAll("#newsDailyBar .news-filter").forEach((b) => b.classList.remove("active"));
    if (btn) btn.classList.add("active");
    renderNews();
  };

  window.onNewsDateChange = function (sel) {
    window.loadNewsWidget(sel.value);
  };

  window.toggleNewsKeep = async function (articleId, checkbox) {
    const next = checkbox.checked;
    checkbox.disabled = true;
    try {
      if (next) {
        await api("/news/bookmarks", { method: "POST", body: JSON.stringify({ article_id: articleId }) });
      } else {
        await api(`/news/bookmarks/${encodeURIComponent(articleId)}`, { method: "DELETE" });
      }
      const item = (newsData.items || []).find((i) => i.id === articleId);
      if (item) {
        item.is_bookmarked = next;
        item.bookmark_count = Math.max(0, (item.bookmark_count || 0) + (next ? 1 : -1));
      }
      if (newsFilter === "kept") renderNews();
    } catch (err) {
      checkbox.checked = !next;   // 回滾
      alert("保留設定失敗：" + err.message);
    } finally {
      checkbox.disabled = false;
    }
  };

  window.openNewsTarget = async function (tarId) {
    const modal = document.getElementById("newsTargetModal");
    const body = document.getElementById("newsTargetBody");
    const title = document.getElementById("newsTargetTitle");
    if (!modal) return;
    title.textContent = "靶點：" + tarId;
    body.innerHTML = "載入中...";
    modal.style.display = "flex";
    try {
      const d = await api(`/news/targets/${encodeURIComponent(tarId)}`);
      title.textContent = `靶點：${d.target_name || d.tar_id}`;
      const herbs = (d.herbs || []).map(
        (h) => `<a class="news-chip news-chip-herb" href="${escNews(h.link)}">${escNews(h.name)}</a>`).join("") || "（無關聯藥材）";
      const diseases = (d.diseases || []).map(
        (x) => `<a class="news-chip news-chip-disease" href="${escNews(x.link)}">${escNews(x.name)}</a>`).join("") || "（無關聯疾病）";
      body.innerHTML = `
        <p style="font-size:12.5px;color:#6b7a70;">
          ${d.drugbank_id ? "DrugBank：" + escNews(d.drugbank_id) + "　" : ""}
          ${d.kegg ? "KEGG：" + escNews(d.kegg) : ""}
        </p>
        <h4 style="margin:12px 0 6px;font-size:13px;">關聯藥材（最多 40 筆）</h4>
        <div class="news-entities">${herbs}</div>
        <h4 style="margin:14px 0 6px;font-size:13px;">關聯疾病（最多 40 筆）</h4>
        <div class="news-entities">${diseases}</div>`;
    } catch (err) {
      body.innerHTML = `載入失敗：${escNews(err.message)}`;
    }
  };

  window.closeNewsTarget = function () {
    const m = document.getElementById("newsTargetModal");
    if (m) m.style.display = "none";
  };

  // 自動初始化。卡片的顯示/隱藏由 dashboard.js 的 applyWidgetVisibility()
  // 依權限矩陣控制，這裡只負責在卡片存在時載入資料。
  function init() {
    if (document.getElementById(CARD_ID)) window.loadNewsWidget();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
