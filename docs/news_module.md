# 每日重點新聞模組（中藥與腫瘤）

> **定位聲明**：科研輔助情報工具，服務於證據查證、安全監測與研究追蹤。
> 內容不構成醫療診斷或治療建議。細胞毒殺、分子對接、動物腫瘤縮小或網路藥理預測，
> 都不能直接推論為病患有效。

追蹤《中藥與腫瘤｜10 個權威官方追蹤網站》所列來源，每日清晨 4:00（Asia/Taipei）
自動收集、過濾、去重、AI 中文摘要、標註證據層級，產出當日 **10 篇重點新聞**，
並把新聞內文比對到平台的藥材 / 成分 / 靶點 / 疾病主檔，讓讀者可以直接點進查詢站。

---

## 1. 檔案位置

```
app/
  models.py                     追加 7 張表（見下方）
  feature_config.py             追加 F0-13-6（Dashboard 卡片）、F0-19（後台分頁權限）
  main.py                       include_router(news) / include_router(news_admin)
  news/
    sources.py                  10 個來源註冊表（端點、權重、證據層級、過濾關鍵字）
    collectors/                 抓取器：PubMed API / ClinicalTrials API / RSS / HTML 爬蟲
    scoring.py                  主題過濾、癌別與介入分類、排序、每日 Top N 選取
    entity_linker.py            新聞 → 藥材/成分/靶點/疾病 比對
    summarizer.py               Claude 中文摘要（httpx 直呼 API，可降級）
    service.py                  每日流程主控 + DB 存取
  routers/
    news.py                     前台 API（需登入）
    news_admin.py               後台 API（require_admin）
frontend/
  dashboard.html                加一張 data-widget-code="F0-13-6" 的卡片
  js/news-widget.js             卡片邏輯
  announcements.html            改為「公告 / 新聞管理」，加 3 個新聞分頁
  js/news-admin.js              後台分頁邏輯
  js/dashboard.js               WIDGET_CARD_MAP 加 F0-13-6
  disease_query.html            支援 ?dis= 深連結（配合新聞的疾病標籤）
tests/test_news_e2e.py          端對端驗證（63 項斷言）
```

## 2. 沿用平台既有基礎建設

新聞模組**不自建**帳號、權限與稽核，全部沿用現成的：

| 需求 | 用的是 |
|---|---|
| DB session | `app.database.get_db` |
| 取得登入者 | `app.deps.get_current_user`（JWT Bearer） |
| 管理者判定 | `app.deps.require_admin`（角色名「管理者」） |
| 稽核紀錄 | `app.deps.write_audit_log` → `models.AuditLog` |
| 建表 | `Base.metadata.create_all()`（啟動時自動） |
| 功能開關 / 權限矩陣 | `feature_config.FEATURE_CONFIG` + `/nav/menu` |

所有欄位型別都維持平台慣例（`String(uuid)` 主鍵、`Text` 存 JSON、`Enum`），
因此本機沒設 `DATABASE_URL` 時退回 SQLite 仍可正常運作。

## 3. 資料表

| 表 | 用途 |
|---|---|
| `news_sources` | 10 個來源、權重、健康度（連續失敗次數）、爬蟲選擇器設定 |
| `news_articles` | 文章本體、分類標註、排序分數、軟刪除欄位、`search_blob` |
| `news_article_entities` | 新聞 ↔ 藥材/成分/靶點/疾病 的真實外鍵關聯 |
| `news_daily_digests` | 每日精選（預設 10 篇），含入選理由與置頂 |
| `user_news_bookmarks` | 使用者勾選保留 |
| `news_collection_runs` | 每日收集執行紀錄 |
| `news_settings` | 每日篇數、相關度門檻、免責聲明等 |

## 4. 排序哲學

不看熱度，看證據可信度：

| 因子 | 權重 |
|---|---|
| 主題相關度（腫瘤 × 中藥雙面向） | 0.30 |
| 來源權威度（NCI 0.90 > CT.gov 0.88 > About Herbs 0.86 > … > 中國官方站 0.70） | 0.22 |
| 證據成熟度（human 1.00 / mixed 0.75 / unknown 0.60 / preclinical 0.40） | 0.20 |
| 研究設計（統合分析 1.00 → 個案報告 0.30） | 0.16 |
| 時效性（半衰期 5 天） | 0.12 |
| **安全訊號加成** | +0.12 |

單一來源每日上限 4 篇，避免 PubMed 洗版；安全訊號同分時排最前；
臨床前研究（in vitro / 分子對接 / 網路藥理）自動降權並強制標示「不可推論至病患層級」。

## 5. 實體連結

`entity_linker.py` 把新聞內文比對到 TCMSP 主檔，前台顯示為可點標籤：

- 藥材 → `tcmsp_query.html?herb={herb_id}`
- 疾病 → `disease_query.html?dis={dis_id}`
- 靶點 → 無專屬查詢頁，改開彈窗（`GET /news/targets/{tar_id}` 回傳關聯藥材與疾病）
- 成分 → 目前只記錄不產生連結

比對規則刻意保守，寧可漏抓也不誤連：

- 拉丁字母以「詞」為單位做 1~4 連字詞比對，需完整詞界，長度 <5 或落在停用詞表的不建索引
- 中文以 2~8 字滑動視窗比對（中文無詞界可用）
- 基因/靶點符號（AKT1、TP53）**大小寫敏感**，否則會誤中大量無關字串
- 成分名稱門檻更嚴（≥6 字元），避免 water / glucose 這類通用字把每篇都連上

**效能**：用「詞典查表 + n-gram」而不是 29k 詞的正規表示式聯集。
實測（499 藥材 + 3,311 靶點 + 837 疾病 + 29,384 成分，共 34,491 條索引）：
索引建立 201 ms、每篇文章比對 1.2 ms，一次收集 120 篇僅增加 0.15 秒。

比對到的實體中文名會併進 `search_blob`，所以後台搜「胃癌」也找得到標題是英文的
gastric cancer 研究（沒有 AI 翻譯時尤其重要）。

## 6. API

### 前台（需登入）

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/news/daily?date=YYYY-MM-DD` | 每日重點新聞；該日未產生時自動回退最近一日 |
| GET | `/news/archive` | 歷史瀏覽（`days` / `source` / `cancer_type` / `safety_only` / `q`） |
| GET | `/news/sources` | 啟用中的來源清單 |
| GET | `/news/targets/{tar_id}` | 靶點彈窗：關聯藥材與疾病 |
| POST | `/news/bookmarks` | 勾選保留 |
| GET | `/news/bookmarks` | 我的保留 |
| DELETE | `/news/bookmarks/{article_id}` | 取消保留 |

### 後台（require_admin）

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/news/admin/articles/search` | 多條件查詢（可查已刪除） |
| POST | `/news/admin/articles/soft-delete` | **刪除舊新聞 + 註記（必填）** |
| POST | `/news/admin/articles/restore` | 還原 |
| POST | `/news/admin/digest/pin` | 置頂／取消置頂 |
| GET / PUT | `/news/admin/sources` | 來源健康度與設定（爬蟲選擇器在此改，不需重新部署） |
| GET | `/news/admin/runs` | 收集執行紀錄 |
| POST | `/news/admin/collect` | 立即執行一次收集 |
| POST | `/news/admin/collect/scheduled` | **排程專用**，不需登入，走 `Authorization: Bearer` 密鑰，見下節 |
| GET / PUT | `/news/admin/settings` | 每日篇數等設定 |

### 刪除設計

- **軟刪除為主**：前台隱藏，後台仍可查詢與還原。
- **註記必填**：寫入文章本身，並同步寫進平台的 `AuditLog`（action = `news_soft_delete`）。
- **保護已保留文章**：`exclude_bookmarked` 預設 `true`，批次刪除不會動到使用者勾選保留的項目，
  回應會回報保護了幾筆。使用者的「我的保留」仍看得到該文並標記 `article_removed`。
- **可先試算**：`dry_run: true` 只回報影響筆數，不寫入、不留稽核紀錄。

## 7. 每日 04:00 排程

**Render free plan 沒有 Cron Job**（付費方案才有），所以由外部排程呼叫：

```bash
curl -X POST "https://tcm-onco-backend.onrender.com/news/admin/collect/scheduled" \
  -H "Authorization: Bearer $NEWS_COLLECT_SECRET" \
  -H "Content-Type: application/json" -d '{}' \
  --max-time 600 --connect-timeout 90
```

**密鑰走 `Authorization: Bearer` 標頭，不要放在網址查詢字串**——查詢字串會被 Render 的
存取日誌、反向代理與瀏覽器歷史記錄下來，標頭不會。

在 Render 後台設環境變數 `NEWS_COLLECT_SECRET`。**未設定時該端點回 503 停用**
（而不是變成任何人都能觸發的公開端點）。密鑰比對用 `secrets.compare_digest`，避免時間差攻擊。

目前有兩個排程來源，擇一即可：

| 方案 | 密鑰存放位置 | 說明 |
|---|---|---|
| **GitHub Actions**（`.github/workflows/daily-news.yml`，建議） | GitHub repo secret | 密鑰不會出現在程式碼或提示詞裡，安全性最好；含喚醒預熱、3 次重試、結果摘要 |
| **Claude 排程任務**（已建立並啟用） | 排程任務的提示詞內 | 免設定即可運作，失敗時會推播通知 |

⚠️ Render free plan 會休眠，第一次呼叫要等 30–60 秒冷啟動，加上收集本身 1–3 分鐘，
逾時請設 10 分鐘以上。GitHub Actions 版會先打一次 `/docs` 把伺服器叫醒再送實際請求。

### 其他環境變數

| 變數 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | AI 中文摘要；未設定時自動降級為規則式摘要，流程不中斷 |
| `PUBMED_API_KEY` | 選填，NCBI 速率 3→10 req/s |
| `NEWS_CONTACT_EMAIL` | NCBI 使用規範要求帶上聯絡信箱 |
| `NEWS_SUMMARY_MODEL` | 預設 `claude-sonnet-4-5` |

## 8. 測試

```bash
python tests/test_news_e2e.py       # 63 項斷言，用 SQLite 不連外網
```

已驗證：功能代碼經 seed 建立、真實 JWT 登入、未登入 401、一般使用者查後台 403、
管理者 200、主題過濾、近似重複去重、安全訊號排 #1、臨床前排末位、每篇都有解讀注意事項、
實體連結三種類型與連結網址正確、靶點彈窗帶出關聯藥材與疾病、收藏跨使用者隔離、
中文關鍵字搜尋、刪除註記必填、試算與實際刪除筆數一致、批次刪除保護已保留文章、
前台隱藏但後台查得到、還原、稽核寫進 `AuditLog` 且試算不留紀錄、來源健康度、
執行紀錄、設定驗證、排程端點（未設密鑰 503／無標頭 401／錯誤密鑰 401／密鑰放查詢字串無效／正確密鑰 200）。

## 9. 來源實測狀態（2026-08）

| # | 來源 | 方式 | 狀態 |
|---|---|---|---|
| 1 | WHO 傳統醫學 | RSS | ✅ `who.int/rss-feeds/news-english.xml`（全站 feed，必須開主題過濾） |
| 2 | NCI | RSS | ✅ 2 個官方 feed。⚠️ `/syndication/rss.xml` 會 403，別用 |
| 3 | NCI OCCAM | 爬蟲 | 無 feed |
| 4 | NCCIH | 爬蟲 | ⚠️ `/news/rss` 實測 404（常被誤引用），頁面無 rel=alternate |
| 5 | PubMed | API | E-utilities，建議申請 api_key |
| 6 | ClinicalTrials.gov | API | ✅ v2 實測回傳 JSON |
| 7 | MSK 整合醫學 | 爬蟲 | `/news` 未暴露 RSS |
| 8 | MSK About Herbs | 爬蟲 | 資料庫型，一律標記為安全訊號來源 |
| 9 | 中國衛健委 | 爬蟲 | ⚠️ 設 `allow_failure`，海外節點可能不通 |
| 10 | 中國中醫藥管理局 | 爬蟲 | ⚠️ 同上 |

第 9、10 項在雲端沙箱無法連線驗證（DNS 解析失敗）。Render 在新加坡，實際可達性
請看首次收集後的後台「新聞來源健康度」分頁。若不通可直接於該頁停用，或修改
`config` 內的選擇器 — 都不需要改程式重新部署。
