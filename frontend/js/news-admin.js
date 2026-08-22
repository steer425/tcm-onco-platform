/**
 * 新聞管理（公告管理頁的分頁，功能代碼 F0-19）
 *
 * 包含：文章查詢、軟刪除+註記、還原、來源健康度、收集執行紀錄。
 * 管理者操作一律由後端寫進全站稽核紀錄（AuditLog），可於「稽核 / 登入紀錄」頁查詢。
 *
 * ⚠️ 新聞內容來自第三方網站，一律經 escNewsAdmin() 跳脫後才寫入 DOM。
 */

(function () {
  const EVIDENCE_LABEL = {
    policy_global: "政策與全球標準", clinical_evidence: "癌症臨床與實證",
    research_policy: "研究政策與資助", natural_product: "天然物研究與安全",
    literature_index: "學術文獻索引", trial_registry: "臨床試驗登錄",
    cancer_center: "癌症中心臨床實務", herb_safety: "草藥安全與交互作用",
    national_policy: "國家衛生政策", tcm_policy: "中醫藥國家政策",
  };

  let nPage = 1;
  let nRows = [];
  let nSelected = new Set();
  let sourcesLoaded = false;
  let runsLoaded = false;
  let nSourceRows = [];
  const SENSITIVE_CONFIG_KEYS = new Set(["api_key", "apikey", "secret", "token", "password"]);
  const isSensitiveKey = (key) => SENSITIVE_CONFIG_KEYS.has(String(key).toLowerCase());

  function escNewsAdmin(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function showMsg(text) {
    const el = document.getElementById("nMsg");
    if (!el) return;
    el.textContent = text;
    el.style.display = text ? "" : "none";
  }

  // ---------- 分頁切換 ----------
  function initTabs() {
    const tabs = document.querySelectorAll(".tabs button[data-tab]");
    if (!tabs.length) return;
    tabs.forEach((btn) => {
      btn.addEventListener("click", () => {
        tabs.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const key = btn.dataset.tab;
        ["ann", "news", "newsSources", "newsRuns"].forEach((k) => {
          const panel = document.getElementById("tab-" + k);
          if (panel) panel.style.display = (k === key) ? "" : "none";
        });
        if (key === "news" && !nRows.length) newsAdminSearch(1);
        if (key === "newsSources" && !sourcesLoaded) loadNewsSources();
        if (key === "newsRuns" && !runsLoaded) loadNewsRuns();
      });
    });
  }

  // ---------- 文章查詢 ----------
  window.newsAdminSearch = async function (page) {
    nPage = page || 1;
    const view = document.getElementById("nView").value;
    const body = {
      q: document.getElementById("nQ").value.trim() || null,
      only_deleted: view === "deleted",
      include_deleted: view === "all",
      date_from: document.getElementById("nFrom").value || null,
      date_to: document.getElementById("nTo").value || null,
      is_safety_signal: document.getElementById("nSafety").checked ? true : null,
      page: nPage,
      page_size: 50,
      sort: "collected_desc",
    };
    try {
      const data = await api("/news/admin/articles/search", {
        method: "POST", body: JSON.stringify(body),
      });
      nRows = data.items || [];
      nSelected = new Set();
      document.getElementById("nTotal").textContent = data.total;
      document.getElementById("nPage").textContent = nPage;
      document.getElementById("nSelected").textContent = 0;
      const checkAll = document.getElementById("nCheckAll");
      if (checkAll) checkAll.checked = false;
      renderNewsTable();
      showMsg("");
    } catch (err) {
      showMsg("查詢失敗：" + err.message);
    }
  };

  function renderNewsTable() {
    const tbody = document.getElementById("nTableBody");
    tbody.innerHTML = "";
    nRows.forEach((a) => {
      const statusText = a.is_deleted ? "已刪除"
        : (a.status === "archived" ? "已封存" : "正常");
      const statusCls = a.is_deleted ? "status-off"
        : (a.status === "archived" ? "status-expired" : "status-live");
      const digest = (a.in_digest_dates || []).length
        ? `<div class="news-admin-sub">曾入選 ${escNewsAdmin(a.in_digest_dates[0])}</div>` : "";
      const note = a.delete_note
        ? `<div class="news-admin-note">刪除註記：${escNewsAdmin(a.delete_note)}</div>` : "";
      const safety = a.is_safety_signal
        ? ` <span class="status-pill status-off">安全</span>` : "";
      const embargoed = a.is_embargoed
        ? ` <span class="status-pill status-scheduled" title="${
            a.embargo_until ? "預計解禁：" + escNewsAdmin(a.embargo_until.slice(0, 10)) : "尚未設定解禁時間"
          }">未解禁</span>` : "";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input type="checkbox" data-id="${escNewsAdmin(a.id)}" onchange="newsAdminToggleRow(this)"></td>
        <td>
          <a href="${escNewsAdmin(a.url)}" target="_blank" rel="noopener">${escNewsAdmin(a.title_zh || a.title)}</a>${safety}${embargoed}
          ${digest}${note}
        </td>
        <td style="font-size:12px;">${escNewsAdmin(a.source.name_zh)}</td>
        <td style="font-size:12px;">${escNewsAdmin(EVIDENCE_LABEL[a.evidence_level] || a.evidence_level)}</td>
        <td style="font-size:12px;">${escNewsAdmin((a.collected_at || "").slice(0, 10))}</td>
        <td style="font-size:12px;">${a.bookmark_count || 0}</td>
        <td><span class="status-pill ${statusCls}">${statusText}</span></td>`;
      tbody.appendChild(tr);
    });
  }

  window.newsAdminToggleRow = function (cb) {
    const id = cb.dataset.id;
    if (cb.checked) nSelected.add(id); else nSelected.delete(id);
    document.getElementById("nSelected").textContent = nSelected.size;
  };

  window.newsAdminToggleAll = function (cb) {
    document.querySelectorAll("#nTableBody input[type=checkbox]").forEach((c) => {
      c.checked = cb.checked;
      if (cb.checked) nSelected.add(c.dataset.id); else nSelected.delete(c.dataset.id);
    });
    document.getElementById("nSelected").textContent = nSelected.size;
  };

  window.newsAdminPage = function (delta) {
    const next = nPage + delta;
    if (next < 1) return;
    newsAdminSearch(next);
  };

  // ---------- 刪除 / 還原 ----------
  window.newsAdminDelete = async function (dryRun) {
    const note = document.getElementById("nNote").value.trim();
    if (!note) { showMsg("請先填寫刪除註記（必填，會寫入稽核紀錄）"); return; }

    const olderRaw = document.getElementById("nOlderThan").value;
    const useIds = nSelected.size > 0;
    if (!useIds && !olderRaw) {
      showMsg("請勾選要刪除的新聞，或填寫「刪除幾天前」的條件");
      return;
    }

    const body = {
      note: note,
      dry_run: !!dryRun,
      exclude_bookmarked: document.getElementById("nProtect").checked,
    };
    if (useIds) body.article_ids = Array.from(nSelected);
    else body.older_than_days = parseInt(olderRaw, 10);

    if (!dryRun && !confirm(
      useIds ? `確定要刪除勾選的 ${nSelected.size} 則新聞？` :
               `確定要刪除 ${olderRaw} 天前的新聞？`)) return;

    try {
      const r = await api("/news/admin/articles/soft-delete", {
        method: "POST", body: JSON.stringify(body),
      });
      showMsg(r.message);
      if (!dryRun) {
        document.getElementById("nNote").value = "";
        await newsAdminSearch(nPage);
      }
    } catch (err) {
      showMsg("刪除失敗：" + err.message);
    }
  };

  window.newsAdminRestore = async function () {
    if (!nSelected.size) { showMsg("請先勾選要還原的新聞"); return; }
    try {
      const r = await api("/news/admin/articles/restore", {
        method: "POST",
        body: JSON.stringify({ article_ids: Array.from(nSelected),
                               note: document.getElementById("nNote").value.trim() || null }),
      });
      showMsg(r.message);
      await newsAdminSearch(nPage);
    } catch (err) {
      showMsg("還原失敗：" + err.message);
    }
  };

  // ---------- 來源健康度 ----------
  async function loadNewsSources() {
    const tbody = document.getElementById("nSourceBody");
    tbody.innerHTML = `<tr><td colspan="6">載入中...</td></tr>`;
    try {
      const rows = await api("/news/admin/sources");
      sourcesLoaded = true;
      nSourceRows = rows;
      tbody.innerHTML = "";
      rows.forEach((s) => {
        const state = s.last_error
          ? `<span style="color:#c0392b;">連續失敗 ${s.consecutive_failures} 次：${escNewsAdmin(String(s.last_error).slice(0, 90))}</span>`
          : `<span style="color:#2f6f4f;">最近成功 ${s.last_success_at ? escNewsAdmin(new Date(s.last_success_at).toLocaleString("zh-Hant")) : "—"}</span>`;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>
            <a href="${escNewsAdmin(s.homepage)}" target="_blank" rel="noopener">${escNewsAdmin(s.name_zh)}</a>
            <div class="news-admin-sub">${escNewsAdmin(s.name_en)}</div>
          </td>
          <td style="font-size:12px; text-transform:uppercase;">${escNewsAdmin(s.kind)}</td>
          <td style="font-size:12px;">${Number(s.weight).toFixed(2)}</td>
          <td style="font-size:12px;">${s.article_count}</td>
          <td style="font-size:12px;">${state}</td>
          <td><input type="checkbox" ${s.is_enabled ? "checked" : ""}
                     onchange="newsAdminToggleSource('${escNewsAdmin(s.slug)}', this)"></td>
          <td><button class="secondary" onclick="openSourceConfigModal('${escNewsAdmin(s.slug)}')">設定</button></td>`;
        tbody.appendChild(tr);
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7">載入失敗：${escNewsAdmin(err.message)}</td></tr>`;
    }
  }

  window.newsAdminToggleSource = async function (slug, cb) {
    const next = cb.checked;
    cb.disabled = true;
    try {
      await api("/news/admin/sources", {
        method: "PUT", body: JSON.stringify({ slug: slug, is_enabled: next }),
      });
    } catch (err) {
      cb.checked = !next;
      alert("更新失敗：" + err.message);
    } finally {
      cb.disabled = false;
    }
  };

  // ---------- 來源爬蟲設定（config）編輯 ----------
  // 敏感欄位（api_key 等）後端 GET 回應已經遮蔽成 "********"（見 app/routers/news_admin.py
  // 的 _redact_config()），這裡的密碼框一律從空白開始：使用者沒有輸入新值就不送這個欄位，
  // 絕對不能把畫面上顯示的遮蔽字串當作「新密鑰」送回後端，不然會把真正的金鑰洗成 "********"。
  window.openSourceConfigModal = function (slug) {
    const src = nSourceRows.find((s) => s.slug === slug);
    if (!src) return;
    document.getElementById("newsSourceConfigModal").dataset.slug = slug;
    document.getElementById("newsSourceConfigTitle").textContent = `來源設定：${src.name_zh}`;
    document.getElementById("newsSourceConfigMsg").textContent = "";

    const config = src.config || {};
    const keys = Object.keys(config);
    const rows = keys.map((key) => {
      const value = config[key];
      if (isSensitiveKey(key)) {
        return `
          <div class="cfg-row" style="margin-bottom:10px;">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">${escNewsAdmin(key)}
              <span style="font-weight:400;color:#8a958f;">（敏感欄位，目前為 ${escNewsAdmin(String(value))}，留空＝不修改）</span>
            </label>
            <input type="password" data-key="${escNewsAdmin(key)}" data-sensitive="1"
                   placeholder="輸入新值以更新，留空則沿用原本的金鑰" style="width:100%;">
          </div>`;
      }
      const isComplex = value !== null && typeof value === "object";
      const original = isComplex ? JSON.stringify(value, null, 2) : String(value);
      return `
        <div class="cfg-row" style="margin-bottom:10px;">
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">${escNewsAdmin(key)}</label>
          ${isComplex
            ? `<textarea data-key="${escNewsAdmin(key)}" data-json="1" data-original="${escNewsAdmin(original)}"
                        rows="3" style="width:100%;font-family:monospace;font-size:12px;">${escNewsAdmin(original)}</textarea>`
            : `<input type="text" data-key="${escNewsAdmin(key)}" data-original="${escNewsAdmin(original)}"
                      value="${escNewsAdmin(original)}" style="width:100%;">`}
        </div>`;
    }).join("");

    document.getElementById("newsSourceConfigFields").innerHTML =
      rows || `<p style="font-size:12px;color:#8a958f;">目前沒有任何設定欄位。</p>`;
    document.getElementById("newsSourceConfigNewKey").value = "";
    document.getElementById("newsSourceConfigModal").style.display = "flex";
  };

  window.closeSourceConfigModal = function () {
    document.getElementById("newsSourceConfigModal").style.display = "none";
  };

  window.addSourceConfigField = function () {
    const keyInput = document.getElementById("newsSourceConfigNewKey");
    const key = keyInput.value.trim();
    if (!key) return;
    const container = document.getElementById("newsSourceConfigFields");
    const placeholder = container.querySelector("p");
    if (placeholder) placeholder.remove();
    const row = document.createElement("div");
    row.className = "cfg-row";
    row.style.marginBottom = "10px";
    const sensitive = isSensitiveKey(key);
    row.innerHTML = `
      <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">
        ${escNewsAdmin(key)}${sensitive ? "（敏感欄位）" : ""}
      </label>
      <input type="${sensitive ? "password" : "text"}" data-key="${escNewsAdmin(key)}"
             ${sensitive ? 'data-sensitive="1"' : 'data-original=""'} style="width:100%;">`;
    container.appendChild(row);
    keyInput.value = "";
  };

  window.saveSourceConfig = async function () {
    const modal = document.getElementById("newsSourceConfigModal");
    const slug = modal.dataset.slug;
    const msg = document.getElementById("newsSourceConfigMsg");
    const changed = {};

    try {
      document.querySelectorAll("#newsSourceConfigFields [data-key]").forEach((el) => {
        const key = el.dataset.key;
        if (el.dataset.sensitive === "1") {
          if (el.value.trim() !== "") changed[key] = el.value.trim();
          return;
        }
        const raw = el.value;
        if (raw === (el.dataset.original || "")) return;  // 沒被改過，不送（保持 payload 最小）
        if (el.dataset.json === "1") {
          changed[key] = JSON.parse(raw);  // 格式不合法時的例外交給外層 catch
        } else if (raw.trim() !== "" && !isNaN(raw)) {
          changed[key] = Number(raw);
        } else if (raw === "true" || raw === "false") {
          changed[key] = raw === "true";
        } else {
          changed[key] = raw;
        }
      });
    } catch (e) {
      msg.textContent = "格式錯誤：" + e.message;
      return;
    }

    if (!Object.keys(changed).length) {
      msg.textContent = "沒有任何欄位被修改。";
      return;
    }

    try {
      await api("/news/admin/sources", {
        method: "PUT", body: JSON.stringify({ slug: slug, config: changed }),
      });
      closeSourceConfigModal();
      sourcesLoaded = false;
      await loadNewsSources();
    } catch (err) {
      msg.textContent = "儲存失敗：" + err.message;
    }
  };

  // ---------- 收集執行紀錄 ----------
  async function loadNewsRuns() {
    const tbody = document.getElementById("nRunBody");
    tbody.innerHTML = `<tr><td colspan="10">載入中...</td></tr>`;
    try {
      const rows = await api("/news/admin/runs");
      runsLoaded = true;
      tbody.innerHTML = "";
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="10" style="color:#8a958f;">尚無收集紀錄。</td></tr>`;
        return;
      }
      rows.forEach((r) => {
        const cls = r.status === "success" ? "status-live"
          : (r.status === "partial" ? "status-scheduled"
          : (r.status === "failed" ? "status-off" : "status-expired"));
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td style="font-size:12px;">${escNewsAdmin(r.run_date)}</td>
          <td style="font-size:12px;">${escNewsAdmin(r.trigger_type)}</td>
          <td><span class="status-pill ${cls}">${escNewsAdmin(r.status)}</span></td>
          <td style="font-size:12px;">${r.fetched_count}</td>
          <td style="font-size:12px;">${r.new_count}</td>
          <td style="font-size:12px;">${r.duplicate_count}</td>
          <td style="font-size:12px;">${r.digest_count}</td>
          <td style="font-size:12px;">${r.linked_entity_count}</td>
          <td style="font-size:12px;">${r.duration_ms ? (r.duration_ms / 1000).toFixed(1) + "s" : "—"}</td>
          <td style="font-size:11.5px; color:#c0392b;">${escNewsAdmin(r.error_message || "")}</td>`;
        tbody.appendChild(tr);
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="10">載入失敗：${escNewsAdmin(err.message)}</td></tr>`;
    }
  }

  window.newsAdminCollect = async function () {
    const btn = document.getElementById("nCollectBtn");
    if (!confirm("立即執行一次收集？需時 1–3 分鐘，期間請勿離開此頁。")) return;
    btn.disabled = true;
    btn.textContent = "收集中...";
    try {
      const r = await api("/news/admin/collect", { method: "POST", body: JSON.stringify({}) });
      alert(`收集完成（${r.status}）\n抓取 ${r.fetched} 筆、新增 ${r.new_articles} 筆、`
            + `重複 ${r.duplicates} 筆、精選 ${r.digest_size} 篇、實體連結 ${r.linked_entities} 個。`);
      runsLoaded = false;
      await loadNewsRuns();
    } catch (err) {
      alert("收集失敗：" + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "立即執行一次收集";
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTabs);
  } else {
    initTabs();
  }
})();
