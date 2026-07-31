"""
將 TCMSP 藥材關聯資料從 JSON 檔案匯入資料庫。

使用方式：
    python -m app.import_tcmsp_data /path/to/tcmsp_data.json

可重複執行（idempotent）：已存在的資料會先清空對應資料表再重新匯入，
避免重複匯入造成資料重複或違反 unique constraint。
"""
import json
import sys

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, engine, Base


def _s(v):
    """統一轉成字串，None 維持 None（原始資料型別混雜 str/int/float，資料庫欄位皆用字串儲存以求簡單一致）"""
    return None if v is None else str(v)


def import_data(json_path: str):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        print("清空既有 TCMSP 資料表...")
        db.query(models.TcmspTargetDisease).delete()
        db.query(models.TcmspIngredientTarget).delete()
        db.query(models.TcmspHerbIngredient).delete()
        db.query(models.TcmspHerb).delete()
        db.query(models.TcmspIngredient).delete()
        db.query(models.TcmspTarget).delete()
        db.query(models.TcmspDisease).delete()
        db.commit()

        print(f"匯入 {len(data['herbs'])} 種藥材...")
        db.bulk_insert_mappings(models.TcmspHerb, [
            {
                "id": h["herb_id"],
                "herb_cn_name": h.get("herb_cn_name"),
                "herb_pinyin": h.get("herb_pinyin"),
                "herb_en_name": h.get("herb_en_name"),
                "child_cn_name": h.get("child_cn_name"),
                "child_en_name": h.get("child_en_name"),
            }
            for h in data["herbs"]
        ])

        print(f"匯入 {len(data['ingredients'])} 個成分...")
        db.bulk_insert_mappings(models.TcmspIngredient, [
            {
                "mol_id": i["mol_id"],
                "molecule_name": i.get("molecule_name"),
                "mw": _s(i.get("mw")), "hdon": _s(i.get("hdon")), "hacc": _s(i.get("hacc")),
                "alogp": _s(i.get("alogp")), "halflife": _s(i.get("halflife")), "ob": _s(i.get("ob")),
                "caco2": _s(i.get("caco2")), "bbb": _s(i.get("bbb")), "dl": _s(i.get("dl")),
                "fasa": _s(i.get("fasa")), "tpsa": _s(i.get("tpsa")), "rbn": _s(i.get("rbn")),
                "source": i.get("source"),
            }
            for i in data["ingredients"]
        ])

        print(f"匯入 {len(data['targets'])} 個靶點...")
        db.bulk_insert_mappings(models.TcmspTarget, [
            {
                "tar_id": t["tar_id"], "target_id": t.get("target_id"),
                "drugbank_id": t.get("drugbank_id"), "target_name": t.get("target_name"),
                "kegg": t.get("kegg"), "source": t.get("source"),
            }
            for t in data["targets"]
        ])

        print(f"匯入 {len(data['diseases'])} 個疾病...")
        db.bulk_insert_mappings(models.TcmspDisease, [
            {
                "dis_id": d["dis_id"], "disease_id": d.get("disease_id"),
                "disease_name": d.get("disease_name"), "icd9": d.get("icd9"), "icd10": d.get("icd10"),
            }
            for d in data["diseases"]
        ])
        db.commit()

        print(f"匯入 {len(data['herb_ingredient'])} 筆藥材-成分關聯...")
        db.bulk_insert_mappings(models.TcmspHerbIngredient, [
            {"id": models.gen_id(), "herb_id": r["herb_id"], "mol_id": r["mol_id"]}
            for r in data["herb_ingredient"]
        ])

        print(f"匯入 {len(data['ingredient_target'])} 筆成分-靶點關聯...")
        db.bulk_insert_mappings(models.TcmspIngredientTarget, [
            {
                "id": models.gen_id(), "mol_id": r["mol_id"], "tar_id": r["tar_id"],
                "validated": _s(r.get("validated")), "svm_score": _s(r.get("svm_score")),
                "rf_score": _s(r.get("rf_score")),
            }
            for r in data["ingredient_target"]
        ])

        print(f"匯入 {len(data['target_disease'])} 筆靶點-疾病關聯...")
        db.bulk_insert_mappings(models.TcmspTargetDisease, [
            {"id": models.gen_id(), "tar_id": r["tar_id"], "dis_id": r["dis_id"]}
            for r in data["target_disease"]
        ])
        db.commit()
        print("匯入完成！")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使用方式：python -m app.import_tcmsp_data /path/to/tcmsp_data.json")
        sys.exit(1)
    import_data(sys.argv[1])
