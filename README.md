# TCM 中藥腫瘤篩選平台 — 目標零後台系統

**目前版本：v1.1.1**（已通過使用者本機測試審查並正式上版，詳見 [CHANGELOG.md](./CHANGELOG.md)）

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
