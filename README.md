# TCM 中藥腫瘤篩選平台 — 目標零後台系統

**目前版本：v1.28.6**（已通過使用者本機測試審查並正式上版，詳見 [CHANGELOG.md](./CHANGELOG.md)）

本次交付內容：**目標零（帳號 / 角色 / 權限矩陣 / 帳號審核 / 第三方登入 / 稽核紀錄 / 備份紀錄 / 登入紀錄）** 後端 API + 對應前端頁面，以及登入後可見的 **Dashboard（施工中佔位頁）**。

## 一、如何在本機啟動測試

```bash
cd tcm_backend
python3 -m venv venv          # 建議使用虛擬環境
source venv/bin/activate       # Windows 用 venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

啟動後：

- 前端頁面：http://localhost:8000/app/index.html
- API 文件（Swagger）：http://localhost:8000/docs
- 資料庫：SQLite 檔案 `tcm_platform.db`，會在第一次啟動時自動建立於專案目錄下

**測試帳號**：`admin` / `0000`（系統啟動時自動建立，僅供本機測試，正式環境請務必更改密碼並移除此預設帳號建立邏輯）

## 二、已完成功能對照

| 功能清單項目 | 後端 API | 前端頁面 |
|---|---|---|
| 功能項目顯示控制（啟用/顯示前台/顯示後台，併入權限矩陣統一編輯） | `/features`（GET/POST/PUT/DELETE）、`/roles/{id}/permissions` | `roles.html`（權限矩陣視窗） |
| 動態導覽選單（依角色權限顯示前台/後台項目） | `/nav/menu` | `js/nav.js`（所有頁面共用） |
| F0-2 角色管理（新增/編輯/刪除/查詢，含查看角色底下帳號） | `/roles`, `/roles/{id}/users` | `roles.html` |
| 權限矩陣（can_view / can_execute） | `/features`, `/roles/{id}/permissions` | `roles.html`（權限矩陣 Modal） |
| 帳號管理（新增/編輯/刪除=軟刪除/查詢） | `/users` | `users.html` |
| 帳號申請審核 | `/auth/apply`, `/account-applications` | 登入頁申請 Modal、`applications.html` |
| 第三方登入綁定（Google/小紅書/WeChat，骨架） | `/oauth-accounts` | 尚未做前端頁面（見待辦） |
| 稽核紀錄（僅查詢+備注，不可刪除/修改） | `/audit-logs` | `logs.html` |
| 登入紀錄（IP、裝置識別、登入/登出時間、停留秒數） | `/login-logs`，登入/登出時自動寫入 | `logs.html` |
| 資料庫備份紀錄（骨架，尚未接實際備份程序） | `/backup-jobs` | `logs.html` |
| Dashboard（登入後可見，施工中佔位） | `/dashboard` | `dashboard.html` |
| F5-1 中藥行管理（後台） | `/pharmacies`, `/pharmacies/{id}/reviews`, `/pharmacy-reviews/{id}` | `pharmacies.html` |
| F5-2 中藥行地理推薦（前台） | `/public/pharmacies`, `/public/pharmacies/{id}`, `/public/pharmacies/{id}/reviews` | `finder.html` |
| F5-3 評價新增/編輯/刪除（前台，使用者本人） | `/public/pharmacies/{id}/reviews`, `/public/reviews/{id}` | `finder.html` |

## 三、重要設計說明與限制

1. **軟刪除原則**：帳號刪除採軟刪除（標記為停用+原因），角色刪除為真刪除但要求底下無帳號；稽核紀錄、登入紀錄不提供刪除，以保留軌跡完整性。
2. **登入紀錄的「網卡編號」**：瀏覽器基於隱私限制，**無法取得使用者裝置的真實 MAC 位址**。目前以前端產生的裝置指紋字串（`device_id`）替代，作為同一裝置的識別依據，並非真實網卡編號，這點請留意與原始需求的落差，待確認是否有其他可接受的替代方案（例如企業內網才有的裝置管理系統）。
3. **第三方登入（Google/小紅書/WeChat）**：目前僅完成「綁定關係」的資料表與 CRUD 骨架（`/oauth-accounts`）。真正的 OAuth 授權流程（跳轉、取得 code、換 token）需要各平台的 client id/secret 與已核准的回呼網址，這部分仍在先前列出的「待確認事項」中（小紅書/WeChat 開發者資格尚待查證）。
4. **資料庫備份**：目前僅提供備份「紀錄」的查詢與手動登錄 API，尚未串接實際的自動備份程序（例如排程 + 資料庫匯出 + 異地備援），待技術選型確認後再串接。
5. **權限矩陣的判斷邏輯**：帳號若擁有「管理者」角色，一律視為擁有全部權限；一般角色則依 `role_permissions` 表中的 `can_view` / `can_execute` 判斷。此判斷邏輯目前只用在後端 `require_permission()` 這個共用 dependency 上，尚未套用到所有既有 API（本次僅示範於帳號/角色/權限相關 API 皆為「僅限管理者」）——後續其他模組開發時，可依此框架依 F-code 掛上對應的權限檢查。

## 四、待辦（下一步建議）

- [ ] 第三方登入前端頁面 + 實際 OAuth flow 串接（待開發資格確認）
- [ ] 密碼強度規則、帳號鎖定（連續登入失敗）機制
- [ ] JWT 撤銷/黑名單機制（目前登出僅記錄登出時間，token 本身在到期前仍可使用，屬已知限制）
- [ ] 自動化測試（pytest）覆蓋所有 API
- [ ] 部署腳本與正式環境設定（環境變數管理 SECRET_KEY、資料庫改為 PostgreSQL 等）

## 四之一、Windows 批次檔：加快每次更新本機資料夾與推送到 GitHub 的流程

每次收到新版本 zip，解壓縮後，資料夾裡固定會附上這兩個批次檔（`.bat`），直接雙擊執行即可，不用每次手動打指令：

### `update_local_folder.bat`

把「這次解壓縮出來的新版本」同步覆蓋到 `D:\tcm_backend`：

- 用 `robocopy /MIR` 做鏡像同步，**保留 `.git` 資料夾**，不會影響 git 版本控制歷史
- 除了 `.git` 之外，`D:\tcm_backend` 裡「這次新版本沒有的檔案」會被刪除，讓資料夾內容跟這次交付的版本完全一致——如果你在裡面有自己額外放的檔案（例如本機測試用的 `.db`、`.env`），建議先自行備份
- 執行前會先列出來源/目的地路徑並要求輸入 `Y` 確認，不會不小心誤觸

### `git_push.bat`

依序執行 `git add .` → `git commit -m "..."` → `git push`：

- 直接雙擊執行：使用批次檔裡預先寫好、對應這次版本的提交訊息
- 或是自己開命令提示字元帶自訂訊息執行：`git_push.bat "自訂的提交訊息"`
- 固定會先切換到 `D:\tcm_backend` 再執行 git 指令，如果專案資料夾不是放在這個路徑，要修改批次檔開頭的 `PROJECT_DIR` 設定
- 一樣會先列出提交訊息並要求輸入 `Y` 確認

### 建議的更新流程

1. 收到新版本 zip，解壓縮到任意資料夾（不用直接解壓縮到 `D:\tcm_backend`）
2. 雙擊解壓縮出來的 `update_local_folder.bat` → 輸入 `Y` → 完成後 `D:\tcm_backend` 就是最新版本
3. 雙擊 `git_push.bat` → 輸入 `Y` → 完成後就推送到 GitHub 了，Render／Cloudflare 會自動偵測部署

## 五、部署到 Render（後端 API 上線）

本專案已附上 `render.yaml`，可直接用 Render 的「Blueprint」功能一鍵讀取設定並部署。

### 步驟

1. 前往 https://render.com 註冊/登入（可以直接用 GitHub 帳號登入，比較快）
2. 右上角 **New +** → 選擇 **Blueprint**
3. 選擇要連接的 GitHub repo：`steer425/tcm-onco-platform`
   - 如果是第一次連接，Render 會要求安裝 GitHub App 並授權存取這個 repo（只需授權這一個 repo 即可，不用給全部 repo 權限）
4. Render 會自動讀到專案裡的 `render.yaml`，顯示即將建立的服務 `tcm-onco-backend`，確認後點 **Apply**
5. 等待幾分鐘讓它跑完 `pip install` 並啟動，狀態變成 **Live** 就代表部署成功
6. 部署完成後，Render 會給你一個網址，格式類似：
   ```
   https://tcm-onco-backend.onrender.com
   ```
   把這個網址記下來，等一下要填到前端的 `API_BASE`

### 部署後驗證

打開瀏覽器輸入：
```
https://tcm-onco-backend.onrender.com/docs
```
如果看到 Swagger API 文件頁面，就代表後端已經成功在線上運作。

### ⚠️ 重要限制：免費方案的資料庫問題

Render **免費方案的檔案系統是「暫時性」的**：
- 每次重新部署（push 新程式碼）、或服務閒置一段時間被喚醒時，**SQLite 資料庫檔案（`tcm_platform.db`）會被重置成初始狀態**（只剩下 seed 產生的預設管理者帳號跟範例中藥行資料，之前建立的角色/帳號/評價等資料都會消失）
- 這對「本機測試」沒問題，但**正式上線給真實使用者用之前，必須換成雲端資料庫（例如 Render 提供的付費 PostgreSQL，或其他雲端 MySQL/PostgreSQL 服務）**，否則資料會不斷遺失
- 這件事已列入待辦事項，等你確認要正式上線的時間點，我再協助把 `app/database.py` 改接 PostgreSQL

### 環境變數說明

`render.yaml` 已設定 `TCM_JWT_SECRET` 由 Render 自動產生一組隨機值（比程式碼裡預設的 `dev-secret-change-me-in-production` 安全），不需要手動填寫。

## 六、Cloudflare Pages 前端串接（部署後端之後再做）

後端在 Render 上線、拿到網址後，需要：

1. 修改 `frontend/js/api.js` 裡的 `API_BASE`，從空字串改成 Render 給的網址：
   ```js
   const API_BASE = "https://tcm-onco-backend.onrender.com";
   ```
2. 把 `frontend/` 這個資料夾內容部署到 Cloudflare Pages（在 Cloudflare Pages 專案設定裡，Build output directory 設為 `frontend`）
3. 回到後端 `app/main.py`，把 CORS 設定從允許所有來源（`allow_origins=["*"]`），改成只允許你的 Cloudflare Pages 網域，例如 `https://fwc-tcmsp.pages.dev`，安全性更好（此步驟屬於上線前建議，非必要但建議）

## 七、TCMSP 藥材關聯資料匯入（目標一/二）

v1.6.0 起，TCMSP 藥材關聯資料已改為存放在資料庫（不再是前端讀取的本機端 JSON 檔案），透過 `/tcmsp/data/full` API 提供。

### 首次建置或更新資料

原始資料檔放在 `data_import/tcmsp_data.json`（不會隨前端部署到 Cloudflare Pages，僅供匯入使用）。執行：

```bash
cd tcm_backend
python -m app.import_tcmsp_data data_import/tcmsp_data.json
```

這個腳本會清空既有 TCMSP 相關資料表後重新匯入，可重複執行（idempotent）。**正式環境（接了 Neon PostgreSQL 之後）也是執行同一個指令**，只是要先確保執行當下的 `DATABASE_URL` 環境變數有指向正式的雲端資料庫（可以在本機終端機用 `export DATABASE_URL=...` 暫時設定後再執行匯入指令，這樣腳本會連到雲端資料庫寫入，而不是本機 SQLite）。

### 後台管理

管理者可在後台查詢藥材列表、編輯備注、下架（軟刪除）藥材（下架後不會出現在前台查詢站）。成分/靶點/疾病/各類關聯表資料量龐大且屬於批次匯入的參考資料，目前不提供逐筆後台編輯，如需更新內容，請重新執行上述匯入腳本。

## 八、正式站／測試站分離（Staging 環境）

> ⚠️ **目前暫停使用**，先專心把正式站搞定。以下步驟保留供之後需要時參考，`render.yaml` 裡對應的 staging 服務設定也已整段註解掉。

系統現在分為兩個完全獨立的環境：

| | 正式站 | 測試站（staging） |
|---|---|---|
| 前端 | `https://fwc-tcmsp.pages.dev` | `https://fwc-tcmsp-staging.pages.dev` |
| 後端 | `https://tcm-onco-backend.onrender.com` | `https://tcm-onco-backend-staging.onrender.com` |
| 資料庫 | Neon 正式 project | Neon 另一個獨立 project |
| Git 分支 | `main` | `staging` |

前端會依照瀏覽網址自動判斷要打哪個後端（`frontend/js/api.js` 的 `resolveApiBase()`），不需要分別維護兩份前端程式碼。

### 建置步驟

**1. 建立 `staging` 分支**
```bash
cd tcm_backend
git checkout -b staging
git push -u origin staging
```
之後平常開發都先 push 到 `staging` 測試，確認沒問題再合併回 `main` 觸發正式站更新：
```bash
git checkout main
git merge staging
git push
```

**2. 在 Neon 另外建一個測試專用的 Project**
跟正式站一樣的申請流程（見上面「Google OAuth 設定」前的資料庫章節），但這次建一個新的 Neon project，例如命名 `tcm-onco-staging`，取得獨立的連線字串。

**3. Render 後端：Blueprint 會自動偵測到 `render.yaml` 裡新增的 `tcm-onco-backend-staging` 服務**
- 回到 Render 的 Blueprint 頁面，重新整理應該會看到新服務可以建立（跟著畫面指示 Apply 即可），它會綁定 `staging` 分支
- 部署完成後，到這個新服務的 Environment 頁面，手動填入：
  - `DATABASE_URL`：剛才 Neon 測試 project 的連線字串
  - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`：可以跟正式站共用同一組（見下一步）

**4. Google Cloud Console：多加一筆重新導向 URI**
回到當初申請 OAuth 用戶端的頁面，在「已授權的重新導向 URI」清單裡**多加一筆**（不要刪掉正式站那筆）：
```
https://tcm-onco-backend-staging.onrender.com/auth/google/callback
```

**5. Cloudflare Pages：新建一個獨立的 Pages 專案**
- Cloudflare Dashboard → Workers & Pages → **新建 Pages 專案**（不是編輯現有的 `fwc-tcmsp` 專案）
- 連接到同一個 GitHub repo：`steer425/tcm-onco-platform`
- **Production branch 選 `staging`**（這是跟正式站設定唯一不同的地方）
- Build output directory：`frontend`
- 專案名稱建議取 `fwc-tcmsp-staging`，這樣網址會自動變成 `fwc-tcmsp-staging.pages.dev`

**6. 測試站的資料匯入**
TCMSP 資料需要對測試資料庫另外匯入一次：
```bash
$env:DATABASE_URL="測試站的 Neon 連線字串"
python -m app.import_tcmsp_data data_import/tcmsp_data.json
```

### 使用方式

- 日常開發／測試：改動程式碼 → push 到 `staging` 分支 → 在 `https://fwc-tcmsp-staging.pages.dev` 測試
- 確認沒問題：合併 `staging` 到 `main` → push → 正式站自動更新

## 九、Google OAuth 設定（第三方登入）

系統已實作真正的 Google OAuth 2.0 登入（Authorization Code Flow），需要你自己申請一組 Google OAuth 用戶端，步驟如下：

### 申請 Google OAuth 用戶端

1. 前往 https://console.cloud.google.com 並登入你的 Google 帳號
2. 建立一個新專案（或使用既有專案），例如命名為 `tcm-onco-platform`
3. 左側選單「API 和服務」→「OAuth 同意畫面」：
   - 使用者類型選 **外部**
   - 填寫應用程式名稱（例如「TCM 中藥腫瘤篩選平台」）、使用者支援電子郵件
   - Scopes 新增 `email`、`profile`、`openid`
   - 若應用程式還在測試階段，記得在「測試使用者」加入你自己與其他要測試的 Google 帳號 email（測試階段只有加入的帳號能登入成功）
4. 左側選單「憑證」→「建立憑證」→「OAuth 用戶端 ID」：
   - 應用程式類型選 **網頁應用程式**
   - 已授權的重新導向 URI 填入：
     ```
     https://tcm-onco-backend.onrender.com/auth/google/callback
     ```
     （本機測試則另外加一筆 `http://localhost:8000/auth/google/callback`）
5. 建立完成後會拿到 **用戶端 ID（Client ID）** 與 **用戶端密鑰（Client Secret）**，請妥善保管，不要提交進版本控制或貼在任何對話/聊天工具裡

### 填入 Render 環境變數

到 Render 的 `tcm-onco-backend` 服務 → **Environment** → 新增/編輯：

| Key | Value |
|---|---|
| `GOOGLE_CLIENT_ID` | 剛才取得的 Client ID |
| `GOOGLE_CLIENT_SECRET` | 剛才取得的 Client Secret |
| `GOOGLE_REDIRECT_URI` | `https://tcm-onco-backend.onrender.com/auth/google/callback`（`render.yaml` 已預設此值，通常不需要改） |
| `FRONTEND_BASE_URL` | `https://fwc-tcmsp.pages.dev`（`render.yaml` 已預設此值，通常不需要改） |

儲存後 Render 會自動重新部署。部署完成後，登入頁應該會自動出現「使用 Google 帳號登入」按鈕（前端會呼叫 `/auth/google/enabled` 判斷是否顯示，未設定金鑰時按鈕不會出現）。

### 帳號治理規則（與一般帳密註冊一致）

- **第一次**用 Google 登入的人，系統會自動建立一筆帳號（帳號欄位＝Google email），狀態為「審核中」，並產生一筆帳號申請紀錄，管理者需要到「帳號審核」頁面核准後，該使用者才能登入成功
- 如果這個 Google email 剛好等於某個既有帳號（例如管理者手動建立過同名帳號），系統會自動把這次 Google 登入綁定到該既有帳號，之後這個人可以繼續用密碼或 Google 兩種方式登入
- 帳號被停用時，即使用 Google 登入也一樣會被擋下

### 已知限制

- 小紅書（RED）、WeChat 的第三方登入尚未實作，仍是先前的資料表 CRUD 骨架（`/oauth-accounts`），需要另外確認這兩個平台的開發者資格與串接規範

## 十、Facebook OAuth 設定（第三方登入）

跟 Google 一樣是真正的 OAuth 2.0 Authorization Code Flow，需要申請一組 Facebook App。

### 申請 Facebook App

1. 前往 https://developers.facebook.com/apps 並登入你的 Facebook 帳號
2. 點 **建立應用程式**，類型選 **消費者** 或 **其他**（依畫面選項，目的是要能用「Facebook 登入」產品）
3. 建立完成後，在應用程式左側選單新增 **Facebook 登入** 產品
4. 「Facebook 登入」→「設定」，在「**有效的 OAuth 重新導向 URI**」填入：
   ```
   https://tcm-onco-backend.onrender.com/auth/facebook/callback
   ```
   （本機測試則另外加一筆 `http://localhost:8000/auth/facebook/callback`）
5. 左側選單「應用程式設定」→「基本資料」，可以取得 **應用程式編號（App ID）** 與 **應用程式密鑰（App Secret）**
6. 應用程式預設是「開發模式」，只有你自己跟加到「測試人員」名單的帳號能登入成功；要開放給所有人使用，需要送 Facebook 審核（申請 `email` 這個 Scope 的存取權限），這步驟這裡先不處理，測試階段用開發模式即可

### 填入 Render 環境變數

| Key | Value |
|---|---|
| `FACEBOOK_CLIENT_ID` | 剛才取得的應用程式編號（App ID） |
| `FACEBOOK_CLIENT_SECRET` | 剛才取得的應用程式密鑰（App Secret） |
| `FACEBOOK_REDIRECT_URI` | `https://tcm-onco-backend.onrender.com/auth/facebook/callback`（`render.yaml` 已預設此值，通常不需要改） |

儲存後 Render 會自動重新部署，登入頁會自動出現「使用 Facebook 帳號登入」按鈕。

### 已知限制

- 部分 Facebook 帳號沒有綁定 email（例如只用手機號碼註冊），這種帳號登入時會被系統擋下並提示「這個 Facebook 帳號沒有提供 email」，因為本系統的帳號體系是以 email 作為帳號識別，沒有 email 就無法建立有意義的帳號名稱
- 應用程式在「開發模式」下，只有你自己與加到測試人員名單的 Facebook 帳號能成功登入；要開放給一般大眾使用需要送 Facebook 審核
- 帳號治理規則（首次登入建立待審核帳號、email 相同自動綁定既有帳號等）跟 Google 完全一致，詳見上一節說明
