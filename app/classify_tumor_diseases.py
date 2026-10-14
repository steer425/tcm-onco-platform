"""
疾病腫瘤分類的檢視／套用腳本（v1.46.0）。判定規則在 app/disease_tumor.py。

    python -m app.classify_tumor_diseases            # 只看結果，不寫入（預設）
    python -m app.classify_tumor_diseases --apply    # 寫入資料庫
    python -m app.classify_tumor_diseases --csv tumor_review.csv   # 另存一份全清單供人工檢查

平常不需要手動跑：migrate_schema、TCMSP 匯入、後台「重算統計」都會呼叫同一支判定。
這支是給「想先看清楚會怎麼分、哪些需要人工確認」用的。
管理者在後台「疾病中文名稱管理」手動指定過的疾病，不論有沒有 --apply 都不會被改。

要對正式資料庫執行，先設定 DATABASE_URL（PowerShell：$env:DATABASE_URL="postgresql://..."）。
"""
import argparse
import csv
import sys

from app import models
from app.database import Base, SessionLocal, engine
from app.disease_tumor import TUMOR_BASIS_LABELS, TUMOR_CLASS_LABELS, apply_tumor_classification, classify_disease


def main(argv=None):
    ap = argparse.ArgumentParser(description="疾病的腫瘤分類：檢視或寫入")
    ap.add_argument("--apply", action="store_true", help="寫入資料庫（預設只顯示結果）")
    ap.add_argument("--csv", help="把每一筆疾病的判定結果另存成 CSV（UTF-8 BOM，Excel 可直接開）")
    args = ap.parse_args(argv)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        r = apply_tumor_classification(db, dry_run=not args.apply)
        label = lambda c: TUMOR_CLASS_LABELS.get(c, "非腫瘤") if c else "非腫瘤"
        print(f"\n共 {r['total']} 種疾病，判定為腫瘤 {r['tumor_total']} 種"
              f"（{r['tumor_total'] / r['total'] * 100:.1f}%）" if r["total"] else "\n資料庫裡沒有疾病資料")
        for c in ["malignant", "in_situ", "benign", "uncertain", "unspecified"]:
            print(f"  {TUMOR_CLASS_LABELS[c]:<12} {r['counts'][c]:>5}")
        print(f"  {'非腫瘤':<12} {r['counts']['none']:>5}")
        print("判定依據：" + "、".join(f"{TUMOR_BASIS_LABELS[k]} {v}" for k, v in r["by_basis"].items()))

        print(f"\n{'已寫入' if args.apply else '若加 --apply 會變動'} {len(r['changed'])} 筆")
        for x in r["changed"][:30]:
            print(f"  {x['dis_id']:<10} {label(x['from'])} → {label(x['to'])}（{TUMOR_BASIS_LABELS.get(x['basis'], '-')}）  {x['disease_name']}")
        if len(r["changed"]) > 30:
            print(f"  …另有 {len(r['changed']) - 30} 筆")

        print(f"\n需要人工看一眼：{len(r['conflicts'])} 筆（不影響寫入，判定以 ICD 為準；要改請到後台手動指定）")
        for x in r["conflicts"]:
            print(f"  {x['dis_id']:<10} ICD9={x['icd9'] or '-'} ICD10={x['icd10'] or '-'}  {x['disease_name']}\n"
                  f"             → {label(x['tumor_class'])}：{x['note']}")

        if args.csv:
            with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["dis_id", "disease_name", "disease_cn_name", "icd9", "icd10",
                            "tumor_class", "分類", "依據", "需要確認的原因"])
                for d in db.query(models.TcmspDisease).order_by(models.TcmspDisease.dis_id).all():
                    if d.tumor_basis == "manual":
                        cls, basis, note = d.tumor_class, "manual", ""
                    else:
                        c = classify_disease(d.disease_name, d.disease_cn_name, d.icd9, d.icd10)
                        cls, basis, note = c["tumor_class"], c["tumor_basis"], c["conflict"] or ""
                    w.writerow([d.dis_id, d.disease_name, d.disease_cn_name or "", d.icd9 or "", d.icd10 or "",
                                cls or "", label(cls), TUMOR_BASIS_LABELS.get(basis, ""), note])
            print(f"\n全清單已存到 {args.csv}")
        if not args.apply:
            print("\n（沒有寫入任何資料。確認無誤後加 --apply）")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
