# 版本更新紀錄（tcm_backend）

## v1.9.0 — 2026-07-31（功能項目顯示控制、前台/後台導覽區隔、動態選單）

### 新增功能

- **功能項目管理**（新頁面 `features.html`，F0-14）：管理者可對每個功能項目勾選「啟用」「顯示於前台」「顯示於後台」，並編輯導覽文字與排序，即時生效
- **Dashboard 小工具開關**：Dashboard 四張卡片（主機資訊/版本資訊/專案文件/2026年目標）現在各自對應一個功能代碼（F0-13-1~F0-13-4），可在「功能項目管理」個別停用/啟用
- **前台／後台導覽區隔**：新增 `GET /nav/menu`，依目前使用者的角色權限（管理者永遠全見；一般角色需要 `can_view` 權限）動態回傳可見的功能項目，側邊選單改由 `js/nav.js` 統一動態渲染，分成「前台功能」「後台管理」兩區塊
- 「一般使用者」角色種子資料現在會自動取得所有 `show_frontend=true` 功能的 `can_view` 權限（目前為：Dashboard、中藥行地理推薦、TCMSP 藥材關聯查詢站）
- `Feature` 資料表新增欄位：`enabled`、`show_frontend`、`show_backend`、`nav_label`、`page_url`、`sort_order`
- 新增 `app/feature_config.py`：全站功能項目設定單一資料來源，`seed.py` 與 `migrate_schema.py` 共用
- 新增 `app/migrate_schema.py`：既有資料庫（尤其正式環境 Neon）需要手動執行一次，補齊 `features` 資料表新欄位並回填正確的導覽設定
- 新增 `/features` PUT 端點（先前只有新增/刪除，沒有編輯）
- 新增 `rules.md`：記錄「每個功能獨立頁面」「功能顯示控制三層機制」等開發規範，並列入 Dashboard 專案文件清單

### 部署注意事項

**正式環境（Render + Neon）這次更新後，除了照常 push 程式碼，還需要額外執行一次遷移指令**：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

沒有執行的話，`features` 資料表會缺少新欄位，`/nav/menu`、`/features` 等 API 會報錯。

### 已知限制

- 目前只有「選單看不看得到」是動態控制的，個別 API 的存取權限仍然是各自路由用 `require_admin`／`require_permission()` 明確檢查——兩者需要一起維護，不能只靠隱藏選單當作安全機制
- 按鈕層級的操作權限（`can_execute`）後端已有檢查機制，但前端還沒有依此動態隱藏「編輯/刪除」按鈕

## v1.8.0 — 2026-07-31（Dashboard 全面改版：不再是施工中佔位頁）

### 新增功能

- **主機資訊卡片**：列出 GitHub、Cloudflare Pages、Render、Neon 四個服務的角色說明與連結（`GET /project-info/hosts`）
- **版本資訊卡片**：顯示目前版本號徽章，下方列出所有歷史版本，每筆固定長度摘要 + 「詳細」按鈕開啟 Modal 顯示該版本完整 CHANGELOG 內容（Markdown 渲染）。後端新增 `GET /project-info/version`，會自動解析 `CHANGELOG.md` 切成結構化版本清單，不需要手動維護重複資料
- **專案文件卡片**：README、版本更新紀錄、2026 年工作目標三份文件，點按鈕開啟 Modal 直接閱讀（Markdown 渲染），後端新增 `GET /project-info/docs`、`GET /project-info/docs/{doc_id}`，直接讀取專案內對應的 `.md` 檔案內容
- **2026 年工作目標卡片**：五大目標摘要 + 完成狀態標示（目標五已完成，其餘進行中/規劃中），可點「查看完整文件」看完整內容
- 新增 `docs/2026_goals.md`：整理五大目標的詳細說明與目前狀態
- 前端加入 `marked.js`（CDN）做 Markdown 轉 HTML 渲染

### 已知限制

- 「2026 年工作目標」摘要卡片的五筆資料是寫死在前端 JS 裡（`GOALS_SUMMARY`），跟 `docs/2026_goals.md` 內容需要手動保持同步；如果之後目標異動頻繁，可考慮改成後端統一解析
- 版本資訊的「摘要」是取 CHANGELOG 標題括號內文字，若某版本沒有標題文字，會退回取內文第一行，可能不夠精簡

## v1.7.3 — 2026-07-31（TCMSP 查詢站效能優化 + 移除「本地資料庫版」字樣）

### 效能優化

- `app/main.py` 加入 `GZipMiddleware`：大型 JSON 回應（如 `/tcmsp/data/full`）傳輸前自動壓縮，減少網路傳輸量
- `/tcmsp/data/full` 加入伺服器端記憶體快取（10 分鐘 TTL），並直接快取「已序列化好的 JSON bytes」，命中快取時完全跳過資料庫查詢與序列化開銷
- 本機測試：首次請求（無快取）約 5.5 秒，快取命中後降到約 1.1 秒；正式環境（Render + Neon，兩者皆有網路延遲）預期改善幅度會更明顯
- 後台編輯／下架藥材時會主動清除快取，確保管理者的異動立即反映在前台查詢站，不用等 10 分鐘 TTL 過期

### 介面調整

- 移除頁面標題與 `<title>` 裡的「（本地資料庫版）」／「（本地資料庫）」字樣

## v1.7.2 — 2026-07-31（緊急修正：TCMSP 查詢站「完全無資料」的真正原因）

### 問題

`tcmsp_query.html` 裡有一行遺留的樣板佔位符沒有替換：

```js
const VERSION_SNAPSHOTS = __VERSION_SNAPSHOTS_JSON__;
```

瀏覽器執行到這行會拋出 `ReferenceError: __VERSION_SNAPSHOTS_JSON__ is not defined`，**導致整個 `<script>` 後續程式碼全部中斷**，包括負責載入資料的 `bootstrapData()` 完全沒有機會執行。這就是使用者回報「查詢站完全沒有資料、畫面卡在請選擇藥材」的真正原因——**跟 Neon 資料庫是否有匯入資料無關**，之前排查方向（懷疑資料庫沒匯入）是誤判，特此更正。

### 修正

- `VERSION_SNAPSHOTS` 固定改為空物件 `{}`：版本歷史說明文字仍可查看，但不提供舊版本下載（舊版樣板的下載功能需要外部快照檔案，此次整合沒有對應資料來源）
- 全文搜尋確認沒有其他遺漏的 `__XXX__` 樣板佔位符

## v1.7.1 — 2026-07-31（暫停 staging 環境，先專心搞定正式站）

v1.7.0 建置的正式站／測試站分離架構評估後覺得太複雜，暫時停用，先集中處理正式站：

- `render.yaml`：staging 服務整段註解掉（設定保留，之後要恢復把每行開頭的 `# ` 拿掉即可）
- `frontend/js/api.js`：拿掉依網域判斷 API 位置的邏輯，改回固定指向正式站後端
- `app/main.py`：CORS 移除 staging 網域，只保留正式站與本機測試
- README「正式站／測試站分離」章節保留供之後參考，並加註目前暫停使用

## v1.7.0 — 2026-07-31（正式站／測試站環境分離）

### 新增功能

- `render.yaml` 新增第二個服務 `tcm-onco-backend-staging`，綁定 `staging` 分支，環境變數與正式站完全獨立（各自的 `DATABASE_URL`、`FRONTEND_BASE_URL`、`GOOGLE_REDIRECT_URI`、`TCM_JWT_SECRET`）
- `app/main.py` CORS 設定新增允許 `https://fwc-tcmsp-staging.pages.dev`（含其 Cloudflare Pages 預覽網址）
- `frontend/js/api.js` 新增 `resolveApiBase()`：依前端目前部署的網域（正式站/測試站/本機）自動決定要呼叫哪個後端 API，同一份前端程式碼可以同時部署到兩個環境
- README 新增完整「正式站／測試站分離」設定章節，涵蓋 Git 分支策略、Neon 測試專用資料庫、Render Blueprint 新增服務、Google OAuth 多加一筆重新導向 URI、Cloudflare Pages 新建獨立專案等步驟

### 使用方式

日常開發／測試都先 push 到 `staging` 分支，在 `https://fwc-tcmsp-staging.pages.dev` 驗證沒問題後，再合併回 `main` 觸發正式站更新，降低直接動到正式環境的風險。

### 已知限制

- 兩個環境目前共用同一組 Google OAuth 用戶端（只是在 Google Cloud Console 多加一筆測試站的重新導向 URI），如果之後想讓兩邊完全獨立（例如不同的 OAuth 應用程式審核狀態），需要另外申請一組新的 Client ID/Secret
- 測試站的 TCMSP 資料、帳號、角色等都需要在測試資料庫另外手動建置/匯入一次，不會自動從正式站同步

## v1.6.0 — 2026-07-31（TCMSP 藥材關聯資料改為資料庫化，取代本機端 JSON 檔案）

### 背景

先前版本（v1.4.0～v1.5.1）的 TCMSP 藥材關聯資料是直接放在前端可讀取的靜態 JSON 檔案（`frontend/data/tcmsp_data.json`），純粹由瀏覽器端 fetch 讀取後在本機運算查詢/篩選，資料庫本身完全沒有這批資料，也無法透過後台管理。這次依需求把資料正式匯入資料庫，並改由後端 API 提供查詢。

### 新增功能

- `app/models.py` 新增 6 張 TCMSP 相關資料表：`tcmsp_herbs`（藥材）、`tcmsp_ingredients`（成分）、`tcmsp_targets`（靶點）、`tcmsp_diseases`（疾病）、`tcmsp_herb_ingredient`（藥材-成分關聯）、`tcmsp_ingredient_target`（成分-靶點關聯）、`tcmsp_target_disease`（靶點-疾病關聯）
- 新增 `app/import_tcmsp_data.py` 匯入腳本：`python -m app.import_tcmsp_data data_import/tcmsp_data.json`，可重複執行（先清空再匯入），本機 SQLite 測試匯入全部資料（502 藥材、13,728 成分、1,751 靶點、564 疾病、共約 9 萬筆關聯）耗時約 4.5 秒
- 新增後端 API：
  - `GET /tcmsp/data/full`（登入即可查詢，供前台查詢站使用，取代原本讀取靜態 JSON 檔案）
  - `GET /tcmsp/herbs`、`PUT /tcmsp/herbs/{id}`、`DELETE /tcmsp/herbs/{id}`（後台管理，僅限管理者：查詢/編輯備注與狀態/軟刪除下架）
- `tcmsp_query.html` 改為呼叫 `/tcmsp/data/full` API，不再讀取本機端 JSON 檔案
- 原始資料檔搬移到 `data_import/tcmsp_data.json`（不會隨前端部署到 Cloudflare Pages，只作為匯入來源保留）

### 已知限制

- 成分/靶點/疾病/各類關聯表資料量龐大（合計約 9 萬筆），屬於批次匯入的參考資料，暫不提供逐筆後台編輯介面；如需更新內容，需重新執行匯入腳本（會清空重建）
- `/tcmsp/data/full` 目前是即時查詢資料庫組裝完整資料回傳（未加快取），資料量大時每次請求都需要重新查詢組裝，如果之後使用者數增加、效能出現問題，可考慮加上伺服器端快取
- 正式環境（Render + Neon）需要手動執行一次匯入腳本（並指向正式的 `DATABASE_URL`），才會有資料；程式碼部署本身不會自動觸發資料匯入

## v1.5.1 — 2026-07-31（修正：改用真正的原始完整資料取代重建版本）

### 背景

v1.4.0 因為手上只有 `tcmsp_herb_details_merged_500.json`（原始爬取資料，未含中文名稱與 ICD 編碼），只能自己寫轉換腳本重建一份簡化版資料，並在多處用預設值/推斷值頂替缺漏欄位（例如 495 種藥材沒有中文名稱、疾病沒有 ICD9/10）。

使用者後續提供了完整的原始專案原始碼（`HERB_Q_1.7z`），裡面的 `tcmsp_herb_query_site.html` 是當時實際上線運作的完整版本，內嵌了真正正式的資料。比對後發現核心關聯數量（成分/靶點/疾病/各類關聯表）完全一致，證實資料源頭相同，但正式版額外包含：

- **全部 502 種藥材的正式中文名稱、拼音、分類**（v1.4.0 版本只有人參屬 5 種藥材有中文名稱，其餘用英文學名頂替）
- **疾病的 ICD9 / ICD10 編碼**（v1.4.0 版本此欄位全部是空值）
- 靶點的 DrugBank ID、KEGG 對照等額外欄位
- 成分的 TPSA、RBN 等額外 ADME 欄位
- 標準化的 `TAR00002`／`DIS00001` 格式編號（v1.4.0 版本靶點編號是未加前綴的原始數字）

### 修正內容

- `frontend/data/tcmsp_data.json` 改為直接使用從 `tcmsp_herb_query_site.html` 抽取出的正式資料（11.8MB），取代 v1.4.0 用腳本重建的簡化版（9.1MB）
- 頁面程式碼（`tcmsp_query.html`）與資料載入邏輯不需變動，直接相容新資料

### 已知限制（更新）

- 前一版「495 種藥材沒有中文名稱」「疾病沒有 ICD 編碼」的限制已解決
- 其餘限制維持不變：純前端運作、後台無法編輯此資料集，需要更新須替換 `tcmsp_data.json` 檔案本身

## v1.5.0 — 2026-07-31（真正的 Google OAuth 登入，取代先前的骨架）

### 新增功能

- 實作完整 Google OAuth 2.0 Authorization Code Flow：
  - `GET /auth/google/enabled` — 查詢是否已設定 Google 金鑰（供前端判斷是否顯示按鈕）
  - `GET /auth/google/login` — 導向 Google 登入頁（含 CSRF state 保護）
  - `GET /auth/google/callback` — Google 導回後交換 token、取得使用者 email，完成登入或建立待審核帳號
- 新增 `app/oauth_google.py`：封裝 Google OAuth 的網址建構與 token/使用者資訊交換邏輯
- 登入頁（`index.html`）新增「使用 Google 帳號登入」按鈕，僅在後端已設定 Google 金鑰時顯示
- 新增 `oauth_callback.html` 中繼頁面，處理 Google 登入完成後的 token 寫入與導轉
- **帳號治理與一般註冊一致**：第一次用 Google 登入會建立「審核中」帳號＋一筆帳號申請紀錄，需管理者於「帳號審核」頁核准後才能登入；若 Google email 對應到既有帳號則自動綁定
- `render.yaml` 新增 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`（皆為 `sync: false`，需於 Render 後台手動填入）、`GOOGLE_REDIRECT_URI`、`FRONTEND_BASE_URL` 環境變數
- README 新增完整「Google OAuth 設定」章節，含 Google Cloud Console 申請步驟

### 重要說明：修正先前的誤解

先前對話中容易被誤以為「第三方登入已經完成」，但實際上此前只有：(1) 早期規劃文件把它列為 F0-6 待辦項目、(2) 一個純資料表 CRUD 骨架（`/oauth-accounts`，只能手動輸入 provider_user_id，沒有真正的登入按鈕與授權流程）。本版本才是第一次真正實作可運作的 Google 登入。

### 已知限制

- CSRF state 使用伺服器記憶體內暫存，僅適合單一伺服器程序；多 worker/多實例部署需改用 Redis 等共享暫存
- 小紅書（RED）、WeChat 第三方登入仍未實作，維持先前的資料表 CRUD 骨架，需另外確認開發者資格與串接規範
- 尚未實測真實 Google 帳號完整登入流程（本次僅完成程式碼邏輯與錯誤路徑的自動化測試），需要你申請好 Client ID/Secret 後實際跑一次才能最終確認

## v1.4.0 — 2026-07-31（整合 TCMSP 藥材關聯查詢站，目標一/二）

### 新增功能

- 新增 `frontend/tcmsp_query.html`：整合先前獨立開發的「TCMSP 藥材關聯查詢站」（v00.01.05 版樣板），涵蓋：
  - 左側 500 種藥材清單搜尋
  - 右側 Ingredients／Related Targets／Related Diseases 分頁表格（含欄位說明、排序、數值篩選）
  - 成分-靶點-疾病關聯網絡圖（vis-network），可全螢幕檢視、點節點看詳情、列印、下載圖片
  - 圖上文字語言切換（繁中／簡中／English）、版面自訂配置、單一藥材 JSON/CSV 下載、版本歷史查詢
- 資料來源：使用者提供的 `tcmsp_herb_details_merged_500.json`（500 種藥材，TCMSP 網站爬取彙整），經正規化去重後產出 `frontend/data/tcmsp_data.json`（9.1MB，13,728 個不重複成分、1,751 個不重複靶點、564 個不重複疾病）
- **架構調整**：原始樣板是把資料直接內嵌在 HTML 裡（`const DATA = __DATA_JSON__`），考量到 500 種藥材的完整資料量偏大，改為讓頁面用 `fetch()` 非同步載入外部 `data/tcmsp_data.json`，避免單一 HTML 檔案過於肥大、影響載入速度
- **登入整合**：頁面加入與平台共用的登入驗證（沿用 `js/api.js`），未登入會導回登入頁；頁首新增導覽列（返回 Dashboard／登出），並已加入所有頁面的側邊選單連結

### 已知限制

- 500 種藥材中，僅人參屬 5 種（人參、三七、西洋參、竹節參、紅參）有對照中文名稱，其餘 495 種暫以英文學名顯示，待後續人工翻譯補充
- 疾病資料的 ICD9/ICD10 欄位原始資料中沒有提供，目前顯示為空值
- 靶點的「彙總／補充」來源分類為簡化推斷（依資料出現的關聯類型判斷），非原始資料庫的精確分級標記
- 此頁面純前端運作（資料查詢、篩選、網絡圖皆在瀏覽器端處理），與後端資料庫無關，不支援後台管理（新增/編輯/刪除藥材資料）；若需要維護此資料集，需重新產生 `tcmsp_data.json` 並替換

## v1.3.0 — 2026-07-31（支援雲端 PostgreSQL，解決資料庫重置問題）

**狀態：已通過使用者實測驗證** —— 後端已接上 Neon 的免費 PostgreSQL（透過 Render 環境變數 `DATABASE_URL`），並實際測試「新增帳號 → 手動觸發 Render 重新部署 → 確認帳號仍存在」，證實資料不再因重新部署而消失，資料庫重置問題已解決。

### 新增功能

- `app/database.py` 改為讀取環境變數 `DATABASE_URL`：
  - 有設定時連接雲端 PostgreSQL（正式環境用）
  - 未設定時自動退回本機 SQLite 檔案（本機開發測試用，行為與之前版本相同）
  - 自動將 `postgres://` 開頭的連線字串轉換為 SQLAlchemy 2.0 要求的 `postgresql://`
- `requirements.txt` 新增 `psycopg2-binary`（PostgreSQL 驅動）
- `render.yaml` 新增 `DATABASE_URL` 環境變數欄位（`sync: false`，不寫入版本控制，需於 Render 後台手動填入）

### ⚠️ 重要提醒：Render 自帶的免費 PostgreSQL 也會過期，並非長久解法

原本以為「換成 PostgreSQL」就能徹底解決資料庫被重置的問題，但查證後發現：**Render 自己附的免費 PostgreSQL 資料庫本身只保留 30 天，到期後 14 天內沒升級為付費方案，資料庫連同所有資料會被整個刪除**。這跟原本 SQLite 在免費方案上「重新部署就重置」的問題性質類似，只是把期限從「每次重啟」延後到「30 天」，並非真正的永久解法。

**建議做法**：改接**永久免費**的第三方 PostgreSQL 服務（例如 Neon、Supabase 皆有不到期的免費額度），Render 後端只需要一組連線字串即可連接，資料庫實際放在哪個平台跟後端部署位置無關。這部分已經完成程式碼支援，下一步需要你選定要用哪家 Postgres 服務、建立資料庫後把連線字串填入 Render 的 `DATABASE_URL` 環境變數即可。

### 已知限制

- SQLAlchemy 的 Enum 型別在 PostgreSQL 會建立原生 ENUM 型別，未來若要異動欄位選項（例如新增角色狀態），需要額外處理資料庫遷移（migration），目前專案尚未導入 Alembic 等遷移工具
- Neon 免費方案本身也有額度限制（例如閒置一段時間會休眠、儲存空間上限），雖然不會像 Render 免費 Postgres 一樣「30 天到期就整個刪除」，但正式上線有大量使用者時仍需評估是否要升級付費方案

## v1.2.0 — 2026-07-31（前後端分離部署：Render + Cloudflare Pages）

**狀態：已通過使用者正式環境驗證** —— 前端 `https://fwc-tcmsp.pages.dev/`（Cloudflare Pages，GitHub 自動部署）+ 後端 `https://tcm-onco-backend.onrender.com`（Render，GitHub 自動部署，Blueprint 方式）已成功串接，使用 `admin`/`0000` 登入後台驗證通過，Dashboard 與左側選單（角色管理／帳號管理／帳號審核／中藥行管理／中藥行地理推薦／稽核登入紀錄）皆正常顯示。

- 後端已部署上線：`https://tcm-onco-backend.onrender.com`（Render Blueprint 部署）
- 前端 `js/api.js` 的 `API_BASE` 改為指向線上後端網址，不再依賴與後端同源
- CORS 設定從允許所有來源（`*`）收緊為僅允許：
  - `https://fwc-tcmsp.pages.dev`（Cloudflare Pages 正式網址）
  - `https://*.fwc-tcmsp.pages.dev`（Cloudflare Pages 預覽部署網址，正規表示式比對）
  - `http://localhost:8000` / `http://127.0.0.1:8000`（本機測試）
- ⚠️ 提醒：Render 免費方案為暫時性檔案系統，重新部署或服務休眠喚醒後 SQLite 資料會被重置（沿用 v1.1.1 的已知限制，尚未解決）

## v1.1.1 — 2026-07-31（新增 Render 部署設定）

- 新增 `render.yaml`，可透過 Render 的 Blueprint 功能一鍵部署後端 API
- README 新增「部署到 Render」「Cloudflare Pages 前端串接」兩個章節，說明完整部署流程
- ⚠️ 記錄已知限制：Render 免費方案檔案系統為暫時性，SQLite 資料庫會在重新部署/服務喚醒時被重置，正式上線前需改接雲端 PostgreSQL（已列入待辦）

## v1.1.0 — 2026-07-31（目標五：中藥行地理推薦，前台 + 後台）

### 新增功能

- **後台：中藥行管理**（`pharmacies.html`）：新增 / 編輯 / 刪除（軟刪除=下架）/ 查詢中藥行資料（名稱、地址、電話、營業時間、經緯度、簡介、備注）
- **後台：評價管理**：於中藥行管理頁可查看每間中藥行的所有評價、補充管理備注、刪除不當評價
- **前台：中藥行地理推薦**（`finder.html`）：
  - 使用瀏覽器定位（`navigator.geolocation`）取得使用者座標，以 Haversine 公式計算距離並排序（未授權定位時退回依名稱排序）
  - 顯示中藥行資訊、平均星等、所有評價
  - 登入使用者可對每間中藥行新增一則評價（1~5 星 + 文字），並可編輯/刪除自己的評價（每人每店限一則）
- 後端新增 API：`/pharmacies`（後台 CRUD）、`/pharmacies/{id}/reviews`、`/pharmacy-reviews/{id}`（後台評價管理）、`/public/pharmacies`、`/public/pharmacies/{id}`、`/public/pharmacies/{id}/reviews`、`/public/reviews/{id}`（前台）
- 新增功能代碼 F5-1（中藥行資料管理）、F5-2（中藥行地理推薦前台）、F5-3（評價管理），已登錄於權限矩陣的功能清單中
- 系統啟動時會建立 3 筆範例中藥行測試資料（僅供本機測試辨識畫面用）

### 已知限制

- 前台頁面尚未依「權限矩陣」動態隱藏/顯示選單（例如非管理者理論上也看得到「中藥行管理」連結，但後端 API 已用 `require_admin` 擋下，實際操作會被拒絕）——這是全站共通的前端限制，待後續統一處理
- 尚未整合實際地圖圖資（如 Google Maps/OpenStreetMap 嵌入），目前僅列表呈現 + 距離排序
- 經緯度需由後台人員手動輸入，尚未提供地址自動轉換座標（Geocoding）功能

## v1.0.1 — 2026-07-31（調整預設管理員測試帳號）

- 依需求將系統啟動時自動建立的預設管理員帳號密碼改為 `admin` / `0000`
- ⚠️ 提醒：`0000` 為極弱密碼，僅適合本機測試環境快速登入使用；正式環境上線前務必更換為高強度密碼，並建議移除「啟動時自動建立預設帳號」這段邏輯

## v1.0.0 — 2026-07-31（目標零：後台管理與系統共通功能，第一版上版）

**狀態：已通過使用者本機測試審查，正式列為 v1.0.0**

### 新增功能

- **Dashboard**：登入後可見的首頁，目前顯示「施工中」佔位內容（`dashboard.html` / `GET /dashboard`）
- **角色管理**（F0-2）：新增 / 編輯 / 刪除 / 查詢角色，並可查看角色底下已設定帳號（`roles.html`）
- **權限矩陣**：每個角色可針對每個功能模組個別設定「可見（can_view）」「可執行（can_execute）」（`roles.html` 權限矩陣視窗）
- **帳號管理**（F0-5）：新增 / 編輯 / 刪除（軟刪除，標記停用+原因）/ 查詢帳號，含角色指派、密碼重設（`users.html`）
- **帳號申請與審核**（F0-4）：使用者於登入頁提出申請 → 管理者於「帳號審核」頁核准／駁回，核准後自動啟用並指派預設角色（`applications.html`）
- **第三方登入綁定骨架**（F0-6）：Google / 小紅書 / WeChat 綁定關係 CRUD API（`/oauth-accounts`），尚未含前端頁面與正式 OAuth 流程
- **稽核紀錄**（F0-11）：系統重大操作自動寫入稽核紀錄，後台僅提供查詢與補充備注，不提供刪除／修改（`logs.html`）
- **登入紀錄**（F0-12）：登入/登出自動記錄 IP、裝置識別字串、登入與登出時間、停留秒數（`logs.html`）
- **資料庫備份紀錄骨架**（F0-10）：備份執行紀錄查詢、手動觸發紀錄、補充備注（`logs.html`），尚未串接實際自動備份程序

### 已知限制（詳見 README「重要設計說明與限制」）

- 登入紀錄的裝置識別為瀏覽器指紋，非真實網卡 MAC 位址
- 第三方登入僅完成綁定關係骨架，尚未串接真實 OAuth 授權流程
- 資料庫備份僅為紀錄骨架，尚未串接實際備份排程
- JWT 目前無黑名單機制，登出僅記錄登出時間，token 到期前理論上仍可使用

### 技術細節

- Backend：FastAPI + SQLAlchemy（SQLite，開發環境）+ JWT（python-jose）+ bcrypt 密碼雜湊
- Frontend：純 HTML/CSS/JS（無框架），透過 REST API 與後端溝通
- 已完成端對端測試：登入、Dashboard、角色 CRUD、權限矩陣設定、帳號申請/審核、登入/稽核紀錄查詢、備份紀錄觸發

### 下一步（尚未排入本版本）

- 目標一 / 二平台化、目標三 DNA 檢測系統、目標四癌症病患中藥建議、目標五中藥行地理推薦
- 第三方登入正式串接（待小紅書 / WeChat 開發者資格確認）
- 自動化測試套件、正式環境部署設定
