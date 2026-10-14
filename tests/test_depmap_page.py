"""F1-8 腫瘤細胞株依賴查詢站（Step 6）— 端對端驗證。

不連外網。DepMap 資料用小型 fixture 直接寫進資料表，數字刻意取自人參實測的形狀：
  BCL2   選擇性、強依賴（40／1208，最強 -2.615 在 OCI-LY-19）
  AHR    選擇性但是受體 → 要有方向性警示
  NOISE1 選擇性但只有一株剛越過門檻 → 強依賴株數 0（畫面當雜訊）
  PSMG1  依賴 54.1% → 被選擇性門檻刷掉，要列出原因
  CDK1   泛必需 → 排除
  ZERO1  任何細胞株都不依賴
另外有一個**非活性成分**也連到 BCL2，用來確認「打到它的成分」只列活性成分。

最重要的三組斷言：
  1. 排序是「選擇性當門檻、效應量當排序」（v1.41.3 定案）
  2. 報表腳本 inspect_depmap 與 API 給出同一份結果（共用 depmap_analysis）
  3. 唯讀模式的本機快取（只含 CACHED_TABLES）也跑得動
"""
import os
import subprocess
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_depmap_page.db")

# ⛔ 測試會寫入、刪除資料，**絕不能跑在正式資料庫上**（v1.43.0 實際發生過）。
# 同一個 PowerShell 視窗先前若為了跑維運腳本設過 $env:DATABASE_URL（Neon），
# 上面的 setdefault 不會覆蓋它，測試就直接連上正式庫。所以非 SQLite 一律拒絕執行。
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。\n"
              "   請先清掉：Remove-Item Env:DATABASE_URL　或開一個新的 PowerShell 視窗再跑。")
if (os.environ["DATABASE_URL"] == "sqlite:///./test_depmap_page.db"
        and os.path.exists("test_depmap_page.db")):
    os.remove("test_depmap_page.db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import depmap_analysis as dm, models
from app.database import SessionLocal, engine as main_engine
from app.local_cache import CACHED_TABLES
from app.main import app
from app.routers import depmap as depmap_router
from app.security import hash_password

FAIL = []
REL = "24Q2"
N = 1208


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


def seed(db):
    db.add(models.TcmspHerb(id=336, herb_cn_name="人参", herb_pinyin="Renshen",
                            herb_en_name="Panax Ginseng", status="active"))
    db.add(models.TcmspHerb(id=999, herb_cn_name="下架藥", herb_en_name="Gone", status="inactive"))
    ings = [("MOLA01", "ginsenoside rh2", "36.3", "0.56"),      # 活性
            ("MOLA02", "kaempferol", "41.9", "0.24"),           # 活性
            ("MOLX01", "inactive thing", "5.0", "0.10")]        # 非活性
    for mol, name, ob, dl in ings:
        db.add(models.TcmspIngredient(mol_id=mol, molecule_name=name, ob=ob, dl=dl, mw="300"))
        db.add(models.TcmspHerbIngredient(herb_id=336, mol_id=mol))
    targets = {"TAR01": ("Apoptosis regulator Bcl-2", "BCL2"),
               "TAR02": ("Aryl hydrocarbon receptor", "AHR"),
               "TAR03": ("Noise protein", "NOISE1"),
               "TAR04": ("Proteasome assembly chaperone 1", "PSMG1"),
               "TAR05": ("Cyclin-dependent kinase 1", "CDK1"),
               "TAR06": ("Zero dependency protein", "ZERO1"),
               "TAR07": ("Unmapped protein", None)}
    for tar, (name, sym) in targets.items():
        db.add(models.TcmspTarget(tar_id=tar, target_name=name))
        if sym:
            db.add(models.TcmspTargetUniprot(tar_id=tar, gene_symbol=sym, status="auto"))
    edges = [("MOLA01", "TAR01", "1"), ("MOLA02", "TAR01", None), ("MOLA01", "TAR02", None),
             ("MOLA02", "TAR03", None), ("MOLA01", "TAR04", None), ("MOLA02", "TAR05", None),
             ("MOLA01", "TAR06", None), ("MOLA02", "TAR07", None),
             ("MOLX01", "TAR01", None)]                              # 非活性成分也打 BCL2
    for mol, tar, val in edges:
        db.add(models.TcmspIngredientTarget(mol_id=mol, tar_id=tar, validated=val))

    lines = [("ACH-000001", "OCI-LY-19", "Lymphoid", "Mature B-Cell Neoplasms"),
             ("ACH-000002", "MCF7", "Breast", "Invasive Breast Carcinoma"),
             ("ACH-000003", "HEPG2", "Liver", "Hepatocellular Carcinoma"),
             ("ACH-000004", "K562", "Myeloid", "Myeloproliferative Neoplasms")]
    for mid, name, lin, dis in lines:
        db.add(models.DepMapModel(id=mid, cell_line_name=name, stripped_cell_line_name=name.replace("-", ""),
                                  oncotree_lineage=lin, oncotree_primary_disease=dis, release=REL))
    # 摘要：母體 1208，達門檻株數照人參實測的形狀
    summ = [("BCL2", 40, "-2.61517", "ACH-000001", False),
            ("AHR", 30, "-1.2", "ACH-000003", False),
            ("NOISE1", 1, "-0.52", "ACH-000002", False),
            ("PSMG1", 653, "-1.8", "ACH-000004", False),
            ("CDK1", 1208, "-3.0", "ACH-000002", True),
            ("ZERO1", 0, "-0.1", None, False)]
    for sym, n, mn, mid, ess in summ:
        db.add(models.DepMapGeneSummary(gene_symbol=sym, release=REL, n_lines_total=N,
                                        n_dependent=n, min_effect=mn, min_effect_depmap_id=mid,
                                        mean_effect="-0.3", is_common_essential=ess))
    deps = [("ACH-000001", "BCL2", "-2.61517"), ("ACH-000004", "BCL2", "-1.4"),
            ("ACH-000002", "BCL2", "-0.6"),
            ("ACH-000003", "AHR", "-1.2"), ("ACH-000001", "AHR", "-0.7"),
            ("ACH-000002", "NOISE1", "-0.52"),
            ("ACH-000004", "PSMG1", "-1.8"), ("ACH-000001", "PSMG1", "-1.1"),
            ("ACH-000001", "CDK1", "-3.0"), ("ACH-000002", "CDK1", "-2.5"),
            ("ACH-000003", "CDK1", "-2.9"), ("ACH-000004", "CDK1", "-2.8")]
    for mid, sym, eff in deps:
        db.add(models.DepMapGeneDependency(depmap_id=mid, gene_symbol=sym, gene_effect=eff, release=REL))
    db.add(models.DepMapImportRun(release=REL, effect_threshold="-0.5", gene_scope="tcmsp_targets",
                                  n_models=4, n_genes_scanned=6, n_dependency_rows=len(deps),
                                  n_common_essential=1))
    if not db.query(models.User).filter(models.User.account == "dmuser").first():
        u = models.User(account="dmuser", password_hash=hash_password("0000"),
                        status=models.UserStatus.active)
        db.add(u)
        db.flush()
        general = db.query(models.Role).filter(models.Role.name == "一般使用者").first()
        if general:
            db.add(models.UserRole(user_id=u.id, role_id=general.id))
    db.commit()


def main(client):
    print("\n" + "=" * 60)
    print("F1-8 腫瘤細胞株依賴查詢站 端對端驗證")
    print("=" * 60)
    db = SessionLocal()

    print("\n【尚未匯入 DepMap】")
    r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.get("/depmap/meta", headers=A)
    check("沒有任何匯入紀錄 → 404 並提示要先匯入",
          r.status_code == 404 and "import_depmap" in r.text, r.text[:120])

    seed(db)
    r = client.post("/auth/login", json={"account": "dmuser", "password": "0000"})
    U = {"Authorization": f"Bearer {r.json()['access_token']}"}

    print("\n【權限與基本資訊】")
    check("未帶 token → 401", client.get("/depmap/meta").status_code == 401)
    m = client.get("/depmap/meta", headers=U).json()
    check("一般使用者看得到（前台查詢站）", m.get("release") == REL, m)
    check("母體是篩選過的細胞株數", m["n_lines_screened"] == N, m["n_lines_screened"])
    check("**授權標註含來源、版本與 CC BY 4.0**",
          "DepMap" in m["attribution"] and REL in m["attribution"] and "CC BY 4.0" in m["attribution"])
    check("門檻照實回傳（-0.5 有依賴、-1.0 強依賴）",
          m["effect_threshold"] == -0.5 and m["strong_effect"] == -1.0, m)

    print("\n【藥材 → 選擇性依賴靶點】")
    check("不存在的藥材 → 404", client.get("/depmap/herbs/12345/selective", headers=U).status_code == 404)
    check("已下架的藥材 → 404", client.get("/depmap/herbs/999/selective", headers=U).status_code == 404)
    d = client.get("/depmap/herbs/336/selective", headers=U).json()
    f = d["funnel"]
    check("漏斗：3 個成分裡 2 個活性", f["all_ingredients"] == 3 and f["active_ingredients"] == 2, f)
    check("漏斗：活性成分連到 7 個靶點、6 個已標準化符號",
          f["targets"] == 7 and f["symbols"] == 6, f)
    check("漏斗各層互斥加總：泛必需 + 無依賴 + 有選擇性依賴 = DepMap 有資料",
          f["common_essential"] + f["no_dependency"] + f["selective"] == f["with_depmap"] == 6, f)
    check("有選擇性依賴 = 通過門檻 + 被刷掉",
          f["selective"] == f["gated"] + f["dropped"] == 4, f)

    genes = [g["gene_symbol"] for g in d["gated"]]
    check("**排序依最強效應**：BCL2（-2.615）→ AHR（-1.2）→ NOISE1（-0.52）",
          genes == ["BCL2", "AHR", "NOISE1"], genes)
    check("**泛必需 CDK1 不在選擇性清單**，列在排除名單",
          "CDK1" not in genes and d["excluded_essential"] == ["CDK1"], d["excluded_essential"])
    check("**PSMG1（54.1%）被選擇性門檻刷掉並寫出原因**（v1.41.2 曾把它排第一）",
          [x["gene_symbol"] for x in d["dropped"]] == ["PSMG1"]
          and "54.1%" in d["dropped"][0]["dropped_reason"], d["dropped"])
    bcl2 = d["gated"][0]
    check("BCL2 的比例、強依賴株數與最依賴細胞株正確",
          bcl2["ratio"] == round(40 / N, 4) and bcl2["n_strong"] == 2
          and bcl2["best_line"]["cell_line_name"] == "OCI-LY-19"
          and bcl2["best_line"]["primary_disease"] == "Mature B-Cell Neoplasms", bcl2)
    check("細胞株附 DepMap 連結",
          bcl2["best_line"]["depmap_url"].endswith("/cell_line/ACH-000001"))
    check("**打到 BCL2 的成分只列活性成分**（MOLX01 非活性，不列）",
          sorted({i["mol_id"] for i in bcl2["ingredients"]}) == ["MOLA01", "MOLA02"],
          bcl2["ingredients"])
    check("成分邊帶出 TCMSP 原始欄位（尚未分層，只照實帶出）",
          any(i["tcmsp_validated"] == "1" for i in bcl2["ingredients"]))
    ahr = next(g for g in d["gated"] if g["gene_symbol"] == "AHR")
    check("**AHR 標方向性警示（受體）**，BCL2 不標",
          ahr["receptor_warning"] is True and bcl2["receptor_warning"] is False)
    noise = next(g for g in d["gated"] if g["gene_symbol"] == "NOISE1")
    check("只有一株剛越過門檻的 → 強依賴株數 0（畫面當雜訊）", noise["n_strong"] == 0, noise)
    check("**API 不提供 lineage 富集**（已被對照基因集檢定推翻）",
          not any("lineage" in k for k in d.keys()), list(d.keys()))
    check("回傳附授權標註", "CC BY 4.0" in d["attribution"])

    d2 = client.get("/depmap/herbs/336/selective?max_ratio=0.03", headers=U).json()
    check("門檻收到 3%：BCL2（3.3%）也被刷掉，AHR（2.5%）留下",
          [g["gene_symbol"] for g in d2["gated"]] == ["AHR", "NOISE1"]
          and "BCL2" in [x["gene_symbol"] for x in d2["dropped"]], d2["gated"])
    check("門檻超出範圍 → 422",
          client.get("/depmap/herbs/336/selective?max_ratio=0", headers=U).status_code == 422)

    print("\n【基因 → 細胞株】")
    g = client.get("/depmap/genes/bcl2/lines", headers=U).json()
    check("小寫基因符號也查得到", g["summary"]["gene_symbol"] == "BCL2")
    check("依效應由強到弱", [x["gene_effect"] for x in g["items"]] == [-2.61517, -1.4, -0.6], g["items"])
    check("**說明只列達門檻的株，其餘不是沒測過**",
          "1205" in g["note"] and "未達依賴門檻" in g["note"], g["note"])
    check("查不到的基因 → 404",
          client.get("/depmap/genes/NOPE1/lines", headers=U).status_code == 404)

    print("\n【細胞株 → 本藥材的選擇性靶點（規格 B 反查）】")
    s = client.get("/depmap/lines/search?q=oci", headers=U).json()
    check("以名稱搜尋細胞株", [x["depmap_id"] for x in s["items"]] == ["ACH-000001"], s)
    s = client.get("/depmap/lines/search?q=Breast", headers=U).json()
    check("以癌別搜尋細胞株", [x["depmap_id"] for x in s["items"]] == ["ACH-000002"], s)
    ln = client.get("/depmap/lines/ACH-000001?herb_id=336", headers=U).json()
    check("**OCI-LY-19 依賴的選擇性靶點只列 BCL2、AHR**（PSMG1 已刷掉、CDK1 泛必需都不列）",
          [x["gene_symbol"] for x in ln["items"]] == ["BCL2", "AHR"], ln["items"])
    check("帶出這株的 gene effect 與打到它的成分",
          ln["items"][0]["gene_effect_in_line"] == -2.61517 and ln["items"][0]["ingredients"])
    check("不存在的細胞株 → 404",
          client.get("/depmap/lines/ACH-999999?herb_id=336", headers=U).status_code == 404)
    check("沒給 herb_id → 422",
          client.get("/depmap/lines/ACH-000001", headers=U).status_code == 422)

    print("\n【功能項目與導覽】")
    feat = db.query(models.Feature).filter(models.Feature.code == "F1-8").first()
    check("F1-8 由 seed 建立", feat is not None and feat.page_url == "tumor-cells.html")
    menu = client.get("/nav/menu", headers=U)
    check("一般使用者的導覽選單看得到這一頁",
          menu.status_code == 200 and "tumor-cells.html" in menu.text, menu.status_code)
    check("前端頁面存在", client.get("/app/tumor-cells.html").status_code == 200)

    print("\n【報表腳本與 API 共用同一份判定】")
    env = {**os.environ}
    out = subprocess.run([sys.executable, "-m", "app.inspect_depmap", "--herb", "336",
                          "--permutations", "0"], capture_output=True, text=True,
                         env=env, encoding="utf-8")
    txt = out.stdout
    check("inspect_depmap 跑得起來", out.returncode == 0, out.stderr[-300:])
    i_b, i_a, i_n = txt.find("| BCL2 |"), txt.find("| AHR |"), txt.find("| NOISE1 |")
    check("**腳本的排序與 API 相同**（BCL2 → AHR → NOISE1）",
          -1 < i_b < i_a < i_n, (i_b, i_a, i_n))
    check("腳本也把 PSMG1 列在被刷掉的清單",
          "被選擇性門檻刷掉的 1 個" in txt and "| PSMG1 |" in txt)

    print("\n【唯讀模式：只含 CACHED_TABLES 的本機快取也跑得動】")
    cache = create_engine("sqlite://")
    tables = [t for t in models.Base.metadata.sorted_tables if t.name in CACHED_TABLES]
    models.Base.metadata.create_all(bind=cache, tables=tables)
    with main_engine.connect() as src, cache.begin() as dst:
        for t in tables:
            rows = [dict(r._mapping) for r in src.execute(select(t))]
            if rows:
                dst.execute(t.insert(), rows)
    local = sessionmaker(bind=cache)()
    try:
        sel = dm.select_herb_targets(local, 336, REL)
        check("快取裡算出的選擇性靶點與正式庫相同",
              [x.gene_symbol for x in sel["gated"]] == genes, [x.gene_symbol for x in sel["gated"]])
        res = depmap_router.herb_selective(336, dm.DEFAULT_MAX_RATIO, None, local)
        check("**herb_selective 端點在快取上不會 no such table**",
              [x["gene_symbol"] for x in res["gated"]] == genes)
        res = depmap_router.line_detail("ACH-000001", 336, dm.DEFAULT_MAX_RATIO, None, local)
        check("line_detail 端點在快取上也可用", res["total"] == 2)
        res = depmap_router.depmap_meta(None, local)
        check("meta 端點在快取上也可用", res["release"] == REL)
    except Exception as exc:  # noqa: BLE001
        check("唯讀快取可用", False, repr(exc)[:200])
    finally:
        local.close()

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 腫瘤細胞株依賴查詢站驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        main(c)
