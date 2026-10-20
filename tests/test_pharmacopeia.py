"""F1-10 兩岸中藥典比較 — 驗收腳本（v1.51.0，不連外網）。

python -m tests.test_pharmacopeia（或 python -m tests.run_all）

涵蓋：
  1. 臺灣中藥典第四版 JSON 的完整性：394 筆（資訊網 385＋濃縮製劑 9）、項次 001～385 連續、飲片接在所屬藥材後面、
     8 味修正公告都在、啟動自動載入且不重複寫入
  2. 比對規則：中文名＋學名 → auto；只有中文名且學名不同 → 同名異物；只有學名 → 異名同物；
     第三版舊學名、芪／耆、生藥名寫法（Radix Bupleuri）、飲片
  3. **重新比對不動人工判過的列**（確認、否決、人工指定）
  4. API：清單、15 欄、飲片沿用基原、修正公告、官方連結、成分 MOL 展開、權限與稽核紀錄
"""
import os
import sys

DB_FILE = "test_pharmacopeia.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{DB_FILE}")
# ⛔ 測試會寫入、刪除資料，絕不能跑在正式資料庫上（v1.43.0 實際發生過）
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。")
if os.environ["DATABASE_URL"] == f"sqlite:///./{DB_FILE}" and os.path.exists(DB_FILE):
    os.remove(DB_FILE)

import json

from fastapi.testclient import TestClient

from app import models
from app import thp as T
from app.database import SessionLocal
from app.main import app
from app.security import hash_password

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra != '' else ''}")
    if not cond:
        FAIL.append(label)


def by_name(db, name, kind=None):
    q = db.query(models.ThpMonograph).filter(models.ThpMonograph.name_zh == name)
    if kind:
        q = q.filter(models.ThpMonograph.kind == kind)
    return q.first()


def maps_of(db, seq):
    return {r.herb_id: r for r in db.query(models.ThpTcmspMap).filter(models.ThpTcmspMap.thp_seq == seq).all()}


def main():
    with TestClient(app) as client:          # with：跑 startup → 自動載入臺灣中藥典
        db = SessionLocal()

        # ------------------------------------------------------------ 1. 資料
        print("\n【臺灣中藥典第四版資料】")
        data = T.load_json()
        items = data["items"]
        site = [i["site_no"] for i in items if i["site_no"]]
        check("394 筆＝資訊網 385＋濃縮製劑 9", len(items) == 394 and len(site) == 385
              and sum(1 for i in items if i["kind"] == "preparation") == 9, (len(items), len(site)))
        check("項次 001～385 連續不重複", site == [f"{n:03d}" for n in range(1, 386)])
        check("001 丁香、002 人參、003 白參（飲片）、004 紅參（飲片）",
              [(i["site_no"], i["name_zh"], i["kind"]) for i in items[:4]]
              == [("001", "丁香", "herb"), ("002", "人參", "herb"), ("003", "白參", "processed"), ("004", "紅參", "processed")],
              [(i["site_no"], i["name_zh"]) for i in items[:4]])
        check("30 個飲片都有所屬藥材", sum(1 for i in items if i["kind"] == "processed" and i["parent"]) == 30)
        check("沒有「薑」這個空的總標題，生薑、乾薑各自成項",
              not any(i["name_zh"] == "薑" for i in items)
              and any(i["name_zh"] == "生薑" for i in items) and any(i["name_zh"] == "乾薑" and i["kind"] == "herb" for i in items))
        herbs_ = [i for i in items if i["kind"] == "herb"]
        check("每個藥材都有中文名、拉丁生藥名、英文名、基原",
              all(i["name_zh"] and i["latin_name"] and i["en_name"] and i["origin"] for i in herbs_))
        check("基原都以「本品」開頭、「。」結尾（沒有和含量黏在一起）",
              all(i["origin"].startswith("本品") and i["origin"].endswith("。") for i in herbs_),
              [i["name_zh"] for i in herbs_ if not i["origin"].endswith("。")][:5])
        no_sp = sorted(i["name_zh"] for i in herbs_ if not i["species"])
        check("只有礦物類沒有物種學名", no_sp == sorted(["代赭石", "石膏", "芒硝", "滑石"]), no_sp)
        amended = sorted(i["name_zh"] for i in items if i["amendment"])
        check("114-07-30 修正公告 8 味都掛上", amended == sorted(["大黃", "川芎", "五加皮", "辛夷", "兒茶", "砂仁", "柴胡", "茯神"]), amended)
        check("學名修正對照表 49 筆（第三版舊學名，比對 TCMSP 用）", len(data["synonyms"]) == 49)

        check("啟動時已自動載入 394 筆", db.query(models.ThpMonograph).count() == 394)
        res = T.ensure_loaded(db)
        check("資料沒變就不重寫（第二次 loaded=0）", res["loaded"] == 0, res)
        ren = by_name(db, "人參", "herb")
        white = by_name(db, "白參")
        check("飲片的 parent_seq 指到所屬藥材", white.parent_seq == ren.seq)

        # ------------------------------------------------------------ 2. 比對
        print("\n【比對規則】")
        H = [
            # herb_id, 中文（簡體）, 學名／英文名, 預期
            (101, "人参", "Panax Ginseng C. A. Mey"),          # 名＋學名 → auto
            (102, "红参", "Panax Ginseng C. A. Mey"),          # 飲片紅參（名）、人參（學名，異名同物）
            (103, "黄芪", "Astragalus Membranaceus (Fisch.) Bge."),   # 芪／耆＋第三版舊學名 → auto
            (104, "丁香", "Eugenia Caryophyllata Thunb."),     # 同名、TCMSP 用舊屬名 → 同名異物
            (105, "柴胡", "Radix Bupleuri"),                   # 生藥名寫法 → name＋latin → auto
            (106, "某某草", "Fictus herbus L."),               # 臺灣中藥典沒有 → 只在 TCMSP
        ]
        for hid, cn, en in H:
            db.add(models.TcmspHerb(id=hid, herb_cn_name=cn, herb_en_name=en, status="active"))
        db.add(models.TcmspIngredient(mol_id="MOLX1", molecule_name="ginsenoside rg1", ob="40", dl="0.3"))
        db.add(models.TcmspIngredient(mol_id="MOLX2", molecule_name="sucrose", ob="5", dl="0.1"))
        db.add(models.TcmspHerbIngredient(herb_id=101, mol_id="MOLX1"))
        db.add(models.TcmspHerbIngredient(herb_id=101, mol_id="MOLX2"))
        db.commit()
        st = T.rematch(db)

        m_ren, m_red = maps_of(db, ren.seq), maps_of(db, by_name(db, "紅參").seq)
        check("人參 ↔ 人参：中文名＋學名 → auto", m_ren.get(101) and m_ren[101].status == "auto"
              and m_ren[101].method == "name+species", m_ren.get(101) and (m_ren[101].method, m_ren[101].status))
        check("人參 ↔ 红参：只有學名 → pending、異名同物",
              m_ren.get(102) and m_ren[102].status == "pending" and "diff_name_same_species" in (m_ren[102].flags or ""))
        check("飲片紅參 ↔ 红参：中文名 → pending、標飲片",
              m_red.get(102) and m_red[102].status == "pending" and "processed" in (m_red[102].flags or ""))
        m_hq = maps_of(db, by_name(db, "黃耆", "herb").seq)
        check("黃耆 ↔ 黄芪：芪／耆視為同字＋第三版舊學名 → auto",
              m_hq.get(103) and m_hq[103].status == "auto" and m_hq[103].method == "name+species",
              m_hq.get(103) and (m_hq[103].method, m_hq[103].status))
        m_dx = maps_of(db, by_name(db, "丁香").seq)
        check("丁香 ↔ 丁香（Eugenia）：同名異物 → pending 並標旗",
              m_dx.get(104) and m_dx[104].status == "pending" and "same_name_diff_species" in (m_dx[104].flags or ""))
        m_ch = maps_of(db, by_name(db, "柴胡").seq)
        check("柴胡 ↔ 柴胡（Radix Bupleuri）：中文名＋生藥名字詞 → auto",
              m_ch.get(105) and m_ch[105].status == "auto" and m_ch[105].method == "name+latin",
              m_ch.get(105) and (m_ch[105].method, m_ch[105].status))
        same = [m.seq for m in db.query(models.ThpMonograph).filter(models.ThpMonograph.kind == "processed").all()
                if m.parent_seq and db.get(models.ThpMonograph, m.parent_seq).name_zh == m.name_zh]
        check("與所屬藥材同名的飲片（大黃、黃耆…）不重複比對",
              len(same) >= 2 and not db.query(models.ThpTcmspMap).filter(models.ThpTcmspMap.thp_seq.in_(same)).count(),
              len(same))
        check("濃縮製劑不比對",
              not db.query(models.ThpTcmspMap).join(models.ThpMonograph, models.ThpMonograph.seq == models.ThpTcmspMap.thp_seq)
              .filter(models.ThpMonograph.kind == "preparation").count())
        check("統計：已對上的 TCMSP 藥材 3（人参、黄芪、柴胡）", st["tcmsp_matched"] == 3, st)
        check("統計：同名異物 1", st["same_name_diff_species"] == 1, st["same_name_diff_species"])

        # ------------------------------------------------------------ 3. 人工判過的不被覆蓋
        print("\n【重新比對不動人工判過的列】")
        admin = db.query(models.User).filter(models.User.account == "admin").first()
        T.review(db, m_dx[104], "confirm", admin, "Eugenia caryophyllata 是 Syzygium aromaticum 的舊名")
        T.review(db, m_ren[102], "reject", admin, "紅參另有飲片項")
        db.commit()
        db.query(models.TcmspHerb).filter(models.TcmspHerb.id == 104).update({"herb_en_name": "Eugenia Caryophyllata"})
        db.commit()
        T.rematch(db)
        check("已確認的同名異物列維持 confirmed", maps_of(db, by_name(db, "丁香").seq)[104].status == "confirmed")
        check("已否決的列維持 rejected，沒有被重新建立成 pending",
              maps_of(db, ren.seq)[102].status == "rejected")

        # ------------------------------------------------------------ 4. API
        print("\n【API】")
        r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
        A = {"Authorization": f"Bearer {r.json()['access_token']}"}
        if not db.query(models.User).filter(models.User.account == "phuser").first():
            db.add(models.User(account="phuser", password_hash=hash_password("Plain1234x"),
                               status=models.UserStatus.active))
            db.commit()
        r = client.post("/auth/login", json={"account": "phuser", "password": "Plain1234x"})
        U = {"Authorization": f"Bearer {r.json()['access_token']}"}

        check("未登入 → 401", client.get("/pharmacopeia/thp").status_code == 401)
        lst = client.get("/pharmacopeia/thp", headers=U).json()
        check("清單 394 筆、附統計與「中國側」標示",
              len(lst["items"]) == 394 and "中國藥典 2010" in lst["cn_side_label"] and lst["stats"]["thp_items"] == 394)
        check("一般使用者 can_review = false", lst["can_review"] is False)
        check("管理者 can_review = true", client.get("/pharmacopeia/thp", headers=A).json()["can_review"] is True)

        d = client.get(f"/pharmacopeia/thp/{ren.seq}", headers=U).json()
        check("單一品項有 12 個內文欄位＋名稱三欄（共 15 欄）",
              set(d["fields"]) == set(T.FIELDS) and d["name_zh"] == "人參" and d["latin_name"] and d["en_name"])
        check("官方連結 p=002", d["official_url"] == "https://www.cmthp.mohw.gov.tw/Search/SearchDetail?v=4&p=002", d["official_url"])
        check("功能、用法與用量、注意事項全文", d["fields"]["functions"] and d["fields"]["usage_dosage"]
              and d["fields"]["precautions"] == "反藜蘆。", d["fields"]["precautions"])
        check("列出飲片白參、紅參", [c["name_zh"] for c in d["children"]] == ["白參", "紅參"])
        dw = client.get(f"/pharmacopeia/thp/{white.seq}", headers=U).json()
        check("飲片沿用所屬藥材的基原並標示", dw["origin_inherited"] and dw["fields"]["origin"].startswith("本品為五加科")
              and dw["parent"]["name_zh"] == "人參" and dw["latin_name"] == ren.latin_name)
        dc = client.get(f"/pharmacopeia/thp/{by_name(db, '柴胡').seq}", headers=U).json()
        check("柴胡帶出 114 年修正公告（藥用部位改為根及根莖）",
              dc["amendment"] and "乾燥根及根莖" in dc["amendment"]["content"] and "藥用部位" in dc["amendment"]["note"])
        prep = db.query(models.ThpMonograph).filter(models.ThpMonograph.kind == "preparation").first()
        dp = client.get(f"/pharmacopeia/thp/{prep.seq}", headers=U).json()
        check("濃縮製劑沒有資訊網連結", dp["official_url"] is None and dp["site_no"] is None)
        check("不存在的品項 → 404", client.get("/pharmacopeia/thp/99999", headers=U).status_code == 404)

        ing = client.get("/pharmacopeia/tcmsp-herbs/101/ingredients", headers=U).json()
        check("展開 TCMSP 藥材成分：MOL 清單＋活性判定",
              [(i["mol_id"], i["active"]) for i in ing["items"]] == [("MOLX1", True), ("MOLX2", False)]
              and ing["active"] == 1, ing.get("items"))
        only = [h["herb_id"] for h in client.get("/pharmacopeia/tcmsp-only", headers=U).json()["items"]]
        check("只在 TCMSP：某某草；已否決的紅參也算沒對上？→ 不，紅參還有飲片 pending", 106 in only and 101 not in only, only)

        pend = maps_of(db, by_name(db, "紅參").seq)[102]
        check("一般使用者審核 → 403",
              client.post(f"/pharmacopeia/map/{pend.id}/review", json={"action": "confirm"}, headers=U).status_code == 403)
        r = client.post(f"/pharmacopeia/map/{pend.id}/review", json={"action": "confirm", "note": "紅參飲片"}, headers=A)
        check("管理者確認 → confirmed", r.status_code == 200 and r.json()["status"] == "confirmed", r.text[:120])
        r = client.post("/pharmacopeia/map", json={"thp_seq": by_name(db, "八角茴香").seq, "herb_id": 106, "note": "測試"}, headers=A)
        check("人工指定 → confirmed、method=manual", r.status_code == 200)
        db.expire_all()
        man = maps_of(db, by_name(db, "八角茴香").seq)[106]
        check("人工指定的列 method=manual", man.method == "manual" and man.status == "confirmed")
        r = client.post("/pharmacopeia/rematch", headers=A)
        db.expire_all()
        check("重新比對後人工指定的列還在", r.status_code == 200 and maps_of(db, by_name(db, "八角茴香").seq).get(106) is not None)
        acts = {a.action for a in db.query(models.AuditLog).filter(models.AuditLog.action.like("thp_%")).all()}
        check("審核、人工指定、重新比對都寫進稽核紀錄", {"thp_map_confirm", "thp_map_manual", "thp_rematch"} <= acts, acts)
        check("審核參數錯誤 → 422",
              client.post(f"/pharmacopeia/map/{pend.id}/review", json={"action": "delete"}, headers=A).status_code == 422)
        db.close()

    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print(f"   - {f}")
        raise SystemExit(1)
    print("✅ 兩岸中藥典比較驗證全部通過")


if __name__ == "__main__":
    main()
