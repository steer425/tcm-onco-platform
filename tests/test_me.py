"""個人化設定 → 個人資訊（/me/*，v1.44.0）— 端對端驗證。

最重要的三組斷言：
  1. **只看得到自己**：別人的登入紀錄、跟自己無關的稽核紀錄一筆都不能出現
  2. **別人對自己帳號做的事要看得到**（管理者重設密碼、改角色），而且看得出改了什麼
  3. 變更密碼：驗證目前密碼、強度規則、成功後新舊密碼的登入結果、稽核不含密碼內容、
     唯讀模式下仍可變更
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_me.db")

# ⛔ 測試會寫入、刪除資料，**絕不能跑在正式資料庫上**（v1.43.0 實際發生過）。
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。\n"
              "   請先清掉：Remove-Item Env:DATABASE_URL　或開一個新的 PowerShell 視窗再跑。")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_me.db"
        and os.path.exists("test_me.db")):
    os.remove("test_me.db")

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import hash_password

FAIL = []
PW = "Alice2026x"


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


def login(client, account, password):
    return client.post("/auth/login", json={"account": account, "password": password})


def main(client):
    print("\n" + "=" * 60)
    print("個人資訊（/me）端對端驗證")
    print("=" * 60)
    db = SessionLocal()
    general = db.query(models.Role).filter(models.Role.name == "一般使用者").first()
    for acc in ("alice", "bob"):
        u = models.User(account=acc, password_hash=hash_password(PW), status=models.UserStatus.active)
        db.add(u)
        db.flush()
        if general:
            db.add(models.UserRole(user_id=u.id, role_id=general.id))
    db.commit()
    alice = db.query(models.User).filter(models.User.account == "alice").first()

    # 兩人各登入幾次；alice 登入兩次（上一次＋本次）
    login(client, "bob", PW)
    login(client, "alice", PW)
    r = login(client, "alice", PW)
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = login(client, "admin", "0000")
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}

    print("\n【權限】")
    for path in ("/me/profile", "/me/login-logs", "/me/audit-logs"):
        check(f"未登入 {path} → 401", client.get(path).status_code == 401)

    print("\n【個人資訊】")
    p = client.get("/me/profile", headers=H).json()
    check("帳號、狀態、角色", p["account"] == "alice" and p["status"] == "active"
          and "一般使用者" in p["roles"], p)
    check("累計登入 2 次、有上一次登入", p["login_count"] == 2 and p["previous_login"], p)
    check("從未變更密碼", p["password_changed_at"] is None)
    check("回傳密碼規則供畫面顯示", p["password_rules"]["min_length"] == 8)
    check("**不回傳密碼雜湊**", "password_hash" not in str(p))

    print("\n【登入紀錄：只看得到自己】")
    lg = client.get("/me/login-logs", headers=H).json()
    check("alice 只看到自己的 2 筆", lg["total"] == 2, lg["total"])
    check("沒有 bob 或 admin 的紀錄",
          all(i["id"] for i in lg["items"])
          and db.query(models.LoginLog).filter(models.LoginLog.id.in_([i["id"] for i in lg["items"]]),
                                               models.LoginLog.user_id != alice.id).count() == 0)
    check("由新到舊、標示登入方式", lg["items"][0]["login_at"] >= lg["items"][1]["login_at"]
          and lg["items"][0]["method"] == "password")
    check("limit 參數有效", len(client.get("/me/login-logs?limit=1", headers=H).json()["items"]) == 1)

    print("\n【異動紀錄】")
    au = client.get("/me/audit-logs", headers=H).json()
    check("預設不含登入／登出", all(i["action"] not in ("login", "logout") for i in au["items"]), au)
    au2 = client.get("/me/audit-logs?include_login=true", headers=H).json()
    check("勾選後包含自己的登入", sum(1 for i in au2["items"] if i["action"] == "login") == 2, au2["total"])
    check("**看不到 bob 與 admin 的登入**", all(i["by_me"] for i in au2["items"]), au2["items"])

    # 管理者對 alice 帳號做事：重設密碼＋調整角色
    r = client.put(f"/users/{alice.id}", headers=A,
                   json={"password": "AdminSet99", "role_ids": [general.id] if general else []})
    check("管理者更新 alice 200", r.status_code == 200, r.text[:200])
    # 管理者對 bob 做事：alice 不該看到
    bob = db.query(models.User).filter(models.User.account == "bob").first()
    client.put(f"/users/{bob.id}", headers=A, json={"notes": "bob only"})
    # v1.49.0：管理者重設密碼 → alice 原本的登入全部失效
    check("**管理者重設密碼後，alice 原本的 token 失效**", client.get("/me/profile", headers=H).status_code == 401)
    H = {"Authorization": f"Bearer {login(client, 'alice', 'AdminSet99').json()['access_token']}"}
    au = client.get("/me/audit-logs", headers=H).json()
    other = [i for i in au["items"] if not i["by_me"]]
    check("**看得到管理者對自己帳號的操作**，標示為他人操作",
          len(other) == 1 and other[0]["actor_account"] == "admin" and other[0]["action"] == "update_user", other)
    check("**說明寫出改了什麼**（重設密碼、調整角色），不含密碼內容",
          "重設密碼" in other[0]["detail"] and "調整角色" in other[0]["detail"]
          and "AdminSet99" not in other[0]["detail"], other[0]["detail"])
    check("看不到管理者對 bob 的操作", all("bob" not in (i["detail"] or "") for i in au["items"]))

    print("\n【變更密碼】")
    cur = "AdminSet99"     # 管理者剛重設過
    def put(cur_pw, new, conf=None):
        return client.put("/me/password", headers=H, json={
            "current_password": cur_pw, "new_password": new, "confirm_password": conf or new})
    r = put("wrong-one", "Better2026z")
    check("目前密碼錯 → 400（不是 401，前端不會被登出）", r.status_code == 400 and "目前密碼" in r.text, r.text)
    check("兩次不一致 → 400", put(cur, "Better2026z", "Better2026y").status_code == 400)
    for bad, why in [("Ab1", "太短"), ("abcdefghij", "沒有數字"), ("1234567890", "沒有字母"),
                     ("alice2026xx", "含帳號"), ("password1", "常見密碼"), (cur, "與目前相同")]:
        r = put(cur, bad)
        check(f"拒絕：{why}", r.status_code == 400, r.json().get("detail"))
    check("拒絕超過 72 位元組（bcrypt 會靜默截斷）",
          put(cur, "密碼" * 12 + "a1").status_code == 400)

    r = put(cur, "Better2026z")
    check("合格的新密碼 → 200，要求重新登入（v1.49.0：所有裝置含自己都登出）",
          r.status_code == 200 and r.json().get("relogin") is True, r.text)
    check("改密碼後這個 token 也失效", client.get("/me/profile", headers=H).status_code == 401)
    check("舊密碼不能再登入", login(client, "alice", cur).status_code == 401)
    check("新密碼可以登入", login(client, "alice", "Better2026z").status_code == 200)
    log = (db.query(models.AuditLog).filter(models.AuditLog.action == "change_own_password").all())
    check("寫入一筆 change_own_password 稽核", len(log) == 1)
    check("**稽核不含任何密碼內容**",
          all(x not in (log[0].detail or "") for x in ("Better2026z", cur)), log[0].detail)
    H = {"Authorization": f"Bearer {login(client, 'alice', 'Better2026z').json()['access_token']}"}
    check("個人資訊顯示最近一次自行變更密碼", client.get("/me/profile", headers=H).json()["password_changed_at"])
    check("輸錯目前密碼不寫稽核（避免雜訊）", db.query(models.AuditLog).filter(
        models.AuditLog.action == "change_own_password").count() == 1)

    print("\n【唯讀模式】")
    db.merge(models.SystemSetting(key="read_only_mode", value="true"))
    db.commit()
    check("唯讀模式下一般寫入被擋（423）",
          client.put(f"/users/{bob.id}", headers=A, json={"notes": "x"}).status_code == 423)
    r = client.put("/me/password", headers=H, json={
        "current_password": "Better2026z", "new_password": "Safer2026q", "confirm_password": "Safer2026q"})
    check("**唯讀模式下仍可變更自己的密碼**", r.status_code == 200, r.text[:200])
    db.merge(models.SystemSetting(key="read_only_mode", value="false"))
    db.commit()

    print("\n【前端】")
    page = client.get("/app/personal-settings.html")
    check("頁面有四個新區塊", all(t in page.text for t in ("個人資訊", "密碼設定", "登入紀錄", "異動紀錄")))

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 個人資訊驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        main(c)
