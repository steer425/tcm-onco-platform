"""疾病的腫瘤分類（v1.46.0）— 端對端驗證。

三組最重要的斷言：
  1. 判定規則：ICD 優先、多碼取最嚴重、常見誤判字樣（cancer pain、hyperplasia、aneurysm、glaucoma）不會被當成腫瘤
  2. **手動指定永遠不會被自動分類覆蓋**（重算統計、migrate、重新匯入都走同一支 recompute）
  3. 前台三條讀取路徑（疾病清單、疾病詳情、藥材詳情、完整資料）都帶出同一組欄位
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_disease_tumor.db")

# ⛔ 測試會寫入、刪除資料，**絕不能跑在正式資料庫上**（v1.43.0 實際發生過）。
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。\n"
              "   請先清掉：Remove-Item Env:DATABASE_URL　或開一個新的 PowerShell 視窗再跑。")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_disease_tumor.db"
        and os.path.exists("test_disease_tumor.db")):
    os.remove("test_disease_tumor.db")

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.disease_tumor import classify_disease
from app.main import app
from app.recompute_stats import recompute_all_stats

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


# (dis_id, 英文名, 中文名, icd9, icd10, 預期分類, 預期依據)
CASES = [
    ("DIS001", "Breast cancer", "乳腺癌", "174,175", "C50", "malignant", "icd10"),
    ("DIS002", "Colorectal cancer", None, None, "C18-C20", "malignant", "icd10"),
    ("DIS003", "Lung cancer", None, None, "C34,D02.2", "malignant", "icd10"),            # 多碼取最嚴重
    ("DIS004", "Carcinoma in situ of cervix", None, None, "D06", "in_situ", "icd10"),
    ("DIS005", "Pituitary adenoma", None, None, "D35.2", "benign", "icd10"),
    ("DIS006", "Polycythemia vera", None, None, "D45", "uncertain", "icd10"),            # 病名沒有 tumor 字樣
    ("DIS007", "Leukemia", None, "204-208", None, "malignant", "icd9"),                   # 只有 ICD-9
    ("DIS008", "Solid tumors", None, None, None, "unspecified", "name"),                 # 只有病名
    ("DIS009", "Uterine fibroids", None, None, None, "benign", "name"),
    ("DIS010", "Cancer pain", None, None, None, None, None),                             # 併發症，不是腫瘤
    ("DIS011", "Benign prostatic hyperplasia", None, "600", "N40", None, None),          # 增生不是贅生
    ("DIS012", "Glaucoma", None, None, None, None, None),                                # -oma 字尾陷阱
    ("DIS013", "Aortic aneurysm", "主動脈瘤", None, None, None, None),                   # 動脈瘤
    ("DIS014", "Anemia", None, None, "D50-D64", None, None),                             # D 碼但不在腫瘤範圍
    ("DIS015", "Hypertension", None, "401", "I10", None, None),
    ("DIS016", None, "胃癌", None, None, "malignant", "name"),                            # 只有中文名
    ("DIS017", "Tumor lysis syndrome", None, None, None, None, None),
    ("DIS018", "Neurofibromatosis", None, None, None, None, None),
]


def unit():
    print("\n【判定規則】")
    for dis_id, en, cn, i9, i10, want_cls, want_basis in CASES:
        r = classify_disease(en, cn, i9, i10)
        check(f"{en or cn} → {want_cls or '非腫瘤'}（{want_basis or '-'}）",
              (r["tumor_class"], r["tumor_basis"]) == (want_cls, want_basis), r)
    r = classify_disease("Cancer pain", None, None, None)
    check("病名有腫瘤字樣但被排除時，留下需要確認的說明", r["conflict"] and "併發症" in r["conflict"], r)
    r = classify_disease("Hypertension", None, None, "C50")
    check("ICD 說是腫瘤、病名沒有字樣 → 依 ICD，並標示需要確認",
          r["tumor_class"] == "malignant" and r["conflict"], r)
    r = classify_disease("Breast cancer", None, None, "I10")
    check("病名說是腫瘤、ICD 不在範圍 → 依 ICD（非腫瘤），並標示需要確認",
          r["tumor_class"] is None and r["conflict"], r)


def main(client):
    unit()
    db = SessionLocal()
    for dis_id, en, cn, i9, i10, *_ in CASES:
        db.add(models.TcmspDisease(dis_id=dis_id, disease_name=en, disease_cn_name=cn, icd9=i9, icd10=i10))
    # 一條藥材 → 成分 → 靶點 → 疾病，驗藥材詳情也帶出分類
    db.add(models.TcmspHerb(id=77, herb_cn_name="测试草", herb_en_name="Test Herb", status="active"))
    db.add(models.TcmspIngredient(mol_id="MOL777", molecule_name="testol"))
    db.add(models.TcmspHerbIngredient(herb_id=77, mol_id="MOL777"))
    db.add(models.TcmspTarget(tar_id="TAR777", target_name="Test protein"))
    db.add(models.TcmspIngredientTarget(mol_id="MOL777", tar_id="TAR777"))
    for d in ("DIS001", "DIS015"):
        db.add(models.TcmspTargetDisease(tar_id="TAR777", dis_id=d))
    db.commit()

    print("\n【重算統計時一併判定】")
    recompute_all_stats(db)
    db.expire_all()
    got = {d.dis_id: (d.tumor_class, d.tumor_basis) for d in db.query(models.TcmspDisease).all()}
    check("18 筆全部依規則寫入",
          all(got[c[0]] == (c[5], c[6]) for c in CASES),
          [(c[0], got[c[0]]) for c in CASES if got[c[0]] != (c[5], c[6])])

    A = {"Authorization": "Bearer " + client.post("/auth/login", json={"account": "admin", "password": "0000"}).json()["access_token"]}

    print("\n【前台讀取路徑】")
    lst = {d["dis_id"]: d for d in client.get("/tcmsp/diseases/public/list", headers=A).json()}
    check("疾病清單帶 tumor_class／tumor_basis", lst["DIS001"]["tumor_class"] == "malignant"
          and lst["DIS001"]["tumor_basis"] == "icd10" and lst["DIS015"]["tumor_class"] is None)
    check("疾病清單仍帶 target_count", "target_count" in lst["DIS001"])
    det = client.get("/tcmsp/diseases/public/DIS006/detail", headers=A).json()
    check("疾病詳情帶分類", det["diseases"][0]["tumor_class"] == "uncertain", det["diseases"])
    hd = client.get("/tcmsp/herbs/public/77/detail", headers=A).json()
    hdm = {d["dis_id"]: d["tumor_class"] for d in hd["diseases"]}
    check("藥材詳情的疾病帶分類", hdm == {"DIS001": "malignant", "DIS015": None}, hdm)
    full = {d["dis_id"]: d for d in client.get("/tcmsp/data/full", headers=A).json()["diseases"]}
    check("完整資料（/tcmsp/data/full）帶分類", full["DIS008"]["tumor_class"] == "unspecified")

    print("\n【後台：篩選】")
    def admin(q=""):
        return client.get("/tcmsp/diseases" + q, headers=A).json()
    check("只看腫瘤 → 10 筆", len(admin("?tumor=tumor")) == 10, len(admin("?tumor=tumor")))
    check("只看非腫瘤 → 8 筆", len(admin("?tumor=non_tumor")) == 8)
    rv = {d["dis_id"] for d in admin("?tumor=review")}
    check("需要確認：Cancer pain、Tumor lysis syndrome（病名有字樣但被排除）",
          {"DIS010", "DIS017"} <= rv, rv)
    check("後台列表帶自動判定結果", all("tumor_auto_class" in d for d in admin()))

    print("\n【後台：手動指定】")
    r = client.put("/tcmsp/diseases/DIS015", headers=A, json={"tumor_class": "benign"})
    check("手動指定 200", r.status_code == 200 and r.json()["tumor_basis"] == "manual", r.text[:200])
    client.put("/tcmsp/diseases/DIS001", headers=A, json={"tumor_class": "none"})
    recompute_all_stats(db)
    db.expire_all()
    d15 = db.get(models.TcmspDisease, "DIS015")
    d1 = db.get(models.TcmspDisease, "DIS001")
    check("**重算統計後手動指定仍保留**（Hypertension 仍為良性）", (d15.tumor_class, d15.tumor_basis) == ("benign", "manual"))
    check("**手動指定為非腫瘤也保留**（Breast cancer 仍為非腫瘤）", (d1.tumor_class, d1.tumor_basis) == (None, "manual"))
    row = next(x for x in admin("?tumor=manual") if x["dis_id"] == "DIS001")
    check("手動指定過的仍顯示「自動判定會是」", row["tumor_auto_class"] == "malignant", row)
    check("只看手動指定 → 2 筆", len(admin("?tumor=manual")) == 2)

    r = client.put("/tcmsp/diseases/DIS015", headers=A, json={"disease_cn_name": "高血壓"})
    db.expire_all()
    check("只改中文名稱（沒帶 tumor_class）不會動到分類",
          (db.get(models.TcmspDisease, "DIS015").tumor_basis) == "manual")
    client.put("/tcmsp/diseases/DIS015", headers=A, json={"tumor_class": "auto"})
    db.expire_all()
    d15 = db.get(models.TcmspDisease, "DIS015")
    check("選「自動判定」→ 交回系統，立即重判", (d15.tumor_class, d15.tumor_basis) == (None, None))
    check("不認得的分類 → 400",
          client.put("/tcmsp/diseases/DIS015", headers=A, json={"tumor_class": "cancerish"}).status_code == 400)

    logs = [x.detail for x in db.query(models.AuditLog).filter(models.AuditLog.action == "update_tcmsp_disease").all()]
    check("稽核寫出分類怎麼變（手動指定）", any("腫瘤分類 非腫瘤 → 良性腫瘤（手動指定）" in (x or "") for x in logs), logs)
    check("稽核寫出交回自動判定", any("交回自動判定" in (x or "") for x in logs), logs)
    check("只改中文名稱的那次稽核不提腫瘤分類",
          "編輯疾病 Hypertension：中文名稱 → 高血壓" in logs, logs)
    check("只改分類的那次稽核不提中文名稱",
          "編輯疾病 Hypertension：腫瘤分類 非腫瘤 → 良性腫瘤（手動指定）" in logs, logs)

    full = {d["dis_id"]: d for d in client.get("/tcmsp/data/full", headers=A).json()["diseases"]}
    check("後台修改後，前台完整資料快取立即失效", full["DIS001"]["tumor_class"] is None)

    print("\n【前端】")
    for page in ("disease_query.html", "tcmsp_query.html", "tcmsp-diseases.html"):
        check(f"{page} 載入 tumor-class.js", "js/tumor-class.js" in client.get(f"/app/{page}").text)
    js = client.get("/app/js/tumor-class.js").text
    from app.disease_tumor import TUMOR_CLASS_LABELS
    check("前端標籤與後端 TUMOR_CLASS_LABELS 一致",
          all(f'{k}: "{v}"' in js for k, v in TUMOR_CLASS_LABELS.items()))

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 疾病腫瘤分類驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        main(c)
