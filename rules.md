# 開發規範（rules.md）

本文件記錄 TCM 中藥腫瘤篩選平台的核心開發約定，新增功能前請先閱讀，維持全站架構一致。

---

## 一、每個功能項目使用獨立 HTML 頁面

**規則**：後台每一個功能模組（角色管理、帳號管理、中藥行管理...）都必須是獨立的 `.html` 頁面 + 對應的獨立 `.js` 檔案，不要把多個不相關的功能塞進同一個頁面。

**原因**：這樣才能搭配下面第二節「功能項目顯示控制」機制（在角色管理的「權限矩陣」視窗一併設定），用同一套邏輯個別控制每個功能是否啟用、要顯示在前台還是後台、哪些角色可以看到——如果多個功能擠在同一頁，就沒辦法用頁面層級做這種細粒度控制。

**命名慣例**：
- 頁面檔名使用小寫、有意義的英文，例如 `roles.html`、`pharmacies.html`
- 對應的 JS 檔案放在 `frontend/js/`，同名，例如 `roles.js`
- 每個頁面在後端 `app/feature_config.py` 裡要有一筆對應的功能項目設定（見下一節）

## 二、功能項目顯示控制機制

系統用同一套 `features` 資料表機制，統一控制「這個功能要不要顯示」跟「誰可以看到」，分成三層：

1. **`enabled`（總開關）**：在「角色管理」頁面任一角色的「權限矩陣」視窗可以切換。關閉後，這個功能對所有人（包含管理者）都會消失，通常用在還沒開發完、或臨時要下架的功能。
2. **`show_frontend` / `show_backend`（顯示區域）**：決定這個功能出現在前台導覽選單、後台導覽選單，或兩者都出現。可以同時勾選。只對「有對應頁面」的功能（`page_url` 不是空的）有意義，Dashboard 小工具這種非獨立頁面的項目不受這兩個欄位影響。
3. **角色權限矩陣（`can_view`）**：決定「哪些角色」看得到這個已啟用的功能。管理者角色永遠可以看到全部已啟用功能（略過權限矩陣檢查）；其他角色需要在「角色管理」頁面個別勾選 `can_view`。

**新增一個功能項目的完整流程**：

1. 在 `app/feature_config.py` 的 `FEATURE_CONFIG` 加一筆設定（code、module、name、nav_label、page_url、show_frontend、show_backend、sort_order）
2. 重新啟動後端（`seed_default_data()` 會自動把新項目寫進資料庫），或針對已存在的資料庫執行 `python -m app.migrate_schema` 回填
3. 到「角色管理」頁面點任一角色的「權限矩陣」按鈕，會看到這個新功能項目出現在清單裡：左側「可見/可執行」設定該角色專屬權限，右側「啟用/前台/後台/導覽文字/排序」是全站共用設定（改了會影響所有角色，含管理者），**兩者在同一個視窗一次設定完成**，不需要另外開一個「功能項目管理」頁面
4. 前端頁面記得在 `<body>` 加上 `data-current-page="xxx.html"`，並用 `<nav id="navContainer"></nav>` 取代寫死的選單——導覽選單會由 `js/nav.js` 呼叫 `GET /nav/menu` 動態渲染，不需要在每個頁面手動維護 `<a>` 清單

> **歷史備註**：v1.9.0 曾經另外做了一個獨立的「功能項目管理」頁面（`features.html`），跟角色管理的「權限矩陣」功能重疊，v1.10.0 已經整併：全站共用設定（啟用/前台/後台/導覽文字/排序）現在直接在「權限矩陣」視窗編輯，`features.html` 已移除。後端 `/features` 系列 API 仍保留（GET/POST/PUT/DELETE），供未來需要程式化管理時使用，只是拿掉了對應的獨立管理頁面。

## 三、前台／後台區隔

- **前台**：一般使用者角色預設可見的功能（`show_frontend = true` 且該角色 `can_view = true`），目前包含 Dashboard、中藥行地理推薦、TCMSP 藥材關聯查詢站
- **後台**：管理者角色專用的管理功能（`show_backend = true`），目前包含角色管理、帳號管理、帳號審核、中藥行管理、稽核/登入紀錄
- 導覽選單會依照回傳的項目自動分成「前台功能」「後台管理」兩區塊顯示（`js/nav.js` 的 `renderNav()`）
- **重要**：目前只有「選單看不看得到」是動態控制的；個別 API 的存取權限仍然是各自後端路由裡用 `require_admin` 或 `require_permission()` 明確檢查，兩者要一起維護，不能只改前端選單就以為安全了

## 四、Dashboard 小工具

Dashboard 頁面的四張卡片（主機資訊／版本資訊／專案文件／2026年工作目標）也是走 `features` 機制，代碼為 `F0-13-1` ~ `F0-13-4`，`page_url` 為 `null`（非獨立頁面）。

因為 Dashboard 是同一個頁面同時給管理者跟一般使用者看，小工具的 `show_frontend` / `show_backend` 欄位語意跟一般頁面不同：

- 管理者登入看 Dashboard 時，只看 `show_backend = true` 的小工具
- 一般使用者登入看 Dashboard 時，只看 `show_frontend = true` 的小工具

所以同一張卡片，可以設定成「只給管理者看」「只給一般使用者看」「兩邊都看」「兩邊都不看（＝直接關掉 enabled）」，在「角色管理」頁面任一角色的「權限矩陣」視窗個別勾選即可，不需要區分是不是有 `page_url`。

## 四之一、查詢站類頁面標準功能清單

目前三個查詢站（`tcmsp_query.html`／`disease_query.html`／`darkgene_query.html`）都必須具備以下功能，新增任何一個查詢站類頁面時，這份清單就是驗收標準：

| # | 功能 | 說明 | 對應元素/實作方式 |
|---|---|---|---|
| 1 | 繁體/簡體語系切換 | 搜尋欄旁的下拉選單，用 OpenCC-JS 即時轉換頁面中文顯示（中文名稱、網絡圖節點文字等） | `<select id="uiLangSelect">`，狀態存 `localStorage.tcm_ui_lang`，切換時重繪清單與詳情 |
| 2 | 淺色/深色主題切換 | 頂部導覽列「🌗 切換淺色/深色」，套用個人化設定裡的查詢站配色偏好 | `<a id="themeToggleLink">` + `body[data-page-theme="light"]` CSS 覆寫區塊，讀寫 `/user-preferences/query_station_theme` |
| 3 | 個人化設定連結 | 頂部導覽列可以直接連到個人化設定頁面 | `<a href="personal-settings.html">` |
| 4 | 網絡關聯圖全螢幕放大 | 「⛶ 放大檢視關聯圖」按鈕，開啟全螢幕 Modal，可點節點看詳情 | `#networkModal` / `#networkModalCanvas` / `#networkNodeDetail`，`renderNetwork(containerId, isModal)` 要能同時畫背景小圖跟全螢幕大圖 |
| 5 | 選取項目變更時同步更新全螢幕畫布 | 如果全螢幕正開著，切換挑選器/顯示層級/選取項目時，全螢幕那張圖也要跟著更新，不能只更新看不到的背景小圖 | 用 `modalOpen` 旗標追蹤全螢幕開關狀態，重繪時判斷是否要同步呼叫 `renderNetwork("networkModalCanvas", true)` |
| 6 | JSON/CSV 下載 | 下載目前選取項目的關聯資料 | `#downloadJsonBtn` / `#downloadCsvBtn` |
| 7 | 網絡圖每層節點數量可調整 | 下拉選單調整每層最多顯示幾個節點，**預設選中的數字要讀取後台可設定的參數**，不能寫死在前端程式碼裡（改動還要重新部署才生效） | `#maxTargetsSel` / `#maxIngSel` / `#maxHerbSel`，`buildGraphData()` 讀選單的值；預設值透過 `GET /system-settings/graph-limits` 取得（管理者在「系統設定」頁面用數字輸入框設定，不是寫死的下拉選項），`ensureOptionAndSelect()` 負責把管理者設定的值動態加進選單並選中 |
| 8 | 顯示層級勾選（全螢幕內也要有） | 可以勾選/取消每一層要不要顯示（例如 Related Targets／Related Ingredients／Related Herbs），逐層關係，關掉上層自動關閉並鎖定下層；**主畫面跟全螢幕 Modal 都要有各自一份勾選框，但共用同一份狀態** | `#layerXxx` / `#modalLayerXxx` 一組 checkbox，`layerVisibility` 物件記錄狀態，`onLayerChange()` 處理連動鎖定，改變後要重算 `currentRelated`（依層級篩選過的資料）並重繪表格＋兩份網絡圖 |
| 9 | 欄寬可拖曳調整 | 表格每一欄右側邊界可以拖曳調整寬度，切換分頁籤時要記住各分頁籤自己的欄寬 | `.col-resizer`（每個 `<th>` 內插入的拖曳把手），`colWidths = { tabName: [w0, w1, ...] }`，`makeColumnsResizable()` 在每次 `renderTable()` 結尾呼叫 |
| 10 | 上下邊界（關聯圖／表格高度比例）可拖曳調整 | 網絡圖跟下方表格中間有一條可以上下拖曳的把手，調整兩者的高度比例 | `#netResizeHandle`，`initNetworkResize()` 只需要呼叫一次（頁面初始化時），用 `mousedown`/`mousemove`/`mouseup` 控制 `#network` 的 `style.height` |
| 11 | 版面配置命名儲存/套用/刪除 | 把目前的欄寬設定＋關聯圖高度存成一個有名字的版面，之後可以下拉選單套用或刪除 | `LAYOUT_STORAGE_KEY`（**每個查詢站要用不同的 key**，例如 `disease_query_layout_presets_v1`，避免三站互相覆蓋），存在 `localStorage`，`#layoutPresetSelect` / `#applyLayoutBtn` / `#layoutNameInput` / `#saveLayoutBtn` / `#deleteLayoutBtn` |
| 12 | 空白狀態提示 | 尚未選擇項目時顯示的提示文字 | `#emptyState`，**必須是跟 `#xxxHeader`／`#bodyWrap` 平行的兄弟元素**，見下一節的重要規範 |

### 後台可設定的查詢站參數

「系統設定」頁面的「查詢站關聯網絡圖：節點數量上限預設值」卡片，用**數字輸入框**（不是預先寫死的下拉選項）設定三個查詢站共用的網絡圖節點數量上限預設值：

- `graph_limit_level1`：第一層（例如每個藥材/疾病/基因最多顯示幾個靶點）
- `graph_limit_level2`：第二層（例如每個靶點最多顯示幾個成分）
- `graph_limit_level3`：第三層（例如每個成分最多顯示幾種藥材）

對應 API：`GET/PUT /system-settings/graph-limits`（沿用 `SystemSetting` 通用 key-value 機制，PUT 僅限管理者，數值需介於 1~9999）。**這幾個數字不應該再寫死在任何前端程式碼裡**——之前寫死「3」導致 BRCA1 的 12 種藥材被裁到只剩 3 個顯示，這是真實發生過的 bug（v1.21.1），所以才改成這樣可設定的架構。

## 五之一、查詢站類頁面（左側清單／右側詳情）的結構規範

TCMSP 藥材查詢站、疾病查詢站、暗黑基因查詢站都用「左側清單、右側詳情」版面。這種頁面的空白提示元素（`#emptyState`）**絕對不能巢狀放在會被整段覆寫的容器裡**（例如 `#xxxHeader`）。

**已經踩過兩次的真實 bug**（v1.17.2 疾病查詢站、v1.20.1 暗黑基因查詢站）：把 `#emptyState` 寫成 `#xxxHeader` 的子元素，第一次選擇項目時，程式碼把 `#xxxHeader.innerHTML` 整個換成標題內容，連帶把巢狀在裡面的 `#emptyState` 一起刪除。之後任何一次呼叫「選取項目」的函式，只要函式一開頭想去隱藏 `#emptyState`（`document.getElementById("emptyState").style.display = "none"`），就會因為元素已經不存在而拋出例外中斷，導致「點第二個以後的項目完全沒反應」。

**規則**：`#emptyState` 必須跟 `#xxxHeader`／`#bodyWrap` 設計成平行的兄弟元素，不要巢狀在任何會被 `innerHTML = ...` 整段覆寫的容器裡面。新增查詢站類頁面時，這是第一件要檢查的事。

## 五、待補強事項

- 目前非管理者角色的權限，都要手動一個一個在角色管理頁面勾選 `can_view`，沒有「新增功能自動給某角色權限」的機制（除了種子資料裡「一般使用者」角色會自動拿到所有 `show_frontend=true` 的功能）
- 個別頁面內的按鈕/操作層級權限（`can_execute`）目前後端已有機制（`require_permission()`），但前端還沒有依此動態隱藏「編輯/刪除」按鈕，只是後端 API 會擋（按下去才會看到錯誤訊息），這個之後可以優化

## 六、配色主題系統

全站配色改用 CSS 變數 + `data-theme` 屬性設計，主題定義集中在 `frontend/css/style.css` 開頭：

```css
[data-theme="ocean"] { --primary: #2563a8; --primary-dark: #173f6b; ... }
```

- `frontend/js/theme.js`：每個頁面 `<head>` 都會載入，向後端查詢目前主題（`GET /system-settings/theme`，不需登入），套用到 `<html data-theme="...">`
- 管理者可在「系統設定」頁面（`system-settings.html`）切換主題，透過 `PUT /system-settings/theme`（僅管理者），全站立即套用（下次頁面載入生效）
- **新增主題**：在 `style.css` 加一組 `[data-theme="xxx"]` 覆寫變數，並在 `app/routers/system_settings.py` 的 `AVAILABLE_THEMES` 加一筆，兩邊都要改

## 七、導覽選單為開合式設計

`js/nav.js` 把「前台功能」「後台管理」各自渲染成可收合的區塊（點分區標題可以收合/展開），展開狀態記錄在瀏覽器 `localStorage`（依裝置/瀏覽器記憶，不是伺服器端設定）。如果目前所在頁面剛好在某個分區裡，該分區會強制展開，避免使用者迷失方向。

## 八、目前所有已建置的獨立頁面

| 頁面 | 對應功能代碼 | 說明 |
|---|---|---|
| `index.html` | - | 登入 / 申請新帳號 |
| `dashboard.html` | F0-13 | Dashboard（含 4 個可開關小工具） |
| `roles.html` | F0-2 | 角色管理（含權限矩陣，已整合全站功能設定） |
| `users.html` | F0-5 | 帳號管理 |
| `applications.html` | F0-4 | 帳號審核 |
| `pharmacies.html` | F5-1（含 F5-3 評價管理） | 中藥行管理 |
| `finder.html` | F5-2 | 中藥行地理推薦（前台） |
| `tcmsp_query.html` | F1-1 | TCMSP 藥材關聯查詢站 |
| `logs.html` | F0-11（含 F0-10 備份紀錄、F0-12 登入紀錄） | 稽核 / 登入 / 備份紀錄 |
| `architecture.html` | F0-1（含 F0-3、F0-9） | 系統架構規劃（渲染 rules.md） |
| `oauth-status.html` | F0-6 | 第三方登入整合狀態 |
| `security.html` | F0-7 | 資安規劃（施工中，列出規劃項目） |
| `reports.html` | F0-8 | 報表設計（施工中，列出規劃項目） |
| `system-settings.html` | F0-16 | 系統設定（配色主題切換） |
| `personal-settings.html` | F0-18 | 個人化設定（全站語系／查詢站配色） |
| `announcements.html` | F0-17 | 公告管理 |
| `patients.html` | F3-1 | 客戶資料管理（病患基本資料／就診紀錄，其餘基因體資料層待擴充） |
| `dark-genes.html` | F3-2 | 暗黑基因管理（癌症基因參考資料，可匯入 TSV／CRUD） |
| `darkgene_query.html` | F3-3 | 暗黑基因關聯查詢站（比照藥材/疾病站的左右分欄呈現） |
| `ginseng_darkgene.html` | F3-4 | 藥材與暗黑基因關聯（反向查詢：預設人參，可換其他藥材，Herb→Ingredients→Targets→Dark Genes） |
| `darkgene-stats.html` | F3-5 | 暗黑基因統計（依 Gene Type 統計有/無中藥靶點，欄位可點擊排序，三層下鑽：統計→基因清單→候選藥材） |
| `darkgene-herb-ranking.html` | F3-6 | 中藥暗黑基因覆蓋統計（以藥材為主，排行哪種藥材覆蓋最多不重複的暗黑基因） |
| `dna-data.html` | F3-7 | DNA 資料管理（檢體/匯入批次/變異 CRUD，多次匯入比較，暗黑基因紅字標註） |
| `dna-test-data.html` | F3-8 | DNA 測試資料產生（可選多位病患，可勾選是否含暗黑基因變異） |
| `dna-report.html` | F3-9 | DNA 檢測報告（單一病患報告，含醒目的非醫療建議警語） |
| `patient-dark-gene-ranking.html` | F3-10 | 病患基因統計排行（哪位病患命中最多不重複暗黑基因） |

> 有些功能代碼共用同一個頁面（例如 F0-10/F0-12 都指向 `logs.html`），這是刻意設計：避免導覽選單出現好幾個連到同一頁的重複連結。共用頁面的功能代碼會把 `show_frontend`/`show_backend` 都設為 `false`，只有「主要代表」該頁面的那個功能代碼會顯示在導覽選單裡，其餘的僅在權限矩陣表格裡顯示頁面路徑供對照。
