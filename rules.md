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
| 6.5 | 「載入全部」下載完成後，處理階段要分段 yield | 下載完成只是第一階段；後面的 `JSON.parse`／重建索引／統計數量並重繪整份清單，全部是同步運算，如果黏在一起做，使用者只會看到進度條卡在 100% 不動，直到全部做完才突然跳出結果，體感像當機。每個階段之間要呼叫 `await yieldToUI()` 讓瀏覽器有機會重繪，並個別更新進度文字（例如「正在解析資料...」→「正在建立索引...」→「正在統計數量並更新清單...」） | `yieldToUI()` = `() => new Promise(r => setTimeout(r, 0))`，`setProgress(100, 文字)` 後面接 `await yieldToUI()` 再做下一段耗時運算，這是 v1.27.2 修過的真實 bug（見 CHANGELOG） |
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

## 五之二、全站語系機制（繁中/簡中/英文/韓文）

`site_language` 個人化設定支援四種值：`tw`（繁體中文，原文，不轉換）／`cn`（簡體中文，OpenCC 字形轉換）／`en`（English，字典比對翻譯）／`ko`（한국어，字典比對翻譯）。

- **tw**：原始語言，`applySiteLanguage('tw')` 不做任何轉換，不需要檢查
- **cn 用 OpenCC**：不管什麼句子都能轉，不需要維護字典，**理論上涵蓋所有文字（包括頁面載入後才動態產生的內容）**，是四種語系裡覆蓋率最完整的一種
- **en/ko 用字典比對**：`frontend/js/i18n-dict.js` 裡維護 `window.I18N_DICT.en` / `window.I18N_DICT.ko`，用「整段文字完全比對」的方式查表替換，**文字裡混著動態資料的句子（例如「共 502 種藥材」）字典比對不到，會維持繁體中文原文**，這是設計限制不是 bug
- 新增頁面要支援全站語系，記得在 `<script src="js/site-lang.js">` 前面加上 `<script src="js/i18n-dict.js">`，並確認頁面有掛載 `js/nav.js`（全站語系是靠 `nav.js` 呼叫 `loadAndApplySiteLanguage()` 觸發的）
- 要擴充英文/韓文覆蓋率，直接往 `i18n-dict.js` 加詞條即可，不用動 `site-lang.js` 的邏輯
- 登入頁（`index.html`）有自己獨立一份精簡版轉換邏輯（`login.js`），因為登入頁在使用者登入前，不能呼叫需要驗證的 `/user-preferences` API，語系選擇先存在 `localStorage`（`tcm_login_lang`），登入成功後才會呼叫 `PUT /user-preferences/site_language` 存回帳號的個人化設定
- **句子中間包著 `<b>`／`<a>` 等標籤時，瀏覽器會把文字拆成好幾段獨立的文字節點**（標籤前、標籤內、標籤後各一段），字典詞條要照這個方式分段建立，不能把整句話當一個詞條，不然完全比對不到、不會翻譯（v1.28.6 踩過這個問題）

### 上版前的強制檢查規則（v1.29.0 起）

**只要這次上版有新增頁面或修改既有頁面的文字內容，一律要檢查全部四種語系**，不能只測其中一種就出貨（韓文測過不代表英文也沒問題，過去發生過兩者覆蓋率不一致的情況）。檢查方式：

1. **靜態文字覆蓋率掃描**：用 Python `HTMLParser` 模擬瀏覽器 `TreeWalker` 的行為，把每個有掛載 `js/nav.js` 的頁面裡 `<script>`/`<style>` 以外的文字節點依標籤邊界切開，比對 `i18n-dict.js` 裡 `en`／`ko` 兩個區塊分別收錄了哪些詞條，找出「有中文字元、但字典裡沒有」的缺漏，兩種語言都要跑，**確認兩者缺漏數一致（理想上都是 0）**——這套掃描邏輯已經在 v1.29.0 開發過程用過，之後可以重複使用同樣的做法（不是現成的腳本檔案，需要每次照這個邏輯重新寫，因為目前沒有把它存成一支可重複執行的工具）
2. **功能性模擬測試**：用模擬瀏覽器環境（jsdom + vm），對新增/修改的頁面實際套用四種語系，確認：
   - `tw`：內容完全不變動
   - `cn`：抽樣文字用 OpenCC 轉換後結果正確，且沒有卡死（避免無窮迴圈風險，見下方 v1.28.2 教訓）
   - `en`／`ko`：關鍵文字正確翻譯出來，且兩者翻譯完整度一致
3. 有缺漏就照第一次做 v1.29.0 補齊的方式：找出缺漏詞條 → 撰寫對應語言翻譯 → 寫入 `i18n-dict.js` 對應區塊（`en:` 和 `ko:` 兩處都要加，成對加入避免覆蓋率不一致）→ 重新掃描確認缺漏歸零

### 重大教訓（v1.28.2）：MutationObserver 無窮迴圈

`site-lang.js` 用 MutationObserver 監看文字變化並即時翻譯，**修改 `node.nodeValue` 前一定要先判斷新舊值是否相同，不同才賦值**（`if (converted !== node.nodeValue) node.nodeValue = converted;`）。如果不管值有沒有變都賦值，賦值動作本身會被同一個 observer 判定為新的異動、又觸發一次轉換又賦值，形成無窮迴圈，把瀏覽器分頁直接卡死（跳出「網頁無回應」）。這個問題只有 en/ko（字典比對）跟 cn（OpenCC）這種需要「修改內容」的語系會踩到，tw 因為不做任何修改不受影響。**之後如果要修改 `site-lang.js` 的轉換邏輯，這個「先比對再賦值」的防護一定要保留**，不要為了效能或簡化程式碼把它拿掉。

## 五之一、查詢站類頁面（左側清單／右側詳情）的結構規範

TCMSP 藥材查詢站、疾病查詢站、暗黑基因查詢站都用「左側清單、右側詳情」版面。這種頁面裡任何**需要跨次渲染持續存在的元素**（空白提示 `#emptyState`、載入進度條、統計文字等）**絕對不能巢狀放在會被整段覆寫的容器裡**（例如 `#xxxHeader`、`#main`）。

**已經踩過三次的真實 bug**（v1.17.2 疾病查詢站、v1.20.1 暗黑基因查詢站、v1.27.x 藥材查詢站的載入進度條）：把這類元素寫成 `#xxxHeader`／`#main` 的子元素，第一次選擇項目時，程式碼把容器的 `innerHTML` 整個換掉，連帶把巢狀在裡面的元素一起刪除。之後任何一次想操作這個元素（例如 `document.getElementById(...).style...`），就會因為元素已經不存在而拋出例外中斷，導致功能整個壞掉（輕則「點第二個以後的項目沒反應」，重則像進度條這種每次操作都會用到的元素，只要選過一次任何項目就永久失效）。

**規則**：這類元素必須跟 `#xxxHeader`／`#bodyWrap` 設計成平行的兄弟元素，放在頁面裡「不會被覆寫」的固定位置（例如左側面板、或跟 `#main` 同層），不要巢狀在任何會被 `innerHTML = ...` 整段覆寫的容器裡面。新增/修改查詢站類頁面時，先列出「這個元素要不要在容器被覆寫後還能用」，再決定它該放在哪裡，這是第一件要檢查的事。

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
