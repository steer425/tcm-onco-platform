"""帳號安全（v1.49.0）— 端對端驗證。

執行：`python -m tests.test_auth_security`（從專案根目錄）。真的 app、真的 JWT、SQLite。

涵蓋：
  1. 帳號名稱格式（擋掉會被當成網頁標記的字元）、所有設定密碼的地方都套密碼規則
  2. 連續登入失敗鎖定、鎖定中不比對密碼、管理者解鎖、成功登入歸零
  3. token 撤銷：單一登出只影響那個裝置；改密碼／登出所有裝置／管理者重設密碼或強制登出 → 全部失效
  4. 舊 token（沒有 tv／lid）照樣可用，上線不會把所有人踢出去
  5. 啟動時自動補 users 欄位；唯讀模式下仍可登出所有裝置與解鎖
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth_security.db")
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。")
if os.environ["DATABASE_URL"] == "sqlite:///./test_auth_security.db" and os.path.exists("test_auth_security.db"):
    os.remove("test_auth_security.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app import account_security as sec, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.security import create_access_token  # noqa: E402

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra != '' else ''}")
    if not cond:
        FAIL.append(label)


def login(c, account, password):
    return c.post("/auth/login", json={"account": account, "password": password})


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main(c):
    print("\n" + "=" * 60)
    print("帳號安全 端對端驗證")
    print("=" * 60)
    A = H(login(c, "admin", "0000").json()["access_token"])

    print("\n【帳號名稱與密碼規則】")
    r = c.post("/auth/apply", json={"account": "bad<name>", "password": "Goodpass123"})
    check("**申請帳號：名稱含 < > 等字元 → 400**（審核頁曾直接塞進網頁）", r.status_code == 400 and "英文字母" in r.text, r.text[:80])
    r = c.post("/auth/apply", json={"account": "x", "password": "Goodpass123"})
    check("申請帳號：太短 → 400", r.status_code == 400)
    r = c.post("/auth/apply", json={"account": "newbie01", "password": "12345678"})
    check("申請帳號：常見／沒有英文字母的密碼 → 400", r.status_code == 400, r.text[:80])
    r = c.post("/auth/apply", json={"account": "newbie01", "password": "Newbie01pass"})
    check("申請帳號：密碼含帳號名稱 → 400", r.status_code == 400 and "帳號名稱" in r.text, r.text[:80])
    r = c.post("/auth/apply", json={"account": "newbie01", "password": "Green7tea"})
    check("申請帳號：合格 → 200", r.status_code == 200, r.text[:80])
    r = c.post("/auth/apply", json={"account": "first.last+tag@example.org", "password": "Green7tea"})
    check("email 形式的帳號可以申請（第三方登入用 email 當帳號）", r.status_code == 200, r.text[:80])
    r = c.post("/users", headers=A, json={"account": "staff01", "password": "0000"})
    check("**管理者建立帳號也要套密碼規則**", r.status_code == 400, r.text[:80])
    r = c.post("/users", headers=A, json={"account": "a b", "password": "Blue9sky"})
    check("管理者建立帳號：名稱含空白 → 400", r.status_code == 400)
    r = c.post("/users", headers=A, json={"account": "staff01", "password": "Blue9sky"})
    check("管理者建立合格帳號", r.status_code == 200, r.text[:80])
    sid = r.json()["id"]
    r = c.put(f"/users/{sid}", headers=A, json={"password": "short1"})
    check("**管理者重設密碼也要套密碼規則**", r.status_code == 400, r.text[:80])

    print("\n【登入失敗鎖定】")
    codes = [login(c, "staff01", "wrong-pass-1").status_code for _ in range(4)]
    check("前 4 次密碼錯 → 401", codes == [401] * 4, codes)
    r = login(c, "staff01", "wrong-pass-1")
    check("**第 5 次 → 429 並說明鎖定 15 分鐘**", r.status_code == 429 and "15" in r.json()["detail"], r.text[:80])
    r = login(c, "staff01", "Blue9sky")
    check("**鎖定中輸入正確密碼也進不去**（不比對密碼）", r.status_code == 429 and "分鐘後再試" in r.json()["detail"], r.text[:80])
    db = SessionLocal()
    logs = db.query(models.AuditLog).filter(models.AuditLog.action == "login_failed").all()
    check("每次失敗寫稽核（含 IP、不含密碼）",
          len(logs) >= 5 and all("wrong-pass" not in (x.detail or "") for x in logs), len(logs))
    db.close()
    users = c.get("/users", headers=A).json()
    st = next(u for u in users if u["account"] == "staff01")
    check("帳號列表帶出鎖定時間", st["locked_until"] is not None)
    r = c.post(f"/users/{sid}/unlock", headers=A)
    check("管理者解鎖", r.status_code == 200 and r.json()["locked_until"] is None)
    r = login(c, "staff01", "Blue9sky")
    check("解鎖後可登入", r.status_code == 200)
    login(c, "staff01", "nope-1")
    login(c, "staff01", "Blue9sky")
    db = SessionLocal()
    check("成功登入後失敗次數歸零", (db.query(models.User).filter_by(account="staff01").first().failed_login_count or 0) == 0)
    db.close()
    r = login(c, "ghost-user", "whatever1")
    check("不存在的帳號 → 401，訊息與密碼錯相同", r.status_code == 401 and r.json()["detail"] == "帳號或密碼錯誤")

    print("\n【token 撤銷】")
    a = login(c, "staff01", "Blue9sky").json()
    b = login(c, "staff01", "Blue9sky").json()
    TA, TB = H(a["access_token"]), H(b["access_token"])
    check("兩個裝置都能用", c.get("/auth/me", headers=TA).status_code == 200 and c.get("/auth/me", headers=TB).status_code == 200)
    c.post(f"/auth/logout?login_log_id={a['login_log_id']}", headers=TA)
    r = c.get("/auth/me", headers=TA)
    check("**登出後，那個 token 立刻失效**", r.status_code == 401 and "已經登出" in r.json()["detail"], r.text[:80])
    check("另一個裝置不受影響", c.get("/auth/me", headers=TB).status_code == 200)
    r = c.post("/me/logout-all", headers=TB)
    check("登出所有裝置", r.status_code == 200 and r.json()["relogin"] is True, r.text[:80])
    r = c.get("/auth/me", headers=TB)
    check("**登出所有裝置後，自己的 token 也失效**", r.status_code == 401 and "登出所有裝置" in r.json()["detail"], r.text[:80])

    c1 = H(login(c, "staff01", "Blue9sky").json()["access_token"])
    c2 = H(login(c, "staff01", "Blue9sky").json()["access_token"])
    r = c.put("/me/password", headers=c1, json={"current_password": "Blue9sky", "new_password": "Red4apple",
                                                "confirm_password": "Red4apple"})
    check("改密碼成功，要求重新登入", r.status_code == 200 and r.json()["relogin"] is True, r.text[:80])
    check("**改密碼後，所有裝置（含自己）都失效**",
          c.get("/auth/me", headers=c1).status_code == 401 and c.get("/auth/me", headers=c2).status_code == 401)
    check("舊密碼不能登入、新密碼可以",
          login(c, "staff01", "Blue9sky").status_code == 401 and login(c, "staff01", "Red4apple").status_code == 200)

    t = H(login(c, "staff01", "Red4apple").json()["access_token"])
    c.put(f"/users/{sid}", headers=A, json={"password": "Green5leaf"})
    check("**管理者重設密碼 → 對方已登入的裝置失效**", c.get("/auth/me", headers=t).status_code == 401)
    t = H(login(c, "staff01", "Green5leaf").json()["access_token"])
    r = c.post(f"/users/{sid}/revoke-sessions", headers=A)
    check("**管理者強制登出 → 對方 token 失效**", r.status_code == 200 and c.get("/auth/me", headers=t).status_code == 401)
    t = H(login(c, "staff01", "Green5leaf").json()["access_token"])
    c.put(f"/users/{sid}", headers=A, json={"status": "suspended", "suspend_reason": "測試"})
    c.put(f"/users/{sid}", headers=A, json={"status": "active"})
    check("**停用再啟用 → 停用前發出的 token 不會復活**", c.get("/auth/me", headers=t).status_code == 401)

    db = SessionLocal()
    u = db.query(models.User).filter_by(account="staff01").first()
    old = create_access_token({"sub": u.id, "acc": u.account})      # v1.49.0 以前的 token 形狀
    db.close()
    check("舊格式 token（沒有 tv／lid）：已被撤銷過（tv>0）的帳號不能用",
          c.get("/auth/me", headers=H(old)).status_code == 401)
    db = SessionLocal()
    adm = db.query(models.User).filter_by(account="admin").first()
    old_admin = create_access_token({"sub": adm.id, "acc": adm.account})
    db.close()
    check("從沒被撤銷過的帳號（tv=0）用舊 token 可以", c.get("/auth/me", headers=H(old_admin)).status_code == 200)

    print("\n【唯讀模式下仍可自救】")
    c.put("/system-settings/read-only-mode", headers=A, json={"enabled": True})
    db = SessionLocal()
    from app.routers.system_settings import _set_setting_value
    _set_setting_value(db, "read_only_mode", "true")
    db.commit()
    db.close()
    t = login(c, "staff01", "Green5leaf").json()
    check("唯讀模式：一般寫入被擋（423）", c.post("/users", headers=A, json={"account": "zz01", "password": "Blue9sky"}).status_code == 423)
    check("唯讀模式：登出所有裝置可以", c.post("/me/logout-all", headers=H(t["access_token"])).status_code == 200)
    check("唯讀模式：管理者解鎖、強制登出可以",
          c.post(f"/users/{sid}/unlock", headers=A).status_code == 200
          and c.post(f"/users/{sid}/revoke-sessions", headers=A).status_code == 200)
    db = SessionLocal()
    _set_setting_value(db, "read_only_mode", "false")
    db.commit()
    db.close()

    print("\n【啟動時自動補欄位】")
    old_db = "test_auth_old_schema.db"
    if os.path.exists(old_db):
        os.remove(old_db)
    eng = create_engine(f"sqlite:///./{old_db}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR PRIMARY KEY, account VARCHAR, password_hash VARCHAR)"))
    added = sec.ensure_auth_columns(eng)
    cols = {x["name"] for x in inspect(eng).get_columns("users")}
    check("舊資料庫缺的三個欄位都補上", set(added) == {"token_version", "failed_login_count", "locked_until"}
          and {"token_version", "failed_login_count", "locked_until"} <= cols, added)
    check("再跑一次不重複加（可重複執行）", sec.ensure_auth_columns(eng) == [])
    eng.dispose()
    os.remove(old_db)

    print("\n【前端跳脫】")
    root = os.path.join(os.path.dirname(__file__), "..", "frontend", "js")
    apps = open(os.path.join(root, "applications.js"), encoding="utf-8").read()
    usr = open(os.path.join(root, "users.js"), encoding="utf-8").read()
    check("審核頁：帳號與備註經 escHtml", "escHtml(a.account)" in apps and "escHtml(a.notes" in apps)
    check("帳號頁：帳號、停用原因、備註經 escHtml",
          "escHtml(u.account)" in usr and "escHtml(u.suspend_reason" in usr and "escHtml(u.notes" in usr)

    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 帳號安全驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as client:
        main(client)
