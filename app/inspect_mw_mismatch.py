"""
分子量不符的成因分析：這些差值是不是可以用化學解釋的？

## 為什麼要有這一支

人參 Step 2 驗收（`python -m app.verify_ginseng_step2 --herb 336`）跑出 4 筆待確認，
差值分別是 162.1、162.01、324.2、1.02。這些不是隨機的數字：

    162.14 = 一個己糖（葡萄糖）殘基 C6H10O5
    324.28 = 兩個己糖
      1.01 = 一個氫（酸式 vs 陰離子式）

而那三筆 162／324 的成分名稱全部以 `_qt` 結尾——TCMSP 用這個後綴表示**苷元**
（aglycone，去掉糖基之後的配基）。也就是說：**TCMSP 指的是苷元，
用名稱去 PubChem 查回來的卻是帶糖基的母體苷。名稱對上了，分子是別的。**

這正是 `models.TcmspIngredientPubchem` 的註解警告過的那種錯誤：
畫面上一切正常，只是那個 SMILES 屬於別的分子。

## 為什麼統計要分層（v1 版在這裡出過錯，值得留著）

第一版把全部帶差值的映射列混在一起算方向，結論是「TCMSP 較重 1252 : PubChem 較重 266，
假設不成立」。**那個結論是錯的**：1,575 筆裡有 1,311 筆是「≈0 相符」，
那些的方向純粹是兩邊小數位慣例的差別（TCMSP 存 414.79、PubChem 存 414.70），
是雜訊，而且把真正要檢定的 81 筆糖基差整個淹掉。

同樣地，第一版沒有按 status 切分，把早就自動採用的 1,311 筆算進「可以自動採用」，
灌出一個看起來很大、實際上沒有任何待辦意義的數字。

**同一族的錯誤在這個專案已經記錄過三次**（v1.39.3 顯示篩選改動 n、
v1.40.1 卡片與佇列母體不一致）：統計方法沒錯、數字都在合理範圍、
畫面很合理，但**母體選錯，回答的就是別的問題**。

所以這一版：方向**逐桶**計算，數量**逐 status** 切分。

## 判讀原則

差值能被糖基組合解釋，**不代表那筆映射可以採用——恰恰相反**。
它代表我們知道錯在哪：查回來的是母體苷，要的是苷元。
可解釋的是「為什麼錯」，不是「其實沒錯」。

使用方式：

    $env:DATABASE_URL="（Neon 連線字串）"
    python -m app.inspect_mw_mismatch                # 全庫掃描
    python -m app.inspect_mw_mismatch --herb 336     # 加看某味藥材的明細
    python -m app.inspect_mw_mismatch --out mw.md

唯讀，不寫入任何資料。
"""
import argparse
import io
import itertools
import os
import sys

from app import models, pathways
from app.database import SessionLocal

ACCEPTED = ("auto", "confirmed")

# 天然物糖苷常見的糖基殘基質量（脫水後，接上去時失去一分子水）
SUGARS = {
    "己糖/葡萄糖": 162.1424,      # C6H10O5，人參皂苷最常見
    "去氧己糖/鼠李糖": 146.1430,
    "戊糖/木糖·阿拉伯糖": 132.1161,
}
PROTON = 1.00794
WATER = 18.0153

# 只用於「無法解釋」的**二次**分類，刻意不併入主判定。
# 可用的小質量單位一多，任何差值都湊得出來，分類本身就失去意義——
# 分開報告，才看得出主張的強度是靠糖基，還是靠事後加單位湊出來的。
ACYL = {
    "葡萄醣醛酸": 176.1241,
    "乙醯基": 42.0367,
    "丙二醯基": 86.0463,
    "硫酸基": 79.9568,
}

TOL = 0.5          # Da；TCMSP 與 PubChem 的分子量本身就有小數位差異
MAX_SUGARS = 4     # 皂苷最多接到四個糖基
SAME_CPD = ("≈0 相符", "≈1 質子", "≈18 水合")


def _fix_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _check_db_target():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("⚠️  DATABASE_URL 沒有設定，會退回本機空的 SQLite。")
        print('    請先執行：$env:DATABASE_URL="（Neon 連線字串）"')
        sys.exit(2)
    print(f"資料庫：{url.split('@')[-1].split('/')[0] if '@' in url else '(local)'}")


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _combos(units: dict, max_n: int):
    out = []
    names = list(units)
    for n in range(1, max_n + 1):
        for combo in itertools.combinations_with_replacement(names, n):
            total = sum(units[c] for c in combo)
            label = " + ".join(f"{combo.count(c)}×{c}" for c in dict.fromkeys(combo))
            out.append((total, label, n))
    return sorted(out)


SUGAR_COMBOS = _combos(SUGARS, MAX_SUGARS)
# 二次分類：糖基 + 醯基／醣醛酸的混合，最多各兩個
MIXED = _combos({**SUGARS, **ACYL}, 3)


def classify(delta):
    """主分類。回傳 (桶名, 說明)。"""
    if delta is None:
        return "無差值", ""
    d = abs(delta)
    if d <= 0.2:
        return "≈0 相符", "小數位差異，同一化合物"
    if abs(d - PROTON) <= 0.2:
        return "≈1 質子", "酸式 vs 陰離子式，同一化合物"
    if abs(d - WATER) <= 0.3:
        return "≈18 水合", "水合物 vs 無水物，同一化合物"
    for total, label, n in SUGAR_COMBOS:
        if abs(d - total) <= TOL:
            return f"糖基 ×{n}", f"{label}（差 {total:.2f}）"
    return "無法解釋", ""


def classify_second_pass(delta):
    """只對「無法解釋」再試一次，納入醯基／醣醛酸。回傳說明或 None。"""
    d = abs(delta) if delta is not None else None
    if d is None:
        return None
    for total, label, n in MIXED:
        if abs(d - total) <= TOL:
            return f"{label}（差 {total:.2f}）"
    return None


def main():
    ap = argparse.ArgumentParser(description="分子量不符的成因分析")
    ap.add_argument("--herb", default=None, help="另外列出某味藥材活性成分的明細（herb_id）")
    ap.add_argument("--out", default=None, help="另存成 markdown 檔")
    args = ap.parse_args()

    _fix_console()
    _check_db_target()

    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    db = SessionLocal()
    try:
        P, I = models.TcmspIngredientPubchem, models.TcmspIngredient
        rows = (db.query(P, I.molecule_name)
                .join(I, I.mol_id == P.mol_id)
                .filter(P.mw_delta.isnot(None)).all())

        out("# 分子量不符的成因分析")
        out()
        out(f"帶分子量差值的映射列：**{len(rows)}** 筆")
        out()
        out("> 方向逐桶計算、數量逐 status 切分。合併計算會被「≈0 相符」那一桶"
            "（佔絕大多數、方向純屬小數位慣例）帶偏，這是第一版犯過的錯。")
        out()

        buckets = {}
        n_accepted_all = 0

        for r, name in rows:
            delta = _num(r.mw_delta)
            bucket, _ = classify(delta)
            b = buckets.setdefault(bucket, {
                "n": 0, "qt": 0, "accepted": 0, "queue": 0,
                "pc_heavy": 0, "tc_heavy": 0, "unknown": 0,
                "second": 0, "examples": [],
            })
            b["n"] += 1
            if (name or "").strip().lower().endswith("_qt"):
                b["qt"] += 1

            if r.status in ACCEPTED:
                b["accepted"] += 1
                n_accepted_all += 1
            else:
                b["queue"] += 1

            t, p = _num(r.tcmsp_mw), _num(r.molecular_weight)
            if t is None or p is None:
                b["unknown"] += 1
            elif p > t:
                b["pc_heavy"] += 1
            elif p < t:
                b["tc_heavy"] += 1

            if bucket == "無法解釋" and classify_second_pass(delta):
                b["second"] += 1

            if len(b["examples"]) < 3:
                b["examples"].append((r.mol_id, name, r.mw_delta))

        order = sorted(buckets, key=lambda k: -buckets[k]["n"])

        out("## 一、差值分類 × 狀態")
        out()
        out("| 分類 | 全部 | 已採用 | **仍在佇列** | `_qt` | 例子 |")
        out("|---|---|---|---|---|---|")
        for k in order:
            b = buckets[k]
            ex = "；".join(f"{n or m}（Δ{d}）" for m, n, d in b["examples"])
            out(f"| {k} | {b['n']} | {b['accepted']} | **{b['queue']}** | {b['qt']} | {ex} |")
        out()
        out(f"已採用（auto／confirmed）合計 {n_accepted_all} 筆——"
            f"這些**不在待辦裡**，不該算進「可以整批處理」的數字。")

        out()
        out("## 二、方向（逐桶檢定）")
        out()
        out("假設：TCMSP 指的是苷元、PubChem 查回母體苷 → **PubChem 那側應該比較重**。")
        out("「≈0 相符」桶不參與檢定：那一桶的方向是小數位慣例，不是化學。")
        out()
        out("| 分類 | PubChem 較重 | TCMSP 較重 | 無法判定 | 方向是否支持假設 |")
        out("|---|---|---|---|---|")
        for k in order:
            b = buckets[k]
            if k == "≈0 相符":
                verdict = "（不適用，小數位雜訊）"
            elif k in SAME_CPD:
                verdict = "（不適用，同一化合物）"
            elif b["pc_heavy"] > b["tc_heavy"] * 3:
                verdict = "✅ 支持"
            elif b["tc_heavy"] > b["pc_heavy"] * 3:
                verdict = "❌ 相反"
            else:
                verdict = "⚠️ 混雜"
            out(f"| {k} | {b['pc_heavy']} | {b['tc_heavy']} | {b['unknown']} | {verdict} |")

        sugar_pc = sum(b["pc_heavy"] for k, b in buckets.items() if k.startswith("糖基"))
        sugar_tc = sum(b["tc_heavy"] for k, b in buckets.items() if k.startswith("糖基"))
        sugar_n = sum(b["n"] for k, b in buckets.items() if k.startswith("糖基"))
        sugar_qt = sum(b["qt"] for k, b in buckets.items() if k.startswith("糖基"))
        out()
        out(f"糖基各桶合計：PubChem 較重 **{sugar_pc}**、TCMSP 較重 {sugar_tc}。")
        if sugar_n:
            out(f"糖基桶共 {sugar_n} 筆，其中 **{sugar_qt} 筆（{sugar_qt / sugar_n * 100:.0f}%）**"
                f"名稱以 `_qt` 結尾。")

        out()
        out("## 三、待確認佇列該怎麼處理（只算仍在佇列的）")
        out()
        q_same = sum(buckets.get(k, {}).get("queue", 0) for k in SAME_CPD)
        q_sugar = sum(b["queue"] for k, b in buckets.items() if k.startswith("糖基"))
        q_unexp = buckets.get("無法解釋", {}).get("queue", 0)
        q_total = q_same + q_sugar + q_unexp

        out("| 性質 | 佇列筆數 | 該怎麼處理 |")
        out("|---|---|---|")
        out(f"| 同一化合物的不同形式（≈0／≈1／≈18） | {q_same} | "
            f"**可以整批採用**，不需要人工逐筆看 |")
        out(f"| 糖基差（母體苷 vs 苷元） | {q_sugar} | "
            f"**查回來的是別的分子，要否決重解**——不是確認 |")
        out(f"| 無法解釋 | {q_unexp} | 保留人工審核 |")
        out(f"| 合計 | {q_total} | |")

        second = buckets.get("無法解釋", {}).get("second", 0)
        unexp_qt = buckets.get("無法解釋", {}).get("qt", 0)
        out()
        out("### 「無法解釋」裡還有多少可能是同一個成因")
        out()
        out(f"- 名稱以 `_qt` 結尾：**{unexp_qt}** 筆——苷元卻無法用糖基差解釋，"
            f"可能是糖基超過 {MAX_SUGARS} 個，或帶醯基")
        out(f"- 納入醣醛酸／乙醯基／丙二醯基／硫酸基後可湊出：**{second}** 筆")
        out()
        out("⚠️ 第二次分類**不當作結論**。可用的小質量單位一多，任何差值都湊得出來；")
        out("它只用來估「還有多少可能是同一族問題」，不作為採用或否決的依據。")

        # ---- 指定藥材的明細 ----
        if args.herb:
            herb = (db.query(models.TcmspHerb)
                    .filter(models.TcmspHerb.id == int(args.herb)).first())
            if not herb:
                out(f"\n（找不到 herb_id={args.herb}）")
            else:
                ob_min, dl_min = pathways.adme_thresholds(db)
                mol_ids = pathways.active_ingredients(db, herb.id, ob_min, dl_min)["passed"]
                sub = (db.query(P, I.molecule_name)
                       .join(I, I.mol_id == P.mol_id)
                       .filter(P.mol_id.in_(mol_ids))
                       .filter(P.status.notin_(ACCEPTED)).all())
                out()
                out(f"## 四、{herb.herb_cn_name or herb.herb_en_name}"
                    f"（herb_id={herb.id}）未採用的活性成分明細")
                out()
                out("| mol_id | 成分名稱 | 狀態 | CID | TCMSP 分子量 | PubChem 分子量 | 差 | 判讀 |")
                out("|---|---|---|---|---|---|---|---|")
                for r, name in sorted(sub, key=lambda x: x[0].mol_id):
                    d = _num(r.mw_delta)
                    bucket, why = classify(d)
                    if bucket == "無法解釋":
                        alt = classify_second_pass(d)
                        if alt:
                            why = f"二次分類：{alt}"
                    t, p = _num(r.tcmsp_mw), _num(r.molecular_weight)
                    arrow = ""
                    if t is not None and p is not None:
                        arrow = "PubChem 較重" if p > t else ("TCMSP 較重" if p < t else "相同")
                    note = bucket + (f"：{why}" if why else "")
                    if arrow:
                        note += f"｜{arrow}"
                    out(f"| {r.mol_id} | {name or '-'} | {r.status} | {r.cid or '-'} | "
                        f"{r.tcmsp_mw or '-'} | {r.molecular_weight or '-'} | "
                        f"{r.mw_delta or '-'} | {note} |")
    finally:
        db.close()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
        print(f"\n已寫入 {args.out}")


if __name__ == "__main__":
    main()
