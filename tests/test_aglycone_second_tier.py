"""苷元第二層解析（分子式推算＋子結構比對，v1.47.0）— 端對端驗證。

不連外網：PubChem 的 HTTP 層以 fixture 取代（回應形狀照抄 PUG-REST）。
化學數字用真實的例子：人參皂苷 Rh4（C36H60O8）去掉一個葡萄糖 → 苷元 C30H50O3（458.7）。

重點斷言：
  * 分子式推算有三道驗算（糖基組合、扣得動、扣完分子量與 TCMSP 相符）
  * 候選依「是不是母體苷的一部分」排序，第一名是真正的苷元
  * **永遠不自動採用**；立體異構物要提示人工挑選
  * 只動自動否決的苷元誤配；人工否決、非苷元的列不動；連線失敗不動、下次重跑
  * 覆蓋率卡片的「第二層待處理」與批次佇列數同一件事
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aglycone_second_tier.db")

# ⛔ 測試會寫入、刪除資料，**絕不能跑在正式資料庫上**（v1.43.0 實際發生過）。
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。\n"
              "   請先清掉：Remove-Item Env:DATABASE_URL　或開一個新的 PowerShell 視窗再跑。")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_aglycone_second_tier.db"
        and os.path.exists("test_aglycone_second_tier.db")):
    os.remove("test_aglycone_second_tier.db")

import base64

from fastapi.testclient import TestClient

from app import models, tcmsp_pubchem as pc
from app.database import SessionLocal
from app.main import app

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


def fp(bits):
    """位元集合 → PubChem Fingerprint2D 的 base64（前 4 位元組是長度 881）。"""
    data = bytearray(111)
    for i in bits:
        data[i // 8] |= 1 << (7 - i % 8)
    return base64.b64encode((881).to_bytes(4, "big") + bytes(data)).decode()


PARENT_BITS = set(range(0, 120))
TRUE_AGLY = set(range(0, 70))                         # 完全包含在母體裡
UNRELATED = set(range(0, 40)) | set(range(300, 340))  # 同分子式但不像母體的一部分


def prop(cid, formula, mw, inchikey, bits):
    return {"CID": cid, "CanonicalSMILES": f"C{cid}", "IsomericSMILES": f"C{cid}@",
            "InChIKey": inchikey, "MolecularFormula": formula, "MolecularWeight": mw,
            "IUPACName": f"compound {cid}", "Fingerprint2D": fp(bits)}


PROPS = {
    "1001": prop(1001, "C36H60O8", "620.9", "PARENTRH4XXXXX-UHFFFAOYSA-N", PARENT_BITS),   # 母體苷
    "2001": prop(2001, "C30H50O3", "458.7", "AGLYCONEPPTXXX-AAAAAAAAAA-N", TRUE_AGLY),     # 真正的苷元
    "2002": prop(2002, "C30H50O3", "458.7", "AGLYCONEPPTXXX-BBBBBBBBBB-N", TRUE_AGLY),     # 同平面結構的立體異構物
    "2003": prop(2003, "C30H50O3", "458.7", "UNRELATEDISOMR-UHFFFAOYSA-N", UNRELATED),     # 無關的異構物
}
FORMULA_HITS = {"C30H50O3": ["2003", "2001", "2002", "1001"]}
CALLS = {"formula": 0, "props": 0}
NET_DOWN = {"on": False}


def fake_formula(client, formula, max_records=pc.FORMULA_MAX_RECORDS):
    CALLS["formula"] += 1
    if NET_DOWN["on"]:
        raise RuntimeError("connect timeout")
    return FORMULA_HITS.get(formula, [])


def fake_props(client, cids, pause=0.25):
    CALLS["props"] += 1
    return [PROPS[c] for c in cids if c in PROPS]


def fake_synonyms(client, cid):
    return {"2001": ["protopanaxatriol-like", "12345-67-8"]}.get(str(cid), [])


PARENT = {"cid": "1001", "molecular_formula": "C36H60O8", "molecular_weight": "620.9"}


def main():
    print("\n" + "=" * 60)
    print("苷元第二層解析（分子式推算＋子結構比對）")
    print("=" * 60)

    print("\n【分子式運算】")
    check("解析分子式", pc.parse_formula("C36H60O8") == {"C": 36, "H": 60, "O": 8})
    check("鹽類／混合物（帶點號或電荷）不解析", pc.parse_formula("C2H3O2.Na") is None
          and pc.parse_formula("C5H5N+") is None)
    check("Hill 排序（C、H 在前，其餘依字母）",
          pc.format_formula({"O": 3, "H": 50, "C": 30}) == "C30H50O3"
          and pc.format_formula({"N": 1, "C": 2, "H": 7, "Cl": 1}) == "C2H7ClN")
    check("計算分子量", abs(pc.formula_mass({"C": 30, "H": 50, "O": 3}) - 458.727) < 0.01,
          pc.formula_mass({"C": 30, "H": 50, "O": 3}))

    r = pc.aglycone_formula("C36H60O8", "458.7", "620.9")
    check("**Rh4 去掉一個葡萄糖 → C30H50O3**", r["ok"] and r["formula"] == "C30H50O3", r)
    check("說明扣了哪些糖基", "1×己糖" in r.get("sugars", ""), r.get("sugars"))
    r = pc.aglycone_formula("C42H72O14", "476.7", "801.0")   # Rg1（兩個葡萄糖）→ C30H52O4
    check("兩個糖基也扣得對（Rg1 → C30H52O4）", r["ok"] and r["formula"] == "C30H52O4", r)
    r = pc.aglycone_formula("C36H60O8", "300.0", "620.9")
    check("分子量差湊不出糖基 → 不推算", not r["ok"] and "無法以" in r["reason"], r["reason"])
    r = pc.aglycone_formula("C5H10O5", "", "150.1")
    check("缺 TCMSP 分子量 → 不推算", not r["ok"])
    r = pc.aglycone_formula("C10H8", "-12.0", "150.1")
    check("扣不動（元素會變負）→ 不推算", not r["ok"])

    print("\n【子結構指紋】")
    check("指紋解碼與編碼一致", pc.fp_bits(fp({0, 7, 8, 880})) == {0, 7, 8, 880})
    check("壞的 base64 回 None", pc.fp_bits("@@@") is None and pc.fp_bits(None) is None)
    check("真正的苷元完全包含在母體裡（1.0）", pc.fp_containment(TRUE_AGLY, PARENT_BITS) == 1.0)
    check("無關異構物只部分包含（< 0.9）",
          pc.fp_containment(UNRELATED, PARENT_BITS) < pc.CONTAIN_MIN,
          pc.fp_containment(UNRELATED, PARENT_BITS))

    orig = (pc.search_by_formula, pc.fetch_properties, pc.fetch_synonyms, pc.time.sleep)
    pc.search_by_formula, pc.fetch_properties, pc.fetch_synonyms = fake_formula, fake_props, fake_synonyms
    pc.time.sleep = lambda *_a: None
    try:
        print("\n【單筆解析】")
        r = pc.resolve_aglycone(None, "Ginsenoside-Rh4_qt", "458.7", PARENT)
        check("**狀態是 pending，永遠不自動採用**", r["status"] == "pending", r["status"])
        check("第一名是完全包含在母體裡的苷元（不是無關異構物）",
              r["cid"] in ("2001", "2002"), r.get("cid"))
        check("母體苷本身不會出現在候選裡",
              all(c["cid"] != "1001" for c in r["candidates"]), [c["cid"] for c in r["candidates"]])
        check("候選依包含度排序，無關異構物排最後",
              r["candidates"][-1]["cid"] == "2003", [c["cid"] for c in r["candidates"]])
        check("候選帶包含度與相似度供審核",
              all("containment" in c and "similarity" in c for c in r["candidates"]))
        check("**同平面結構的立體異構物 → 提示人工挑立體構型**", "立體異構物" in r["note"], r["note"])
        check("註記交代推算過程（母體 CID、扣掉的糖、推算的分子式）",
              all(x in r["note"] for x in ("1001", "己糖", "C30H50O3")), r["note"])
        check("method 為 aglycone_formula", r["method"] == "aglycone_formula")

        FORMULA_HITS["C30H50O3"] = ["2003", "1001"]
        r = pc.resolve_aglycone(None, "Ginsenoside-Rh4_qt", "458.7", PARENT)
        check("同分子式都不像母體的一部分 → unresolved", r["status"] == "unresolved", r["status"])
        FORMULA_HITS["C30H50O3"] = []
        r = pc.resolve_aglycone(None, "Ginsenoside-Rh4_qt", "458.7", PARENT)
        check("PubChem 查無此分子式 → unresolved", r["status"] == "unresolved"
              and "查無此分子式" in r["note"], r["note"])
        r = pc.resolve_aglycone(None, "X_qt", "100.0", PARENT)
        check("推算不出分子式 → unresolved，不打 PubChem", r["status"] == "unresolved")
        NET_DOWN["on"] = True
        r = pc.resolve_aglycone(None, "Ginsenoside-Rh4_qt", "458.7", PARENT)
        check("連線失敗 → error（之後可重跑）", r["status"] == "error", r["status"])
        NET_DOWN["on"] = False
        FORMULA_HITS["C30H50O3"] = ["2003", "2001", "2002", "1001"]

        print("\n【批次端點】")
        db = SessionLocal()
        ings = [("MOLA01", "Ginsenoside-Rh4_qt", "458.7"),    # 自動否決的苷元誤配 → 要處理
                ("MOLA02", "alexandrin_qt", "476.7"),         # 多筆命中全是母體苷 → 要處理（推算出 C29H48O5，PubChem 查無）
                ("MOLA03", "Something_qt", "458.7"),          # 人工否決 → 不動
                ("MOLA04", "plain compound", "300.0"),        # 不是苷元 → 不動
                ("MOLA05", "Rg5_qt", "458.7")]                # 自動否決，但這次連線失敗 → 不動
        for mol_id, name, mw in ings:
            db.add(models.TcmspIngredient(mol_id=mol_id, molecule_name=name, mw=mw, ob="40", dl="0.3"))
        admin = db.query(models.User).filter(models.User.account == "admin").first()
        rh4 = pc.glycoside_mismatch("Ginsenoside-Rh4_qt", "458.7", "620.9")
        db.add(models.TcmspIngredientPubchem(
            mol_id="MOLA01", cid="1001", molecular_formula="C36H60O8", molecular_weight="620.9",
            inchikey="PARENTRH4XXXXX-UHFFFAOYSA-N", tcmsp_mw="458.7", mw_delta="162.2",
            method="aglycone_parent", confidence="0.0", status="rejected", candidates=pc.dumps([]), note=rh4))
        db.add(models.TcmspIngredientPubchem(   # 多筆命中：cid 空，母體在候選裡
            mol_id="MOLA02", cid=None, tcmsp_mw="476.7", method="aglycone_parent", confidence="0.0",
            status="rejected", note="多筆皆為母體苷",
            candidates=pc.dumps([{"cid": "3001", "molecular_formula": "C35H58O10", "molecular_weight": "638.8"},
                                 {"cid": "3002", "molecular_formula": "C35H58O10", "molecular_weight": "638.8"}])))
        db.add(models.TcmspIngredientPubchem(
            mol_id="MOLA03", cid="1001", molecular_formula="C36H60O8", molecular_weight="620.9",
            tcmsp_mw="458.7", method="aglycone_parent", confidence="0.0", status="rejected",
            note="人工否決", reviewed_by=admin.id))
        db.add(models.TcmspIngredientPubchem(
            mol_id="MOLA04", cid="4001", molecular_formula="C10H8", molecular_weight="462.0",
            tcmsp_mw="300.0", method="exact", confidence="0.0", status="rejected", note="非苷元"))
        db.add(models.TcmspIngredientPubchem(
            mol_id="MOLA05", cid="1001", molecular_formula="C36H60O8", molecular_weight="620.9",
            tcmsp_mw="458.7", method="aglycone_parent", confidence="0.0", status="rejected", note=rh4))
        db.commit()

        A = {"Authorization": "Bearer " + client.post(
            "/auth/login", json={"account": "admin", "password": "0000"}).json()["access_token"]}
        s = client.get("/tcmsp/ingredient-mapping/stats", headers=A).json()
        check("**卡片的第二層待處理＝批次佇列**：3 筆（人工否決、非苷元不算）",
              s.get("aglycone_second_tier") == 3, s.get("aglycone_second_tier"))

        # MOLA02 的母體 C35H58O10（638.8）去掉一個己糖 → C29H48O5（476.7），fixture 沒有這個分子式 → unresolved
        # MOLA05 要模擬連線失敗：用 mol_id 判斷
        real = pc.resolve_aglycones_many

        def flaky(items, **kw):
            out = real([i for i in items if i[0] != "MOLA05"], **kw)
            out.update({i[0]: {"status": "error", "note": "timeout"} for i in items if i[0] == "MOLA05"})
            return out
        pc.resolve_aglycones_many = flaky
        try:
            r = client.post("/tcmsp/ingredient-mapping/resolve-aglycones", headers=A, json={"limit": 10}).json()
        finally:
            pc.resolve_aglycones_many = real
        check("一批處理 3 筆：待確認 1、找不到 1、連線失敗 1",
              r["processed"] == 3 and r["pending"] == 1 and r["unresolved"] == 1 and r["error"] == 1, r)
        check("連線失敗的那筆算在剩餘裡（下次重跑）", r["remaining"] == 1, r["remaining"])

        db.expire_all()
        row = lambda m: db.query(models.TcmspIngredientPubchem).filter_by(mol_id=m).one()
        a1 = row("MOLA01")
        check("苷元誤配那筆轉為待確認、method 為 aglycone_formula",
              a1.status == "pending" and a1.method == "aglycone_formula", (a1.status, a1.method))
        check("結構欄位換成候選苷元，不再是母體苷",
              a1.cid in ("2001", "2002") and a1.molecular_formula == "C30H50O3", (a1.cid, a1.molecular_formula))
        check("分子量差值改為候選苷元與 TCMSP 的差", float(a1.mw_delta) < 0.5, a1.mw_delta)
        check("候選清單存下來給審核者挑", len(pc.json.loads(a1.candidates)) == 3)
        a2 = row("MOLA02")
        check("推算不出苷元的那筆 → unresolved，母體苷結構不再掛在這一列",
              a2.status == "unresolved" and a2.cid is None and a2.molecular_formula is None, (a2.status, a2.cid))
        check("**人工否決的不動**", row("MOLA03").status == "rejected" and row("MOLA03").note == "人工否決")
        check("非苷元的否決列不動", row("MOLA04").status == "rejected" and row("MOLA04").method == "exact")
        check("連線失敗的那筆原封不動", row("MOLA05").status == "rejected"
              and row("MOLA05").method == "aglycone_parent")

        s = client.get("/tcmsp/ingredient-mapping/stats", headers=A).json()
        check("卡片剩 1 筆（就是連線失敗那筆）", s.get("aglycone_second_tier") == 1, s.get("aglycone_second_tier"))
        q = client.get("/tcmsp/ingredient-mapping/review?status=pending", headers=A).json()
        check("待確認清單看得到它、方法標記正確",
              any(i["mol_id"] == "MOLA01" and i["method"] == "aglycone_formula" for i in q["items"]))

        r = client.post("/tcmsp/ingredient-mapping/confirm", headers=A,
                        json={"mol_id": "MOLA01", "cid": "2002", "note": "依母體立體構型挑選"}).json()
        check("人工從候選挑一筆確認 → confirmed，保留 aglycone_formula 來源",
              r["status"] == "confirmed" and r["method"] == "aglycone_formula" and r["cid"] == "2002",
              (r["status"], r["method"], r["cid"]))
        k = client.get("/tcmsp/ingredient-mapping/lookup?key=AGLYCONEPPTXXX-BBBBBBBBBB-N", headers=A).json()
        check("確認後可用苷元的 InChIKey 反查到這個成分", k["total"] == 1, k)
        k = client.get("/tcmsp/ingredient-mapping/lookup?key=PARENTRH4XXXXX-UHFFFAOYSA-N", headers=A).json()
        check("母體苷的 InChIKey 反查不到這個成分", all(i.get("mol_id") != "MOLA01" for i in k.get("items", [])), k)
        acts = [x.action for x in db.query(models.AuditLog).all()]
        check("批次寫入共用稽核表", "tcmsp_resolve_aglycones" in acts)

        r = client.post("/tcmsp/ingredient-mapping/resolve-aglycones", headers=A, json={"limit": 10}).json()
        check("再跑一次只處理剩下那 1 筆", r["processed"] == 1 and r["pending"] == 1, r)
        r = client.post("/tcmsp/ingredient-mapping/resolve-aglycones", headers=A, json={"limit": 10}).json()
        check("全部處理完後回 0 筆", r["processed"] == 0 and r["remaining"] == 0, r)
        U = client.post("/auth/login", json={"account": "nobody", "password": "x"})
        check("未登入不能執行", client.post("/tcmsp/ingredient-mapping/resolve-aglycones",
                                          json={"limit": 1}).status_code == 401)
        db.close()
    finally:
        pc.search_by_formula, pc.fetch_properties, pc.fetch_synonyms, pc.time.sleep = orig

    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print("   -", f)
        raise SystemExit(1)
    print("✅ 苷元第二層解析驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        client = c
        main()
