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

    print("步驟 1／3：補齊 features 資料表欄位...")
    with engine.begin() as conn:
        for stmt in ALTER_STATEMENTS:
            try:
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
            feature.nav_label = item.get("nav_label")
            feature.page_url = item.get("page_url")
            feature.show_frontend = item.get("show_frontend", False)
            feature.show_backend = item.get("show_backend", True)
            feature.sort_order = item.get("sort_order", 0)
            updated += 1
        db.commit()
        print(f"完成，共處理 {updated} 筆功能項目。")
    finally:
        db.close()


if __name__ == "__main__":
    run()
