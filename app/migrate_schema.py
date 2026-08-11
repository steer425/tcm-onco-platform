"""
一次性 schema 遷移腳本：目前專案尚未導入 Alembic，資料庫變更需要手動執行這類腳本補齊。

用途：v1.9.0 為 `features` 資料表新增欄位（enabled/show_frontend/show_backend/nav_label/page_url/sort_order），
既有資料庫（尤其是正式環境 Neon）需要執行這支腳本，才會有這些新欄位並回填正確的預設值。

使用方式：
    python -m app.migrate_schema

可重複執行（每個 ALTER 都包在 try/except 裡，欄位已存在時會略過）。
"""
from sqlalchemy import text

from app import models
from app.database import SessionLocal, engine
from app.feature_config import FEATURE_CONFIG

ALTER_STATEMENTS = [
    "ALTER TABLE features ADD COLUMN enabled BOOLEAN DEFAULT TRUE NOT NULL",
    "ALTER TABLE features ADD COLUMN show_frontend BOOLEAN DEFAULT FALSE NOT NULL",
    "ALTER TABLE features ADD COLUMN show_backend BOOLEAN DEFAULT TRUE NOT NULL",
    "ALTER TABLE features ADD COLUMN nav_label VARCHAR",
    "ALTER TABLE features ADD COLUMN page_url VARCHAR",
    "ALTER TABLE features ADD COLUMN sort_order INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE tcmsp_diseases ADD COLUMN disease_cn_name VARCHAR",
    "ALTER TABLE pharmacies ADD COLUMN opens_at VARCHAR",
    "ALTER TABLE pharmacies ADD COLUMN closes_at VARCHAR",
    "ALTER TABLE pharmacies ADD COLUMN view_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE pharmacies ADD COLUMN favorite_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE pharmacies ADD COLUMN share_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE pharmacies ADD COLUMN nav_click_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE pharmacies ADD COLUMN opening_date VARCHAR",
    "ALTER TABLE pharmacies ADD COLUMN discount_percent INTEGER",
    "ALTER TABLE pharmacies ADD COLUMN discount_description VARCHAR",
    "ALTER TABLE pharmacies ADD COLUMN discount_valid_until VARCHAR",
    "ALTER TABLE tcmsp_herbs ADD COLUMN target_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE tcmsp_herbs ADD COLUMN dark_gene_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE tcmsp_herbs ADD COLUMN gencc_disease_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE tcmsp_diseases ADD COLUMN target_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE dark_genes ADD COLUMN has_tcmsp_target BOOLEAN DEFAULT FALSE NOT NULL",
]


def run():
    print("步驟 0/3：為 oauthprovider enum 型別新增 'facebook' 列舉值（僅 PostgreSQL 需要，SQLite 會直接略過）...")
    # ALTER TYPE ... ADD VALUE 不能包在一般交易區塊裡執行，這裡用 AUTOCOMMIT 隔離等級單獨跑。
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TYPE oauthprovider ADD VALUE IF NOT EXISTS 'facebook'"))
        print("  已新增（或本來就存在）")
    except Exception as e:
        print("  略過（可能是 SQLite 環境，或型別/數值已存在）：", str(e)[:150])

    print("步驟 1／3：補齊 features / tcmsp_diseases 資料表欄位...")
    # 重要：每句 ALTER 都要用「獨立交易」執行，不能共用同一個 engine.begin()。
    # PostgreSQL 的交易機制是「一句失敗，整個交易裡後面所有語句都會被連坐拖累失敗」
    # （錯誤訊息會是 InFailedSqlTransaction），即使那句語句本身完全沒問題。
    # 先前的版本共用同一個交易，導致只要第一句「欄位已存在」失敗，
    # 後面真正需要執行的 ALTER（例如新增 disease_cn_name 欄位）永遠不會真的跑到。
    for stmt in ALTER_STATEMENTS:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            print("  執行成功：", stmt)
        except Exception as e:
            print("  略過（可能欄位已存在）：", stmt, "-", str(e)[:120])

    print("步驟 2/3：依 FEATURE_CONFIG 回填既有功能項目的導覽資料...")
    db = SessionLocal()
    try:
        # v1.10.0：移除已併入「權限矩陣」的舊版「功能項目管理」獨立頁面（F0-14）
        obsolete = db.query(models.Feature).filter(models.Feature.code == "F0-14").first()
        if obsolete:
            db.query(models.RolePermission).filter(models.RolePermission.feature_id == obsolete.id).delete()
            db.delete(obsolete)
            db.commit()
            print("  已移除舊版 F0-14（功能項目管理獨立頁面，功能已併入角色管理的權限矩陣視窗）")

        updated = 0
        for item in FEATURE_CONFIG:
            feature = db.query(models.Feature).filter(models.Feature.code == item["code"]).first()
            if not feature:
                # 資料庫裡還沒有這筆功能（例如新增的項目），直接建立
                db.add(models.Feature(
                    code=item["code"], module=item["module"], name=item["name"],
                    nav_label=item.get("nav_label"), page_url=item.get("page_url"),
                    show_frontend=item.get("show_frontend", False),
                    show_backend=item.get("show_backend", True),
                    sort_order=item.get("sort_order", 0),
                    enabled=True,
                ))
                updated += 1
                continue
            feature.module = item["module"]
            feature.name = item["name"]
            feature.nav_label = item.get("nav_label")
            feature.page_url = item.get("page_url")
            feature.sort_order = item.get("sort_order", 0)
            # 注意：不覆蓋 show_frontend／show_backend／enabled 這幾個欄位！
            # 這些欄位在「角色管理→權限矩陣」視窗裡是管理者可以自行調整的「全站共用設定」
            # （見 app/routers/permissions.py 的 update_permission_matrix），如果每次遷移都
            # 無條件用 FEATURE_CONFIG 的預設值覆蓋回去，管理者在後台做的調整會被悄悄洗掉，
            # 而且不會有任何錯誤訊息——這是真實發現過的潛在風險（v1.32.4），不是理論疑慮。
            # 只同步「開發者定義、管理者不會去改的」內容性欄位（名稱、連結、排序）。
            updated += 1
        db.commit()
        print(f"完成，共處理 {updated} 筆功能項目。")

        print("步驟 3/3：回填疾病中文名稱種子資料（只補目前是空值的項目，不覆蓋既有翻譯）...")
        import json
        from pathlib import Path
        seed_path = Path(__file__).resolve().parent.parent / "data_import" / "disease_cn_name_seed.json"
        if seed_path.is_file():
            with open(seed_path, encoding="utf-8") as f:
                seed = json.load(f)
            filled = 0
            for dis_id, cn_name in seed.items():
                disease = db.query(models.TcmspDisease).filter(models.TcmspDisease.dis_id == dis_id).first()
                if disease and not disease.disease_cn_name:
                    disease.disease_cn_name = cn_name
                    filled += 1
            db.commit()
            print(f"  已回填 {filled} 筆疾病中文名稱")
        else:
            print("  找不到種子檔案，略過（正常情況：尚未執行過 TCMSP 資料匯入）")

        print("步驟 4/4：重算統計欄位（藥材/疾病靶點數、暗黑基因比對結果）...")
        print("  這一步很重要：上面的 ALTER TABLE 新增了統計欄位，正式環境的舊資料如果不重算，")
        print("  這幾個欄位的值會停留在預設的 0/False，不會自動變成正確數字。")
        from app.recompute_stats import recompute_all_stats
        recompute_all_stats(db)
    finally:
        db.close()


if __name__ == "__main__":
    run()
