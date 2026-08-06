"""
產生 100 筆「測試用」病患資料 + 就診紀錄，供本機開發/展示使用。

⚠️ 重要：這是合成的假資料，不是任何真實病患資訊。所有姓名、證件號碼、地址、電話
   都是隨機組合產生，證件號碼刻意使用不符合真實檢查碼規則的格式，
   避免與真實身分證號碼混淆。病患識別碼、病歷號都會加上 TEST 前綴方便日後篩選/清除。

使用方式：
    python -m app.generate_test_patients

可重複執行：每次執行前會先清掉「病患識別碼以 TEST- 開頭」的舊測試資料再重新產生，
不會影響任何非測試資料（真實資料的 patient_id 不會用這個前綴）。
"""
import random
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, engine, Base

SURNAMES = list("陳林黃張李王吳劉蔡楊許鄭謝洪郭邱曾廖賴徐周葉蘇莊呂江何蕭羅高潘")
GIVEN_NAMES = [
    "志明", "怡君", "俊傑", "淑芬", "建宏", "美玲", "家豪", "雅婷", "承翰", "詩涵",
    "宗翰", "佳蓉", "冠廷", "思穎", "柏諺", "宜臻", "彥廷", "欣怡", "彥安", "婉婷",
    "育誠", "郁文", "哲瑋", "雅雯", "俊宏", "淑惠", "宇軒", "婷婷", "泰安", "秀琴",
]
CITIES_DISTRICTS = [
    ("台北市", "大安區"), ("台北市", "信義區"), ("台北市", "士林區"),
    ("新北市", "板橋區"), ("新北市", "新店區"), ("新北市", "三重區"),
    ("桃園市", "中壢區"), ("台中市", "西屯區"), ("台中市", "北屯區"),
    ("台南市", "東區"), ("高雄市", "左營區"), ("高雄市", "苓雅區"),
    ("新竹市", "東區"), ("基隆市", "仁愛區"), ("宜蘭縣", "宜蘭市"),
]
STREET_NAMES = ["中正路", "中山路", "民生路", "和平路", "民權路", "自由路", "光復路", "忠孝路"]
ETHNICITIES = ["漢族"] * 8 + ["阿美族", "泰雅族", "客家"]
HOSPITALS = ["台北榮民總醫院", "台大醫院", "林口長庚醫院", "中國醫藥大學附設醫院", "高雄醫學大學附設醫院", "馬偕紀念醫院"]
DEPARTMENTS = ["血液腫瘤科", "腫瘤內科", "放射腫瘤科", "一般內科", "中醫科"]

# 常見癌症診斷（ICD-10 C 開頭），符合本平台（TCM 中藥腫瘤篩選）的使用情境
DIAGNOSES = [
    ("C16", "胃癌"), ("C18", "大腸癌"), ("C22", "肝癌"), ("C25", "胰臟癌"),
    ("C34", "肺癌"), ("C50", "乳癌"), ("C53", "子宮頸癌"), ("C61", "攝護腺癌"),
    ("C67", "膀胱癌"), ("C73", "甲狀腺癌"), ("C82", "濾泡性淋巴瘤"), ("C91", "淋巴性白血病"),
]


def random_date(start_year, end_year):
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def fake_id_number(idx):
    # 刻意用不符合真實身分證檢查碼規則的格式（字母固定用 T 開頭），避免與真實證號混淆
    return f"T{idx:09d}"


def generate():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        print("清除舊的測試資料（patient_id 以 TEST- 開頭）...")
        old_test_patients = db.query(models.Patient).filter(models.Patient.patient_id.like("TEST-%")).all()
        for p in old_test_patients:
            db.query(models.Encounter).filter(models.Encounter.patient_id == p.id).delete()
            db.delete(p)
        db.commit()
        print(f"  清除了 {len(old_test_patients)} 筆舊測試病患資料")

        print("產生 100 筆測試病患資料...")
        created_patients = 0
        created_encounters = 0
        for i in range(1, 101):
            city, district = random.choice(CITIES_DISTRICTS)
            street = random.choice(STREET_NAMES)
            sex = random.choice(["M", "F"])
            patient = models.Patient(
                patient_id=f"TEST-P{i:05d}",
                id_type="身分證",
                id_number=fake_id_number(i),
                name=random.choice(SURNAMES) + random.choice(GIVEN_NAMES),
                sex_code=sex,
                birth_date=random_date(1940, 1996),
                nationality_code="TW",
                ethnicity_code=random.choice(ETHNICITIES),
                address=f"{city}{district}{street}{random.randint(1,300)}號",
                telephone=f"09{random.randint(10,99)}-{random.randint(100,999)}-{random.randint(100,999)}",
                medical_record_no=f"TEST-MR{i:05d}",
                notes="系統產生的測試資料，非真實病患",
            )
            db.add(patient)
            db.flush()  # 取得 patient.id 供就診紀錄使用

            # 每位病患產生 1~3 筆就診紀錄
            for j in range(random.randint(1, 3)):
                diag_code, diag_name = random.choice(DIAGNOSES)
                encounter = models.Encounter(
                    encounter_id=f"TEST-E{i:05d}-{j+1}",
                    patient_id=patient.id,
                    medical_institution=random.choice(HOSPITALS),
                    department=random.choice(DEPARTMENTS),
                    diagnosis_code=diag_code,
                    diagnosis_name=diag_name,
                    encounter_date=random_date(2023, 2026),
                    notes="系統產生的測試資料，非真實就診紀錄",
                )
                db.add(encounter)
                created_encounters += 1
            created_patients += 1

        db.commit()
        print(f"完成！共產生 {created_patients} 筆測試病患、{created_encounters} 筆測試就診紀錄。")
    finally:
        db.close()


if __name__ == "__main__":
    generate()
