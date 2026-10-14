"""批次手動指定腫瘤分類（app/set_disease_tumor_class.py，v1.46.1）— 驗證。

重點斷言：預設不寫入；病名對不上整批不寫；寫入後重算統計不會被改回去；可重複執行。
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_set_tumor_class.db")

# ⛔ 測試會寫入、刪除資料，**絕不能跑在正式資料庫上**（v1.43.0 實際發生過）。
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。\n"
              "   請先清掉：Remove-Item Env:DATABASE_URL　或開一個新的 PowerShell 視窗再跑。")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_set_tumor_class.db"
        and os.path.exists("test_set_tumor_class.db")):
    os.remove("test_set_tumor_class.db")

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.recompute_stats import recompute_disease_tumor_class
from app.set_disease_tumor_class import CORRECTIONS, run

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


# 與正式資料相同的病名與 ICD（2026-10-15 tumor_review.csv）
PROD = [
    ("DIS00459", "Leukemia, Myeloid, Acute", "205.0", "E92.0"),
    ("DIS00552", "Neurogenic bladder", "188", "C67"),
    ("DIS00066", "Angiogenesis in metastatic and atherosclerotic processes", None, None),
    ("DIS00370", "Hereditary Polyposis Syndromes", None, None),
    ("DIS00474", "Lymphangiomatosis", None, None),
    ("DIS00200", "Colorectal cancer", None, None),     # 不在修正清單，不能被動到
]
WANT = {"DIS00459": "malignant", "DIS00552": None, "DIS00066": None, "DIS00370": "benign", "DIS00474": "benign"}


def state(db):
    db.expire_all()
    return {d.dis_id: (d.tumor_class, d.tumor_basis) for d in db.query(models.TcmspDisease).all()}


def main():
    db = SessionLocal()
    for dis_id, name, i9, i10 in PROD:
        db.add(models.TcmspDisease(dis_id=dis_id, disease_name=name, icd9=i9, icd10=i10))
    db.commit()
    recompute_disease_tumor_class(db)
    before = state(db)
    check("自動判定與正式資料相同（DIS00459 非腫瘤、DIS00552 惡性、DIS00066 惡性）",
          before["DIS00459"][0] is None and before["DIS00552"][0] == "malignant"
          and before["DIS00066"][0] == "malignant", before)

    print("\n【預設不寫入】")
    r = run(db, apply=False)
    check("列出 5 筆會修改", len(r["changed"]) == 5 and not r["errors"], r)
    check("資料完全沒變", state(db) == before)

    print("\n【病名對不上 → 整批不寫】")
    bad = CORRECTIONS[:4] + [("DIS00474", "Something else", "benign", "x")]
    r = run(db, apply=True, corrections=bad)
    check("回報錯誤", len(r["errors"]) == 1 and "編號可能變了" in r["errors"][0], r["errors"])
    check("前 4 筆也沒有寫入", state(db) == before)
    r = run(db, apply=True, corrections=[("DIS99999", "Nope", None, "x")])
    check("找不到 Dis ID → 錯誤", r["errors"] and "找不到" in r["errors"][0])

    print("\n【寫入】")
    r = run(db, apply=True)
    after = state(db)
    check("5 筆都改成指定值且為管理者指定",
          all(after[k] == (v, "manual") for k, v in WANT.items()), after)
    check("清單以外的疾病沒被動到", after["DIS00200"] == before["DIS00200"])
    logs = db.query(models.AuditLog).filter(models.AuditLog.action == "update_tcmsp_disease").all()
    check("寫 5 筆稽核，註明腳本與原因",
          len(logs) == 5 and all("set_disease_tumor_class" in (x.detail or "") for x in logs),
          [x.detail for x in logs])

    print("\n【重算統計不會改回去】")
    recompute_disease_tumor_class(db)
    check("重算後仍為管理者指定值", state(db) == after)

    print("\n【可重複執行】")
    r = run(db, apply=True)
    check("再跑一次：0 筆修改、5 筆跳過", not r["changed"] and len(r["skipped"]) == 5, r)
    check("沒有多寫稽核", db.query(models.AuditLog).filter(
        models.AuditLog.action == "update_tcmsp_disease").count() == 5)

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 批次指定腫瘤分類驗證全部通過")


if __name__ == "__main__":
    with TestClient(app):
        main()
