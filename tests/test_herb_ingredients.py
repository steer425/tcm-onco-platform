"""F1-7 藥材活性成分與結構標準化端點 — 驗收腳本（不連外網）。

**這支測試最重要的部分是母體一致性。**

F1-6（全庫覆蓋率）與 F1-7（單一藥材）回答的是不同問題，但兩者的「活性成分」
判定必須是同一份——v1.40.1 的事故就是同一個母體被寫了兩次，兩邊回答了不同的
問題（見 `rules.md`「進度數字與批次佇列必須共用同一支母體判定」）。

所以下面第一組斷言直接拿端點的回傳值去比對 `pathways.active_ingredients()`
的結果：只要有人日後在端點裡重寫一次 OB／DL 條件，這條就會紅。

跟其他驗收腳本一樣**不是 pytest**（函式名稱不是 test_*），
`python -m pytest tests/` 會 collected 0 items。
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_herb_ingredients.db")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_herb_ingredients.db"
        and os.path.exists("test_herb_ingredients.db")):
    os.remove("test_herb_ingredients.db")

from fastapi.testclient import TestClient

from app import models, pathways, tcmsp_pubchem as pc
from app.database import SessionLocal
from app.main import app
from app.security import hash_password

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


def main():
    client = TestClient(app)
    db = SessionLocal()

    # ---------- 測試資料 ----------
    print("\n【測試資料】")
    HERB_ID = 9001
    if not db.query(models.TcmspHerb).filter(models.TcmspHerb.id == HERB_ID).first():
        db.add(models.TcmspHerb(id=HERB_ID, herb_cn_name="测试参",
                                herb_pinyin="Ce Shi Shen",
                                herb_en_name="Test Ginseng", status="active"))
    # 下架的藥材不該查得到
    if not db.query(models.TcmspHerb).filter(models.TcmspHerb.id == 9002).first():
        db.add(models.TcmspHerb(id=9002, herb_en_name="Retired Herb", status="inactive"))

    # ob / dl 以字串存（可攜型別規範），其中刻意放一筆 'NA' 缺值
    ING = [
        # mol_id,      name,                 mw,       ob,     dl
        ("MOLH01", "alpha-compound", "302.25", "46.43", "0.28"),   # 活性，已標準化
        ("MOLH02", "beta-compound_qt", "414.71", "55.0", "0.30"),  # 活性，待確認（苷元誤配）
        ("MOLH03", "gamma-compound", "128.17", "40.0", "0.25"),    # 活性，查無結果
        ("MOLH04", "delta-compound", "200.10", "38.0", "0.20"),    # 活性，尚未處理（無映射列）
        ("MOLH05", "epsilon-compound", "150.00", "12.0", "0.30"),  # 非活性（OB 不足）
        ("MOLH06", "zeta-compound", "180.00", "NA", "0.30"),       # ADME 缺值
    ]
    for mol_id, name, mw, ob, dl in ING:
        if not db.query(models.TcmspIngredient).filter(
                models.TcmspIngredient.mol_id == mol_id).first():
            db.add(models.TcmspIngredient(mol_id=mol_id, molecule_name=name,
                                          mw=mw, ob=ob, dl=dl))
    db.flush()
    for mol_id, *_ in ING:
        if not db.query(models.TcmspHerbIngredient).filter(
                models.TcmspHerbIngredient.herb_id == HERB_ID,
                models.TcmspHerbIngredient.mol_id == mol_id).first():
            db.add(models.TcmspHerbIngredient(herb_id=HERB_ID, mol_id=mol_id))

    def mapping(mol_id, status, cid, **kw):
        if db.query(models.TcmspIngredientPubchem).filter(
                models.TcmspIngredientPubchem.mol_id == mol_id,
                models.TcmspIngredientPubchem.cid == cid).first():
            return
        db.add(models.TcmspIngredientPubchem(mol_id=mol_id, status=status, cid=cid, **kw))

    mapping("MOLH01", "auto", "111", canonical_smiles="CCO",
            cas_number="117-39-5", inchikey="AAAAAAAAAA-BBBBBBBBBB-C", mw_delta=None)
    # 同一個成分兩筆映射：已採用的那筆必須勝出（best_mapping_by_mol）
    mapping("MOLH01", "pending", "999", canonical_smiles="CC", mw_delta="50.0")
    mapping("MOLH02", "pending", "222", canonical_smiles="CCC",
            inchikey="DDDDDDDDDD-EEEEEEEEEE-F", mw_delta="162.1")
    mapping("MOLH03", "unresolved", None)

    if not db.query(models.User).filter(models.User.account == "hiuser").first():
        db.add(models.User(account="hiuser", password_hash=hash_password("0000"),
                           status=models.UserStatus.active))
    db.commit()
    check("測試藥材與成分就緒",
          db.query(models.TcmspHerbIngredient).filter(
              models.TcmspHerbIngredient.herb_id == HERB_ID).count() == 6)

    r = client.post("/auth/login", json={"account": "hiuser", "password": "0000"})
    U = {"Authorization": f"Bearer {r.json()['access_token']}"}

    URL = f"/tcmsp/herbs/public/{HERB_ID}/active-ingredients"

    # ---------- 權限與錯誤處理 ----------
    print("\n【權限與錯誤處理】")
    check("未帶 token → 401", client.get(URL).status_code == 401)
    check("不存在的藥材 → 404",
          client.get("/tcmsp/herbs/public/999999/active-ingredients",
                     headers=U).status_code == 404)
    check("已下架的藥材 → 404",
          client.get("/tcmsp/herbs/public/9002/active-ingredients",
                     headers=U).status_code == 404)

    data = client.get(URL, headers=U).json()

    # ---------- 母體一致性（本測試的核心） ----------
    print("\n【母體一致性】")
    ob_min, dl_min = pathways.adme_thresholds(db)
    meta = pathways.active_ingredients(db, HERB_ID, ob_min, dl_min)
    check("**端點的活性成分母體＝pathways.active_ingredients() 的結果**",
          data["totals"]["active"] == meta["passed_count"] == 4,
          (data["totals"]["active"], meta["passed_count"]))
    check("回傳的 mol_id 與該函式挑出的完全相同",
          sorted(i["mol_id"] for i in data["items"]) == sorted(meta["passed"]),
          [i["mol_id"] for i in data["items"]])
    check("全部成分數與活性成分數分得開",
          data["totals"]["all_ingredients"] == 6, data["totals"]["all_ingredients"])
    check("ADME 缺值單獨計數，不混進「不達標」",
          data["totals"]["missing_adme"] == 1, data["totals"]["missing_adme"])
    check("門檻值有回傳，畫面才知道這份名單是用什麼條件篩的",
          data["thresholds"]["ob_min"] == ob_min and data["thresholds"]["dl_min"] == dl_min,
          data["thresholds"])

    # ---------- 標準化狀態 ----------
    print("\n【標準化狀態】")
    by_mol = {i["mol_id"]: i for i in data["items"]}
    check("已標準化只算 auto／confirmed",
          data["totals"]["standardised"] == 1, data["totals"]["standardised"])
    check("**同一成分有多筆映射時，已採用的那筆勝出**",
          by_mol["MOLH01"]["status"] == "auto" and by_mol["MOLH01"]["cid"] == "111",
          (by_mol["MOLH01"]["status"], by_mol["MOLH01"]["cid"]))
    check("待確認不算已標準化", by_mol["MOLH02"]["status"] == "pending")
    check("查無結果如實回報", by_mol["MOLH03"]["status"] == "unresolved")
    check("**沒有映射列的成分回 untouched，與『查無結果』分得開**",
          by_mol["MOLH04"]["status"] == "untouched", by_mol["MOLH04"]["status"])
    check("SMILES／CAS／InChIKey 只算已採用的那筆",
          (data["totals"]["with_smiles"], data["totals"]["with_cas"],
           data["totals"]["with_inchikey"]) == (1, 1, 1),
          (data["totals"]["with_smiles"], data["totals"]["with_cas"],
           data["totals"]["with_inchikey"]))
    check("分子量差有帶出來，畫面才能提示苷元誤配",
          by_mol["MOLH02"]["mw_delta"] == 162.1, by_mol["MOLH02"]["mw_delta"])
    check("by_status 加總等於活性成分數",
          sum(data["by_status"].values()) == data["totals"]["active"], data["by_status"])

    # ---------- 共用判定本身 ----------
    print("\n【共用判定】")
    best = pc.best_mapping_by_mol(db, ["MOLH01", "MOLH02", "MOLH04"])
    check("best_mapping_by_mol 對多筆映射取已採用的", best["MOLH01"].cid == "111")
    check("沒有映射的成分不會出現在結果裡", "MOLH04" not in best)
    check("空清單回空 dict，不炸也不查整張表", pc.best_mapping_by_mol(db, []) == {})

    # ---------- 藥材基本資料 ----------
    print("\n【藥材基本資料】")
    check("回傳藥材名稱供畫面顯示",
          data["herb"]["herb_id"] == HERB_ID and data["herb"]["herb_en_name"] == "Test Ginseng",
          data["herb"])
    check("成分名稱為 TCMSP 英文原名（資料庫沒有中文名稱欄位）",
          by_mol["MOLH01"]["molecule_name"] == "alpha-compound")

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print(f"   - {f}")
        raise SystemExit(1)
    print("✅ 藥材活性成分端點驗證全部通過")


if __name__ == "__main__":
    main()
