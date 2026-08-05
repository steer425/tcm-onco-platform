# 版本更新紀錄（tcm_backend）

## v1.17.1 — 2026-08-05（修正進度條卡在 0%，新增預設藥材/疾病後台設定，疾病站同步支援漸進式載入）

### 1. 修正「載入全部」進度條卡在 0% 的真正原因

前端與後端分屬不同網域（Cloudflare Pages / Render），瀏覽器基於安全性，跨網域請求**預設不會把 `Content-Length` 這類回應標頭公開給 JavaScript 讀取**，除非伺服器明確在 CORS 設定裡加上 `Access-Control-Expose-Headers`。這導致進度條算式裡的「總大小」永遠是 0，一直停在「載入中...0%」，看起來像當機。

- `app/main.py` 的 CORS 設定加上 `expose_headers=["Content-Length"]`
- 前端同步強化：就算真的拿不到總大小，也會改顯示「已下載 X MB」而不是卡住不動，避免再次看起來像當機

### 2. 新增「預設藥材」「預設疾病」後台設定

- 系統設定頁面新增「查詢站預設項目」卡片：可搜尋並選擇 TCMSP 藥材／疾病查詢站首次載入要顯示的預設項目，取代原本寫死搜尋「Ginseng」／清單第一筆的邏輯
- 後端新增 `GET/PUT /system-settings/default-herb`、`GET/PUT /system-settings/default-disease`
- 查詢站左側清單現在**只顯示預設項目**（不再列出全部 502/564 筆），要找其他項目直接搜尋即可（清單名稱本身已全部載入，搜尋不受影響），或按「載入全部」看完整清單

### 3. TCMSP 疾病關聯查詢站也補上漸進式載入

比照藥材站的做法：

- 新增輕量後端端點：`GET /tcmsp/diseases/public/list`、`GET /tcmsp/diseases/public/{dis_id}/detail`
- 首次載入只抓疾病清單 + 預設疾病的完整關聯資料，其餘疾病點擊時隨選載入
- 新增「載入全部」按鈕與即時下載進度條

### 已知限制

- 疾病站的單一疾病詳情端點，最差情況（例如靶點連結到上千個成分時）回應可達約 1.7MB，雖然仍比完整 11.6MB 資料集小很多，但沒有藥材站的單一藥材詳情（通常僅數十~數百 KB）那麼輕量——這是資料關聯本質上的差異（單一靶點可能連結全資料庫上千種成分），非程式邏輯問題

## v1.17.0 — 2026-08-05（查詢站效能優化、繁簡切換、淺色/深色主題與個人化設定）

### 1. TCMSP 藥材關聯查詢站載入效能大幅優化

- 新增輕量後端端點：`GET /tcmsp/herbs/public/list`（僅藥材清單，~0.1秒）、`GET /tcmsp/herbs/public/{herb_id}/detail`（單一藥材完整關聯資料，~0.07秒）
- **首次載入只抓藥材清單 + 人參詳情**，不再一次下載全部 502 種藥材的完整關聯資料（原本要等 5 秒以上）
- 點擊清單裡任何其他藥材時，會自動隨選載入該藥材的資料（同樣很快），瀏覽過的藥材會快取在記憶體不重複請求
- 新增「載入全部」按鈕：需要一次拿到全部資料時（例如離線使用、批次分析）可以手動觸發，並顯示**即時下載進度條**（實際位元組進度，非假動畫）

### 2. 動態進度條

- 頁面右側空白狀態下方新增進度條，「載入全部」下載過程中即時顯示百分比與已下載/總大小（MB）

### 3. 繁體中文／簡體中文切換

- 兩個查詢站都新增語系下拉選單（搜尋欄位旁），透過 OpenCC-JS 即時轉換：藥材/疾病/分類中文名稱、網絡圖節點文字、節點詳情面板，全部套用選定的字形
- 選擇會記住在瀏覽器（localStorage），不需要每次重新選
- 疾病站的網絡圖節點文字與「中文名稱」欄位，現在優先使用資料庫裡真實的 `disease_cn_name`（v1.15 已 100% 覆蓋），取代原本只有 116 筆的舊靜態字典

### 4. 淺色／深色主題 + 個人化設定（新功能）

- 兩個查詢站新增 `body[data-page-theme="light"]` 淺色主題樣式，覆蓋原本固定的深色主題
- 新增「個人化設定」頁面（F0-18，任何登入帳號都能使用，不受角色權限限制），目前有「關聯查詢站 CSS 設定」一項（深色/淺色）
- 查詢站頂部導覽列也新增「🌗 切換淺色/深色」快速按鈕，不用特地跳頁面
- 設定儲存在新增的 `user_preferences` 資料表（依帳號各自獨立），**只影響自己看到的畫面，不影響其他使用者**；下次登入會自動套用上次的選擇
- 後端新增 `GET/PUT /user-preferences/{key}` API，通用 key-value 設計，之後要加其他個人化設定項目可以直接沿用

### 部署注意事項

需要重新執行遷移腳本（回填新增的 F0-18 功能項目；`user_preferences`／`announcements` 等全新資料表會在一般啟動流程自動建立，不需要遷移腳本處理）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

### 已知限制

- 淺色主題目前是手動撰寫的覆寫樣式，涵蓋頁面上大部分區塊，但少數較少見的元素（例如照片彈出視窗某些邊角）可能還是深色配色殘留，之後發現可以再補
- OpenCC-JS 透過外部 CDN（jsdelivr）載入，如果使用者網路環境擋掉該網域，語系切換會直接原樣顯示文字（不會壞掉，只是不會轉換），不影響其他功能

## v1.16.1 — 2026-08-05（修正全螢幕檢視時顯示層級勾選無反應的問題）

### 問題

在全螢幕檢視關聯網絡圖時，勾選/取消「顯示層級」（Related Targets/Ingredients/Herbs）或調整節點數量下拉選單，畫面沒有任何變化。原因是重繪邏輯寫死只更新背景那個小的網絡圖容器（`network`），沒有同步更新全螢幕模式實際顯示的畫布（`networkModalCanvas`），所以狀態其實有正確改變，只是使用者看不到畫面更新。

### 修正

- 新增 `modalOpen` 狀態旗標，追蹤全螢幕檢視目前是否開啟
- 顯示層級勾選、節點數量下拉選單變更時，如果全螢幕檢視正開著，會同步重繪 `networkModalCanvas`，不會再只更新看不到的背景小圖

## v1.16.0 — 2026-08-05（疾病查詢站補齊與藥材查詢站對等的互動功能）

### 新增功能

「TCMSP 疾病關聯查詢站」原本只是精簡版，這次補齊跟「TCMSP 藥材關聯查詢站」對等的核心互動功能：

- **靶點挑選器**：左側新增可勾選的 Related Targets 清單（對應藥材站的成分挑選器），每個項目顯示關聯成分數量
- **挑選器工具列**：全選靶點／全不選／只選有成分資料／只選有藥材資料／「顯示 Selected」套用按鈕（顯示目前套用筆數）
- **顯示層級勾選**（Related Targets／Related Ingredients／Related Herbs）：逐層關係，關掉上層會自動一併關閉並鎖定下層，主畫面與全螢幕檢視共用同一套規則與狀態
- **網絡圖節點數量可調整**：每層最多顯示幾個靶點/成分/藥材，透過下拉選單即時調整（原本是寫死的數字）
- **全螢幕檢視點擊節點看詳情**：點任何節點（疾病/靶點/成分/藥材）會在右側面板顯示該節點詳細欄位
- 表格內容會反映目前挑選器＋顯示層級的篩選結果，不是固定顯示全部

### 已知限制（相較藥材站，這次沒有做的部分）

- 沒有做欄寬/圖表高度的拖曳調整與「儲存版面配置」功能
- 沒有做成分數值篩選（MW/OB%/DL/ALogP 等門檻篩選），因為疾病站的挑選對象是「靶點」而非「成分」，數值篩選的適用性較低
- 沒有做圖上文字語言切換（繁体/简体/English），因為靶點與成分目前資料庫裡沒有中文名稱欄位（只有疾病與藥材有），語言切換的效果有限，之後如果靶點/成分也建立中文名稱欄位，可以再補上

## v1.15.2 — 2026-08-05（修正遷移腳本：ALTER 語句連坐失敗導致新欄位從未真正建立）

### 問題

使用者實測回報 `disease_cn_name` 欄位在 Neon 上仍然不存在，即使已經執行過 `migrate_schema.py` 並看到「完成」訊息。追查 Render 日誌發現真正原因：**所有 `ALTER TABLE` 語句原本共用同一個資料庫交易**，PostgreSQL 的交易機制是「一句失敗，同一交易裡後面所有語句都會被連坐拖累失敗」（錯誤代碼 `InFailedSqlTransaction`）——只要清單裡第一句（例如 `enabled` 欄位已存在）失敗，後面真正需要新增的欄位（包括這次的 `disease_cn_name`）就永遠不會真的執行到，即使腳本最後仍印出「完成」字樣，掩蓋了這個問題。

### 修正

- `app/migrate_schema.py`：每一句 `ALTER TABLE` 改為**各自獨立的資料庫交易**（獨立的 `engine.begin()`），一句失敗不會再拖累其他語句
- 已在本機重複執行兩次驗證：腳本能正常跑完，不會中途崩潰

### 部署注意事項

這次修正的是遷移腳本本身，**請重新執行一次遷移指令**，這次應該會看到 `disease_cn_name` 欄位真正被建立：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

接著重新執行匯入指令拿到完整的疾病中文翻譯：

```bash
python -m app.import_tcmsp_data data_import/tcmsp_data.json
```

## v1.15.1 — 2026-08-05（補齊全部 564 種疾病的中文翻譯，覆蓋率 100%）

### 新增內容

- `data_import/disease_cn_name_seed.json` 從 116 筆擴充到 **564 筆（全部疾病）**，翻譯依標準醫學術語逐筆處理
- 已重新匯入本機測試資料庫驗證：564 筆疾病、564 筆有中文名稱，覆蓋率 100%

### 已知限制

- 這批翻譯是一次性人工整理，未經專業醫學審定；如果之後發現不夠精準或有更通用的譯名，可以直接到「疾病中文名稱管理」頁面（F1-3）逐筆修正——修正後即使重新執行匯入腳本也不會被覆蓋（v1.15.0 已建立的保護機制）
- 少數罕見疾病、症候群、遺傳學專有名詞（例如 `DIS01001` 血型系統類目、`DIS01011` 未明確命名的症候群）維持較直譯或保留原文縮寫的翻法，之後如有更精確的中文醫學名詞可以再更新

## v1.15.0 — 2026-08-05（疾病中文名稱：資料庫欄位 + 後台管理頁面）

### 新增功能

- `tcmsp_diseases` 資料表新增 `disease_cn_name` 欄位
- 從原本「TCMSP 藥材關聯查詢站」內建的靜態翻譯字典，抽取出 **116 筆**既有的疾病中文翻譯，改為正式匯入資料庫作為初始種子資料（`data_import/disease_cn_name_seed.json`），不再只是寫死在前端 JS 裡
- 新增後台管理頁面 `tcmsp-diseases.html`（F1-3，疾病中文名稱管理）：可搜尋、篩選「尚無中文名稱」的項目、逐筆編輯中文名稱與備注
- 新增後端 API：`GET /tcmsp/diseases`、`PUT /tcmsp/diseases/{dis_id}`
- 「TCMSP 疾病關聯查詢站」左側列表、詳情標題、網絡圖節點，都會優先顯示中文名稱（沒有翻譯的疾病維持顯示英文名稱）
- **重新匯入保護機制**：`app/import_tcmsp_data.py` 匯入前會先備份既有的疾病中文名稱，重新執行匯入腳本（例如之後要更新 TCMSP 原始資料）不會洗掉管理者手動修正過的翻譯——已透過完整測試驗證此行為

### 部署注意事項

需要重新執行遷移腳本（新增 `disease_cn_name` 欄位、新功能項目 F1-3、回填種子翻譯資料）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

如果之前已經匯入過 TCMSP 資料，這次遷移只會回填「目前是空值」的疾病翻譯，不會覆蓋任何既有內容。如果想要一次拿到完整的 116 筆種子翻譯，也可以直接重新執行一次匯入腳本：

```bash
python -m app.import_tcmsp_data data_import/tcmsp_data.json
```

## v1.14.0 — 2026-08-05（新增 TCMSP 疾病關聯查詢站）

### 新增功能

- 新頁面 `disease_query.html`（F1-2）：與「TCMSP 藥材關聯查詢站」資料同源（同一個 `/tcmsp/data/full` API），但以**疾病**為查詢起點，左側改列出 564 種疾病，右側顯示反向關聯：Related Targets → Related Ingredients → Related Herbs
- 呈現方式與藥材查詢站一致：同樣的深色主題、KPI 統計卡片、分頁籤表格、Disease→Targets→Ingredients→Herbs 網絡關聯圖（可全螢幕檢視）、單一疾病 JSON/CSV 下載
- 後端不需要新增 API，直接複用既有的 `/tcmsp/data/full`，前端在瀏覽器端建立反向索引（`targetsByDisease`／`ingredientsByTarget`／`herbsByIngredient`）
- 登入後即可在導覽選單看到這個功能項目（前台），管理者可到「角色管理」的權限矩陣視窗調整哪些角色可以使用、要不要停用/顯示於前台或後台
- 網絡圖為避免節點過於密集，僅顯示部分節點（每個疾病最多 8 個靶點、每個靶點最多 4 個成分、每個成分最多 3 個藥材），完整清單仍可在下方表格查看

### 部署注意事項

需要重新執行遷移腳本（新增 F1-2 功能項目）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

## v1.13.6 — 2026-08-05（無角色帳號預設也能看到 Dashboard，不再是空白畫面）

### 問題

第三方登入（Google/Facebook）新建立的帳號經審核啟用後，如果沒有另外指派角色，會因為 `/nav/menu` 的邏輯「沒有角色 = 完全看不到任何功能」，登入後只看到一片空白（連 Dashboard 都看不到）。

### 修正

- `app/routers/nav.py` 新增 `BASELINE_CODES`（Dashboard 本體 + 5 個小工具）：這些項目只要帳號是登入中的有效狀態就一定看得到，不需要額外指派角色或權限矩陣設定，作為全站的保底落地頁
- 其餘功能（角色管理、中藥行管理等）仍然完全依角色權限矩陣控制，這次修正不影響既有的權限管控

## v1.13.5 — 2026-08-05（修正併發重複請求仍會撞到「授權碼已使用過」的問題）

### 問題

v1.13.4 加了授權碼重放快取，但使用者實測仍然出現同樣的錯誤。追查後發現 v1.13.4 的做法不夠：兩個重複的 callback 請求幾乎是**同時**進來的，各自檢查快取時都看到「還沒有結果」（因為對方也還沒寫入），於是兩邊都跑去跟 Facebook 交換 token，其中一個必然失敗。單純檢查快取擋不住這種併發競爭（race condition）。

### 修正

- 新增 `_get_oauth_code_lock()`：為每一組授權碼建立一個 `asyncio.Lock`
- `google_callback`／`facebook_callback` 用這個鎖把「檢查快取 → 交換 token → 寫入快取」整段包起來：第二個重複請求會**排隊等待**第一個請求完成，而不是同時衝去對 Facebook/Google 發請求；等鎖釋放後，第二個請求會直接讀到快取結果，不會再重新呼叫第三方 API
- 已透過模擬併發請求的測試驗證：兩個同時打進來的重複請求，確認只有一個會真正執行 token 交換

## v1.13.4 — 2026-08-05（修正 Facebook 登入「授權碼已使用過」的間歇性失敗）

### 問題

使用者實測時 Render 日誌顯示：`Facebook token 交換失敗：{"error":{"message":"This authorization code has been used."...}}`，但當下只操作了一次登入。追查後研判是 Facebook（或部分瀏覽器）的登入完成頁，在特定情境下會**觸發兩次**跳轉回我們的 `callback` 網址、帶著同一組授權碼——授權碼是一次性的，第一次成功交換後，第二次必然會被 Facebook 判定「已使用過」而失敗，使用者只會看到失敗那一次的畫面。

### 修正

- `google_callback`／`facebook_callback` 新增授權碼重放快取（`_cache_oauth_result` / `_get_cached_oauth_result`）：同一組授權碼在 60 秒內重複進來時，直接回放第一次成功的登入結果，不會再重新跟 Google/Facebook 交換 token，自然也不會撞到「已使用過」的錯誤
- 附帶好處：避免了重複的 `login_log`／稽核紀錄寫入

### 已知限制

- 這組快取一樣是伺服器記憶體內的暫存（規模很小、生命週期只有 60 秒，風險遠低於先前的 CSRF state 問題），如果兩個重複請求剛好落在 Render 重新部署交接的新舊程序上，快取不會共享，理論上還是可能重現這個錯誤，但機率非常低（需要「重複請求」與「部署交接」兩個時間窗口疊在一起）

## v1.13.3 — 2026-08-05（登入頁第三方登入按鈕加上重試機制，因應 Render 冷啟動）

### 問題

使用者回報登入頁完全沒有顯示 Google/Facebook 登入按鈕，看起來像「沒有整合第三方登入」。實際原因是 Render 免費方案閒置一段時間會休眠，喚醒需要 30~60 秒；登入頁載入當下如果後端還在睡，查詢 `/auth/google/enabled`／`/auth/facebook/enabled` 的請求會直接失敗，而原本的程式碼是「查詢失敗就悄悄不顯示按鈕」，沒有任何提示或重試，容易誤導使用者以為功能不存在或設定遺失。

### 修正

- `frontend/js/login.js` 的 `checkOAuthEnabled()` 改為查詢失敗時每 8 秒重試一次，最多重試 6 次（涵蓋 Render 冷啟動最長約 1 分鐘的喚醒時間）
- 第一次查詢失敗時，登入頁會顯示提示文字「第三方登入服務啟動中，請稍候...」，查到結果或重試次數用盡後自動隱藏
- 不影響一般帳號密碼登入，這段邏輯全程都是非阻塞的背景查詢

## v1.13.2 — 2026-07-31（第三方登入失敗時記錄實際錯誤訊息）

### 問題

Google／Facebook 登入若在「交換 token」這步失敗，畫面只會顯示通用的「與第三方服務交換登入憑證失敗」，實際上 Google/Facebook 回傳的詳細錯誤原因完全沒有被記錄下來，導致除錯時完全看不到問題出在哪。

### 修正

- `google_callback`、`facebook_callback` 在 token 交換失敗時，改為把 Google/Facebook 回應的實際錯誤內容印到伺服器日誌（`print`，會顯示在 Render 的 Logs 分頁），格式為 `[Google OAuth] token exchange failed: ...` / `[Facebook OAuth] token exchange failed: ...`
- 使用者看到的畫面訊息不變（仍是友善的通用訊息），但管理者現在可以到 Render 後台的 Logs 分頁查到具體原因（例如 redirect_uri 不匹配、client_secret 錯誤等）

## v1.13.1 — 2026-07-31（修正第三方登入「驗證逾時或失效」的真正原因）

### 問題

使用者實測 Facebook 登入時出現「登入驗證逾時或失效，請重新嘗試」，追查後發現根因：CSRF state 原本存在伺服器記憶體的 `set` 裡（v1.5.0 就存在的已知限制），Render 重新部署交接新舊程序時，登入請求（產生 state）跟回呼請求（驗證 state）如果剛好落在不同程序，新程序的記憶體是空的，驗證就會失敗——這不是使用者操作問題，是架構本身的限制在部署交接的時間點被踩到了。

### 修正

- `app/security.py` 新增 `create_oauth_state_token()` / `verify_oauth_state_token()`：CSRF state 改用簽章 + 短效期（5 分鐘）的 JWT token，驗證時純粹靠簽章與時效判斷，**不需要查任何伺服器端儲存狀態**，因此不受多程序/重新部署影響
- Google、Facebook 登入流程都改用這個新機制，移除原本的 `_oauth_states` 記憶體暫存
- 已通過測試：模擬「產生 state 的程序」與「驗證 state 的程序」是完全不同的程序（重新載入整個模組），驗證仍然正確通過

## v1.13.0 — 2026-07-31（Facebook OAuth 登入、Render 主機資訊連結改指向 Swagger）

### 新增功能

- **真正的 Facebook OAuth 登入**（比照 Google 的 Authorization Code Flow）：
  - `GET /auth/facebook/enabled`、`GET /auth/facebook/login`、`GET /auth/facebook/callback`
  - 新增 `app/oauth_facebook.py` 封裝 Facebook OAuth 網址建構與 token/使用者資訊交換邏輯
  - 登入頁新增「使用 Facebook 帳號登入」按鈕，僅在後端已設定 Facebook 金鑰時顯示
  - 帳號治理規則跟 Google 完全一致（首次登入建立待審核帳號、email 相同自動綁定既有帳號、帳號停用一樣會被擋下）
  - Google／Facebook 共用的登入綁定邏輯抽成 `_handle_oauth_login()`，避免重複程式碼
  - `render.yaml` 新增 `FACEBOOK_CLIENT_ID`／`FACEBOOK_CLIENT_SECRET`（`sync: false`，需於 Render 後台手動填入）、`FACEBOOK_REDIRECT_URI`
  - README 新增完整「Facebook OAuth 設定」章節，含 Facebook App 申請步驟
  - `oauth-status.html` 更新 Facebook 的串接狀態為「已完成」
- Dashboard「主機資訊」卡片的 Render 項目連結，從單純的網址改為直接開啟 Swagger API 文件頁（`/docs`）

### 部署注意事項

這次資料庫變動除了 `features` 表照常回填，還新增了 `OAuthProvider` enum 型別的 `facebook` 列舉值。**正式環境（Neon PostgreSQL）需要重新執行遷移腳本**，腳本已更新為會自動處理這個 enum 新增（SQLite 環境會自動略過這步，不影響本機測試）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

### 已知限制

- 部分 Facebook 帳號沒有綁定 email（例如手機號碼註冊），登入時會被系統擋下，因為帳號體系以 email 作為識別
- Facebook App 預設為「開發模式」，只有加到測試人員名單的帳號能登入，要開放一般大眾使用需要送 Facebook 審核（這部分需要你自己在 Facebook Developers 後台操作，程式碼已就緒）

## v1.12.1 — 2026-07-31（修正公告時區 bug，Dashboard 支援直接編輯版面）

### 問題與修正

**公告新增後不顯示在前台的真正原因**：`<input type="datetime-local">` 給的是瀏覽器「當地時間」字串，沒有時區資訊；前端原本直接把這串文字送給後端，後端會誤把它當成 UTC 時間比對，導致「現在」被誤判成還沒到（例如台灣時區 UTC+8，等於系統以為公告要 8 小時後才開始顯示）。修正為前端送出前用 `new Date(value).toISOString()` 轉換成正確的 UTC 時間字串。

### 新增功能：Dashboard 直接編輯版面

- Dashboard 頂部新增「🛠 編輯版面」按鈕（僅管理者看得到）
- 進入編輯模式後，每張卡片上方會出現工具列：
  - **顯示開關**：勾選/取消即時儲存（對應管理者視角的 `show_backend`）
  - **拖曳排序**：直接拖曳卡片調整順序，放開滑鼠自動儲存新順序（`sort_order`，同步影響「系統設定」頁面看到的排序）
- 編輯模式下，即使是目前被設定為隱藏的卡片也會顯示出來（半透明），方便管理者重新打開；離開編輯模式後恢復正常顯示規則

### 已知限制

- Dashboard 拖曳排序目前只有管理者看得到「編輯版面」按鈕，且排序共用同一組 `sort_order`（後台視角跟前台視角看到的順序相同），如果之後需要「前台/後台各自不同排序」，需要另外加欄位

## v1.12.0 — 2026-07-31（公告管理系統 + Dashboard 顯示規則簡化面板）

### 新增功能

- **公告管理系統（全新）**：
  - 後端新增 `Announcement`、`AnnouncementFile` 資料表；`AnnouncementFile` 內容以 base64 直接存資料庫，不依賴 Render 免費方案不持久的檔案系統
  - 後台 CRUD：新增/編輯/下架（軟刪除）/查詢公告，可設定開始/結束顯示時間，**時間到自動下架**（查詢時即時依 `start_at`/`end_at`/`status` 計算 `is_currently_visible`，不需要排程工作）
  - 歷史公告查詢：後台列表可篩選「目前顯示中」/「未顯示（含已過期/未開始/已下架）」/全部
  - 每則公告可上傳多個附件（單檔上限 5MB），可下載、可個別刪除
  - 新頁面 `announcements.html`（F0-17）
  - Dashboard 新增第五張卡片「公告」，顯示目前生效中的公告與附件下載連結，代碼 F0-13-5，走跟其他小工具一樣的前台/後台顯示規則機制
- **系統設定頁面新增「Dashboard 顯示規則」面板**：直接列出 5 張 Dashboard 卡片，逐一勾選「啟用/前台/後台」即可儲存，不用再繞去角色管理的權限矩陣視窗設定（角色管理那邊仍然保留同樣的編輯能力，兩處資料互通，改任一邊都會同步反映）

### 部署注意事項

需要重新執行遷移腳本（新增 `announcements`、`announcement_files` 資料表由一般啟動流程的 `create_all` 自動建立，不需特別處理；但 `features` 資料表需要回填新增的 F0-13-5、F0-17 兩筆功能項目）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

### 已知限制

- 公告附件用 base64 存資料庫，單則公告建議附件總大小不要超過幾 MB，避免公告列表 API 回應變大變慢（目前公告列表 API 本身不包含檔案內容，只有附件的檔名/大小中繼資料，下載才會真正讀取 base64 內容，所以列表效能不受影響，但資料庫本身儲存空間會累積）
- 沒有排程通知機制（例如公告快到期前提醒管理者），純粹是查詢當下即時判斷是否顯示

## v1.11.0 — 2026-07-31（補齊未完成功能頁面、開合式選單、可命名配色主題）

### 新增功能

- **補齊先前沒有頁面的功能項目**：
  - `architecture.html`：系統架構規劃（F0-1/F0-3/F0-9 共用，直接渲染 `rules.md` 內容）
  - `oauth-status.html`：第三方登入整合狀態總覽（F0-6，顯示 Google/Facebook/小紅書/WeChat 目前串接狀態）
  - `security.html`：資安規劃（F0-7，列出已完成與規劃中的資安項目）
  - `reports.html`：報表設計（F0-8，列出規劃中的報表項目）
  - `system-settings.html`：系統設定（F0-16，新頁面，見下方主題系統）
  - F0-10（資料庫備份與還原）、F0-12（登入紀錄查詢）、F5-3（評價管理）改為指向既有頁面（`logs.html`／`pharmacies.html`），避免重工也避免導覽選單出現重複連結
- **權限矩陣表格顯示完整頁面路徑**：角色管理的權限矩陣視窗，每個功能項目現在會標示 `frontend\xxx.html` 完整路徑，取代原本模糊的「頁面：xxx」
- **導覽選單改為開合式設計**：`js/nav.js` 把「前台功能」「後台管理」各自做成可收合區塊，展開狀態記在瀏覽器 `localStorage`；目前所在頁面所屬的分區會強制展開
- **可命名的配色主題系統**：
  - 新增 4 組主題（森林綠/海洋藍/暖橘/石墨灰），定義在 `frontend/css/style.css` 的 `[data-theme="xxx"]` 區塊
  - 新增 `SystemSetting` 通用 key-value 資料表，`GET/PUT /system-settings/theme` API（GET 不需登入，登入頁也能套用主題；PUT 僅限管理者）
  - 新增 `frontend/js/theme.js`，所有頁面 `<head>` 載入時套用目前主題
  - 管理者可在「系統設定」頁面即時切換主題，全站套用

### 部署注意事項

需要重新執行遷移腳本（新增了 `system_settings` 資料表，以及 F0-16 功能項目、既有功能項目的頁面路徑調整）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

## v1.10.0 — 2026-07-31（「功能項目管理」併入「權限矩陣」，移除重複頁面）

### 問題

角色管理的「權限矩陣」（設定單一角色的 can_view/can_execute）跟獨立的「功能項目管理」頁面（設定全站共用的 enabled/show_frontend/show_backend）都在管理同一份 `features` 資料，兩個入口容易搞混。

### 變更

- **移除** `frontend/features.html`、`frontend/js/features.js`，以及對應的導覽項目 F0-14
- **角色管理「權限矩陣」視窗整合為單一表格**：同時顯示、編輯「這個角色專屬」的可見/可執行權限，以及「全站共用」的啟用/前台/後台/導覽文字/排序設定，一次儲存
- 後端 `GET /roles/{id}/permissions`、`PUT /roles/{id}/permissions` 擴充：回傳與接受全站功能設定欄位（`enabled`/`show_frontend`/`show_backend`/`nav_label`/`page_url`/`sort_order`），PUT 時全站欄位只在有帶值時才更新，避免其他角色沒帶這些欄位時被意外清空
- `/features` 系列 API（GET/POST/PUT/DELETE）維持不變，供未來程式化管理使用

### 部署注意事項

需要重新執行遷移腳本，這次除了照常回填欄位，還會**清除既有資料庫裡的舊版 F0-14**（含它的角色權限紀錄）：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

## v1.9.1 — 2026-07-31（Dashboard 小工具支援前台/後台差異化顯示）

### 問題

v1.9.0 的 Dashboard 小工具只有單一「啟用」開關，管理者跟一般使用者看到的 Dashboard 小工具組合完全一樣，沒辦法個別設定「這張卡片只給管理者看」或「這張卡片只給一般使用者看」。

### 修正

- `frontend/js/dashboard.js`：改為依「目前登入者是否為管理者」，分別檢查小工具的 `show_backend`（管理者視角）或 `show_frontend`（一般使用者視角）欄位，決定卡片要不要顯示——同一個 Dashboard 頁面，管理者跟一般使用者現在可以看到不同組合的小工具
- `frontend/features.html` / `js/features.js`：開放小工具項目的「前台」「後台」勾選框（先前因為小工具沒有獨立頁面，這兩個勾選框被鎖住不能改）
- `app/feature_config.py`：小工具的 `show_frontend` / `show_backend` 預設值改為皆為 `True`（維持與 v1.8.0 一致的預設行為：兩種身分預設都看得到，管理者可再自行調整成不同組合）
- `rules.md` 更新「Dashboard 小工具」章節，說明小工具的 `show_frontend`/`show_backend` 語意跟一般頁面不同（不是「導覽選單分區」，而是「管理者視角 vs 一般使用者視角」）

### 部署注意事項

這次沒有新增資料庫欄位，但既有資料的預設值不對（v1.9.0 部署時已經把小工具的 `show_frontend`/`show_backend` 回填成 `False`）。**建議重新執行一次遷移指令**，它會依最新的 `feature_config.py` 重新回填：

```bash
$env:DATABASE_URL="你的 Neon 連線字串"
python -m app.migrate_schema
```

⚠️ 提醒：`migrate_schema.py` 的回填邏輯目前是「無條件覆寫」，如果之後在「功能項目管理」頁面手動調整過某些項目的顯示設定，重跑這支腳本會把那些手動調整覆蓋回設定檔的預設值。目前階段（尚未有正式使用者依賴自訂設定）重跑沒問題，之後如果要在正式環境保留管理者的自訂設定，這支腳本需要改成只回填「資料庫裡還沒有值」的欄位，而不是整批覆寫。

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
