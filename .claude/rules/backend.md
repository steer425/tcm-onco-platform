# FastAPI & SQLAlchemy 後端開發規範

## 1. 資料庫與 Model 規範 (重要)
*   **相容性限制**：必須同時相容生產環境 (Postgres) 與本地開發環境 (SQLite)。
*   **禁用原生型態**：絕對禁止使用 Postgres 專屬型態（例如 `ENUM`、`ARRAY`、`JSONB`、`INET`、`GIN`）。
*   **JSON 儲存方案**：所有 JSON 格式的欄位，一律使用 `Text` 型態定義，並在程式碼中以 JSON 字串形式進行序列化/反序列化。
*   **主鍵規則**：所有資料表主鍵一律使用 String/UUID，並呼叫 `gen_id()` 自動生成。
*   **架構同步**：新增資料表時，必須確保其為 `Base` 的子類別，並注意目前總表數約為 39 張。

## 2. 唯讀模式與 Session 依賴注入
*   **Session 選擇**：
    *   一般讀寫操作：使用 `get_db`。
    *   查詢站台/純讀取操作：**必須**使用 `get_query_db`。
*   **運作原理**：`get_query_db` 在唯讀模式啟動時會自動切換至本地 SQLite 快取（參考 `app/local_cache.py`），切勿在純查詢的 API 中誤用 `get_db` 導致快取機制失效。

## 3. 權限與審核日誌 (Authentication & ACL)
*   **管理者權限**：核心邏輯中已存在特定設計，角色名稱為 `"管理者"` 時會自動跳過（Bypass）所有權限檢查。
*   **功能權限檢查**：新路由若需檢查權限，使用 `require_permission(feature_code, need_execute=True)`，它會比對 `feature_config` 中的代碼與 `RolePermission`。
*   **操作留痕**：任何變更性操作一律調用 `write_audit_log(...)` 寫入全域單一的 `AuditLog` 資料表。**禁止**為個別功能建立獨立的 audit tables。

## 4. 功能配置與資料初始化 (Feature Config)
*   **單一事實來源**：所有頁面、小工具、導覽標籤及 URL 路由的權限基底，一律以 `app/feature_config.py` 中的 `FEATURE_CONFIG` 串列為準。
*   **初始化邏輯**：當執行 `seed_default_data()` 或 `migrate_schema.py` 時：
    *   若為**新功能**：直接插入（Insert）資料庫。
    *   若為**既有功能**：僅更新 `module`、`name`、`nav_label`、`page_url`、`sort_order`。
    *   **絕對不要覆蓋**：`enabled`、`show_frontend`、`show_backend` 這三個欄位，因為管理員會在前端 UI 線上調整這些設定（此處曾發生過嚴重 Bug v1.32.4）。

## 5. 安全性與特殊模組
*   **新聞模組安全**：處理敏感內容或秘密時，API 必須回傳 `503` 狀態碼，且必須使用 `secrets.compare_digest` 進行安全字串比對，防範時序攻擊（Timing Attack）。

## 6. 自製遷移腳本規範 (migrate_schema.py)
*   **禁用 Alembic**：本專案「不使用」 Alembic。禁止生成 `alembic` 資料夾、`env.py` 或 `versions/` 遷移檔案。
*   **腳本修改原則**：當需要修改資料庫架構（Schema）時，必須手動編輯 `migrate_schema.py`。
*   **邏輯一致性**：編寫遷移邏輯時，必須嚴格遵守與 `seed_default_data()` 相同的「更新 vs 覆蓋」邏輯（即：允許更新模組與導覽標籤，但**絕對不可**覆蓋管理員在線上調整的 `enabled`、`show_frontend`、`show_backend` 欄位）。
*   **SQLite 相容性**：由於 SQLite 不支援標準的 `ALTER TABLE DROP COLUMN` 或部分 `ALTER COLUMN` 操作，在編寫 `migrate_schema.py` 的 DDL 語句時，必須確保語法在 Postgres 與 SQLite 都能順利執行（或在腳本中加入環境判斷）。
