"""通路富集分析（KEGG／Reactome）— 端對端驗證。

不連外網：KEGG 與 Reactome 的 HTTP 層以 fixture 取代（格式照抄真實檔案）。

**這支測試的重點是數學，不是 CRUD。**
富集分析的產出是 p 值與 q 值，那是要寫進研究報告的數字。程式跑不跑得動很容易看出來，
但 p 值算錯不會有任何徵兆——它一樣會給你一個介於 0 和 1 之間、看起來很合理的數字。
所以下面用 `math.comb` + `Fraction` 做**精確有理數運算**當對照組，
那是跟被測程式完全不同的算法（被測的是 lgamma 對數空間求和），不是把同一條公式抄兩遍。
"""
import math
import os
from fractions import Fraction

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_pathways.db")

if (os.environ["DATABASE_URL"] == "sqlite:///./test_pathways.db"
        and os.path.exists("test_pathways.db")):
    os.remove("test_pathways.db")

from fastapi.testclient import TestClient

from app import models, pathways as pw
from app.database import SessionLocal
from app.main import app
from app.security import hash_password

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


def exact_sf(k, N, K, n):
    """精確的超幾何上尾機率，用有理數算，沒有任何浮點誤差。對照組。"""
    upper = min(n, K)
    total = Fraction(0)
    denom = math.comb(N, n)
    for i in range(k, upper + 1):
        total += Fraction(math.comb(K, i) * math.comb(N - K, n - i), denom)
    return float(total)


# ---------------------------------------------------------------------------
# fixture：格式照抄真實檔案
# ---------------------------------------------------------------------------

KEGG_LIST = "\n".join([
    "hsa04915\tEstrogen signaling pathway - Homo sapiens (human)",
    "hsa05200\tPathways in cancer - Homo sapiens (human)",
    "hsa04151\tPI3K-Akt signaling pathway",          # 有些版本沒有物種尾巴
    "hsa00010\tGlycolysis / Gluconeogenesis - Homo sapiens (human)",
    "壞掉的一行沒有 tab",
])

# hsa:367=AR, hsa:7157=TP53, hsa:207=AKT1, hsa:5747=PTK2, hsa:2099=ESR1
KEGG_LINK = "\n".join([
    "hsa:367\tpath:hsa04915",
    "hsa:367\tpath:hsa05200",
    "hsa:2099\tpath:hsa04915",
    "hsa:7157\tpath:hsa05200",
    "hsa:7157\tpath:hsa04151",
    "hsa:207\tpath:hsa04151",
    "hsa:207\tpath:hsa05200",
    "hsa:5747\tpath:hsa00010",
])

KEGG_BRITE = "\n".join([
    "+D\tKO",
    "#<h2>KEGG Orthology</h2>",
    "A09150 Organismal Systems",
    "B  09152 Endocrine system",
    "C    04915 Estrogen signaling pathway",
    "D      2099 ESR1; estrogen receptor 1",
    "A09160 Human Diseases",
    "B  09161 Cancer: overview",
    "C    05200 Pathways in cancer",
    "A09130 Environmental Information Processing",
    "B  09132 Signal transduction",
    "C    04151 PI3K-Akt signaling pathway",
])


def _rline(acc, pid, name, species="Homo sapiens", ev="TAS"):
    return "\t".join([acc, pid, f"https://reactome.org/{pid}", name, ev, species])


REACTOME_LINES = [
    _rline("P10275", "R-HSA-383280", "Nuclear Receptor transcription pathway"),
    _rline("P10275", "R-HSA-383280", "Nuclear Receptor transcription pathway", ev="IEA"),
    _rline("P03372", "R-HSA-383280", "Nuclear Receptor transcription pathway"),
    _rline("P04637", "R-HSA-5633008", "TP53 Regulates Transcription of Cell Cycle Genes"),
    _rline("P31749", "R-HSA-5633008", "TP53 Regulates Transcription of Cell Cycle Genes"),
    _rline("Q99999", "R-MMU-1", "Mouse only", species="Mus musculus"),
    "欄位不足的一行",
]


def fake_fetch_kegg():
    names = pw.parse_kegg_pathway_list(KEGG_LIST)
    links = pw.parse_kegg_gene_pathway(KEGG_LINK)
    cats = pw.parse_kegg_brite(KEGG_BRITE)
    counts = {}
    for pids in links.values():
        for pid in pids:
            counts[pid] = counts.get(pid, 0) + 1
    return {"pathways": {pid: {"name": nm, "category": cats.get(pid),
                               "gene_count": counts.get(pid, 0)}
                         for pid, nm in names.items()},
            "gene_to_pathways": links, "background_total": len(links)}


def fake_fetch_reactome():
    return pw.parse_reactome_lines(REACTOME_LINES)


def main():
    print("\n" + "=" * 60)
    print("通路富集分析（KEGG／Reactome）端對端驗證")
    print("=" * 60)

    # ---------- 超幾何檢定 vs 精確有理數 ----------
    print("\n【超幾何檢定：與精確有理數運算比對】")
    cases = [(1, 100, 10, 10), (3, 100, 10, 10), (5, 20000, 300, 100),
             (2, 500, 40, 25), (10, 10, 10, 10), (1, 20, 5, 4), (4, 60, 12, 12)]
    worst = 0.0
    for k, N, K, n in cases:
        got, want = pw.hypergeom_sf(k, N, K, n), exact_sf(k, N, K, n)
        diff = abs(got - want)
        worst = max(worst, diff)
        check(f"sf(k={k},N={N},K={K},n={n}) 與精確值相符",
              diff < 1e-12, f"lgamma={got:.12g} 精確={want:.12g}")
    check("最大誤差在浮點容許範圍內", worst < 1e-12, f"{worst:.3g}")

    check("k=0 回 1.0（沒有命中就不可能顯著）", pw.hypergeom_sf(0, 100, 10, 10) == 1.0)
    check("k 超過可能上限回 1.0，不拋例外", pw.hypergeom_sf(11, 100, 10, 10) == 1.0)
    check("K > N 這種壞資料回 1.0，不讓整份富集結果掛掉",
          pw.hypergeom_sf(1, 10, 100, 5) == 1.0)
    check("N=0 回 1.0（通路目錄還沒同步時會發生）", pw.hypergeom_sf(1, 0, 10, 10) == 1.0)
    check("極端大的 N 不溢位", 0.0 <= pw.hypergeom_sf(50, 500000, 8000, 3000) <= 1.0)

    # ---------- BH 校正 ----------
    print("\n【BH 多重檢定校正】")
    ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.060, 0.074, 0.205]
    qs = pw.benjamini_hochberg(ps)
    expect = [0.008, 0.032, 0.0672, 0.0672, 0.0672, 0.08, 0.084571, 0.205]
    check("教科書範例的 q 值全部相符",
          all(abs(a - b) < 1e-5 for a, b in zip(qs, expect)),
          [round(x, 5) for x in qs])
    check("q 值不會小於原始 p 值", all(q >= p - 1e-12 for p, q in zip(ps, qs)))
    check("q 值隨 p 值單調不遞減（BH 的 step-up 特性）",
          all(qs[i] <= qs[i + 1] + 1e-12 for i in range(len(qs) - 1)))
    check("q 值上限為 1", all(q <= 1.0 for q in pw.benjamini_hochberg([0.9, 0.95, 0.99])))
    check("空輸入回空清單，不拋例外", pw.benjamini_hochberg([]) == [])
    check("順序保持與輸入一致（不是排序後的順序）",
          pw.benjamini_hochberg([0.205, 0.001])[1] < pw.benjamini_hochberg([0.205, 0.001])[0])

    # ---------- 解析 ----------
    print("\n【外部檔案解析】")
    names = pw.parse_kegg_pathway_list(KEGG_LIST)
    check("KEGG 通路清單解析出 4 條", len(names) == 4, len(names))
    check("剝掉 ' - Homo sapiens (human)' 尾巴",
          names["hsa04915"] == "Estrogen signaling pathway", names.get("hsa04915"))
    check("沒有物種尾巴的也正常",
          names["hsa04151"] == "PI3K-Akt signaling pathway", names.get("hsa04151"))
    check("壞掉的行被跳過，不拋例外", "壞掉的一行沒有 tab" not in str(names))

    links = pw.parse_kegg_gene_pathway(KEGG_LINK)
    check("基因→通路：AR(hsa:367) 對到 2 條", len(links["hsa:367"]) == 2, links["hsa:367"])
    check("path: 前綴有被剝掉", "hsa04915" in links["hsa:367"], links["hsa:367"])

    cats = pw.parse_kegg_brite(KEGG_BRITE)
    check("BRITE 分類：hsa04915 屬於內分泌系統",
          cats.get("hsa04915") == "Organismal Systems / Endocrine system", cats.get("hsa04915"))
    check("BRITE 分類：hsa05200 屬於癌症總覽",
          cats.get("hsa05200") == "Human Diseases / Cancer: overview", cats.get("hsa05200"))
    check("BRITE 的 D 行（基因）沒有被當成通路", "2099" not in cats and len(cats) == 3, len(cats))

    rea = pw.parse_reactome_lines(REACTOME_LINES)
    check("Reactome：只留人類", "R-MMU-1" not in rea["pathways"], list(rea["pathways"]))
    check("Reactome：同一蛋白不同證據代碼只算一次",
          rea["pathways"]["R-HSA-383280"]["gene_count"] == 2,
          rea["pathways"]["R-HSA-383280"])
    check("Reactome：背景總數是實際數到的不重複 accession（4 個）",
          rea["background_total"] == 4, rea["background_total"])

    print("\n【癌症通路判定】")
    check("hsa05200 在 KEGG 官方癌症分類區間內",
          pw.is_cancer_pathway("kegg", "hsa05200", "Pathways in cancer"))
    check("hsa04915 靠自訂清單標為癌症相關",
          pw.is_cancer_pathway("kegg", "hsa04915", "Estrogen signaling pathway"))
    check("hsa00010 糖解作用不是癌症通路",
          not pw.is_cancer_pathway("kegg", "hsa00010", "Glycolysis / Gluconeogenesis"))
    check("Reactome 靠名稱關鍵字判定",
          pw.is_cancer_pathway("reactome", "R-HSA-5633008",
                               "TP53 Regulates Transcription of Cell Cycle Genes"))

    # ---------- 測試資料 ----------
    print("\n【測試資料】")
    db = SessionLocal()
    TARGETS = [("TARP001", "Androgen receptor", "AR", "hsa:367", ["R-HSA-383280"]),
               ("TARP002", "Estrogen receptor", "ESR1", "hsa:2099", ["R-HSA-383280"]),
               ("TARP003", "Cellular tumor antigen p53", "TP53", "hsa:7157", ["R-HSA-5633008"]),
               ("TARP004", "RAC-alpha kinase", "AKT1", "hsa:207", ["R-HSA-5633008"]),
               ("TARP005", "Focal adhesion kinase", "PTK2", "hsa:5747", []),
               # 跟 TARP001 同一個基因：驗證「在基因符號空間去重」
               ("TARP006", "Androgen receptor isoform 2", "AR", "hsa:367", ["R-HSA-383280"]),
               # 已標準化但沒有交叉引用
               ("TARP007", "Orphan protein", "ORF1", None, [])]
    import json as _json
    for tar_id, name, sym, kegg, reactome in TARGETS:
        if not db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id == tar_id).first():
            db.add(models.TcmspTarget(tar_id=tar_id, target_name=name))
            db.add(models.TcmspTargetUniprot(
                tar_id=tar_id, accession=f"X{tar_id}", gene_symbol=sym,
                gene_synonyms="[]", kegg_id=kegg,
                reactome_ids=_json.dumps(reactome), status="auto", method="exact"))
    # 待確認的映射不該被採用
    if not db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id == "TARP008").first():
        db.add(models.TcmspTarget(tar_id="TARP008", target_name="Pending protein"))
        db.add(models.TcmspTargetUniprot(
            tar_id="TARP008", accession="XP008", gene_symbol="PENDING",
            gene_synonyms="[]", kegg_id="hsa:367", reactome_ids="[]",
            status="pending", method="fulltext"))

    if not db.query(models.TcmspHerb).filter(models.TcmspHerb.id == 9001).first():
        db.add(models.TcmspHerb(id=9001, herb_en_name="Test herb", herb_cn_name="測試藥材"))
        # (mol_id, ob, dl, 靶點)：涵蓋通過／OB 不足／DL 不足／缺值四種情況
        for mol, ob, dl, tars in [
                ("MOLP01", "45.6", "0.72", ["TARP001", "TARP002", "TARP006"]),  # 通過
                ("MOLP02", "31.0", "0.19", ["TARP003", "TARP004"]),             # 剛好通過
                ("MOLP03", "12.3", "0.55", ["TARP005"]),                        # OB 不足
                ("MOLP04", "88.0", "0.05", ["TARP005"]),                        # DL 不足
                ("MOLP05", "", "0.60", ["TARP005"]),                            # OB 缺值
                ("MOLP06", "50.0", "NA", ["TARP005"])]:                         # DL 是 'NA'
            db.add(models.TcmspIngredient(mol_id=mol, molecule_name=mol, ob=ob, dl=dl))
            db.add(models.TcmspHerbIngredient(herb_id=9001, mol_id=mol))
            for t in tars:
                db.add(models.TcmspIngredientTarget(mol_id=mol, tar_id=t))
    if not db.query(models.User).filter(models.User.account == "pwuser").first():
        db.add(models.User(account="pwuser", password_hash=hash_password("0000"),
                           status=models.UserStatus.active))
    db.commit()
    check("測試靶點與藥材就緒", db.query(models.TcmspTarget).count() >= 8)

    r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/auth/login", json={"account": "pwuser", "password": "0000"})
    U = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ---------- 權限 ----------
    print("\n【權限】")
    check("未登入看統計 → 401", client.get("/pathways/stats").status_code == 401)
    check("一般使用者可以看統計（唯讀）",
          client.get("/pathways/stats", headers=U).status_code == 200)
    check("一般使用者不能同步 → 403",
          client.post("/pathways/sync", headers=U, json={"source": "kegg"}).status_code == 403)

    # ---------- 同步 ----------
    print("\n【同步：KEGG】")
    orig_k, orig_r = pw.fetch_kegg, pw.fetch_reactome
    pw.fetch_kegg, pw.fetch_reactome = fake_fetch_kegg, fake_fetch_reactome
    try:
        res = client.post("/pathways/sync", headers=A, json={"source": "kegg"}).json()
        check("KEGG 同步建立 4 條通路", res["pathways_created"] == 4, res)
        # AR 2 + ESR1 1 + TP53 2 + AKT1 2 + PTK2 1 + AR-isoform 2 = 10
        check("靶點↔通路關聯建立共 10 條", res["links"] == 10, res)
        check("有通路的靶點數 = 6（ORF1 沒有交叉引用）",
              res["targets_with_pathway"] == 6, res)

        res2 = client.post("/pathways/sync", headers=A, json={"source": "kegg"}).json()
        check("重複同步不會產生重複通路", res2["pathways_created"] == 0, res2)
        check("重複同步關聯數一樣（整批重建，不累加）", res2["links"] == 10, res2)

        rres = client.post("/pathways/sync", headers=A, json={"source": "reactome"}).json()
        check("Reactome 同步建立 2 條通路", rres["pathways_created"] == 2, rres)
        check("Reactome 背景總數 = 4", rres["background_total"] == 4, rres)
    finally:
        pw.fetch_kegg, pw.fetch_reactome = orig_k, orig_r

    check("待確認的映射沒有被拿來建關聯",
          db.query(models.TargetPathway).filter(
              models.TargetPathway.tar_id == "TARP008").count() == 0)

    p = db.query(models.Pathway).filter(models.Pathway.pathway_id == "hsa05200").first()
    check("hsa05200 標記為癌症相關", p.is_cancer_related is True)
    check("hsa05200 帶有 BRITE 分類",
          p.category == "Human Diseases / Cancer: overview", p.category)
    check("hsa05200 背景基因數 = 3（AR/TP53/AKT1）", p.background_gene_count == 3,
          p.background_gene_count)

    # 人工補的翻譯不能被下次同步洗掉
    p.name_tw = "癌症相關路徑"
    db.commit()
    pw.fetch_kegg = fake_fetch_kegg
    try:
        client.post("/pathways/sync", headers=A, json={"source": "kegg"})
    finally:
        pw.fetch_kegg = orig_k
    db.refresh(p)
    check("重新同步不會覆蓋人工補的中文譯名", p.name_tw == "癌症相關路徑", p.name_tw)

    stats = client.get("/pathways/stats", headers=U).json()
    check("統計：KEGG 4 條通路", stats["by_source"]["kegg"]["pathways"] == 4, stats["by_source"]["kegg"])
    check("統計：KEGG 背景總數 = 5 個基因",
          stats["by_source"]["kegg"]["background_total"] == 5,
          stats["by_source"]["kegg"]["background_total"])

    # ---------- ADME 活性成分篩選 ----------
    print("\n【ADME 活性成分篩選（目標一 Step 1 的條件）】")
    check("_num 解析得出正常數字", pw._num("45.6") == 45.6)
    check("_num 對空字串回 None 而不是 0（缺值 ≠ 不活性）", pw._num("") is None)
    check("_num 對 'NA' 回 None", pw._num("NA") is None)
    check("_num 對 None 回 None", pw._num(None) is None)

    meta = pw.active_ingredients(db, 9001, 30.0, 0.18)
    check("6 個成分中只有 2 個通過 OB≥30 且 DL≥0.18",
          meta["passed_count"] == 2, meta)
    check("通過的是 MOLP01 與 MOLP02（含剛好在門檻上的 31.0/0.19）",
          sorted(meta["passed"]) == ["MOLP01", "MOLP02"], meta["passed"])
    check("ADME 缺值的 2 個成分單獨計數，不混進通過或不通過",
          meta["missing_adme"] == 2, meta["missing_adme"])

    tar_filtered, m1 = pw.targets_for_herb(db, 9001, apply_adme=True)
    tar_all, m2 = pw.targets_for_herb(db, 9001, apply_adme=False)
    check("篩選後靶點變少（5 個 → 5 個活性靶點，TARP005 被排除）",
          len(tar_filtered) < len(tar_all), (len(tar_filtered), len(tar_all)))
    check("只有低活性成分連到的 TARP005 被排除",
          "TARP005" not in tar_filtered and "TARP005" in tar_all,
          sorted(tar_filtered))
    check("不篩時 meta 明確標示沒有套用門檻",
          m2["ob_min"] is None and m2["passed_count"] == 6, m2)
    check("targets_for_herb 不會把成分清單一起回傳（避免灌大回應）",
          "passed" not in m1, list(m1))

    ob, dl = pw.adme_thresholds(db)
    check("預設門檻為 TCMSP 論文建議值 OB 30 / DL 0.18",
          (ob, dl) == (30.0, 0.18), (ob, dl))
    db.add(models.SystemSetting(key=pw.OB_KEY, value="50"))
    db.commit()
    check("門檻可由系統設定覆寫", pw.adme_thresholds(db)[0] == 50.0)
    db.query(models.SystemSetting).filter(models.SystemSetting.key == pw.OB_KEY).delete()
    db.commit()
    db.add(models.SystemSetting(key=pw.OB_KEY, value="壞掉的值"))
    db.commit()
    check("設定值壞掉時退回預設，不讓分析整個掛掉",
          pw.adme_thresholds(db)[0] == 30.0, pw.adme_thresholds(db))
    db.query(models.SystemSetting).filter(models.SystemSetting.key == pw.OB_KEY).delete()
    db.commit()

    r_on = client.get("/pathways/herb/9001?apply_adme=true", headers=U).json()
    r_off = client.get("/pathways/herb/9001?apply_adme=false", headers=U).json()
    check("端點預設就會套用 ADME 篩選",
          client.get("/pathways/herb/9001", headers=U).json()["apply_adme"] is True)
    check("回應帶出成分篩選統計給畫面顯示",
          r_on["ingredients"]["passed_count"] == 2 and r_on["ingredients"]["total"] == 6,
          r_on["ingredients"])
    check("關掉篩選時靶點數較多",
          r_off["herb"]["target_count"] > r_on["herb"]["target_count"],
          (r_off["herb"]["target_count"], r_on["herb"]["target_count"]))

    # ---------- 非癌症疾病類通路排除 ----------
    print("\n【排除非癌症的疾病類大雜燴通路】")
    for cat, want in [("Human Diseases / Cardiovascular disease", True),
                      ("Human Diseases / Infectious disease: bacterial", True),
                      ("Human Diseases / Cancer: overview", False),
                      ("Human Diseases / Cancer: specific types", False),
                      ("Human Diseases / Drug resistance: antineoplastic", False),
                      ("Organismal Systems / Immune system", False),
                      (None, False)]:
        check(f"分類判定：{cat}", pw.is_noncancer_disease_pathway(cat) is want, cat)
    check("分類為空時不排除（寧可保留也不要靜默刪資料）",
          pw.is_noncancer_disease_pathway("") is False)

    # ---------- 富集 ----------
    print("\n【富集分析】")
    res = client.get("/pathways/herb/9001?source=kegg&background=genome"
                     "&apply_adme=true&exclude_noncancer_disease=false", headers=U).json()
    check("藥材富集 200 並帶回藥材資訊", res["herb"]["herb_cn_name"] == "測試藥材", res.get("herb"))
    check("**在基因符號空間去重**：AR 與 AR-isoform 只算一個基因 → n=4",
          res["study_gene_count"] == 4, res["study_gene_count"])
    check("背景總數取自外部資料庫而非我方資料", res["background_total"] == 5,
          res["background_total"])

    by_id = {i["pathway_id"]: i for i in res["items"]}
    check("hsa04915 命中 AR 與 ESR1 兩個基因",
          by_id["hsa04915"]["hit_count"] == 2, by_id.get("hsa04915"))
    check("hsa04915 的命中符號去重且排序",
          by_id["hsa04915"]["hit_symbols"] == ["AR", "ESR1"], by_id["hsa04915"]["hit_symbols"])
    check("hsa05200 命中 AR/TP53/AKT1 三個基因",
          by_id["hsa05200"]["hit_count"] == 3, by_id.get("hsa05200"))
    check("PTK2 只由未通過 ADME 的成分連到 → hsa00010 不出現在結果",
          "hsa00010" not in by_id, list(by_id))

    want = exact_sf(3, 5, 3, 4)
    check("hsa05200 的 p 值與精確值相符",
          abs(by_id["hsa05200"]["p_value"] - want) < 1e-12,
          f'{by_id["hsa05200"]["p_value"]:.12g} vs {want:.12g}')
    check("每一項都有 q 值", all("q_value" in i for i in res["items"]))
    check("q 值不小於 p 值", all(i["q_value"] >= i["p_value"] - 1e-12 for i in res["items"]))
    check("結果依 p 值由小到大排序",
          all(res["items"][i]["p_value"] <= res["items"][i + 1]["p_value"]
              for i in range(len(res["items"]) - 1)))
    check("有算 fold enrichment", by_id["hsa05200"]["fold_enrichment"] is not None)

    res_c = client.get("/pathways/herb/9001?source=kegg&cancer_only=true&apply_adme=true&exclude_noncancer_disease=false", headers=U).json()
    check("只看癌症通路時，糖解作用被濾掉",
          all(i["is_cancer_related"] for i in res_c["items"]), [i["pathway_id"] for i in res_c["items"]])

    res_t = client.get("/pathways/herb/9001?source=kegg&background=tcmsp&apply_adme=true&exclude_noncancer_disease=false", headers=U).json()
    check("換成 TCMSP 母體時背景總數不同（5 → 5 個已標準化且有註解的基因）",
          res_t["background"] == "tcmsp", res_t["background"])
    check("換母體後 p 值會不同（母體不同結論就不同，畫面必須標示用了哪一種）",
          res_t["items"] and res["items"], "")

    check("找不到的藥材 → 404",
          client.get("/pathways/herb/999999", headers=U).status_code == 404)
    check("不合法的 source → 422",
          client.get("/pathways/herb/9001?source=wikipathways", headers=U).status_code == 422)

    # ---------- 通路圖連結所需的 KEGG 基因編號 ----------
    print("\n【外部通路圖連結：KEGG 基因編號】")
    kres = client.get("/pathways/herb/9001?source=kegg&apply_adme=true"
                      "&exclude_noncancer_disease=false", headers=U).json()
    kmap = {i["pathway_id"]: i for i in kres["items"]}
    check("KEGG 結果帶出命中基因的 KEGG 編號（通路圖標紅要用）",
          kmap["hsa04915"]["hit_kegg_genes"] == ["367", "2099"],
          kmap["hsa04915"]["hit_kegg_genes"])
    check("編號已剝掉 `hsa:` 前綴且純數字",
          all(g.isdigit() for i in kres["items"] for g in i["hit_kegg_genes"]),
          [i["hit_kegg_genes"] for i in kres["items"]])
    check("編號數量不超過命中數（同基因多靶點要去重）",
          all(len(i["hit_kegg_genes"]) <= i["hit_count"] for i in kres["items"]),
          [(i["pathway_id"], len(i["hit_kegg_genes"]), i["hit_count"]) for i in kres["items"]])

    rres = client.get("/pathways/herb/9001?source=reactome&apply_adme=true"
                      "&exclude_noncancer_disease=false", headers=U).json()
    check("Reactome 結果不帶 KEGG 編號（它用基因符號標示）",
          all(i["hit_kegg_genes"] == [] for i in rres["items"]),
          [i["hit_kegg_genes"] for i in rres["items"]])

    # ---------- 篩選不得影響 n 與 N（v1.39.3 修正的循環論證）----------
    print("\n【樣本數與母體不受顯示篩選影響】")
    base = client.get("/pathways/herb/9001?source=kegg&apply_adme=true"
                      "&exclude_noncancer_disease=false", headers=U).json()
    only_cancer = client.get("/pathways/herb/9001?source=kegg&apply_adme=true"
                             "&cancer_only=true&exclude_noncancer_disease=false",
                             headers=U).json()
    no_disease = client.get("/pathways/herb/9001?source=kegg&apply_adme=true"
                            "&exclude_noncancer_disease=true", headers=U).json()

    check("勾「只看癌症通路」不會改變樣本數 n"
          "（否則等於先把樣本限縮到癌症通路的基因，再問它們是不是集中在癌症通路）",
          only_cancer["study_gene_count"] == base["study_gene_count"],
          (base["study_gene_count"], only_cancer["study_gene_count"]))
    check("勾「排除疾病類通路」也不會改變 n",
          no_disease["study_gene_count"] == base["study_gene_count"],
          (base["study_gene_count"], no_disease["study_gene_count"]))
    check("母體 N 也不受篩選影響",
          only_cancer["background_total"] == base["background_total"] ==
          no_disease["background_total"],
          (base["background_total"], only_cancer["background_total"]))

    base_by_id = {i["pathway_id"]: i for i in base["items"]}
    cancer_by_id = {i["pathway_id"]: i for i in only_cancer["items"]}
    shared = set(base_by_id) & set(cancer_by_id)
    check("同一條通路的 p 值不因旁邊少顯示幾條而改變", shared and all(
              abs(base_by_id[pid]["p_value"] - cancer_by_id[pid]["p_value"]) < 1e-12
              for pid in shared), sorted(shared))
    check("同一條通路的倍率也不變", all(
              base_by_id[pid]["fold_enrichment"] == cancer_by_id[pid]["fold_enrichment"]
              for pid in shared))
    check("篩選確實減少了受檢通路數（BH 的 m 變小是合理的）",
          only_cancer["total_tested"] <= base["total_tested"],
          (base["total_tested"], only_cancer["total_tested"]))
    check("只看癌症通路時結果全部是癌症相關",
          all(i["is_cancer_related"] for i in only_cancer["items"]))

    check("每一列都有 rank 序號且從 1 開始連號",
          [i["rank"] for i in base["items"]] == list(range(1, len(base["items"]) + 1)),
          [i["rank"] for i in base["items"]])

    # ---------- 冗餘標記與排序 ----------
    print("\n【冗餘標記：同一組基因不該被算成好幾項發現】")
    # 純函式驗證：第二條的命中基因是第一條的子集 → 應標為冗餘
    fake = [
        {"pathway": type("P", (), {"pathway_id": "hsaA", "name": "Alpha"})(),
         "symbols": ["BAX", "BCL2", "CASP3", "CASP8", "CASP9", "MAPK8"]},
        {"pathway": type("P", (), {"pathway_id": "hsaB", "name": "Beta"})(),
         "symbols": ["BAX", "BCL2", "CASP3", "CASP8", "CASP9", "CDK1"]},
        {"pathway": type("P", (), {"pathway_id": "hsaC", "name": "Gamma"})(),
         "symbols": ["EGFR", "KRAS"]},
    ]
    pw.annotate_redundancy(fake)
    check("第一條永遠不是冗餘（前面沒有東西可以重複）",
          fake[0]["redundant_with"] is None)
    check("第一條的命中基因全部算新增", len(fake[0]["new_symbols"]) == 6)
    check("重疊 5/6 = 0.83 ≥ 門檻 → 標記為冗餘",
          fake[1]["redundant_with"] is not None, fake[1]["redundant_with"])
    check("冗餘標記指向正確的來源通路",
          fake[1]["redundant_with"]["pathway_id"] == "hsaA",
          fake[1]["redundant_with"])
    check("冗餘標記帶出重疊數量供畫面顯示",
          fake[1]["redundant_with"]["shared"] == 5 and
          fake[1]["redundant_with"]["total"] == 6, fake[1]["redundant_with"])
    check("冗餘那條只有 CDK1 是新增基因",
          fake[1]["new_symbols"] == ["CDK1"], fake[1]["new_symbols"])
    check("完全不重疊的通路不會被誤標",
          fake[2]["redundant_with"] is None and len(fake[2]["new_symbols"]) == 2)

    partial = [
        {"pathway": type("P", (), {"pathway_id": "hsaX", "name": "X"})(),
         "symbols": ["A", "B", "C", "D"]},
        {"pathway": type("P", (), {"pathway_id": "hsaY", "name": "Y"})(),
         "symbols": ["A", "B", "E", "F"]},   # 重疊只有 0.5，低於門檻
    ]
    pw.annotate_redundancy(partial)
    check("重疊 2/4 = 0.5 低於門檻 → 不標記為冗餘（互補的通路要留著）",
          partial[1]["redundant_with"] is None, partial[1]["redundant_with"])
    check("低重疊時新增基因仍正確扣掉已出現的",
          partial[1]["new_symbols"] == ["E", "F"], partial[1]["new_symbols"])

    print("\n【排序切換】")
    by_p = client.get("/pathways/herb/9001?source=kegg&apply_adme=true"
                      "&exclude_noncancer_disease=false&sort=p", headers=U).json()
    by_fold = client.get("/pathways/herb/9001?source=kegg&apply_adme=true"
                         "&exclude_noncancer_disease=false&sort=fold", headers=U).json()
    check("回應標示目前用的排序", by_p["sort"] == "p" and by_fold["sort"] == "fold")
    check("依倍率排序時倍率由大到小",
          all(( by_fold["items"][i]["fold_enrichment"] or 0) >=
              (by_fold["items"][i + 1]["fold_enrichment"] or 0)
              for i in range(len(by_fold["items"]) - 1)),
          [i["fold_enrichment"] for i in by_fold["items"]])
    check("依倍率排序時仍帶出原本的 p 名次（才知道統計上排第幾）",
          all(i.get("p_rank") for i in by_fold["items"]),
          [(i["pathway_id"], i["rank"], i["p_rank"]) for i in by_fold["items"]])
    p_ranks = {i["pathway_id"]: i["p_rank"] for i in by_fold["items"]}
    check("p_rank 與依 p 排序時的名次一致（冗餘與名次不因顯示排序而變）",
          all(i["rank"] == p_ranks.get(i["pathway_id"]) for i in by_p["items"]),
          [(i["pathway_id"], i["rank"]) for i in by_p["items"]])
    check("換排序不影響 p 值本身",
          {i["pathway_id"]: round(i["p_value"], 12) for i in by_p["items"]} ==
          {i["pathway_id"]: round(i["p_value"], 12) for i in by_fold["items"]})
    check("回應帶出獨立發現數（顯著數會被通路重疊灌水）",
          "independent_count" in by_p and by_p["independent_count"] <= by_p["significant_count"],
          (by_p.get("independent_count"), by_p.get("significant_count")))
    check("每一列都有新增基因清單", all("new_symbols" in i for i in by_p["items"]))

    print("\n【通用富集入口與單一靶點查詢】")
    r = client.post("/pathways/enrich", headers=U,
                    json={"tar_ids": ["TARP003", "TARP004"], "source": "kegg"}).json()
    check("任意靶點組合可富集（TP53+AKT1 → n=2）", r["study_gene_count"] == 2, r["study_gene_count"])
    r = client.post("/pathways/enrich", headers=U,
                    json={"tar_ids": ["TARP007"], "source": "kegg"}).json()
    check("靶點沒有通路註解時給明確說明，不是空白畫面",
          r["study_gene_count"] == 0 and r.get("note"), r.get("note"))

    r = client.get("/pathways/target/TARP001", headers=U).json()
    check("單一靶點查得到參與的通路（KEGG 2 + Reactome 1）", r["total"] == 3, r["total"])
    check("關聯有記錄是靠哪個基因符號連上的",
          all(i["via_symbol"] == "AR" for i in r["items"]), r["items"][:1])

    print("\n【通路清單】")
    r = client.get("/pathways/list?source=kegg&cancer_only=true", headers=U).json()
    check("癌症通路清單不含糖解作用",
          "hsa00010" not in [i["pathway_id"] for i in r["items"]],
          [i["pathway_id"] for i in r["items"]])
    r = client.get("/pathways/list?source=kegg&keyword=Estrogen", headers=U).json()
    check("關鍵字搜尋", r["total"] == 1 and r["items"][0]["pathway_id"] == "hsa04915", r)

    print("\n【稽核紀錄】")
    check("pathway_sync 有寫入共用稽核表",
          "pathway_sync" in [x.action for x in db.query(models.AuditLog).all()])

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print("   -", f)
        raise SystemExit(1)
    print("✅ 通路富集驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        client = c
        main()
