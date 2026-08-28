"""成分標準化（TCMSP → PubChem）— 端對端驗證。

不連外網：PubChem 的 HTTP 層以 fixture 取代（回應結構照抄真實的 PUG-REST 格式）。

**這支測試最重要的部分是分子量交叉驗證。**
名稱對上就當作解析成功，是這類工作最容易犯、也最難發現的錯——
畫面上一切正常，只是那個 SMILES 屬於別的分子。所以下面用實際會遇到的
四種情況當回歸斷言：相符、水合物差 18 Da、鹽類差幾十 Da、以及缺值。
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ingredient_mapping.db")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_ingredient_mapping.db"
        and os.path.exists("test_ingredient_mapping.db")):
    os.remove("test_ingredient_mapping.db")

from fastapi.testclient import TestClient

from app import models, tcmsp_pubchem as pc
from app.database import SessionLocal
from app.main import app
from app.security import hash_password

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


# ---------------------------------------------------------------------------
# fixture：照抄 PubChem PUG-REST 的回應形狀
# ---------------------------------------------------------------------------

def _prop(cid, smiles, inchikey, formula, mw, iupac):
    return {"CID": cid, "CanonicalSMILES": smiles, "IsomericSMILES": smiles,
            "InChIKey": inchikey, "MolecularFormula": formula,
            "MolecularWeight": mw, "IUPACName": iupac}


FIXTURE = {
    # 分子量與 TCMSP 相符 → 應自動採用
    "quercetin": [_prop(5280343, "C1=CC(=C(C=C1C2=C(C(=O)C3=C(C=C(C=C3O2)O)O)O)O)O",
                        "REFJWTPEDVJJIY-UHFFFAOYSA-N", "C15H10O7", "302.23",
                        "2-(3,4-dihydroxyphenyl)-3,5,7-trihydroxychromen-4-one")],
    # 分子量差 18 Da（水合物）→ 名稱對上但化合物不同，應攔下來
    "hydrated compound": [_prop(111111, "CCO", "AAAAAAAAAA-BBBBBBBBBB-C",
                                "C2H8O2", "320.26", "hydrate form")],
    # 分子量差很多（鹽類／同名異物）→ 應攔下來
    "ambiguous salt": [_prop(222222, "CCN", "CCCCCCCCCC-DDDDDDDDDD-E",
                             "C2H7N", "440.50", "some salt")],
    # 多筆命中 → 待確認
    "polyphenol": [_prop(333333, "C1", "EEEEEEEEEE-FFFFFFFFFF-G", "C10H8", "128.17", "alpha"),
                   _prop(444444, "C2", "GGGGGGGGGG-HHHHHHHHHH-I", "C10H8", "128.17", "beta")],
    # PubChem 沒給分子量 → 無法驗證，信心降低但仍自動採用
    "no mw compound": [_prop(555555, "CC", "IIIIIIIIII-JJJJJJJJJJ-K", "C2H6", None, "ethane")],
    # 只有清理過名稱才查得到 → 一律待確認
    "Sitosterol": [_prop(666666, "CCC", "KKKKKKKKKK-LLLLLLLLLL-M",
                         "C29H50O", "414.71", "sitosterol")],
}

SYNONYMS = {
    "5280343": ["Quercetin", "117-39-5", "Sophoretin", "C15H10O7"],
    "666666": ["Sitosterol", "beta-Sitosterol", "83-46-5"],
}


def fake_search(client, name):
    return FIXTURE.get(name, [])


def fake_synonyms(client, cid):
    return SYNONYMS.get(str(cid), [])


def main():
    print("\n" + "=" * 60)
    print("成分標準化（PubChem）端對端驗證")
    print("=" * 60)

    # ---------- 名稱處理 ----------
    print("\n【名稱正規化】")
    check("normalize 壓掉多餘空白", pc.normalize("  Quercetin  ") == "Quercetin")
    check("cleaned_name 剝掉 TCMSP 的 _qt 後綴",
          pc.cleaned_name("Sitosterol_qt") == "Sitosterol", pc.cleaned_name("Sitosterol_qt"))
    check("cleaned_name 剝掉方括號註記",
          pc.cleaned_name("quercetin [supplement]") == "quercetin")
    check("cleaned_name 剝掉一般括號註記",
          pc.cleaned_name("luteolin (natural product)") == "luteolin")
    check("**保留 beta- 立體前綴**（beta-sitosterol ≠ sitosterol，剝掉會解析到錯的化合物）",
          pc.cleaned_name("beta-sitosterol") == "beta-sitosterol",
          pc.cleaned_name("beta-sitosterol"))
    check("保留 (2S)- 立體標示",
          pc.cleaned_name("(2S)-naringenin") == "(2S)-naringenin",
          pc.cleaned_name("(2S)-naringenin"))
    check("保留 (+)- 旋光標示",
          pc.cleaned_name("(+)-Catechin") == "(+)-Catechin", pc.cleaned_name("(+)-Catechin"))

    # ---------- 分子量交叉驗證 ----------
    print("\n【分子量交叉驗證（這一步的核心）】")
    r = pc.mw_check("302.25", "302.23")
    check("差 0.02 Da 視為相符", r["agree"] is True and r["delta"] == 0.02, r)
    r = pc.mw_check("302.25", "302.80")
    check("差 0.55 Da 超過容許值，視為不符", r["agree"] is False, r)
    r = pc.mw_check("302.25", "320.26")
    check("差 18 Da 判為不符，並提示可能是水合物",
          r["agree"] is False and "水合物" in r["reason"], r["reason"])
    r = pc.mw_check("302.25", "440.50")
    check("差 138 Da 判為不符，並提示可能是鹽類或同名異物",
          r["agree"] is False and ("鹽類" in r["reason"] or "同名異物" in r["reason"]),
          r["reason"])
    r = pc.mw_check(None, "302.2")
    check("TCMSP 缺分子量 → agree 為 None（無法驗證 ≠ 驗證通過）", r["agree"] is None, r)
    r = pc.mw_check("302.25", None)
    check("PubChem 缺分子量 → 同樣是 None", r["agree"] is None, r)
    r = pc.mw_check("NA", "302.2")
    check("'NA' 這種壞值不會被當成 0", r["agree"] is None, r)

    print("\n【CAS 與結構圖網址】")
    check("從同義詞挑出 CAS 號",
          pc.pick_cas(["Quercetin", "117-39-5", "QUE"]) == "117-39-5")
    check("沒有 CAS 時回 None", pc.pick_cas(["Quercetin", "QUE"]) is None)
    check("不會把長得像但格式錯的字串當成 CAS",
          pc.pick_cas(["1-2-3456", "abc-12-3"]) is None,
          pc.pick_cas(["1-2-3456", "abc-12-3"]))
    check("結構圖網址只接受純數字 CID",
          pc.image_url("5280343").endswith("/5280343/PNG") and pc.image_url("abc") is None)
    check("結構圖網址是 PubChem 網域",
          pc.image_url("1").startswith("https://pubchem.ncbi.nlm.nih.gov/"))

    # ---------- 解析分層 ----------
    print("\n【解析分層】")
    orig_search, orig_syn, orig_sleep = pc.search_by_name, pc.fetch_synonyms, pc.time.sleep
    pc.search_by_name, pc.fetch_synonyms = fake_search, fake_synonyms
    pc.time.sleep = lambda *_a: None
    try:
        r = pc.resolve_name(None, "quercetin", tcmsp_mw="302.25")
        check("分子量相符 → 自動採用", r["status"] == "auto", r["status"])
        check("帶回 CID 與 InChIKey",
              r["cid"] == "5280343" and r["inchikey"] == "REFJWTPEDVJJIY-UHFFFAOYSA-N", r)
        check("帶回 SMILES", bool(r["canonical_smiles"]))
        check("記錄分子量差值供審核時參考", r["mw_delta"] == 0.02, r["mw_delta"])

        r = pc.resolve_name(None, "hydrated compound", tcmsp_mw="302.25")
        check("**名稱對上但分子量差 18 Da → 待確認，不自動採用**",
              r["status"] == "pending", r["status"])
        check("待確認時說明差多少、可能是什麼原因", "水合物" in (r.get("note") or ""), r.get("note"))
        check("分子量不符時信心分數被調降", r["confidence"] < 0.5, r["confidence"])

        r = pc.resolve_name(None, "ambiguous salt", tcmsp_mw="302.25")
        check("差 138 Da 同樣攔下來", r["status"] == "pending", r["status"])

        r = pc.resolve_name(None, "polyphenol", tcmsp_mw="128.17")
        check("命中多筆 → 待確認", r["status"] == "pending", r["status"])
        check("多筆時把候選存下來給人挑", len(r["candidates"]) == 2, len(r["candidates"]))

        r = pc.resolve_name(None, "no mw compound", tcmsp_mw="30.07")
        check("PubChem 沒給分子量 → 仍自動採用但信心降低",
              r["status"] == "auto" and r["confidence"] < 1.0,
              (r["status"], r["confidence"]))

        r = pc.resolve_name(None, "Sitosterol_qt", tcmsp_mw="414.71")
        check("原名查不到、清理後查得到 → 待確認（即使分子量相符）",
              r["status"] == "pending" and r["method"] == "cleaned",
              (r["status"], r["method"]))
        check("說明是用哪個名稱查到的", "Sitosterol" in (r.get("note") or ""), r.get("note"))

        r = pc.resolve_name(None, "nonexistent compound zzz", tcmsp_mw="100")
        check("查無結果 → unresolved（跟 error 分得開）",
              r["status"] == "unresolved", r["status"])
    finally:
        pc.search_by_name, pc.fetch_synonyms = orig_search, orig_syn
        pc.time.sleep = orig_sleep

    # ---------- 測試資料 ----------
    print("\n【測試資料】")
    db = SessionLocal()
    ING = [("MOLQ01", "quercetin", "302.25", "46.43", "0.28"),          # 活性、相符
           ("MOLQ02", "hydrated compound", "302.25", "55.0", "0.30"),   # 活性、分子量不符
           ("MOLQ03", "polyphenol", "128.17", "40.0", "0.25"),          # 活性、多候選
           ("MOLQ04", "nonexistent compound zzz", "100", "38.0", "0.20"),  # 活性、查無
           ("MOLQ05", "quercetin", "302.25", "12.0", "0.30"),           # 非活性（OB 不足）
           ("MOLQ06", "quercetin", "302.25", "", "0.30")]               # ADME 缺值
    for mol_id, name, mw, ob, dl in ING:
        if not db.query(models.TcmspIngredient).filter(
                models.TcmspIngredient.mol_id == mol_id).first():
            db.add(models.TcmspIngredient(mol_id=mol_id, molecule_name=name,
                                          mw=mw, ob=ob, dl=dl))
    if not db.query(models.User).filter(models.User.account == "pcuser").first():
        db.add(models.User(account="pcuser", password_hash=hash_password("0000"),
                           status=models.UserStatus.active))
    db.commit()
    check("測試成分就緒", db.query(models.TcmspIngredient).count() >= 6)

    r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/auth/login", json={"account": "pcuser", "password": "0000"})
    U = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ---------- 權限 ----------
    print("\n【權限】")
    check("未帶 token 看覆蓋率 → 401",
          client.get("/tcmsp/ingredient-mapping/stats").status_code == 401)
    check("一般使用者看覆蓋率 → 403",
          client.get("/tcmsp/ingredient-mapping/stats", headers=U).status_code == 403)
    check("一般使用者不能解析 → 403",
          client.post("/tcmsp/ingredient-mapping/resolve", headers=U,
                      json={"limit": 10}).status_code == 403)
    check("未帶 token 反查 → 401",
          client.get("/tcmsp/ingredient-mapping/lookup?key=X").status_code == 401)

    # ---------- 批次解析 ----------
    print("\n【批次解析】")
    pc.search_by_name, pc.fetch_synonyms = fake_search, fake_synonyms
    pc.time.sleep = lambda *_a: None
    try:
        r = client.post("/tcmsp/ingredient-mapping/resolve", headers=A,
                        json={"limit": 50, "active_only": True}).json()
        check("**只解析活性成分**：6 個裡只處理 4 個（OB 不足與 ADME 缺值的被排除）",
              r["processed"] == 4, r)
        check("一個自動採用（quercetin）", r["auto"] == 1, r)
        check("兩個待確認（分子量不符、多候選）", r["pending"] == 2, r)
        check("其中 1 筆是分子量不符", r["mw_mismatch"] == 1, r)
        check("一個查無結果", r["unresolved"] == 1, r)

        r2 = client.post("/tcmsp/ingredient-mapping/resolve", headers=A,
                         json={"limit": 50, "active_only": True}).json()
        check("重複執行不會重跑已處理的", r2["processed"] == 0, r2)

        r3 = client.post("/tcmsp/ingredient-mapping/resolve", headers=A,
                         json={"limit": 50, "active_only": False}).json()
        check("關掉活性篩選後，剩下 2 個非活性成分才被處理",
              r3["processed"] == 2, r3)
    finally:
        pc.search_by_name, pc.fetch_synonyms = orig_search, orig_syn
        pc.time.sleep = orig_sleep

    row = (db.query(models.TcmspIngredientPubchem)
           .filter(models.TcmspIngredientPubchem.mol_id == "MOLQ01").first())
    check("自動採用的那筆有存下 CAS（從同義詞挑出來的）",
          row.cas_number == "117-39-5", row.cas_number)
    check("有存下 TCMSP 原本的分子量供對照", row.tcmsp_mw == "302.25", row.tcmsp_mw)

    stats = client.get("/tcmsp/ingredient-mapping/stats", headers=A).json()
    check("覆蓋率只算 auto/confirmed", stats["resolved"] == 3, stats["resolved"])
    check("統計有 SMILES 的筆數", stats["with_smiles"] >= 1, stats["with_smiles"])
    check("統計分子量不符的待確認筆數（這個數字代表驗證確實在運作）",
          stats["mw_mismatch_pending"] == 1, stats["mw_mismatch_pending"])

    # ---------- 審核 ----------
    print("\n【人工審核】")
    q = client.get("/tcmsp/ingredient-mapping/review?status=pending", headers=A).json()
    check("待確認清單有 2 筆", q["total"] == 2, q["total"])
    check("清單帶出 TCMSP 原始名稱", all(i["molecule_name"] for i in q["items"]))
    check("清單帶出結構圖網址供畫面顯示",
          any(i["image_url"] for i in q["items"]),
          [i["image_url"] for i in q["items"]])

    qm = client.get("/tcmsp/ingredient-mapping/review?status=pending&mw_mismatch_only=true",
                    headers=A).json()
    check("**可以只看分子量不符的**（那些比查無結果危險得多）",
          qm["total"] == 1 and qm["items"][0]["mol_id"] == "MOLQ02", qm["total"])

    r = client.post("/tcmsp/ingredient-mapping/confirm", headers=A,
                    json={"mol_id": "MOLQ03", "cid": "444444", "note": "測試確認"})
    check("確認映射 200", r.status_code == 200, r.text[:200])
    check("確認後採用候選裡的 CID 與 InChIKey",
          r.json()["cid"] == "444444" and
          r.json()["inchikey"] == "GGGGGGGGGG-HHHHHHHHHH-I", r.json())
    check("確認後狀態變 confirmed", r.json()["status"] == "confirmed")

    r = client.post("/tcmsp/ingredient-mapping/reject", headers=A,
                    json={"mol_id": "MOLQ02", "note": "分子量差 18 Da，TCMSP 那筆應是無水物"})
    check("否決 200", r.status_code == 200, r.status_code)

    pc.search_by_name, pc.fetch_synonyms = fake_search, fake_synonyms
    pc.time.sleep = lambda *_a: None
    try:
        r = client.post("/tcmsp/ingredient-mapping/resolve", headers=A,
                        json={"limit": 50, "active_only": False}).json()
        check("重跑不會覆蓋人工確認／否決的結果", r["processed"] == 0, r)
    finally:
        pc.search_by_name, pc.fetch_synonyms = orig_search, orig_syn
        pc.time.sleep = orig_sleep
    row = (db.query(models.TcmspIngredientPubchem)
           .filter(models.TcmspIngredientPubchem.mol_id == "MOLQ03").first())
    db.refresh(row)
    check("人工確認的 CID 沒被洗掉", row.cid == "444444", row.cid)

    check("確認不存在的成分 → 404",
          client.post("/tcmsp/ingredient-mapping/confirm", headers=A,
                      json={"mol_id": "NOPE", "cid": "1"}).status_code == 404)
    check("一般使用者不能確認 → 403",
          client.post("/tcmsp/ingredient-mapping/confirm", headers=U,
                      json={"mol_id": "MOLQ03", "cid": "444444"}).status_code == 403)

    # ---------- 反查（標準化的目的）----------
    print("\n【以 InChIKey／CAS／CID 反查】")
    r = client.get("/tcmsp/ingredient-mapping/lookup?key=REFJWTPEDVJJIY-UHFFFAOYSA-N",
                   headers=U).json()
    check("以 InChIKey 反查得到 TCMSP 成分", r["total"] >= 1, r["total"])
    check("反查結果帶出 mol_id 與結構圖",
          r["items"][0]["mol_id"] and r["items"][0]["image_url"], r["items"][0])
    r = client.get("/tcmsp/ingredient-mapping/lookup?key=117-39-5", headers=U).json()
    check("以 CAS 反查得到", r["total"] >= 1, r["total"])
    r = client.get("/tcmsp/ingredient-mapping/lookup?key=5280343", headers=U).json()
    check("以 CID 反查得到", r["total"] >= 1, r["total"])
    r = client.get("/tcmsp/ingredient-mapping/lookup?key=NOSUCHKEY123", headers=U).json()
    check("查不到就回 0，不是報錯", r["total"] == 0, r)
    # MOLQ02 上面已被否決，它的 InChIKey 不該再反查得到——
    # 這裡刻意用「確實存在於資料庫、但狀態是 rejected」的鍵，
    # 否則查一個根本不存在的鍵，結果為 0 也證明不了否決有生效
    r = client.get("/tcmsp/ingredient-mapping/lookup?key=AAAAAAAAAA-BBBBBBBBBB-C",
                   headers=U).json()
    check("已否決的映射不會出現在反查結果（該鍵確實存在於資料庫，只是狀態為 rejected）",
          r["total"] == 0, r)

    # ---------- 稽核 ----------
    print("\n【稽核紀錄】")
    actions = [x.action for x in db.query(models.AuditLog).all()]
    for a in ("tcmsp_resolve_ingredients", "tcmsp_confirm_ingredient_mapping",
              "tcmsp_reject_ingredient_mapping"):
        check(f"{a} 有寫入共用稽核表", a in actions)

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print("   -", f)
        raise SystemExit(1)
    print("✅ 成分標準化驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        client = c
        main()
