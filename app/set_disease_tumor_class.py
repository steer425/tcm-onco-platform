"""
批次手動指定疾病的腫瘤分類（v1.46.1）。

自動判定（app/disease_tumor.py）依 ICD 代碼與病名，但 TCMSP 原始資料本身有錯的代碼，
或學術上需要人來判斷的項目，就用這支一次寫成「管理者指定」（tumor_basis = manual）。
效果與在後台「疾病中文名稱管理」逐筆改下拉完全相同，之後重算統計、重新匯入都不會被改回去；
要交回自動判定，到後台把下拉改回「自動判定」即可。

    python -m app.set_disease_tumor_class            # 只顯示會怎麼改（預設，不寫入）
    python -m app.set_disease_tumor_class --apply    # 寫入

安全檢查：每一筆都核對病名。Dis ID 對不上預期病名（例如資料重新匯入後編號變了）就整批不寫，
避免把分類套到錯的疾病上。已經是指定值的跳過，可重複執行。

要對正式資料庫執行，先設定 DATABASE_URL（PowerShell：$env:DATABASE_URL="postgresql://..."）。
"""
import argparse
import sys

from app import models
from app.database import SessionLocal
from app.deps import write_audit_log
from app.disease_tumor import TUMOR_CLASS_LABELS

# (Dis ID, 預期英文病名, 指定分類（None＝非腫瘤）, 原因)
# 2026-10-15 依正式資料 tumor_review.csv 人工檢查的結果
CORRECTIONS = [
    ("DIS00459", "Leukemia, Myeloid, Acute", "malignant",
     "TCMSP 原始資料 ICD-10 填 E92.0，應為 C92.0（ICD-9 205.0 正確）"),
    ("DIS00552", "Neurogenic bladder", None,
     "TCMSP 原始資料把膀胱癌代碼 C67／188 掛在神經性膀胱上"),
    ("DIS00066", "Angiogenesis in metastatic and atherosclerotic processes", None,
     "描述的是血管新生過程，不是腫瘤本身"),
    ("DIS00370", "Hereditary Polyposis Syndromes", "benign",
     "家族性腺瘤性瘜肉症 ICD-10 D12.6（良性腫瘤），癌前病變"),
    ("DIS00474", "Lymphangiomatosis", "benign",
     "淋巴管瘤 ICD-10 D18.1（良性腫瘤）"),
]


def _label(c):
    return TUMOR_CLASS_LABELS.get(c, "非腫瘤") if c else "非腫瘤"


def run(db, apply: bool, corrections=CORRECTIONS) -> dict:
    """回傳 {"changed": [...], "skipped": [...], "errors": [...]}；有 errors 時不寫入任何一筆。"""
    changed, skipped, errors = [], [], []
    plan = []
    for dis_id, expect_name, cls, reason in corrections:
        if cls is not None and cls not in TUMOR_CLASS_LABELS:
            errors.append(f"{dis_id}：不認得的分類 {cls}")
            continue
        d = db.get(models.TcmspDisease, dis_id)
        if not d:
            errors.append(f"{dis_id}：資料庫裡找不到這筆疾病")
            continue
        if (d.disease_name or "").strip().lower() != expect_name.strip().lower():
            errors.append(f"{dis_id}：病名是「{d.disease_name}」，預期「{expect_name}」，編號可能變了")
            continue
        if (d.tumor_class, d.tumor_basis) == (cls, "manual"):
            skipped.append(f"{dis_id} {d.disease_name}：已經是「{_label(cls)}」（管理者指定）")
            continue
        plan.append((d, cls, reason))
        changed.append(f"{dis_id} {d.disease_name}：{_label(d.tumor_class)} → {_label(cls)}　（{reason}）")

    if errors or not apply:
        db.rollback()
        return {"changed": changed, "skipped": skipped, "errors": errors, "written": False}

    for d, cls, reason in plan:
        before = d.tumor_class
        d.tumor_class, d.tumor_basis = cls, "manual"
        db.commit()
        # 與後台手動指定同一個 action 名稱與文字格式，稽核紀錄裡看起來一致
        write_audit_log(db, None, "update_tcmsp_disease", "tcmsp_disease", d.dis_id,
                        f"編輯疾病 {d.disease_name}：腫瘤分類 {_label(before)} → {_label(cls)}"
                        f"（手動指定，set_disease_tumor_class 腳本；{reason}）")
    return {"changed": changed, "skipped": skipped, "errors": errors, "written": bool(plan)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="批次手動指定疾病的腫瘤分類")
    ap.add_argument("--apply", action="store_true", help="寫入資料庫（預設只顯示）")
    args = ap.parse_args(argv)
    db = SessionLocal()
    try:
        r = run(db, args.apply)
    finally:
        db.close()

    if r["errors"]:
        print("⛔ 有項目核對不過，整批沒有寫入：")
        for x in r["errors"]:
            print("  -", x)
        return 1
    print(f"{'已修改' if args.apply else '加 --apply 會修改'} {len(r['changed'])} 筆：")
    for x in r["changed"]:
        print("  ", x)
    if r["skipped"]:
        print(f"\n跳過 {len(r['skipped'])} 筆（已經是指定值）：")
        for x in r["skipped"]:
            print("  ", x)
    if not args.apply:
        print("\n（沒有寫入任何資料。確認無誤後加 --apply）")
    elif r["written"]:
        print("\n完成。前台查詢站有 10 分鐘快取，最慢 10 分鐘後看到新分類。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
