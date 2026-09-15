"""成分–靶點邊的證據來源盤點（規格 C 的前置查證）。

## 這支要回答的問題

`claude/借鏡_個體化新抗原疫苗_方法論.md` 規格 C 說：

> TCMSP 原始欄位無此資訊，預設歸 tier 3 並標示「來源未區分」

**那個假設可能是錯的。** `models.TcmspIngredientTarget` 有三個欄位：

    validated    TCMSP 標記這條關係是否經實驗驗證
    svm_score    TCMSP 系統藥理學模型的 SVM 預測分數
    rf_score     同上，隨機森林

而 `import_tcmsp_data.py` 第 114 行確實把它們對應進來了。
所以規格 C 可能不必外接 ChEMBL／BindingDB，用手上的資料就能分層。

**欄位存在不等於有值**，所以先盤點再決定怎麼做——
這正是「CAS／InChIKey 第二層查詢」那次沒做而付出代價的一步。

## 為什麼這件事重要

Step 6 目前最強的發現是 BCL2 在 OCI-LY-19 的選擇性依賴。
但那條「人參成分 → BCL2」的邊，**如果只是分子對接預測**，
整個結論的最弱環節就在那裡，報告必須照實說。

第四節會直接查那幾條邊的實際來源。

使用方式：

    $env:DATABASE_URL="（Neon 連線字串）"
    python -m app.inspect_edge_provenance
    python -m app.inspect_edge_provenance --herb 336 --out reports\\edges.md

唯讀，不寫入任何資料。
"""
import argparse
import io
import os
import sys

from app import models, pathways
from app.database import SessionLocal
from app.target_index import standardized_target_symbols

# Step 6 前段的選擇性靶點，逐條查它們的邊是哪一種來源
STEP6_GENES = ["BCL2", "PRKACA", "AKT1", "CASP8", "ERG", "AR",
               "NFKBIA", "RXRA", "AHR", "IKBKB"]


def _fix_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _check_db_target():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("⚠️  DATABASE_URL 沒有設定，會讀到本機空的 SQLite。")
        print('    請先執行：$env:DATABASE_URL="（Neon 連線字串）"')
        sys.exit(2)
    print(f"資料庫：{url.split('@')[-1].split('/')[0] if '@' in url else '(local)'}")


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _blank(v) -> bool:
    return v is None or str(v).strip() in ("", "NA", "None", "null")


def _label(v) -> str:
    """把 validated 的原始值標準化成可讀標籤，但**保留原值**。

    刻意不猜語意：TCMSP 這個欄位在不同釋出版可能是 1/0、Y/N、true/false，
    甚至是空的。這支的任務是**攤開實際內容**，不是替它決定意思。
    """
    return "（空）" if _blank(v) else str(v).strip()


def main():
    ap = argparse.ArgumentParser(description="成分–靶點邊的證據來源盤點")
    ap.add_argument("--herb", default="336", help="另外分析的藥材 herb_id（預設 336 人参）")
    ap.add_argument("--out", default=None, help="另存 markdown")
    args = ap.parse_args()

    _fix_console()
    _check_db_target()

    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    db = SessionLocal()
    try:
        IT = models.TcmspIngredientTarget
        rows = db.query(IT.mol_id, IT.tar_id, IT.validated,
                        IT.svm_score, IT.rf_score).all()
        total = len(rows)

        out("# 成分–靶點邊的證據來源盤點（規格 C 前置查證）")
        out()
        out(f"`tcmsp_ingredient_target` 共 **{total}** 條邊。")
        out()

        # ---------- 一、三個欄位到底有沒有值 ----------
        out("## 一、三個欄位的填充狀況")
        out()
        n_val = sum(1 for r in rows if not _blank(r.validated))
        n_svm = sum(1 for r in rows if _num(r.svm_score) is not None)
        n_rf = sum(1 for r in rows if _num(r.rf_score) is not None)
        out("| 欄位 | 有值 | 佔比 |")
        out("|---|---|---|")
        for name, n in (("validated", n_val), ("svm_score", n_svm), ("rf_score", n_rf)):
            out(f"| `{name}` | {n} | {n / total * 100:.1f}% |" if total else f"| `{name}` | {n} | — |")
        out()
        if not (n_val or n_svm or n_rf):
            out("❌ **三個欄位全空。** 規格 C 無法用既有資料分層，")
            out("必須外接 ChEMBL／BindingDB，或回到「預設 tier 3」的原方案。")
            out("後面幾節不會有內容。")
        else:
            out("✅ **至少有一個欄位有值**——規格 C 可以先用既有資料分層，")
            out("不必馬上外接 ChEMBL／BindingDB。")

        # ---------- 二、validated 的實際取值 ----------
        if n_val:
            out()
            out("## 二、`validated` 的實際取值")
            out()
            out("⚠️ 這裡**不替欄位決定語意**——TCMSP 不同釋出版可能用 1/0、Y/N、true/false。")
            out("先看實際字串，再決定怎麼對應到 tier。")
            out()
            tally: dict = {}
            for r in rows:
                k = _label(r.validated)
                tally[k] = tally.get(k, 0) + 1
            out("| 原始值 | 邊數 | 佔比 |")
            out("|---|---|---|")
            for k, v in sorted(tally.items(), key=lambda x: -x[1]):
                out(f"| `{k}` | {v} | {v / total * 100:.1f}% |")

        # ---------- 三、預測分數的分布 ----------
        svm = [x for x in (_num(r.svm_score) for r in rows) if x is not None]
        rf = [x for x in (_num(r.rf_score) for r in rows) if x is not None]
        if svm or rf:
            out()
            out("## 三、預測分數的分布")
            out()
            out("| 分數 | n | 最小 | 中位 | 最大 |")
            out("|---|---|---|---|---|")
            for name, arr in (("svm_score", svm), ("rf_score", rf)):
                if not arr:
                    continue
                a = sorted(arr)
                out(f"| `{name}` | {len(a)} | {a[0]:.3f} | "
                    f"{a[len(a) // 2]:.3f} | {a[-1]:.3f} |")
            out()
            out("**分數存在本身就是證據層級的訊號**：有預測分數代表這條邊"
                "至少有一部分來自 TCMSP 的模型推論，不是純實測收錄。")

        # ---------- 四、人參那幾條關鍵的邊 ----------
        herb = (db.query(models.TcmspHerb)
                .filter(models.TcmspHerb.id == int(args.herb)).first())
        if herb:
            ob_min, dl_min = pathways.adme_thresholds(db)
            mol_ids = pathways.active_ingredients(db, herb.id, ob_min, dl_min)["passed"]
            sub = [r for r in rows if r.mol_id in set(mol_ids)]

            out()
            out(f"## 四、{herb.herb_cn_name or herb.herb_en_name}"
                f"（herb_id={herb.id}）活性成分的邊")
            out()
            out(f"活性成分 {len(mol_ids)} 個 → 邊 **{len(sub)}** 條")
            out()
            if sub:
                sv = sum(1 for r in sub if not _blank(r.validated))
                ss = sum(1 for r in sub if _num(r.svm_score) is not None)
                out(f"- `validated` 有值：{sv}（{sv / len(sub) * 100:.1f}%）")
                out(f"- 有預測分數：{ss}（{ss / len(sub) * 100:.1f}%）")

            # Step 6 前段靶點逐條列出
            t2s = standardized_target_symbols(db)
            sym_of: dict = {}
            for tar, syms in t2s.items():
                for s in syms:
                    sym_of.setdefault(s, set()).add(tar)

            out()
            out("### ⭐ Step 6 前段靶點的邊是什麼來源")
            out()
            out("**這一節決定 Step 6 那些結論的最弱環節在哪裡。**")
            out("若 BCL2 那條邊只是分子對接預測，報告必須照實說。")
            out()
            out("| 基因 | 邊數 | validated | svm | rf | 成分 |")
            out("|---|---|---|---|---|---|")
            names = dict(db.query(models.TcmspIngredient.mol_id,
                                  models.TcmspIngredient.molecule_name)
                         .filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all()) \
                if mol_ids else {}
            for g in STEP6_GENES:
                tars = sym_of.get(g, set())
                edges = [r for r in sub if r.tar_id in tars]
                if not edges:
                    out(f"| {g} | 0 | — | — | — | （這味藥材沒有這條邊） |")
                    continue
                for r in edges:
                    sv = _label(r.validated)
                    out(f"| {g} | {len(edges)} | `{sv}` | "
                        f"{r.svm_score or '—'} | {r.rf_score or '—'} | "
                        f"{names.get(r.mol_id) or r.mol_id} |")

        out()
        out("---")
        out()
        out("## 下一步怎麼決定")
        out()
        out("- `validated` 有明確的兩種取值 → **可以直接對應 tier 1／tier 3**，"
            "規格 C 的回填策略不必猜")
        out("- 只有預測分數、沒有 `validated` → 全部歸 **tier 3（對接預測）**，"
            "並用分數做強弱區分")
        out("- 三個欄位都空 → 只能外接 ChEMBL／BindingDB，工作量差一個量級")
        out()
        out("⚠️ 無論哪一種，**tier 都必須是邊的屬性、寫進資料表**，"
            "不能只在報表裡算——否則每個用到這些邊的地方都要各自重算一次，"
            "那就是 `rules.md` 說的「同一個判定寫兩份就會分岔」。")
    finally:
        db.close()

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
        print(f"\n已寫入 {args.out}")


if __name__ == "__main__":
    main()
